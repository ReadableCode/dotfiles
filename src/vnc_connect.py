#!/usr/bin/env python3
"""
Open a VNC viewer at a host, offering to install the viewer when it is missing.

What the ``vnc<host>`` aliases actually run. They used to invoke the viewer
directly, which meant a machine that had never run its app-list installer got a
bare ``command not found`` - or, on macOS, silence, because the alias pointed at
a path inside an .app that was not there. Neither says the one useful thing:
which list names the viewer and which installer installs it.

Stdlib-only and one file for every platform, the same contract as
``ssh_aliases.py``: the shells eval what that generator prints, so anything it
points at has to run under a bare ``python3`` on macOS, Linux and Windows alike.

Why TigerVNC everywhere rather than each platform's native client: wayvnc, which
every Pi runs, offers only VeNCrypt, RSA-AES and RA2. macOS Screen Sharing
speaks VNC Auth and Apple ARD, so it cannot negotiate at all - it fails before
asking for a password. TigerVNC speaks every one of them, so a single viewer
reaches the Pis, the Windows boxes running TightVNC, and the Macs.
"""

# %%
# Imports #

import argparse
import os
import shutil
import subprocess
import sys

# %%
# Variables #

DEFAULT_VNC_PORT = 5900

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The macOS cask installs an .app rather than something on PATH, so that one is
# an absolute path; choco and apt/dnf both put ``vncviewer`` on PATH.
MAC_VIEWER = "/Applications/TigerVNC.app/Contents/MacOS/vncviewer"


def platform_key(platform_token=None):
    """darwin / windows / linux from a sys.platform-style token."""
    token = str(platform_token if platform_token is not None else sys.platform).lower()
    if token.startswith("darwin") or token == "mac":
        return "darwin"
    if token.startswith("win"):
        return "windows"
    return "linux"


def linux_installer():
    """
    The app-list installer for this Linux box, chosen by the package manager it
    actually has. Fedora and Debian keep separate lists, so the wrong one would
    report every package missing.
    """
    if shutil.which("apt-get"):
        return "scripts/install_linux_apps.sh", "app_lists/linux_apps.txt"
    if shutil.which("dnf"):
        return "scripts/install_linux_apps_dnf.sh", "app_lists/linux_apps_dnf.txt"
    return None, None


def viewer_plan(key):
    """(viewer command, installer script, app list) for a platform key."""
    if key == "darwin":
        return MAC_VIEWER, "scripts/install_mac_apps.sh", "app_lists/Brewfile"
    if key == "windows":
        return (
            "vncviewer",
            "scripts/install_windows_apps_with_chocolatey.ps1",
            "app_lists/windows_apps_personal_choco.txt",
        )
    installer, app_list = linux_installer()
    return "vncviewer", installer, app_list


def find_viewer(viewer):
    """The runnable viewer path, or None. An absolute path is checked directly, a bare name on PATH."""
    if os.path.isabs(viewer):
        return viewer if os.path.exists(viewer) else None
    return shutil.which(viewer)


# %%
# Install offer #


def ask_yes_no(question):
    """True only for an explicit yes. EOF or a bare Enter means no."""
    try:
        return input(question).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def installer_argv(key, installer):
    """How to run this platform's app-list installer."""
    path = os.path.join(REPO_ROOT, installer)
    if key == "windows":
        shell = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
        return [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path]
    return ["bash", path]


def offer_install(key, viewer, installer, app_list, ask=None, run=subprocess.call):
    """
    Offer to run the app-list installer, returning the viewer path once present.

    The installer is the repo's own, not a hand-written ``brew install`` here:
    the app lists are the single record of what a machine should have, and a
    second install path is how a machine ends up with something its list does
    not name. It installs the whole pending list and prompts for itself, which
    is why this only offers rather than running it unasked.
    """
    ask = ask or ask_yes_no
    print(f"The VNC viewer is not installed on this machine (looked for {viewer}).")
    if not installer:
        print("No app-list installer matches this machine's package manager; install TigerVNC by hand.")
        return None
    print(f"It is named in {app_list} and installed by {installer}.")
    if not sys.stdin.isatty():
        print("Not running on a terminal, so not prompting. Run that installer, then try again.")
        return None
    if not ask(f"Run {installer} now? [y/N] "):
        return None
    run(installer_argv(key, installer))
    return find_viewer(viewer)


# %%
# Connect #


def connect(target, port=DEFAULT_VNC_PORT, platform_token=None, run=subprocess.call, ask=None):
    """
    Launch the viewer at ``target::port``, offering to install it when missing.

    The doubled colon is not optional: TigerVNC reads ``host:5900`` as display
    number 5900, and only ``host::5900`` as a port.
    """
    key = platform_key(platform_token)
    viewer, installer, app_list = viewer_plan(key)
    found = find_viewer(viewer)
    if not found:
        found = offer_install(key, viewer, installer, app_list, ask=ask, run=run)
    if not found:
        return 1
    return run([found, f"{target}::{int(port)}"])


# %%
# Main #


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Open a VNC viewer at a host, offering to install the viewer when it is missing."
    )
    parser.add_argument("target", help="hostname or address of the VNC server")
    parser.add_argument("port", nargs="?", type=int, default=DEFAULT_VNC_PORT, help="VNC port (default 5900)")
    parser.add_argument("--platform", default=None, help="platform token, for testing (defaults to sys.platform)")
    args = parser.parse_args(argv)
    return connect(args.target, args.port, args.platform)


if __name__ == "__main__":
    sys.exit(main())

# %%
