"""
Windows taskbar pins across an uninstall and reinstall.

Uninstalling an app unpins it, and installing it again does not pin it back, so
``app_removals.py`` reinstalling an app through choco would cost the pin. A
pin is two things: a ``.lnk`` in the user's pinned folder and an entry in the
``Taskband`` registry value Explorer reads when it starts. ``snapshot`` copies
both before the first uninstall; ``restore`` puts back the pins that went
missing and whose target exists again, then restarts Explorer so it reads them.

A pin whose target did not come back (the reinstall landed somewhere else) is
reported by name and not restored, because a pin to a missing file is a blank
icon. Pins that were never lost are left exactly as they are.

Stdlib-only. Every function is a no-op off Windows.
"""

# %%
# Imports #

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field

# %%
# Variables #

TASKBAND_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Taskband"
TASKBAND_VALUES = ("Favorites", "FavoritesResolve")


def pin_dir(environ=None):
    environ = os.environ if environ is None else environ
    return os.path.join(
        environ.get("APPDATA", ""), "Microsoft", "Internet Explorer", "Quick Launch", "User Pinned", "TaskBar"
    )


@dataclass
class Snapshot:
    """The pins as they were: copies of the ``.lnk`` files and the Taskband values."""

    directory: str
    values: dict = field(default_factory=dict)  # value name -> (data, registry type)


# %%
# Registry #


def read_taskband():
    """``{name: (data, type)}`` for the Taskband values Explorer keeps the pins in."""
    if sys.platform != "win32":
        return {}
    import winreg

    values = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TASKBAND_KEY) as key:
            for name in TASKBAND_VALUES:
                try:
                    values[name] = winreg.QueryValueEx(key, name)
                except OSError:
                    continue
    except OSError:
        return {}
    return values


def write_taskband(values):
    if sys.platform != "win32" or not values:
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TASKBAND_KEY, 0, winreg.KEY_SET_VALUE) as key:
        for name, (data, kind) in values.items():
            winreg.SetValueEx(key, name, 0, kind, data)


# %%
# Snapshot and restore #


def pinned(directory):
    if not os.path.isdir(directory):
        return []
    return sorted(name for name in os.listdir(directory) if name.lower().endswith(".lnk"))


def snapshot(workdir, directory=None, read=read_taskband):
    """Copy every pin into ``workdir`` and read the Taskband values."""
    directory = pin_dir() if directory is None else directory
    os.makedirs(workdir, exist_ok=True)
    for name in pinned(directory):
        shutil.copy2(os.path.join(directory, name), os.path.join(workdir, name))
    return Snapshot(directory=workdir, values=read())


def lost_pins(snap, directory=None):
    """The pins the snapshot holds that are no longer pinned."""
    directory = pin_dir() if directory is None else directory
    now = {name.lower() for name in pinned(directory)}
    return [name for name in pinned(snap.directory) if name.lower() not in now]


def link_targets(paths, run=subprocess.run):
    """``{path: target}`` for each ``.lnk``, read by the shell that made them."""
    if not paths:
        return {}
    quoted = ", ".join("'" + path.replace("'", "''") + "'" for path in paths)
    script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"foreach ($path in @({quoted})) {{ $path + '|' + $shell.CreateShortcut($path).TargetPath }}"
    )
    try:
        done = run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            errors="replace",
        )
    except OSError:
        return {}
    targets = {}
    for line in done.stdout.splitlines():
        path, sep, target = line.strip().partition("|")
        if sep:
            targets[path] = target
    return targets


def restorable(snap, directory=None, targets=link_targets, exists=os.path.exists):
    """``(back, gone)``: lost pins whose target exists again, and the ones whose target does not."""
    lost = lost_pins(snap, directory)
    found = targets([os.path.join(snap.directory, name) for name in lost])
    back, gone = [], []
    for name in lost:
        target = found.get(os.path.join(snap.directory, name), "")
        (back if target and exists(target) else gone).append(name)
    return back, gone


def restore(snap, names, directory=None, write=write_taskband, restart=None):
    """Put the named pins back, with the Taskband values that listed them, and restart Explorer."""
    directory = pin_dir() if directory is None else directory
    if not names:
        return
    os.makedirs(directory, exist_ok=True)
    for name in names:
        shutil.copy2(os.path.join(snap.directory, name), os.path.join(directory, name))
    write(snap.values)
    (restart or restart_explorer)()


def explorer_running(run=subprocess.run):
    done = run(
        ["tasklist", "/FI", "IMAGENAME eq explorer.exe", "/NH"], capture_output=True, text=True, errors="replace"
    )
    return "explorer.exe" in done.stdout.lower()


def restart_explorer(run=subprocess.run, start=None, wait=10.0, sleep=time.sleep, running=explorer_running):
    """
    Stop Explorer so it reads the pins again. Windows starts it again by itself
    after Stop-Process (taskkill does not get that); ``start`` is the fallback
    when it has not come back within ``wait`` seconds.
    """
    run(["powershell", "-NoProfile", "-NonInteractive", "-Command", "Stop-Process -Name explorer -Force"])
    waited = 0.0
    while waited < wait:
        sleep(0.5)
        waited += 0.5
        if running(run):
            return True
    if start is not None:
        start()
    return False


# %%
