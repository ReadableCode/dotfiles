# WeasyPrint + GTK3 + MSYS2 on Windows (No Admin Rights)

These instructions install everything **inside your user profile**, so no admin permissions are required.

## Install MSYS2 (user-space)

1. Open **PowerShell** (no admin).
2. Install MSYS2 with `winget`:

```powershell
winget install --id MSYS2.MSYS2 -e --accept-source-agreements --accept-package-agreements
```

This installs MSYS2 into your user profile (for example under `%LOCALAPPDATA%\\MSYS2\\msys64`).

> If you already have MSYS2 at `C:\\msys64`, you can skip this step.

## Install GTK3 stack inside MSYS2

You’ll install GTK3 and related libraries using MSYS2’s package manager `pacman`.

1. In a PowerShell window, run this command to install the required packages in the MSYS2 MinGW 64-bit environment:

```powershell
C:\\msys64\\usr\\bin\\bash.exe -lc "pacman -Sy --noconfirm mingw-w64-x86_64-gtk3 mingw-w64-x86_64-gobject-introspection mingw-w64-x86_64-pango mingw-w64-x86_64-gdk-pixbuf2"
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
