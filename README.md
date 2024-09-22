# dotfiles

## Running with pipenv

* Install dependencies for system:

  Linux:

    ```bash
    pip install pipenv
    ```

  Windows:

    In powershell as admin:

    ```bash
    pip install pipenv
    ```
  
    On Windows you may need to add the path to pipenv to your PATH environment variable, it will be printed at the end of the install command most likely

* To install dependencies:

  ```bash
  pipenv install
  ```

  To run:

  ```bash
  pipenv run python src/main.py
  ```

* To make changes to requirements.txt, change the file and then:

  ```bash
  pipenv --rm
  rm Pipfile.lock
  rm Pipfile
  pipenv install # to use the new requirements.txt
  ```

* To enter bash in the virtual environment:

  ```bash
  pipenv shell
  ```

* To Activate or Source the environment and not have to prepend each command with pipenv:

  On Linux:

  ```bash
  source $(pipenv --venv)/bin/activate
  ```
  
  On Windows (Powershell):

  ```bash
  & "$(pipenv --venv)\Scripts\activate.ps1"
  ```

* To Deactivate:

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

To run tests:

```bash
cd tests
pytest # include name of test_file.py to run specific test
```

To exit:

```bash
exit
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
