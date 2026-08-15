# Setting up Python Portable

## Install portable python

- Download and extract from [WinPython](https://github.com/winpython/winpython/wiki)

## Setup uv with portable python

```bash
%USERPROFILE%/userapps/WPy64-<version>/python/python.exe -m pip install uv
```

### Running uv

```bash
# cd to dir with pyproject.toml
%USERPROFILE%\userapps\WPy64-<version>\python\Scripts\uv.exe sync
```

- Activate or select new python path:

```bash
& .venv\Scripts\activate.ps1
```
