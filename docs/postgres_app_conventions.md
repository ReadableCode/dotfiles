# Shared Postgres / PostgREST App Conventions

**Status: UNCOMMITTED DRAFT (2026-08-27).** Written as the single authority the
per-repo `POSTGRES_MIGRATION_PLAN.md` files defer to. Every self-built app that
touches the elitedesk Postgres instance must end up matching this document, and
the migration plans exist to close the gaps.

The reference implementation is **`~/GitHub/Solitaire_Associations`**. Where this
document and that repo disagree, the repo wins and this document is the bug.
Deployment mechanics (compose include, SWAG, Cloudflare, `git_pull.sh`
registration) are NOT repeated here — they live in the
`/personal_deploy_new_web_app` command and are unchanged.

---

## 1. The invariants

Numbered so a plan can cite one. These are not stylistic preferences; each has a
failure mode behind it.

**I1 — One cluster, one database, one schema per app.**
Postgres 17, container `postgres`, database `apps`. An app owns exactly one
schema named in `snake_case` after itself. Nothing an app writes may land in
`public` or in another app's schema. An app never reads another app's schema.

**I2 — Data access goes through PostgREST. Three exceptions, no others.**
The only permitted direct-to-Postgres connections are:
  1. startup bootstrap (superuser, converges the schema),
  2. credential verification at login (superuser, reads `<schema>.users`),
  3. the account-management CLI (superuser).
Everything else — every read and write of application data — is an HTTP call to
PostgREST carrying the caller's JWT. This is what makes RLS the enforcement
point rather than a suggestion.

**I3 — The app's Postgres role is `NOLOGIN` and never holds a password.**
`CREATE ROLE <schema>_user NOLOGIN; GRANT <schema>_user TO postgrest_authenticator;`
PostgREST `SET ROLE`s into it from the JWT's `role` claim. A `LOGIN` role with a
password handed to the app is the anti-pattern: it makes the app the security
boundary instead of the database, and the password then has to live somewhere.

**I4 — Credentials are unreachable through PostgREST.**
`REVOKE ALL ON <schema>.users FROM <schema>_user, web_anon;` in
`deploy/03_secure_users.sql`. The users table is readable only by the superuser
connection that verifies logins. There is no PostgREST path to a password hash,
ever, including via an embedded resource.

**I5 — RLS on every table holding per-user rows.**
`<schema>.jwt_user_id()` reads `request.jwt.claims ->> 'user_id'`, with the
`sub` and pre-v9 `request.jwt.claim.user_id` fallbacks. Each table gets
`ENABLE ROW LEVEL SECURITY` plus a `DROP POLICY IF EXISTS` / `CREATE POLICY`
pair with both `USING` and `WITH CHECK`. Copy
`Solitaire_Associations/deploy/04_rls.sql` and change the table names. Omitting
`WITH CHECK` leaves users able to write rows they cannot read.

**I6 — The app converges its own schema at startup.**
`app/bootstrap.py`, called from the FastAPI lifespan (or the equivalent entry
point for a TUI). Never the docker entrypoint, never a manual step in a deploy
doc, never `docker compose exec`. Version-gated on an integer `SCHEMA_VERSION`
stamped into `<schema>.deploy_meta`; a no-op on every boot after the first.
Failures are logged and the app serves anyway — the next boot retries.

**I7 — Bootstrap SQL is additive and idempotent.**
`CREATE ... IF NOT EXISTS`, `DROP POLICY IF EXISTS` + `CREATE POLICY`,
`CREATE OR REPLACE FUNCTION`. Never `DROP TABLE`, `TRUNCATE`, or
`ALTER COLUMN`. A destructive change is a new numbered file plus a
`SCHEMA_VERSION` bump, reviewed by a human, never something a boot can do by
surprise. Bootstrap ends with `NOTIFY pgrst, 'reload schema';` in its own
committed transaction.

**I8 — No non-Postgres fallback data store.**
No SQLite default, no JSON file, no DuckDB, no "dev mode" that silently swaps
backends. If the database is unreachable the app fails loudly. A fallback that
silently accepts writes is how you end up running against an empty database and
not noticing — the exact hazard `Cash_Flow_Commander/src/db.py` already guards
against by hand, and the reason `duck_db_api` was retired.

**I9 — Every PostgREST request pins its schema.**
`Accept-Profile: <schema>` on reads, `Accept-Profile` + `Content-Profile` on
writes, `Authorization: Bearer <jwt>`. Never rely on the app's schema being
first in the server's `PGRST_DB_SCHEMAS`. Upserts are
`POST /<table>?on_conflict=<cols>` with `Prefer: resolution=merge-duplicates`.

