# WeasyPrint + GTK3 + MSYS2 on Windows (No Admin Rights)

These instructions install everything **inside your user profile**, so no admin permissions are required.

## Install MSYS2 (user-space)

Set up MSYS2 and install the package list by following [msys2.md](./msys2.md).

## GTK3 stack inside MSYS2

WeasyPrint needs these packages from
[app_lists/msys2_packages.txt](../app_lists/msys2_packages.txt):

- `mingw-w64-x86_64-gtk3`
- `mingw-w64-x86_64-gobject-introspection`
- `mingw-w64-x86_64-pango`
- `mingw-w64-x86_64-gdk-pixbuf2`

Install just these from PowerShell:

```powershell
C:\msys64\usr\bin\bash.exe -lc "pacman -S --needed --noconfirm mingw-w64-x86_64-gtk3 mingw-w64-x86_64-gobject-introspection mingw-w64-x86_64-pango mingw-w64-x86_64-gdk-pixbuf2"
```

What these packages are:

- `mingw-w64-x86_64-gtk3`  
  Windows-native GTK3 DLLs and headers (widgets, drawing, event loop).

- `mingw-w64-x86_64-gobject-introspection`  
  Type metadata so higher-level languages (Python) can use GTK and GObject.

- `mingw-w64-x86_64-pango`  
  Text layout and font rendering (glyph shaping, line breaking).

- `mingw-w64-x86_64-gdk-pixbuf2`  
  Image loading/decoding (PNG, JPEG, etc.) used by GTK.

All of these are installed **inside MSYS2’s directory tree** (for example `C:\\msys64\\mingw64\\bin`) and do not touch system folders.

## Add GTK / Pango / Pixbuf DLLs to your PATH (per user)

You need WeasyPrint to see the GTK-related DLLs, which live in the MinGW64 `bin` folder.

1. Determine the MinGW64 binary path (typical):

```text
C:\\msys64\\mingw64\\bin
```

2. Add this path **to your user PATH only**.

In PowerShell, for the current session:

```powershell
$env:Path = "C:\\msys64\\mingw64\\bin;" + $env:Path
```

3. Add to powershell profile for future sessions:

```powershell
notepad $PROFILE
```

4. Add this line to the end of the file and save:

```powershell
$env:Path = "C:\\msys64\\mingw64\\bin;" + $env:Path
```
