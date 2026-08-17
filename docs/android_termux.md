# Android Termux

## Start here: run bootstrap

Set up storage first (next section), then:

```bash
curl -fsSL https://raw.githubusercontent.com/ReadableCode/dotfiles/master/scripts/bootstrap.sh | bash
```

Add `--dry-run` first to see what it would do without changing anything. Bootstrap
detects Termux, installs git if missing, clones dotfiles to `~/GitHub`, and installs
`app_lists/android_termux_apps.txt` via `scripts/install_android_termux_apps.sh`, which
reports what is already installed and prompts once for the rest.

**Termux has no uv build**, so bootstrap skips the python steps there — `uv sync`,
`clone_repos.py` and `deploy_configs.py` do not run, and it says so. Configs are not
deployed on Termux; treat it as a shell-and-tools machine.

The rest of this page is the reference detail.

## Set up storage

If runnning android 14 or later might need to run this for storage to work:

```bash
apt update
apt install termux-api termux-am
```

Run Setup Storage:

```bash
termux-setup-storage
```

## Set default start directory

```bash
nano /data/data/com.termux/files/usr/etc/bash.bashrc
```

Add the following to the end of the file:

```bash
cd /storage/emulated/0/
```

## Deploy Config

The `.bashrc` / `.bash_aliases` mappings live in `deploy_manifest.yaml`
(entries `bashrc` and `bash_aliases` — Termux reports itself as Linux; see
[deploy_configs.md](./deploy_configs.md)). Termux usually has no `uv`, so the
same links from the manifest are created by hand here:

```bash
cd ~
ln -s /storage/emulated/0/Documents/
ln -s /storage/emulated/0/GitHub/
ln -s GitHub/dotfiles/
ln -s dotfiles/application_configs/bash/.bashrc
ln -s dotfiles/application_configs/bash/.bash_aliases
source .bashrc
```

## Install packages

```bash
pkg update
pkg upgrade
bash ~/GitHub/dotfiles/scripts/install_android_termux_apps.sh
pip install --upgrade pipenv
pip3 install setuptools wheel packaging pyproject_metadata cython meson-python versioneer
MATHLIB=m LDFLAGS="-lpython3.11" pip3 install --no-build-isolation --no-cache-dir numpy
LDFLAGS="-lpython3.11" pip3 install --no-build-isolation --no-cache-dir pandas
```

## Install a Python Environment

- Cannot install multiple versions of python with pyenv on android so need to ignore version specified in Pipfile

```bash
export PIPENV_PYTHON=$(which python3.11)
pipenv install --ignore-pipfile
```

## Set up SSHD

Generate Host RSA key:
  
  ```bash
  ssh-keygen -A
  ```

Generate key pair on client machine:

```bash
ssh-keygen
```

Copy public key and add to authorized keys on server:

```bash
nano ~/.ssh/authorized_keys
```

Start sshd:

```bash
sshd
```

SSH into Server:

- Default port is 8022

```bash
ssh u0_a1053@192.168.86.249 -p 8022
```

Turn off password authentication:

```bash
nano /data/data/com.termux/files/usr/etc/ssh/sshd_config
```