**I10 — Tests hit a real database.**
Per Jason's standing rule, DB tests query for real from any machine (via
`https://pgrest.tinkernet.me`). An unreachable dependency is a red test, never
a skip, a deselect, or a stale-cache green.

**I11 — Registration is complete or the app is not done.**
`PGRST_DB_SCHEMAS` in `Docker/docker_compose_projects.yaml` must list the new
schema, and PostgREST must be recreated to pick it up. A schema that bootstraps
but is not in that list returns 404 for every table and looks like an app bug.

---

## 2. The canonical file layout

```
App_Name/
├── app/
│   ├── bootstrap.py     # I6/I7: version-gated converge, superuser
│   ├── config.py        # env only; no fallback DSNs (I8)
│   ├── store.py         # I2/I9: the ONLY module that talks to PostgREST
│   ├── users.py         # I4: superuser reads of <schema>.users
│   └── users_cli.py     # account management, run via docker compose exec
├── deploy/
│   ├── 02_schema.sql        # CREATE SCHEMA/TABLEs + GRANTs to <schema>_user
│   ├── 03_secure_users.sql  # I4 revokes
│   └── 04_rls.sql           # I5 policies
└── tests/
    ├── test_db_real.py        # I10
    └── test_postgrest_real.py # I10
```

`store.py` is the seam that matters. If application code anywhere else opens a
database connection or builds a PostgREST URL, the refactor is incomplete.

## 3. The `users` table shape

Solitaire's is canonical and is a superset of Book-Bot's:

```sql
CREATE TABLE IF NOT EXISTS <schema>.users (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username            text UNIQUE NOT NULL,
    password_hash       text NOT NULL,
    role                text NOT NULL DEFAULT 'user',
    display_name        text NOT NULL DEFAULT '',
    disabled            boolean NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now(),
    password_changed_at timestamptz NOT NULL DEFAULT now()
);
```

`password_changed_at` is load-bearing: sessions issued before it are rejected,
so a password change, a disable, and a re-enable each revoke every live session
without any server-side session store. Book-Bot and load-log gained the four
missing columns (`role`, `display_name`, `disabled`, `password_changed_at`)
additively when the §4 decision landed; postgrest-auth now requires this shape
for every schema it serves.

`password_hash` is an **opaque string**. It is never parsed, reformatted, or
re-encoded by any migration. Algorithms are self-identifying by prefix
(`$2b$` bcrypt, `$argon2id$` argon2id), which is what makes a future unified
verifier possible without touching stored data.

## 4. Auth — DECIDED 2026-08-28: the shared service is the standard

Jason took the decision: **central password verification via postgrest-auth**,
upgraded to Solitaire's crypto and revocation. C2 (one account shared across
sites) was dropped — accounts stay per-app. The surviving constraints and how
each is met:

- **C1. No user-visible change to how anyone logs in, and no password
  resets.** Met by prefix dispatch: the service verifies `$argon2id$` and
  legacy `$2b$` hashes alike and transparently rehashes bcrypt to argon2id on
  the next successful login.
- **C3. Access to the *site* is still gated**, by each app's own login page
  (the syncplex posture) — Authelia forward-auth is not needed for the
  self-built apps.
- **C4. No stacked edge layer.** Authelia fronts only the third-party
  services that cannot gate themselves; its dead `bookbot` rule and the
  `friends` group are retired.

The division of labor:

- **Verification is central** (postgrest-auth): argon2id KDF policy,
  per-username+per-IP lockout, dummy-hash timing defense, `disabled`
  rejected identically to a bad password. Tokens carry
  `role`/`user_id`/`username`/`app_role`/`iat`/`exp`, with an optional
  per-app `ttl_hours` (≤ 720 h) so each app keeps its session policy.
- **Session validation is app-side**: decode the JWT with the shared secret
  and compare `iat` against `password_changed_at` (30 s cached direct-DB
  read). Solitaire's `app/auth.py` is the reference; Book-Bot mirrors it.
  load-log holds the token opaquely and relies on PostgREST's `exp` check
  only (single-user, RLS deferred — documented in its plan).
- **Account management stays app-side**: each app's CLI/signup creates
  argon2id hashes and bumps `password_changed_at` on password change,
  disable, and re-enable.

## 5. Current auth flows (audited 2026-08-27)

