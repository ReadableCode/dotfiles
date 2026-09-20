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

Machines clone dotfiles and nothing else to get their runtime tooling: the
repo puller, the deploy pipeline and the shell helpers never split into
separate repos, and committed Go binaries are the accepted cost of that.

## Context overlays: sibling `*_credentials` repos

Each context a machine belongs to — personal, or a client/company — has its
own private `*_credentials` repo cloned as a sibling of dotfiles (see
`docs/repo_client_credentials.md`). It supplies the secrets, host
inventories, manifests, and company-tagged config variants for that context.

The rule: **everything I need for a job comes from dotfiles plus that
context's own repo layers.** Dotfiles stays context-free — nothing
client-specific is committed here, ever; company-tagged config variants live
in the client's `*_credentials` repo.

Contexts also never reference each other. A client's name, repo, ticket key
or hostname never appears in another client's repos, docs, configs or
commands, not even as an example, and nothing a client's overlay deploys into
a checkout may carry another context's identifiers. The personal context is
the one place that knows every context by name, and its files deploy only to
personal machines. The rule itself lives in the user-level working rules this
repo deploys (`application_configs/claude/rules/working_rules.md`), so it
reaches every session without any client repo carrying it.
It is enforced, not just stated: `src/context_leak_check.py` and the
pre-commit hook built on it (`docs/repo_client_credentials.md`, "Context leak
check") refuse a commit that stages another context's identifiers.

## Client dev repos: anything agent-shaped

A client's credentials repo is cloned on the client's own hardware, so it
carries **no path that names Claude and no bot-guiding markdown**. Each client
context therefore has a second private repo, `<client>_dev`, that holds the
agent tooling and declares its own overlay manifest (the opt-in form, see
`docs/repo_client_credentials.md`). Both clients share the shape:

| Category | Home |
|---|---|
| Secrets: `.env`, tokens, keys, certs, OAuth tokens, gmail filters | `<context>_credentials` |
| Context declarations: `<context>_hosts.json`, `_repos.yaml`, `_mcp_servers.yaml`, `_statusboard.yaml`, `_calendarboard.yaml`, `_googlemail.yaml`, `_googledrive.yaml` | `<context>_credentials` |
| Client app payloads: `configuration.json`, workspaces, shell / PowerShell / ssh fragments, editor settings, git hooks that name no agent | `<context>_credentials` |
| Working notes that become a repo's `CLAUDE.md` | `<context>_credentials` under a **neutral filename**; the dev overlay supplies the destination name |
| Agent tooling: slash commands, skills, project allow lists, user-level Claude settings and `CLAUDE.md`, T3 Code settings, the per-repo `.mcp.json` manifest entry | `<context>_dev` (`personal_dev`; each client has its own) |
| App-owned commands (a personal app's `.claude/commands/`) | the app repo; the context overlay links them |
| Agent notes for a personal repo that does not advertise agent use | `personal_dev/claude/repo_notes/<repo>.md`, deployed as a gitignored `CLAUDE.md` link |
| Context-free payloads (`init_worktree`, user `settings.json`, statusline, themes) and the generated `data/mcp/*.mcp.json` | `dotfiles` |
| Scheduled jobs | the dev repo's `ops/` when they run on a client machine; `personal_dev/ops/` for the homelab |
| Executable code with only that context's consumers | `<context>_dev/src/` (`personal_dev/src/`; each client has its own `scripts/`) |

Claude's auto-memory directories are **not** synced: they are machine-local by
design, written by the agent without review, and accumulate rules and facts
that belong in tracked docs. Durable rules go in the user-level files
(`application_configs/claude/rules/working_rules.md`
here for the context-free ones, each context's `CLAUDE.<context>.md` in its
dev repo for the rest) and durable facts in the doc that owns the topic.

The MCP server *declaration* stays in the credentials repo on purpose: it
holds a URL and env var names, the env file it points at lives there, and the
two clients are meant to work identically.

The two dev repos are listed in different `*_repos.yaml` files because their
clone sets differ - one must be on its client's laptop for that machine's
crontab, the other must never touch client hardware - but their role is the
same.

**The personal context has the same split** (`personal_dev`): the
secrets repo stays a secrets repo, and the agent tooling lives in a
GitHub-private repo that cloud and web sessions can read, which the LAN-hosted
credentials repo never can. It is cloned wherever the credentials repo is.

## Where executable code lives

The dev-repo table above says skills live in `<context>_dev`, which leaves open
where a skill's own Python goes. The test is **the consumer list**, nothing else:

- **Plural or remote consumers — `dotfiles/src/`.** `ticket_pr.py` serves all
  three contexts; `host_facts.py` runs over ssh on machines that never clone a
  dev repo. The command that calls one is a thin wrapper in the dev repo, not
  the owner: `personal_host_facts`, `personal_chrome_bookmarks`,
  `personal_pr_review` and each client's PR commands are all prose over
  `python3 ~/GitHub/dotfiles/src/<tool>.py`.
- **Only one context's consumers — that context's dev repo.** `personal_dev/src/`
  for personal-only code, each client's own `scripts/` for theirs. This bucket
  exists because a tool with a single personal consumer used to have nowhere
  else to go and defaulted into `dotfiles/src/` by omission.
- **A skill's private implementation — inside the skill.**
  `sort-scanned-documents` carries its scripts under its own `scripts/`, and
  every caller is that skill's `SKILL.md`, `references/method.md` or a
  per-folder `CLAUDE.md`. Nothing outside the skill references any of them.
  Moving them to `dotfiles/src/` would split one skill's code across two repos
  and manufacture a coupling it does not have.

"Would I want this at a new job tomorrow?" decides whether **dotfiles** is
cloned somewhere. It never decides whether a given file is shared — the
consumer list does.

Two bounds sit on top of that test, because dotfiles is public and lands on
every client machine: nothing that cannot be public, and nothing that cannot
be exposed to every client. Within those bounds a tool does not need every
context to want it. A general capability two or more contexts could use
belongs here even when a third ignores it — a calendar integration that two
contexts rely on and a third never touches still belongs here, because
interfacing with a browser or a calendar is an ordinary thing for a person to
want on any machine.

`chrome_bookmarks.py` is the worked example of a tool crossing that line: it
was personal-only and lived here as an exception, and once it took a
`--context` and learned to write each context's bookmarks into that context's
own credentials repo, it stopped being an exception and started earning the
place it already had.

Duplication is not the escape hatch. A second copy of a guard eventually loses
a refusal, and the copy without it is the one that does damage. When a second
consumer appears, either it genuinely needs the machinery — promote it once, to
`dotfiles/src/`, and let both callers reach it by absolute path — or it does
not, and it resolves what it needs in two lines. `onedrive_paths.py` is the
worked example: its refusals exist because the July 2026 run filed a batch into
a *replica* of the taxonomy and lost a year, and a runbook that only reads one
known folder carries none of that risk.

## personal_dev: the personal context's code, jobs and tooling

`personal_dev` is the personal context's repo in the same shape every
`<client>_dev` already has: `claude/` for agent tooling, its own
manifest and removals, a `pyproject.toml`, and `src/` for code whose only
consumers are personal. Homelab jobs — the cron- and container-lifecycle work
like the Bitwarden vault backup, the postgres and docker-app backups, log
rotation, the usage monitor — live in its `ops/` tree.

This supersedes the retired `personal-automation` repo (split out of dotfiles
2026-07, folded into `personal_dev` 2026-09). Splitting personal code by
*where it runs* put a second code repo beside a config-only `personal_dev`
and left the personal context as the only one whose `*_dev` repo carried no
code; the client repos never made that split, and neither should this one. A
job that happens to run on the homelab is still personal-context code.

The distinction from dotfiles tooling is unchanged and is about consumers,
not schedules: dotfiles carries what more than one context could reach for,
`personal_dev` carries what only the personal context will ever call.

## Apps: their own repos

Applications with their own lifecycle (deploys, users, data) get their own
repos. Public ones stay standalone so they can be shared and used by others;
they are not folded into the private grab-bag repo even when small.

## Documents and accumulated data: the cloud store

Not everything durable is code or configuration. Scanned paperwork, house
documents, meeting notes and plain life facts accumulate, and none of them
belong in a git repo. The OneDrive personal `Documents` tree and the Drive
folders are that tier, and they are as much a part of the architecture as the
repos above.

- **Data in the cloud store, code and instructions in git.** `carlson-place` is
  the shape: the documents and everything derived from them live in OneDrive,
  the taxonomy, rules and runbook live in `personal_dev`, and the data folder
  holds a one-line pointer back. Never copy scripts into the data folder.
- **The ledger lives with the data, keyed by content.** `_catalog/` by sha256,
  `metadata.json` by message id — so re-runs are idempotent and survive renames.
  Both refuse to create a fresh record when one is missing or ambiguous, because
  an empty ledger re-ingests everything as duplicates. Authored data
  (preferences, notes with no upstream source) has nothing to re-ingest and
  needs no ledger.
- **Resolve the location, never type it.** A path written down as one machine's
  literal breaks on the next Mac, and a wrong one is not a harmless miss: it is
  a batch filed into a replica. Discovery refuses business accounts, checks for
  expected markers, and stops rather than picking between two candidates.
- **The session is anchored in a repo and reaches out to the data.** A session's
  MCP servers and allow list arrive through the manifest's `per_context_repo`
  expansion over `<context>_repos.yaml`, keyed to repo checkouts. Start a
  session *in* a data folder and it has neither — no calendar, no Gmail, no
  Drive. The data folder is a destination, never the working directory.
- **A synced folder is never a deploy target.** Deploy-managed links are
  symlinks with absolute machine-local targets. One inside OneDrive syncs to
  every other machine, where the target is wrong or missing, and worse on
  Windows.

Sync conflicts are handled in the folder's own `CLAUDE.md`, not by architecture:
reconcile any conflict copy before answering from the files. OneDrive
cloud-only placeholders hydrate on read in a local shell; the *Resource deadlock
avoided* failures on record are device-shell mounts, not local sessions.

## Naming new repos

New repos are **lowercase kebab-case** (`load-log`, `postgrest-auth`). The
existing mixed-case names (`Cash_Flow_Commander`, `Book-Bot`, `CrownCentral`)
stay as they are: renaming one touches every manifest, workspace, clone list
and deploy script that names it, for no functional gain.

### A repo named `personal_*` is private, always

`dotfiles` is the only public repo in this layout. Every repo named
`personal_*` - `personal_credentials` (LAN-hosted) and `personal_dev`
(GitHub-private) today, and any future sibling - is **private by design**, and
a new one must be created private before it is first pushed.

This is not a preference. `src/context_leak_check.py` grants the personal
repos a blanket exemption from the client-identifier rules, and it matches
them on the **name prefix**, not on visibility:

    if name == PERSONAL_CONTEXT or name.startswith(PERSONAL_CONTEXT + "_"):
        return {}

So a public repo named `personal_anything` would be silently exempt from every
check that keeps client names, repo slugs, ticket prefixes and hostnames out
of public view - and these repos genuinely carry all of those. They have to:
`personal_credentials` deploys every context and its generated deploy map
enumerates every client repo on one page, which is the whole point of the
exemption.

The prefix is therefore load-bearing. Two ways to stay safe, and both matter:
a repo that must be public is never named `personal_*`, and a repo named
`personal_*` is never made public. If a personal repo ever needs to be public,
rename it out of the prefix first, then let the leak check scan it as an
ordinary repo before the visibility changes.

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
