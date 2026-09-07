# Repo philosophy and boundaries

What belongs in dotfiles, what belongs in sibling repos, and why. Use this
when deciding where a new script, doc, or config should live.

## dotfiles: everything a new machine at a new job needs

This repo gets cloned onto **every** machine — personal, homelab, and work.
It is a portable knowledge base and toolkit: it reminds or codifies things I
know how to do, and carries the tooling that must exist wherever the repo is
cloned.

The litmus test: **"If I sat down at a brand-new machine for a new job
tomorrow, would I want this immediately?"** If yes, it lives here.

That covers:

- **Configs** (`application_configs/`, `app_lists/`) — shell, editor, tmux,
  git, packages per platform.
- **Setup and how-to docs** (`docs/`) — one topic per file. Docs that codify
  knowledge are in scope even when the subject is homelab infrastructure
  (Docker, k3s, UPS monitoring, local AI): the doc is the reminder of how to
  do the thing, even if the thing itself runs elsewhere.
- **Portable tooling** (`src/`, `go_apps/`) — tools that must travel with the
  repo because every context depends on them:
  - `deploy_configs.py` — deploys configs using this repo's manifest plus
    overlay manifests from sibling `*_credentials` repos.
  - `ticket_pr.py` — ticket/PR workflow harness. Deliberately stdlib-only so
    any repo in any context can invoke it with bare `python3`; credentials
    come from the calling repo's env, never from here.
  - `git_puller` — keeps the repo constellation pulled on every machine.

  The same "travels with every machine" reasoning can also justify a tool
  getting its own repo cloned alongside: the status board TUI (remote jobs
  and PRs, panels discovered from sibling `*_credentials` repos) now lives
  in the sibling `status_board` repo (github.com/ReadableCode/status_board).

## Context overlays: sibling `*_credentials` repos

Each context a machine belongs to — personal, or a client/company — has its
own private `*_credentials` repo cloned as a sibling of dotfiles (see
`docs/repo_client_credentials.md`). It supplies the secrets, host
inventories, manifests, and company-tagged config variants for that context.

The rule: **everything I need for a job comes from dotfiles plus that
context's own repo layers.** Dotfiles stays context-free — nothing
client-specific is committed here, ever; company-tagged config variants live
in the client's `*_credentials` repo.

## Client dev repos: anything agent-shaped

A client's credentials repo is cloned on the client's own hardware, so it
carries **no path that names Claude and no bot-guiding markdown**. Each client
context therefore has a second private repo, `<client>_dev`, that holds the
agent tooling and declares its own overlay manifest (the opt-in form, see
`docs/repo_client_credentials.md`). Both clients share the shape
(aligned 2026-09-07):

| Category | Home |
|---|---|
| Secrets: `.env`, tokens, keys, certs, OAuth tokens, gmail filters | `<context>_credentials` |
| Context declarations: `<context>_hosts.json`, `_repos.yaml`, `_mcp_servers.yaml`, `_statusboard.yaml`, `_calendarboard.yaml`, `_googlemail.yaml` | `<context>_credentials` |
| Client app payloads: `configuration.json`, workspaces, shell / PowerShell / ssh fragments, editor settings, git hooks that name no agent | `<context>_credentials` |
| Working notes that become a repo's `CLAUDE.md` | `<context>_credentials` under a **neutral filename**; the dev overlay supplies the destination name |
| Agent tooling: slash commands, skills, project allow lists, memory dirs, user-level Claude settings and `CLAUDE.md`, T3 Code settings, the per-repo `.mcp.json` manifest entry | `<client>_dev` |
| App-owned commands (a personal app's `.claude/commands/`) | the app repo; the context overlay links them |
| Context-free payloads (`init_worktree`, user `settings.json`, statusline, themes) and the generated `data/mcp/*.mcp.json` | `dotfiles` |
| Scheduled jobs | the dev repo's `ops/` when they run on a client machine; `personal-automation` for the homelab |

The MCP server *declaration* stays in the credentials repo on purpose: it
holds a URL and env var names, the env file it points at lives there, and the
two clients are meant to work identically.

The two dev repos are listed in different `*_repos.yaml` files because their
clone sets differ - one must be on its client's laptop for that machine's
crontab, the other must never touch client hardware - but their role is the
same.

**The personal context has no dev repo.** Dev repos exist because of a
two-owner situation: the client owns the work repos and requires approval to
change them, and the credentials repo sits on the client's hardware. Personally
there is one owner, no approval gate and no foreign hardware, so
`personal_credentials/claude/` plays both roles and is cloned on every
personal machine.

## personal-automation: recurring homelab jobs

Things I do on a frequent basis to keep the homelab running — cron- or
container-lifecycle jobs like the Bitwarden vault backup — live in the local
`personal-automation` repo, not here. The distinction from dotfiles tooling:
a homelab job runs on a schedule **on homelab machines**; dotfiles tooling
must be **available on every machine**, including work ones that will never
run a homelab cron.

## Apps: their own repos

Applications with their own lifecycle (deploys, users, data) get their own
repos. Public ones stay standalone so they can be shared and used by others;
they are not folded into the private grab-bag repo even when small.

## Naming new repos

New repos are **lowercase kebab-case** (`load-log`, `postgrest-auth`). The
existing mixed-case names (`Cash_Flow_Commander`, `Book-Bot`, `CrownCentral`)
stay as they are: renaming one touches every manifest, workspace, clone list
and deploy script that names it, for no functional gain.

## Shared `src/utils/`

Several personal repos need the same wrappers (Google Sheets via pygsheets,
display/formatting helpers, config loading, etc.). The **canonical versions
live in the public `readable_utils` package repo**
(github.com/ReadableCode/readable_utils), which personal repos consume as a
uv git dependency pinned to a tag
(`readable-utils @ git+https://... , tag = "vX.Y.Z"`), installing only the
extras they need (`[google]`, `[postgres]`, `[s3]`, `[ntfy]`).

This repo consumes it the same way — `uv run` fetches it on first sync like
any other dependency, so no copies live here. `src/utils/` holds only
dotfiles-specific modules (`inventory_tools`, `secret_tools`,
`calendarboard_tools`), not shared helpers.

The one exception: **work-context repos** never depend on personal remotes;
they vendor whatever they need.
