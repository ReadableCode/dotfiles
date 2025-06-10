# Setting Up Python

## Setting Up Python Using uv

- [https://github.com/astral-sh/uv](https://github.com/astral-sh/uv)

### Install uv on Windows

- Install with script:

```bash
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

- Install uv with chocolatey:

```bash
choco install uv
```

### Install uv on macOS or Linux

- Install with script:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Install a version of python

- Use uv to install a version of python:

```bash
uv python install 3.10.12
```

## Managing Dpendencies

- Init a project:

```bash
uv init
```

- If you have a pyproject.toml file, you can sync the dependencies from the requirements with the venv:

```bash
uv sync
```

- To add a package to the project:

```bash
uv add <package name>
```

- To remove a package from the project:

```bash
uv remove <package name>
```

- To see a tree of dependencies:

```bash
uv tree
```

- To activate on a terminal in Windows:

```powershell
.\.venv\Scripts\Activate.ps1
```

- To activate on a terminal in Linux or macOS:

```bash
source ./.venv/bin/activate
```

### Converting a pipenv project to uv

- CD into the project directory and create a uv project:

```bash
uv init
```

- Or add a section to any existing pyproject.toml file for the project:

```toml
[project]
name = "dotfiles"
version = "0.1.0"
description = "dotfiles"
requires-python = ">=3.10,<3.11"
```

- If you have a requirements.txt file, you can sync the dependencies from the requirements with the venv:

```bash
uv add -r requirements.txt
```

- Add the .gitignore items below:

```bash
*.egg-info/
.venv
```

- Remove the pipfile, pipfile.lock and requirements.txt files:

```bash
rm Pipfile
rm Pipfile.lock
rm requirements.txt
```

- Remove pipenv environments from the system

```bash
pipenv --rm
```

## Installing Python Directly on Windows

- Visit the official Python site at python.org and navigate to the downloads section.

- Click on the "Downloads" tab and choose Python 3.xx for Windows.

- Download the Python 3.xx installer appropriate for your system architecture (32-bit or 64-bit).

- Run the downloaded installer and follow the installation wizard. Make sure to select the option to customize the installation.

- In the customization options, enable the "Add Python to PATH" checkbox. This will add Python to the system's PATH for easy accessibility.

- Continue with the installation process and complete the installation.

### Enabling Long Path Support on Windows (if not done with installer)

- Open a PowerShell or Command Prompt window as an administrator.

- Run the following command to enable long path support in the Windows registry:

   ```bash
   reg add HKLM\SYSTEM\CurrentControlSet\Control\FileSystem /v LongPathsEnabled /t REG_DWORD /d 1 /f
   ```

   This command enables long path support for the system.

### Verifying Python Installation on Windows (if not done with installer)

- Open a new command prompt or PowerShell window.

- Verify that Python 3.xx is installed correctly by running the following command:

   ```bash
   python --version
   ```

   This command should display the installed Python version as "Python 3.xx.x".
