# Google MCP — your own Calendar and Gmail in Claude Code

`src/google_mcp.py` is a stdio MCP server that gives Claude Code read/write
access to Google Calendar and Gmail **through your own Google Cloud OAuth
client**. It exists because the hosted `claude.ai Google Calendar` /
`claude.ai Gmail` connectors ride on the claude.ai account session: the moment a
machine switches to AWS Bedrock (`CLAUDE_CODE_USE_BEDROCK=1`) there is no such
session and those tools silently vanish.

A local stdio server is a subprocess Claude Code spawns, so it does not care
where inference goes — the same tools work identically on Bedrock and on Claude
Enterprise. And because it reads *your* credential files under *your* OAuth
client, access is per-user by construction rather than shared by everyone who
authenticates the same way.

## Registering it

Registration is **generated, then linked per repo**. Each cloned repo declares
the servers it owns and `src/claude_mcp.py` renders every declaration into
**one `data/mcp/<context>.mcp.json` per declaring context** at the start of
every `deploy_configs.py deploy`; each context's manifest then links its file
into every checkout of that context as `<repo>/.mcp.json` (a `per_context_repo`
entry, see [deploy_configs.md](./deploy_configs.md)). Declarations come from:

* `dotfiles/mcp_servers.yaml` — this repo's servers (none today; see below)
* `<context>_credentials/<context>_mcp_servers.yaml` — that context's servers
  (e.g. `acme_mcp_servers.yaml` holding that client's ticketing server and its
  `acme_google` instance)
* `<any-cloned-repo>/<its-dir-name>_mcp_servers.yaml` — a working repo that ships
  its own server declares it itself, the same opt-in rule overlay manifests use

The google server's **code** lives in dotfiles, but dotfiles does not declare
it: which accounts it reaches is a context question. Each credentials repo
declares its own instance, named for the context and pinned to that context's
configs with `--context`:

```yaml
- name: acme_google
  command: uv
  args: ["run", "--project", "{repo_root}", "python",
         "{repo_root}/src/google_mcp.py", "--context", "acme"]
```

So a machine holding several contexts registers `acme_google` and
`personal_google` side by side — each labeled, each reaching exactly its own
context's calendar sources and mailboxes, with nothing shared between them and
no unlabeled server whose account set depends on what happens to be cloned.

Discovery is **every cloned sibling**, so the generated file is whatever the
machine's clones add up to: clone one more repo and its servers appear on the next
deploy, with nothing to register by hand.

Declare-and-generate rather than deploy-a-committed-file is the whole design.
`.mcp.json` has **one fixed name per directory** and cannot be namespaced the
way `<context>_*` commands are, so the file a checkout gets has to be the one
its context owns: a context's generated file holds **only that context's
servers**, is linked only into that context's checkouts, and no file anywhere
names another context's servers. A session started outside a checkout registers
nothing — deliberate. Server *names* must still be unique across all
declarations (they are context-prefixed); a duplicate is a real conflict between
repos and the generator refuses it by name rather than letting load order pick a
winner.

**Adding a machine is nothing.** Declarations use the `{repo_root}` and
`{repo_parent}` tokens, expanded at generate time against the machine actually
running, so there is no per-host payload and no `hosts:` filter to maintain:

```yaml
- name: google
  command: uv
  args: ["run", "--project", "{repo_root}", "python", "{repo_root}/src/google_mcp.py"]
```

Tokens are mandatory rather than cosmetic. Deploy has no templating
(`symlink`/`none` only), so a literal path in a shared file points every machine
at whichever machine wrote it; and a *relative* path fails outright because the
server subprocess inherits the **session's** cwd, not the `.mcp.json` location.

Secrets are named, never stored — `env_secrets` maps the var the server expects
to the var to resolve out of `env_file` (real environment first), through the
same `src/utils/secret_tools.py` path the calendar board uses:

```yaml
- name: jira
  command: npx
  args: ["-y", "mcp-jira-cloud"]
  env:
    JIRA_BASE_URL: https://acme.atlassian.net
  env_secrets:
    JIRA_API_TOKEN: JIRA_TOKEN
  env_file: acme.env
```

The generated files live in dotfiles' gitignored `data/mcp/` — never in a
checkout's tracked tree, and since a document can carry a live token each is
written `0600`. Updates are written **in place** rather than by rename: on
Windows the per-repo links are hard links (the unprivileged fallback), which
share the inode and would keep old content if it were swapped. The per-repo
links themselves are untracked via the global git ignore (`**/.mcp.json`).
Approval is `enableAllProjectMcpServers` in the user settings dotfiles deploys,
so no per-repo enabled list is needed. `deploy_manifest.yaml` carries a
`method: none` entry for `mcp_servers.yaml` so the payload is inventoried; the
files themselves are produced by the generator, and the manifest entries that
link them are marked `generated: true`.

Before 2026-09-02 the generator wrote one machine-level `~/.mcp.json`, inherited
by every directory below it. That did reach every session, including ones outside
the clone root — and that was the problem: every cloned context's servers, a few
hundred tool names, loaded into every session regardless of which client's repo
it was in. The user-folder file is now a removals line. Generation is still the
reason this is not `claude mcp add -s user` (below): one writer per context, no
per-machine registry to drift.

Useful invocations:

```bash
uv run python src/claude_mcp.py --print   # every context's document, secrets redacted
uv run python src/claude_mcp.py --check   # non-zero if any generated file is stale or stray
uv run python src/deploy_configs.py deploy --no-mcp   # skip regeneration
```

