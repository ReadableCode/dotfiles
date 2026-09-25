#!/usr/bin/env python3
"""
Open a VNC viewer at a host, offering to install the viewer when it is missing.

What the ``vnc<host>`` aliases actually run. They used to invoke the viewer
directly, which meant a machine that had never run its app-list installer got a
bare ``command not found`` - or, on macOS, silence, because the alias pointed at
a path inside an .app that was not there. Neither says the one useful thing:
that the viewer is missing, and offers to fetch it.

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


# The macOS cask installs an .app rather than something on PATH, so that one is
# an absolute path; choco and apt/dnf both put ``vncviewer`` on PATH.
MAC_VIEWER = "/Applications/TigerVNC.app/Contents/MacOS/vncviewer"

# RemoteResize defaults to on: the viewer asks the server to match the desktop
# to the local window every time that window changes. wayvnc drives a headless
# Pi whose output cannot be resized, so it refuses, and the viewer logs
# "SetDesktopSize failed: 4" on every resize for the whole session. Turning it
# off keeps the remote at its own size and stops the noise; nothing is lost,
# because the resize was never going to succeed.
#
# AlwaysCursor draws the remote pointer when the server sends an invisible one,
# which is the difference between seeing where you are pointing and not - the
# default is off, and the symptom is simply no cursor. CursorType=System makes
# it the real pointer rather than TigerVNC's fallback dot.
VIEWER_ARGS = ["-RemoteResize=0", "-AlwaysCursor=1", "-CursorType=System"]


def platform_key(platform_token=None):
    """darwin / windows / linux from a sys.platform-style token."""
    token = str(platform_token if platform_token is not None else sys.platform).lower()
    if token.startswith("darwin") or token == "mac":
        return "darwin"
    if token.startswith("win"):
        return "windows"
    return "linux"


def linux_plan():
    """
    (package, install argv) for this Linux box, chosen by the package manager
    it actually has: Fedora and Debian name the viewer differently.
    """
    if shutil.which("apt-get"):
        return "tigervnc-viewer", ["sudo", "apt-get", "install", "-y", "tigervnc-viewer"]
    if shutil.which("dnf"):
        return "tigervnc", ["sudo", "dnf", "install", "-y", "tigervnc"]
    return None, None


def viewer_plan(key):
    """
    (viewer command, package, install argv) for a platform key.

    The install is ONE package, not the whole app list. Running the list
    installer to get a viewer would offer every other pending app on the
    machine, which is not what someone typing ``vncpi4`` asked for.
    """
    if key == "darwin":
        return MAC_VIEWER, "tigervnc", ["brew", "install", "--cask", "tigervnc"]
    if key == "windows":
        return "vncviewer", "tigervnc", ["choco", "install", "tigervnc", "-y"]
    package, argv = linux_plan()
    return "vncviewer", package, argv


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


def offer_install(viewer, package, install_argv, ask=None, run=subprocess.call):
    """
    Offer to install just the viewer, returning its path once present.

    ONE package, with the platform's own manager - not the whole-list
    installer. Someone typing ``vncpi4`` asked for a viewer, and
    ``install_mac_apps.sh`` would put every other pending app on the machine in
    front of them.

    The app lists are not consulted: they gate what a refresh offers on its own,
    and this is a command someone typed, which may install the one thing it
    needs. The prompt is still there, and nothing installs without a terminal.
    """
    ask = ask or ask_yes_no
    print(f"The VNC viewer is not installed on this machine (looked for {viewer}).")
    if not package or not install_argv:
        print("No known package manager on this machine; install TigerVNC by hand.")
        return None
    if not sys.stdin.isatty():
        print(f"Not running on a terminal, so not prompting. Install {package}, then try again.")
        return None
    if not ask("Install {} now? [y/N] ".format(" ".join(install_argv))):
        return None
    run(install_argv)
    return find_viewer(viewer)


# %%
# Connect #


def connect(target, port=DEFAULT_VNC_PORT, platform_token=None, run=subprocess.call, ask=None):
    """
    Launch the viewer at ``target::port``, offering to install it when missing.

    The doubled colon is not optional: TigerVNC reads ``host:5900`` as display
    number 5900, and only ``host::5900`` as a port.
    """
    viewer, package, install_argv = viewer_plan(platform_key(platform_token))
    found = find_viewer(viewer)
    if not found:
        found = offer_install(viewer, package, install_argv, ask=ask, run=run)
    if not found:
        return 1
    return run([found] + VIEWER_ARGS + [f"{target}::{int(port)}"])


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