| Flow | Mechanism | Used by |
|---|---|---|
| **A. Authelia forward-auth** | SSO cookie on `tinkernet.me`, argon2 hashes in `users_database.yml` (file backend, on-server only, not in git), groups `admins`/`friends`, `password_reset: disable`, regulation 4 tries / 2 min → 10 min ban, sessions in `/config/db.sqlite3` | Self-built: `assistant`, `crowncentral`, `herdstone`, `ourcash`. Third-party: `sonarr`(+elite), `radarr`(+elite,4k), `readarr`, `readarraudio`, `lazylibrarian`, `bazarr`, `nzbget`(+elite), `deluge`, `calibre` |
| **B. postgrest-auth service** (the standard since 2026-08-28) | `POST https://auth.tinkernet.me/token {schema,username,password,ttl_hours?}`, **argon2id** in `<schema>.users` (legacy bcrypt verified by prefix, rehashed on login), mints HS256 JWT with `role`/`user_id`/`username`/`app_role`/`iat` | `book_bot`, `load_log`, `solitaire` |
| **C. In-app verify, self-minted JWT** | **argon2id**, app's own auth code, session cookie holds the token | `syncplex` (hashes in `users.json`) |
| **D. nginx basic auth** | `.htpasswd` at the proxy | None as of 2026-08-27 (`duck_db_api` retired; every other occurrence is commented out) |
| **E. App's own internal auth** | Out of scope | `jellyfin`, `nextcloud`, `grafana`, `bitwarden`, `homeassistant` |
| **F. Genuinely open** | No gate at all | `bookbot`*, `loadlog`*, `solitaire`*, `syncplex`*, `website_site`, `charlie_website_*`, `a-girls-guide-to-georgetown`, `minecraft*`, `minio`, `ntfy`, `auth`†, `pgrest`† |

\* Open **at the proxy** by design — the app itself requires a login (flow B or
C). Authelia's config comments this explicitly for the whole group; the dead
`bookbot` rule (`admins`+`friends`) was removed 2026-08-28.

† `auth` and `pgrest` are correctly ungated at nginx: each authenticates its
own requests, and the proxy-confs say so in comments.

### What blocked a single shared login (historical — C2 dropped 2026-08-28)

1. **postgrest-auth is per-schema, not per-identity.** `POST /token` takes a
   `schema` and looks up `<schema>.users`. Accounts are per-app by
   construction. C2 needs one identity table (e.g. an `auth` schema owning
   `users`) with per-app authorization mapped onto it, and `/token` issuing a
   token whose `role` claim is the requested app's role only if that user is
   entitled to it.
2. **Authelia's file backend cannot read Postgres.** Its backends are file and
   LDAP. So Authelia can never share the Postgres users table directly. The
   realistic options are (a) generate `users_database.yml` from Postgres as a
   sync step, keeping Postgres as the source of truth — needs confirmation that
   Authelia 4.39's file backend accepts the hash algorithms in use, since it
   supports several but the set must be checked against the docs, not assumed;
   (b) add a forward-auth endpoint to postgrest-auth (a `GET /verify` that
   nginx `auth_request` can call, plus a login portal and a `tinkernet.me`
   session cookie) and retire Authelia; (c) keep them separate and accept two
   account systems.
3. **Two hash algorithms are in play** (bcrypt in flow B, argon2id in flows A
   and C). This is *not* actually a blocker for C1: a unified verifier can
   dispatch on the `$...$` prefix and transparently rehash to the target
   algorithm on the next successful login. No resets, no user-visible change.
   It only becomes a blocker if a component is chosen that can verify just one
   algorithm.

Resolution: Jason dropped C2 — accounts stay per-app, so items 1 and 2 are
moot. Item 3 was solved exactly as described: the service dispatches on the
hash prefix and rehashes to argon2id on the next successful login.

---

## 6. Known divergences from these conventions

Every one of these has a `POSTGRES_MIGRATION_PLAN.md` in its repo.

| Repo | Gap |
|---|---|
| `Sync_Plex` | Accounts + request queue in JSON files on a host bind-mount. No schema at all. Violates I1, I2, I5, I8. |
| `Cash_Flow_Commander` | Right database and schema, but SQLAlchemy direct-to-Postgres with a `LOGIN` role and password, a SQLite default, no RLS, no PostgREST registration, manual schema creation. Violates I2, I3, I5, I6, I8, I11. |
| `Terminal_To_Do` | SQLite file round-tripped through S3. Violates I1, I2, I5, I6, I8. |
| `Book-Bot` | SQLite `dev mode` fallback (I8); users table missing `role`/`disabled`/`password_changed_at` so sessions cannot be revoked (§3). |
| `load-log` | Alembic instead of the version-gated `deploy/*.sql` bootstrap (I6/I7) — the only app with a second migration mechanism. |
| `Solitaire_Associations` | Conforms. Moved from flow C to flow B when the §4 decision landed (2026-08-28). |
