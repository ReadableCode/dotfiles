# Setting up Python Portable

## Install portable python

- Download and extract from [WinPython](https://github.com/winpython/winpython/wiki)

## Setup uv with portable python

```bash
C:/Users/jason.christiansen/userapps/WPy64-31350/python/python.exe -m pip install uv
```

### Running uv

```bash
# cd to dir with pyproject.toml
C:\Users\jason.christiansen\userapps\WPy64-31350\python\Scripts\uv.exe sync
```

- Activate or select new python path:

```bash
& .venv\Scripts\activate.ps1
```
