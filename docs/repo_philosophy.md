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
  - `status_board.py` — TUI over remote jobs and PRs, panels discovered from
    sibling `*_credentials` repos.
  - `git_puller` — keeps the repo constellation pulled on every machine.

## Context overlays: sibling `*_credentials` repos

Each context a machine belongs to — personal, or a client/company — has its
own private `*_credentials` repo cloned as a sibling of dotfiles (see
`docs/client_credentials_repos.md`). It supplies the secrets, host
inventories, manifests, and company-tagged config variants for that context.

The rule: **everything I need for a job comes from dotfiles plus that
context's own repo layers.** Dotfiles stays context-free — nothing
client-specific is committed here, ever; company-tagged config variants live
in the client's `*_credentials` repo.

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
dotfiles-specific modules (`inventory_tools`, `statusboard_tools`), not
shared helpers.

The one exception: **work-context repos** never depend on personal remotes;
they vendor whatever they need.
