# Setting up Python Portable

## Install portable python

- Download and extract from [WinPython](https://github.com/winpython/winpython/wiki)
  into `%USERPROFILE%\userapps\` — the shared PATH block finds the newest
  `WPy64-*` folder by pattern, see
  [setup_windows_portable_userapps.md](./setup_windows_portable_userapps.md)

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
