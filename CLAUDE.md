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
context-specific lives in that context's sibling `*_credentials` repo, and
recurring homelab jobs live in `personal-automation`. See
`docs/repo_philosophy.md` before proposing to move something out.

## Repository layout

| Path | Purpose |
|------|---------|
| `src/` | Python utilities. `deploy_configs.py` deploys configs to machines from `deploy_manifest.yaml` plus overlay manifests (`<context>_manifest.yaml`) discovered in sibling `*_credentials` repos and in any other sibling repo that opts in by declaring one named after its own directory (so config can be gated by a clone narrower than the credentials repo's — see `docs/deploy_configs.md`); an entry marked `per_context_repo` expands at load time into one link per repo in that context's `<context>_repos.yaml`, which is how each context's `.claude/commands` directory and `.mcp.json` reach every one of its checkouts and no other context's; manifest `hosts:` names must exist in the union of the `*_credentials` host inventories (`<context>_hosts.json`, legacy fallback `hosts.json`). `deploy_map.py` redraws the fleet-wide deployment map (every entry × every machine, as an interactive page plus a diffable JSON) from those same plans on every deploy, writing `deploy_map.{html,json}` into the personal credentials repo — but only on host `envy` (`MAP_HOST`; any other machine writing these tracked files dirties that checkout and blocks its next pull) — the page template is `templates/deploy_map.html` and both must stay context-agnostic, since the rendered map names every machine and client at once. The status board TUI moved to the sibling `status_board` repo (panels still discovered from `<context>_statusboard.yaml` in sibling `*_credentials` repos — see that repo's README). `calendar_board.py` is a calendar TUI: Google Calendar + Outlook-on-the-web (Microsoft Graph) accounts as side-by-side day columns with attendance badges and cross-source overlap flags, sources discovered from `<context>_calendarboard.yaml` in the same repos (see `docs/setup_calendar_board.md`); its shared secret resolution lives in `src/utils/secret_tools.py`. `google_mcp.py` is a stdio MCP server exposing that same Google Calendar account plus Gmail (mailboxes from `<context>_googlemail.yaml`, same overlay pattern) to Claude Code with read/write scope — it exists because the hosted claude.ai Calendar/Gmail connectors die under `CLAUDE_CODE_USE_BEDROCK=1`, whereas a local stdio server is provider-independent (see `docs/setup_google_mcp.md`); dotfiles holds the code but declares no instance — each context's credentials repo declares its own named one pinned with `--context` (e.g. `acme_google`), so every registered server is labeled by context and reaches only that context's accounts; OAuth token refresh is shared with the calendar board via `src/utils/google_oauth_tools.py`, and nothing in that process may print to stdout or the JSON-RPC protocol breaks. `claude_mcp.py` registers that server (and every other MCP server on the machine) by **generating** one `data/mcp/<context>.mcp.json` per declaring context at the start of each deploy, from every cloned sibling repo's `mcp_servers.yaml` / `<dirname>_mcp_servers.yaml` declaration (same opt-in rule as overlay manifests, so working repos can ship servers too, and `--print` names every repo scanned); each context's manifest then links its file into that context's checkouts as `<repo>/.mcp.json` through a `per_context_repo` entry, so a session registers only its own context's servers and no file anywhere names another context's (the pre-2026-09-02 single `~/.mcp.json` loaded every context everywhere); `{repo_root}`/`{repo_parent}` tokens and `env_secrets` var names are resolved at generate time, which is why no per-host payload exists (see `docs/setup_google_mcp.md`). `ssh_aliases.py` is the **single** ssh/vnc alias generator for every shell: it reads the `*_credentials` host inventories and prints alias definitions in the caller's syntax (`--format bash` / `--format powershell`), which `.shared_aliases` and `powershell_aliases.ps1` eval at startup — stdlib-only so a bare `python3` runs it before any venv exists, and the reason jump/port/user logic no longer exists twice (see `docs/client_credentials_repos.md`). `updater_policy.py` (same stdlib-only contract) resolves the current host's `updater` block from those same inventories for `scripts/my_updater.sh` — release ceiling, upgrade cadence, mapped check scripts; host entry only, no group/context defaults (see `docs/setup_linux_workstation.md`). `chrome_bookmarks.py`, `ssh_devices.py` pull data/configs. Shared helpers come from the **`readable-utils` package** (github.com/ReadableCode/readable_utils), a uv git dependency pinned to a tag — no vendored copies. `src/utils/` holds only dotfiles-specific modules (`inventory_tools`, `secret_tools`, `calendarboard_tools`, `google_oauth_tools`, `googlemcp_tools`, `mcpservers_tools`). Homelab-only jobs (Bitwarden backup, Home Assistant/router config pulls, log rotation) live in the local `~/GitHub/personal-automation` repo, not here. |
| `scripts/` | Standalone shell / PowerShell / AHK scripts for install & maintenance tasks. |
| `application_configs/` | Source-of-truth dotfiles for bash, zsh, nvim, tmux, vscode, zed, git, claude, etc. |
| `app_lists/` | Package manifests per platform (Brewfile, choco, winget, apt, Termux). |
| `go_apps/` | Small Go tools (`git_puller`, syncthing cleanup). Prebuilt binaries are committed. The ping/command client-server moved to its own repo (`ReadableCode/go-client-server`). |
| `docs/` | Setup/how-to docs (one per topic). Surfaced via mkdocs. |
| `tests/` | pytest suite (`tests/test_utils/`). |
| `pythonista/` | iOS Pythonista scripts. |

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
- New docs: add a `docs/<topic>.md` following the existing one-topic-per-file
  pattern.
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
