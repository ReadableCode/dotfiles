# CLAUDE.md

Guidance for Claude Code (and other AI agents) working in this repository.

## What this repo is

Personal **dotfiles + cross-machine configuration management**. It stores app
configs, OS package lists, setup docs, and a set of Python/Go/shell utilities
used to sync configs and pull data from various devices and services. It targets
many environments: Linux, Windows (PowerShell/choco/winget), macOS (Brewfile),
WSL, Android (Termux), Raspberry Pi, and iPad/Pythonista.

There is no single "app" — it's a toolbox. Most entry points are individual
scripts under `src/` and `scripts/`.

This repo is cloned onto **every** machine, including work machines, so
anything needed at any job must live here (portable tooling like
`ticket_pr.py` is here on purpose); anything
context-specific lives in that context's sibling `*_credentials` repo (secrets,
inventory, declarations, client payloads) or, if it names Claude or guides an
agent, in that context's `<context>_dev` repo (`personal_dev` for the
personal context; each client has its own), and recurring homelab jobs live in
`personal-automation`. See
`docs/repo_philosophy.md` before proposing to move something out.

## Repository layout

| Path | Purpose |
|------|---------|
| `src/` | Python utilities: the deploy pipeline (`deploy_configs.py`, `deploy_map.py`, `claude_mcp.py`), the calendar / Gmail tools, the stdlib-only helpers the shells call at startup, and the data pullers. One paragraph per tool in **Tool index** below; shared helpers come from the `readable-utils` package, `src/utils/` holds only dotfiles-specific modules. |
| `scripts/` | Standalone shell / PowerShell / AHK scripts for install & maintenance tasks. |
| `application_configs/` | Source-of-truth dotfiles for bash, zsh, nvim, tmux, vscode, zed, git, claude, etc. |
| `app_lists/` | Package manifests per platform (Brewfile, choco, winget, apt, Termux). |
| `go_apps/` | Small Go tools (`git_puller`, syncthing cleanup). Prebuilt binaries are committed. The ping/command client-server moved to its own repo (`ReadableCode/go-client-server`). |
| `docs/` | Setup/how-to docs (one per topic). Surfaced via mkdocs. |
| `tests/` | pytest suite (`tests/test_utils/`). |
| `pythonista/` | iOS Pythonista scripts. |

## Tool index (`src/`)

Each tool has a doc under `docs/` (the `repo_*` and `setup_*` families); this
is the one-paragraph orientation so an agent knows which file to open.

- **`deploy_configs.py`** — deploys configs from `deploy_manifest.yaml` plus
  overlay manifests (`<context>_manifest.yaml`) discovered in sibling
  `*_credentials` repos and in any sibling repo that opts in by declaring one
  named after its own directory (`<dirname>_manifest.yaml`), which is how a
  client's `<client>_dev` repo gates agent tooling by a clone narrower than
  the credentials repo's. An entry marked `per_context_repo` expands at load
  time into one link per repo in that context's `<context>_repos.yaml` (the
  per-repo `.mcp.json`, `.env` and allow-list links). Slash commands stay
  user-level as flat per-file links in `~/.claude/commands`: T3 Code builds
  its menu from that path alone and subfolders there namespace the names.
  Manifest `hosts:` names must exist in the union of the `*_credentials`
  inventories (`<context>_hosts.json`). An overlay loads only where the
  machine's inventory record is in its context (its own inventory or the
  record's `contexts:` list); a checkout held for another reason, such as
  elitedesk hosting a client's git hub, deploys nothing. Doc:
  `docs/repo_deploy_configs.md`.
- **`deploy_map.py`** — redraws the fleet-wide deployment map (every entry x
  every machine, interactive page plus diffable JSON) from those same plans on
  every deploy, into `generated/deploy_map.{html,json}` in the personal
  credentials repo - only on host `envy` (`MAP_HOST`; any other machine
  writing those tracked files dirties that checkout and blocks its next pull).
  Template `templates/deploy_map.html`; both must stay context-agnostic
  because the rendered map names every machine and client at once.
