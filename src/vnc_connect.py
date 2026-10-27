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

A host whose inventory record carries an rdp ``remote_desktop`` block gets
FreeRDP instead (``--rdp <name>``): a GNOME desktop on Wayland shares its live
session only through gnome-remote-desktop, whose VNC side Fedora offers as
anonymous TLS or unencrypted VNC Auth, and its RDP side as TLS. The record
names the user, the env var holding the password and the certificate's sha256
fingerprint; the whole command line goes to FreeRDP on stdin
(``/args-from:stdin``), so the password never appears in a process list, and the
pinned fingerprint means no trust prompt and no other certificate accepted.
FreeRDP is Apache-2.0 on every platform: Homebrew's ``freerdp``, Fedora's
``freerdp``, Debian's ``freerdp3-sdl`` and MSYS2's ucrt64 package on Windows.
"""

# %%
# Imports #

import argparse
import os
import shutil
import subprocess
import sys

from utils.inventory_tools import find_host_record
from utils.secret_tools import resolve_secret

# %%
# Variables #

DEFAULT_VNC_PORT = 5900
DEFAULT_RDP_PORT = 3389
DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# FreeRDP's SDL client. Debian suffixes its binaries with the major version;
# Fedora and Homebrew do not. MSYS2 installs outside PATH on Windows.
RDP_VIEWERS = ("sdl-freerdp", "sdl-freerdp3")
MSYS2_ROOT = r"C:\msys64"
WINDOWS_RDP_VIEWER = MSYS2_ROOT + r"\ucrt64\bin\sdl-freerdp.exe"
WINDOWS_RDP_PACKAGE = "mingw-w64-ucrt-x86_64-freerdp"

# Mirrored sessions are the size of the remote screen, which may not fit this
# one: smart-sizing scales it to the window. The clipboard is shared both ways.
RDP_ARGS = ["/smart-sizing", "+clipboard"]


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


def rdp_plan(key):
    """(viewer candidates, package, install argv) for FreeRDP on a platform key."""
    if key == "darwin":
        return list(RDP_VIEWERS), "freerdp", ["brew", "install", "freerdp"]
    if key == "windows":
        pacman = MSYS2_ROOT + r"\usr\bin\pacman.exe"
        return [WINDOWS_RDP_VIEWER], WINDOWS_RDP_PACKAGE, [pacman, "-S", "--noconfirm", WINDOWS_RDP_PACKAGE]
    if shutil.which("apt-get"):
        return list(RDP_VIEWERS), "freerdp3-sdl", ["sudo", "apt-get", "install", "-y", "freerdp3-sdl"]
    if shutil.which("dnf"):
        return list(RDP_VIEWERS), "freerdp", ["sudo", "dnf", "install", "-y", "freerdp"]
    return list(RDP_VIEWERS), None, None


def find_any_viewer(viewers):
    """The first of several candidate viewers that is installed, or None."""
    for viewer in viewers:
        found = find_viewer(viewer)
        if found:
            return found
    return None


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


def offer_install(viewer, package, install_argv, ask=None, run=subprocess.call, name="TigerVNC"):
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
    viewers = viewer if isinstance(viewer, list) else [viewer]
    print(f"The viewer is not installed on this machine (looked for {', '.join(viewers)}).")
    if not package or not install_argv:
        print(f"No known package manager on this machine; install {name} by hand.")
        return None
    if not sys.stdin.isatty():
        print(f"Not running on a terminal, so not prompting. Install {package}, then try again.")
        return None
    if not ask("Install {} now? [y/N] ".format(" ".join(install_argv))):
        return None
    run(install_argv)
    return find_any_viewer(viewers)


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


def rdp_target(name, root=DEFAULT_ROOT):
    """(host, port, user, password, fingerprint) for an inventory host with an rdp remote_desktop block."""
    context, record = find_host_record(name, root)
    block = (record or {}).get("remote_desktop") or {}
    if block.get("protocol") != "rdp":
        raise ValueError(f"{name}: no rdp remote_desktop block in any inventory under {root}")
    panel = {
        "name": record["name"],
        "password_env": block["password_env"],
        "env_file": block.get("env_file"),
        "_base_dir": os.path.join(root, f"{context}_credentials"),
    }
    host = record.get("hostname") or record["name"]
    port = int(block.get("port") or DEFAULT_RDP_PORT)
    return host, port, block["user"], resolve_secret(panel, "password_env"), block["fingerprint"]


def rdp_arguments(host, port, user, password, fingerprint):
    """FreeRDP's command line, one argument per line, for /args-from:stdin. An empty line ends it."""
    lines = [f"/v:{host}:{int(port)}", f"/u:{user}", f"/p:{password}", f"/cert:fingerprint:{fingerprint}"]
    return "\n".join(lines + RDP_ARGS) + "\n\n"


def run_with_input(argv, text):
    return subprocess.run(argv, input=text, text=True).returncode


def connect_rdp(name, platform_token=None, run=run_with_input, install=subprocess.call, ask=None, root=DEFAULT_ROOT):
    """Launch FreeRDP at an inventory host, offering to install it when missing."""
    target = rdp_target(name, root)
    viewers, package, install_argv = rdp_plan(platform_key(platform_token))
    found = find_any_viewer(viewers)
    if not found:
        found = offer_install(viewers, package, install_argv, ask=ask, run=install, name="FreeRDP")
    if not found:
        return 1
    return run([found, "/args-from:stdin"], rdp_arguments(*target))


# %%
# Main #


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Open a VNC viewer at a host, offering to install the viewer when it is missing."
    )
    parser.add_argument("target", nargs="?", help="hostname or address of the VNC server")
    parser.add_argument("port", nargs="?", type=int, default=DEFAULT_VNC_PORT, help="VNC port (default 5900)")
    parser.add_argument("--rdp", metavar="NAME", help="connect over RDP to this inventory host instead")
    parser.add_argument("--platform", default=None, help="platform token, for testing (defaults to sys.platform)")
    args = parser.parse_args(argv)
    if args.rdp:
        return connect_rdp(args.rdp, args.platform)
    if not args.target:
        parser.error("a target is required without --rdp")
    return connect(args.target, args.port, args.platform)


if __name__ == "__main__":
    sys.exit(main())

# %%
