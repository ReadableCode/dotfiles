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
without any server-side session store. Book-Bot lacks `role`, `disabled`,
`display_name` and `password_changed_at` and therefore cannot revoke a session;
adding the columns is additive and safe.

`password_hash` is an **opaque string**. It is never parsed, reformatted, or
re-encoded by any migration. Algorithms are self-identifying by prefix
(`$2b$` bcrypt, `$argon2id$` argon2id), which is what makes a future unified
verifier possible without touching stored data.

## 4. Auth — UNRESOLVED, and deliberately out of scope for the migrations

Three different login flows exist today (see §5). Jason's constraints on any
unification:

- **C1. No user-visible change to how anyone logs in, and no password resets.**
  Existing hashes must keep working exactly as they are.
- **C2. Ideally one shared account usable across sites**, not one account per
  app.
- **C3. Any combined solution must still gate access to a *site*, not only
  access to the *database*** — i.e. it has to cover what Authelia forward-auth
  does today for apps that have no login of their own.
- **C4. If auth is combined, the redundant edge layer (Authelia / nginx basic
  auth) gets turned off rather than left stacked.**

**No migration plan may implement, change, or unify auth.** Each app keeps its
current login mechanism and its current `password_hash` values byte-for-byte
through its migration. The plans move *storage*; the auth decision is a
separate piece of work that C1 makes strictly easier once every hash lives in
Postgres. Moving hashes verbatim is forward-compatible with every option on the
table.

## 5. Current auth flows (audited 2026-08-27)

| Flow | Mechanism | Used by |
|---|---|---|
| **A. Authelia forward-auth** | SSO cookie on `tinkernet.me`, argon2 hashes in `users_database.yml` (file backend, on-server only, not in git), groups `admins`/`friends`, `password_reset: disable`, regulation 4 tries / 2 min → 10 min ban, sessions in `/config/db.sqlite3` | Self-built: `assistant`, `crowncentral`, `herdstone`, `ourcash`. Third-party: `sonarr`(+elite), `radarr`(+elite,4k), `readarr`, `readarraudio`, `lazylibrarian`, `bazarr`, `nzbget`(+elite), `deluge`, `calibre` |
| **B. postgrest-auth service** | `POST https://auth.tinkernet.me/token {schema,username,password}`, **bcrypt** in `<schema>.users`, mints HS256 JWT with `role`/`user_id` | `book_bot`, `load_log` |
| **C. In-app verify, self-minted JWT** | **argon2id**, app's own `app/auth.py`, same shared `POSTGREST_JWT_SECRET`, session cookie holds the token | `solitaire` (hashes in Postgres), `syncplex` (hashes in `users.json`) |
| **D. nginx basic auth** | `.htpasswd` at the proxy | None as of 2026-08-27 (`duck_db_api` retired; every other occurrence is commented out) |
| **E. App's own internal auth** | Out of scope | `jellyfin`, `nextcloud`, `grafana`, `bitwarden`, `homeassistant` |
| **F. Genuinely open** | No gate at all | `bookbot`*, `loadlog`*, `solitaire`*, `syncplex`*, `website_site`, `charlie_website_*`, `a-girls-guide-to-georgetown`, `minecraft*`, `minio`, `ntfy`, `auth`†, `pgrest`† |

\* Open **at the proxy** by design — the app itself requires a login (flow B or
C). Authelia's config comments this explicitly for syncplex, and `bookbot` has
an Authelia rule for `admins`+`friends` that is dead while its proxy-conf omits
`authelia-location.conf` — **worth confirming that is intentional.**

† `auth` and `pgrest` are correctly ungated at nginx: each authenticates its
own requests, and the proxy-confs say so in comments.

### What blocks a single shared login today

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

None of the above is decided. It is written down so the decision can be made
with the real constraints visible.

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
| `Solitaire_Associations` | Conforms. Its only divergence is auth flow C vs B, which §4 defers. |