- **`claude_mcp.py`** — generates one `data/mcp/<context>.mcp.json` per
  declaring context at the start of each deploy from every cloned sibling
  repo's `mcp_servers.yaml` / `<dirname>_mcp_servers.yaml` (same opt-in rule
  as overlay manifests; `--print` names every repo scanned). Each context's
  overlay then links its file into that context's checkouts as
  `<repo>/.mcp.json`, so a session registers only its own context's servers
  (the pre-2026-09-02 single `~/.mcp.json` loaded every context everywhere).
  Only contexts some loaded entry links get a file: a machine holding a
  context's declaration but not the overlay that consumes it generates
  nothing for it.
  `{repo_root}` / `{repo_parent}` tokens and `env_secrets` var names resolve
  at generate time, which is why no per-host payload exists. Doc:
  `docs/setup_google_mcp.md`.
- **`google_mcp.py`** — stdio MCP server exposing one context's Google
  Calendar plus Gmail (mailboxes from `<context>_googlemail.yaml`) to Claude
  Code with read/write scope. Exists because the hosted claude.ai connectors
  die under `CLAUDE_CODE_USE_BEDROCK=1`; a local stdio server is
  provider-independent. dotfiles holds the code but declares no instance -
  each context's credentials repo declares its own, pinned with `--context`
  (e.g. `acme_google`), so every registered server is labeled by context and
  reaches only that context's accounts. OAuth refresh is shared with the
  calendar board via `src/utils/google_oauth_tools.py`; nothing in that
  process may print to stdout or the JSON-RPC protocol breaks.
- **`calendar_board.py`** — calendar TUI: Google Calendar and Outlook-on-the-web
  (Microsoft Graph) accounts as side-by-side day columns with attendance
  badges and cross-source overlap flags; sources from
  `<context>_calendarboard.yaml` in the same repos. Secret resolution in
  `src/utils/secret_tools.py`. Doc: `docs/setup_calendar_board.md`.
- **`gmail_filters.py`** — makes a Gmail account's filters match
  `<context>_credentials/<context>_gmail_filters.yaml` (file is the source of
  truth; `plan` / `apply` / `backfill`; refuses to run unless Gmail's profile
  matches the yaml's `account:`; never adds SPAM/TRASH, never deletes a label
  or a message; multi-label entries expand into several filters). Doc:
  `docs/repo_gmail_filters.md`.
- **`ssh_aliases.py`** — the single ssh/vnc alias generator for every shell:
  reads the `*_credentials` host inventories and prints alias definitions in
  the caller's syntax (`--format bash` / `--format powershell`), which
  `.shared_aliases` and `powershell_aliases.ps1` eval at startup. Stdlib-only
  so a bare `python3` runs it before any venv exists. Doc:
  `docs/repo_client_credentials.md`.
- **`updater_policy.py`** — same stdlib-only contract; resolves the current
  host's `updater` block (release ceiling, cadence, check scripts) from the
  inventories for `scripts/my_updater.sh`. Host entry only, no group/context
  defaults. Doc: `docs/setup_linux_workstation.md`.
- **`init_worktree.py`** — same contract; brings a fresh git worktree (T3
  Code makes one per thread under `~/.t3/worktrees/<repo>/`) up to parity
  with its main checkout: re-creates the deploy-managed gitignored links with
  absolute targets, adds a folder entry to this host's `<host>.code-workspace`,
  runs `uv sync`. Wrapped by `/init_worktree`
  (`application_configs/claude/commands/`, deployed by the personal and dev
  overlays like every other user-level Claude file, so a client machine that
  must carry no Claude-named path never gets it). Doc:
  `docs/repo_init_worktree.md`.
- **`context_leak_check.py`** — refuses one context's identifiers inside
  another: derives each client's identifiers from its own credentials repo
  (so this file names none), forbids them in every other repo, and forbids
  the other clients' in a client's own two repos. Also the pre-commit hook
  the overlays deploy into those checkouts. Doc:
  `docs/repo_client_credentials.md`, "Context leak check".
- **`clone_repos.py`** — offers to clone every repo the cloned contexts'
  `<context>_repos.yaml` files declare for this machine; run by gitpullall
  between the pull and the deploy.
