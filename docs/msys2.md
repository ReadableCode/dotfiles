# MSYS2 Package Management

This file documents how to manage MSYS2 packages on the Windows host (FFLAP-2229) via the user-scope MSYS2 install at C:\msys64\.

## Capture currently installed packages

From PowerShell, regenerate app_lists/msys2_packages.txt with whatever is currently explicitly installed:

```powershell
C:\msys64\usr\bin\bash.exe -lc "pacman -Qqe | grep -v '^msys2-\|^base\|^filesystem\|^bash\|^pacman\|^ca-certificates\|^coreutils\|^gcc\|^glibc' > /c/Users/jason.christiansen/GitHub/dotfiles/app_lists/msys2_packages.txt"
```

The grep filter excludes base MSYS2 system packages so the list only contains tools intentionally added.

## Install packages from the list on a fresh machine

From an MSYS2 bash shell (C:\msys64\usr\bin\bash.exe -l):

```powershell
pacman -Syu
pacman -S --needed - < ~/GitHub/dotfiles/app_lists/msys2_packages.txt
```

--needed skips anything already installed. The - tells pacman to read package names from stdin.

## Add a new package

Install it normally via pacman, then regenerate the list file using the capture command above. This keeps the list file as the source of truth for what is installed.

## Home directory

`C:\msys64\etc\nsswitch.conf` is set to `db_home: windows` (default was
`cygwin desc`) so MSYS2's `$HOME` is always the Windows profile
(`C:\Users\<user>`) no matter how a shell is launched — mintty, over ssh, or
from PowerShell. Without this, launch contexts that don't pass a `HOME` env
var get `/home/<user>` (`C:\msys64\home\<user>`) instead, and tools like tmux
read their dotfiles from the wrong place. This is a local edit on each
machine, not a deployed config — redo it after a fresh MSYS2 install.

## tmux

tmux (from `app_lists/msys2_packages.txt`) must run inside a POSIX layer, so
on Windows it lives in MSYS2. The deployed `~/.tmux.conf` detects MSYS2 via
`uname -o` and sets `default-command` to PowerShell, so every tmux window is
a PowerShell prompt. Start it from any terminal with:

```powershell
C:\msys64\usr\bin\bash.exe -lc tmux          # new session
C:\msys64\usr\bin\bash.exe -lc "tmux attach" # reattach after disconnect
```

## Notes

- This is the pacman equivalent of a Brewfile for macOS.
- MSYS2 on this host is user-scope and requires no admin to install/update packages.
- The mingw-w64-x86_64-* packages install Windows-native binaries to C:\msys64\mingw64\bin\ which is on PATH via $PROFILE.
- Core Unix utilities (less, grep, sed, etc.) live in C:\msys64\usr\bin\ which is also on PATH.
