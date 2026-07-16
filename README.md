# dotfiles

Portable knowledge base + toolkit, cloned onto every machine (personal and
work). It codifies things I know how to do and carries the configs and
tooling every context depends on; context-specific layers come from sibling
`*_credentials` repos. See `docs/repo_philosophy.md` for what belongs here
versus in sibling repos.

## Running with uv

This project uses [uv](https://docs.astral.sh/uv/) for dependency and
environment management. Python version is pinned in `.python-version`.

* Install uv:

  Linux / macOS:

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

  Windows (PowerShell as admin):

    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

* Install dependencies (creates the virtual environment from `pyproject.toml`
  and `uv.lock`):

  ```bash
  uv sync
  ```

* To run a script (uv resolves the environment automatically, no activation
  needed):

  ```bash
  uv run python src/deploy_configs.py status
  ```

* To add or remove a dependency (updates `pyproject.toml` and `uv.lock`):

  ```bash
  uv add <package>
  uv remove <package>
  ```

* To enter a shell inside the virtual environment:

  On Linux / macOS:

  ```bash
  source .venv/bin/activate
  ```

  On Windows (PowerShell):

  ```powershell
  .venv\Scripts\Activate.ps1
  ```

* To deactivate:

  ```bash
  deactivate
  ```

## Bitwarden backup (moved)

The Bitwarden vault backup job (`src/bitwarden.py`,
`Dockerfile-bitwarden_backup`, and the manual `bw export` instructions) is a
homelab-only job and lives in the local `personal-automation` repo
(`~/GitHub/personal-automation`), along with the Minecraft log tooling. See
that repo's README for the Docker build/run commands and the cutover
checklist. Dotfiles itself stays focused on what every device needs: config
deploy/pull and repo pulling.

## Running Tests

* **`tests/`** — fast unit tests with no external dependencies. A default
  `pytest` run collects only these (configured via `testpaths` in
  `pyproject.toml`), so they're safe to run anywhere, including CI.

  ```bash
  uv run pytest                                       # full unit suite
  uv run pytest tests/test_deploy_configs.py          # a specific file
  ```

