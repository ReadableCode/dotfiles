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

- Add a section to any existing pyproject.toml file for the project:

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
rm Pipfile Pipfile.lock requirements.txt
```

- Remove pipenv environments from the system
