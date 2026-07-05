# dotfiles

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
  uv run python src/deploy_configs.py --dry-run
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

## Running with docker

### Docker - Bitwarden Backup Container

This is a two-step process: **build the image first, then run it.** Run both
commands from the repo root (where `.env` and `Dockerfile-bitwarden_backup`
live).

At run time the container loads config (`BITWARDEN_URL`,
`BITWARDEN_ORG_CONFIGS`, credentials, etc.) from your `.env`. The `.env` is
**mounted** into the container rather than baked into the image or passed with
`--env-file` — the script's `.env` loader strips the surrounding quotes that
most of these values use, whereas `docker --env-file` would pass them through
literally (e.g. `LOG_LEVEL="info"` → `"info"`) and break.

#### Linux / macOS

1. Build the image:

```bash
docker build -t dotfiles-bitwarden_backup \
  --build-arg HOSTNAME=$(hostname) \
  --build-arg BITWARDEN_URL=$(grep '^BITWARDEN_URL=' .env | cut -d '=' -f2- | tr -d '"') \
  -f Dockerfile-bitwarden_backup .
```

1. Run it (mount `.env` read-only, the data volume, and the
   `personal_credentials` folder):

```bash
docker run \
  -v "$(pwd)/.env:/dotfiles/.env:ro" \
  -v "$(pwd)/data:/dotfiles/data" \
  -v "$(pwd)/../personal_credentials:/personal_credentials" \
  dotfiles-bitwarden_backup
```

The JSON exports are also copied to `personal_credentials/bitwarden_exports`.
The image sets `PERSONAL_CREDENTIALS_DIR=/personal_credentials`, so the third
mount maps that back to `../personal_credentials` on the host — matching where
a non-Docker run would put it (`~/GitHub/personal_credentials`). To use a
different location, override the env var (`-e PERSONAL_CREDENTIALS_DIR=...`) and
mount accordingly.

#### Windows (PowerShell)

1. Build the image:

   ```powershell
   $bitwardenUrl = (Get-Content .env | Where-Object { $_ -match "^BITWARDEN_URL=" }) -replace 'BITWARDEN_URL=', '' -replace '"', ''

   docker build -t dotfiles-bitwarden_backup `
     --build-arg HOSTNAME=$(hostname) `
     --build-arg BITWARDEN_URL=$bitwardenUrl `
     -f Dockerfile-bitwarden_backup .
   ```

2. Run it (mount `.env` read-only and the data volume):

   ```powershell
   docker run `
     -v "${PWD}/.env:/dotfiles/.env:ro" `
     -v "${PWD}/data:/dotfiles/data" `
     -v "${PWD}/../personal_credentials:/personal_credentials" `
     dotfiles-bitwarden_backup
   ```

## Running Tests

There are two suites:

* **`tests/`** — fast unit tests with no external dependencies. A default
  `pytest` run collects only these (configured via `testpaths` in
  `pyproject.toml`), so they're safe to run anywhere, including CI.

  ```bash
  uv run pytest                                       # full unit suite
  uv run pytest tests/test_utils/test_date_tools.py   # a specific file
  ```

* **`integration_tests/`** — setup/integration checks for Gmail, Google Sheets,
  and S3. These hit live services and need credentials, so they are **not** run
  by default; a developer runs them by hand to confirm an integration is wired
  up on a given machine. See `integration_tests/README.md`.

  ```bash
  uv run pytest integration_tests/
  ```

## Bitwarden Manual Backup - CLI

```bash
# {"object":"organization","id":{{ ORG_ID }},"name":"CrownCentral","status":2,"type":1,"enabled":true}
bw config server {{ BITWARDEN_URL }}

bw login
# enter username and password

bw sync

bw export --output "/My_Backup/data/bitwarden_backup_$(echo $HOSTNAME | tr '[:upper:]' '[:lower:]').json" --format json
# enter password

bw export --output /My_Backup/data/bitwarden_backup_$(echo $HOSTNAME | tr '[:upper:]' '[:lower:]').csv --format csv
# enter password

bw list organizations
# enter password

bw export --organizationid {{ ORG_ID }} --output "/My_Backup/data/bitwarden_backup_$(echo $HOSTNAME | tr '[:upper:]' '[:lower:]')_CrownCentral.json" --format json
# enter password

bw export --organizationid {{ ORG_ID }} --output "/My_Backup/data/bitwarden_backup_$(echo $HOSTNAME | tr '[:upper:]' '[:lower:]')_CrownCentral.csv" --format csv
# enter password
```
