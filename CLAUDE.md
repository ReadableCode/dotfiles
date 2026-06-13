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

## Repository layout

| Path | Purpose |
|------|---------|
| `src/` | Python utilities. `deploy_configs.py` deploys configs to machines; `bitwarden.py`, `pull_*.py`, `ssh_devices.py` pull data/configs. Shared helpers in `src/utils/`. |
| `scripts/` | Standalone shell / PowerShell / AHK scripts for install & maintenance tasks. |
| `application_configs/` | Source-of-truth dotfiles for bash, zsh, nvim, tmux, vscode, zed, git, claude, etc. |
| `app_lists/` | Package manifests per platform (Brewfile, choco, winget, apt, Termux). |
| `ansible_playbooks/` + `inventory/` | Ansible for provisioning machines. |
| `go_apps/` | Small Go tools (`git_puller`, client/server, syncthing cleanup). Prebuilt binaries are committed. |
| `docs/` | Setup/how-to docs (one per topic). Surfaced via mkdocs. |
| `tests/` | pytest suite (`tests/test_utils/`). |
| `pythonista/` | iOS Pythonista scripts. |
| `triggers/` | Crontab snapshots per host. |

## Python environment & tooling

This project uses **uv** (Python 3.10, pinned in `.python-version`). The
`README.md` still references `pipenv` — that is **stale**; prefer uv.

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

```bash
uv run pytest                # from repo root
uv run pytest tests/test_utils/test_date_tools.py   # single file
```

Some tests touch external services (Gmail, Google Sheets, S3). In a sandboxed
cloud/web session without credentials those will be skipped or fail on auth —
that is expected, not a regression you introduced. Prefer running the specific
test relevant to your change.

## Conventions

- Keep platform-specific things in their existing buckets (e.g. a new package
  goes in the right `app_lists/*` file; a new config goes under
  `application_configs/<app>/`).
- New docs: add a `docs/<topic>.md` following the existing one-topic-per-file
  pattern.
- Match the style of nearby code; respect the flake8 line length (120) and run
  isort before committing.
- Don't commit secrets. `.env` and credential files are gitignored — keep them
  that way.

## Working in a Claude Code web/cloud session

- The container is ephemeral and starts from a fresh clone — commit and push
  anything worth keeping.
- Default workflow here: develop on a feature branch, commit, push that branch.
  Do **not** push to `master` and do **not** open a PR unless explicitly asked.
- Network access depends on the session's network policy; package installs or
  external API calls may be blocked.
