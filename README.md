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
  uv run python src/deploy_configs.py
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

* Building Container:

Linux: (untested new version to match working windows versions below)

```bash
docker build -t dotfiles-bitwarden_backup --build-arg HOSTNAME=$(hostname) --build-arg BW_API_URL=$(grep BITWARDEN_URL .env | cut -d '=' -f2) --build-arg BW_IDENTITY_URL=$(grep BITWARDEN_URL .env | cut -d '=' -f2) -f Dockerfile-bitwarden_backup .
```

Windows:

```powershell
$envFile = ".env"
$bwApiUrl = (Get-Content $envFile | Where-Object { $_ -match "^BW_API_URL=" }) -replace "BW_API_URL=", ""
$bwIdentityUrl = (Get-Content $envFile | Where-Object { $_ -match "^BW_IDENTITY_URL=" }) -replace "BW_IDENTITY_URL=", ""

docker build -t dotfiles-bitwarden_backup `
  --build-arg HOSTNAME=$(hostname) `
  --build-arg BW_API_URL=$bwApiUrl `
  --build-arg BW_IDENTITY_URL=$bwIdentityUrl `
  -f Dockerfile-bitwarden_backup .
```

* Running without interactive mode:

  ```bash
  docker run -v "$(pwd)/data:/dotfiles/data" dotfiles-bitwarden_backup
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