- **`chrome_bookmarks.py`, `ssh_devices.py`** — pull data and configs from
  browsers and devices.
- **`src/utils/`** — dotfiles-specific modules only: `inventory_tools`,
  `secret_tools`, `calendarboard_tools`, `google_oauth_tools`,
  `googlemcp_tools`, `mcpservers_tools`. Shared helpers come from the
  **`readable-utils`** package (github.com/ReadableCode/readable_utils), a uv
  git dependency pinned to a tag - no vendored copies. Homelab-only jobs
  (Bitwarden backup, Home Assistant/router pulls, log rotation) live in the
  sibling `personal-automation` repo, not here. The status board TUI lives in
  the sibling `status_board` repo.

Cron is **not** managed here. A host with scheduled jobs declares them in the
repo that owns that host's deploy, and that repo's deploy script installs the
file verbatim — see `docs/homelab_deployments.md`. The old `triggers/`
crontab snapshots and `scripts/crontab_extractor.sh` were removed (2026-08-14):
they were extract-only, and every personal-fleet snapshot held either nothing
or the stock OS default.

## Python environment & tooling

This project uses **uv** (Python 3.10, pinned in `.python-version`).

```bash
uv sync                      # install deps from pyproject.toml / uv.lock
uv run python src/<script>.py
```

Lint / format / type-check (config in `pyproject.toml`, `.flake8`, `.isort.cfg`):

```bash
uv run flake8 .              # max-line-length 120, max-complexity 15
uv run isort .               # black profile
uv run mypy .                # ignore_missing_imports = true
```

## Tests

One suite: **`tests/`** — fast unit tests, no external deps or credentials
(`testpaths` in `pyproject.toml`), so a plain run is always safe.

```bash
uv run pytest
```

Path setup lives in the repo-root `conftest.py`; don't re-add per-file
`sys.path` hacks.

## Conventions

- Keep platform-specific things in their existing buckets (e.g. a new package
  goes in the right `app_lists/*` file; a new config goes under
  `application_configs/<app>/`).
- **Config variant naming**: host-, platform-, and context-specific configs use
  the suffix scheme `<base>.<token>.<ext>` with a single lowercase token —
  e.g. `workspace.elitedesk.code-workspace` (host),
  `barrier_config.ryzenwhite.sgc` (host), `settings.mac.json` (platform),
  `settings.acme.json` (context tag for a client/company; compound tags use
  underscores inside the token, e.g. `settings.acme_cloud.json` — such
  company-tagged variants live in that client's `*_credentials` repo, not
  here).
  `src/deploy_configs.py` auto-resolves manifest `repo` paths in the order
  **exact hostname → platform → bare default** (hostname matching is
  case-insensitive on the short pre-dot name, so host `ENVY.LOCAL`
  matches token `envy`; platform tokens are `darwin`/`mac`, `linux`,
  `windows`). Context tags are never auto-resolved — they are deployed by
  hand or via a host-filtered manifest entry.
- New docs: add a `docs/<prefix>_<topic>.md`, one topic per file, using one
  of the existing prefix families (`repo_`, `setup_`, `homelab_`, `howto_`,
  `plan_`) and add it to `docs/README.md`.
- Match the style of nearby code; respect the flake8 line length (120) and run
  isort before committing.
- **Commit messages**: plain lowercase description of the change, matching the
  existing `git log` style ("update t3 setup", "improve deploy harnesses").
  No scope/app-name prefixes ("t3code:", "feat:", tool names) — a 2026-08-05
  agent session prefixed a day of commits with `t3code:` and it reads like
  the app branded the history.
- Don't commit secrets. `.env` and credential files are gitignored — keep them
  that way.

## Working in a Claude Code web/cloud session

- The container is ephemeral and starts from a fresh clone — commit and push
  anything worth keeping.
- Default workflow here: develop on a feature branch, commit, push that branch.
  Do **not** push to `master` and do **not** open a PR unless explicitly asked.
- Network access depends on the session's network policy; package installs or
  external API calls may be blocked.