Regeneration is reported loudly and sets a non-zero exit if it fails, unlike the
best-effort deploy map: a silent failure here looks exactly like the connector
outage this server exists to replace.

**Do not use `claude mcp add -s user`.** That writes an unnamed key into
`~/.claude.json` — a file no repo owns, that cannot be redeployed idempotently
or reverted, and never appears in the deployment map. On a machine with several
clients' credentials repos it is also precisely where they would collide.

One wrinkle versus user scope: a project-scoped server needs a **one-time
in-session approval** the first time you use it from a given directory ("New MCP
server found in this project"), exactly as jira did. `claude mcp list` shows
`⏸ Pending approval` until then.

With `--context` the server reaches only that context's
`<context>_calendarboard.yaml` / `<context>_googlemail.yaml`; a pinned context
whose repo is not cloned (or has no such config) reports no accounts rather
than falling back to another context's. Run WITHOUT `--context` the server
discovers **every** sibling `*_credentials` repo, selected by
`source=`/`mailbox=` — the calendar board's behaviour, kept for ad-hoc use,
but registered servers should always pin.

## Where credentials come from

Nothing new to mint if the calendar board already works — the server reuses the
same two config overlays in the sibling `*_credentials` repos.

**Calendar** reads `<context>_calendarboard.yaml`, exactly as
`docs/setup_calendar_board.md` describes. Only `type: google_calendar` sources
are used; Outlook sources are ignored here.

**Mail** reads `<context>_googlemail.yaml`, same overlay pattern, same
secrets-never-in-the-config rule:

```yaml
- name: personal_gmail
  type: gmail
  oauth_env: GMAIL_OAUTH_DEFAULT     # OAuth client JSON (installed/web wrapped)
  token_env: GMAIL_TOKEN_DEFAULT     # google-auth "authorized user" JSON
  env_file: personal.env
```

Both env vars hold **JSON documents**, matching the `GMAIL_OAUTH_<ACCOUNT>` /
`GMAIL_TOKEN_<ACCOUNT>` convention a context's own mail tooling already mints,
so an existing mailbox needs no re-consent (each credentials repo documents
where its tokens come from). The client id/secret are taken from the token
JSON when it carries them and fall back to the OAuth JSON when it does not.

Mailboxes are opt-in one at a time. A shared team inbox is a deliberate
decision, not a default — this server has write scope, so listing one hands an
agent the ability to label, trash and send from it.

Both account types default to the only configured entry, so `source=` /
`mailbox=` can be omitted on a single-account machine. `list_accounts` shows
what is configured and which file declared it.

## One-time Google setup

Only needed for an account the calendar board has never authenticated.

1. In [Google Cloud Console](https://console.cloud.google.com/) create or reuse
   a project and enable **both** the Google Calendar API and the Gmail API.
   Create an OAuth client of type **Desktop app**.
2. Set the consent screen to **Internal** (a Workspace org) or publish it.
   Leaving it in *Testing* caps refresh tokens at **7 days**, which shows up
   later as calendar and mail dying every week for no obvious reason.
3. Calendar: `uv run python src/calendar_board.py --auth <source>` on a machine
   with a browser, then paste the printed refresh token into the env file.
4. Mail: mint a google-auth "authorized user" JSON with a standard
   `InstalledAppFlow` consent and put it in the env file — or reuse the flow
   the context's own mail tooling already has, per that credentials repo's
   notes. The MCP server needs `gmail.modify`; if the same context also runs
   `src/gmail_filters.py` (see `docs/gmail_filters.md`), mint **one** token
   with `gmail.modify` **and** `gmail.settings.basic` — a re-mint with
   `gmail.modify` alone silently breaks filter writes, and a second
   settings-only token competes in the OAuth client's per-account
   refresh-token pool with the first.

Calendar consent is `auth/calendar` and mail consent is `gmail.modify` (plus
`gmail.settings.basic` where filters are managed) — both read/write. No single
token covers calendar and mail; they are separate grants.

## Tools

Calendar: `calendar_agenda` (all calendars for a date range, the board's view),
`calendar_list_calendars`, `calendar_search_events`, `calendar_get_event`,
`calendar_create_event`, `calendar_update_event`, `calendar_delete_event`.

Mail: `gmail_search` (Gmail's own query syntax), `gmail_get_message`,
`gmail_list_labels`, `gmail_modify_message`, `gmail_trash_message`,
`gmail_send_message`, `gmail_profile`.

Writes are real. Calendar writes default to `send_updates="none"` so editing an
event does not mail its guests — pass `"all"` deliberately. Gmail trash is
recoverable and `gmail.modify` cannot permanently delete; **calendar delete is
not recoverable** through the API.

## What the API will not tell you

Events expose `creator` (who made the event) and `organizer` (whose calendar
owns it), and `updated` holds only the *most recent* modification time. Google
records **no per-attendee provenance**, so "who added this guest, and when" is
not answerable from the Calendar API — `calendar_get_event` surfaces everything
there is.

The usable workaround is Gmail: an `Invitation:` / `Updated invitation:` mail is
sent *from the person who made the change* and its body carries a
`Changed: <field>` line plus the guest list as of that moment. Searching
`gmail_search` for the event title reconstructs the edit history that the
calendar itself does not keep.

## Troubleshooting

`revoked consent? re-run --auth <name>` on every call means the refresh token is
dead — the 7-day *Testing* expiry above is the usual cause. Re-mint it.

Nothing but JSON-RPC may reach stdout or the protocol breaks, which is why the
server's imports run inside a `redirect_stdout` (importing `config` prints when
it creates missing repo dirs). Keep any new `print` in this path on stderr.
