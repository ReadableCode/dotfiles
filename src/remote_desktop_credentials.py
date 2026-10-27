"""
Set this machine's GNOME Remote Desktop login from its inventory record.

The one part of RDP Desktop Sharing a deploy cannot place as a file. Its
settings are a system dconf keyfile and its TLS certificate is a link, both
manifest entries, but gnome-remote-desktop keeps the RDP username and password
of a desktop-sharing session only in the user's keyring (libsecret), reachable
only through ``grdctl``. So this runs as a refresh step after the deploy:

    "remote_desktop": {
      "protocol": "rdp",
      "user": "jason",
      "password_env": "BOX_RDP_PASSWORD",
      "env_file": "personal.env",
      ...
    }

on the host's record in ``<context>_hosts.json`` names the user and the env var
holding the password, in ``env_file`` beside the inventory. The keyring copy is
read with ``grdctl status --show-credentials`` and set only when it differs;
the password goes to ``grdctl`` on stdin, never on its command line. When the
login changed or nothing listens on the RDP port, the user's
``gnome-remote-desktop.service`` is restarted: the daemon starts RDP only from
what it reads at startup. A host
with no ``remote_desktop`` block, or one whose protocol is not rdp, is not
governed and nothing runs.

``--check`` reports whether the keyring matches and writes nothing.

The keyring is the logged-in session's: it has to be unlocked, which it is
while someone is signed in at the machine. Over ssh the session bus is found
at ``/run/user/<uid>/bus``.
"""

# %%
# Imports #

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time

from utils.inventory_tools import find_host_record
from utils.secret_tools import resolve_secret

# %%
# Variables #

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# %%
# Functions #


def rdp_block(record):
    """The host's ``remote_desktop`` block when it asks for RDP, else None."""
    block = (record or {}).get("remote_desktop")
    if not isinstance(block, dict) or block.get("protocol") != "rdp":
        return None
    return block


def wanted_credentials(context, record, root):
    """(user, password) the inventory says this host's RDP login is."""
    block = rdp_block(record)
    panel = {
        "name": record.get("name", ""),
        "password_env": block["password_env"],
        "env_file": block.get("env_file"),
        "_base_dir": os.path.join(root, f"{context}_credentials"),
    }
    return block["user"], resolve_secret(panel, "password_env")


def session_environ(environ=None, uid=None):
    """The environment with a session bus address, filled in from /run/user/<uid>/bus over ssh."""
    env = dict(os.environ if environ is None else environ)
    if not env.get("DBUS_SESSION_BUS_ADDRESS"):
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{os.getuid() if uid is None else uid}/bus"
    return env


def parse_rdp_credentials(status_text):
    """(user, password) from the RDP section of ``grdctl status --show-credentials``; None for one not set."""
    user = password = None
    in_rdp = False
    for line in status_text.splitlines():
        if line and not line[0].isspace():
            in_rdp = line.strip() == "RDP:"
            continue
        if not in_rdp:
            continue
        key, _, value = line.strip().partition(": ")
        if key == "Username":
            user = value or None
        elif key == "Password":
            password = value or None
    return user, password


def current_credentials(env, run=subprocess.run):
    """The RDP login the keyring holds now."""
    result = run(["grdctl", "status", "--show-credentials"], env=env, capture_output=True, text=True, check=True)
    return parse_rdp_credentials(result.stdout)


def set_credentials(user, password, env, run=subprocess.run):
    """Write the RDP login to the keyring, the password on stdin."""
    run(["grdctl", "rdp", "set-credentials", user], env=env, input=password + "\n", text=True, check=True)


def listening(port, host="127.0.0.1", timeout=2):
    """Whether something accepts connections on the RDP port."""
    try:
        with socket.create_connection((host, int(port)), timeout):
            return True
    except OSError:
        return False


def restart_daemon(env, run=subprocess.run):
    """Restart the user's gnome-remote-desktop, which starts RDP only from settings it reads at startup."""
    run(["systemctl", "--user", "restart", "gnome-remote-desktop.service"], env=env, check=True)


def sync(hostname, root, check=False, run=subprocess.run, which=shutil.which, environ=None, is_listening=listening):
    """Bring this host's RDP login in line with its inventory record. Returns an exit code."""
    context, record = find_host_record(hostname, root)
    if rdp_block(record) is None:
        return 0
    if not which("grdctl"):
        print(f"{record['name']} declares an rdp remote_desktop, but grdctl is not installed here.")
        return 1
    block = rdp_block(record)
    port = int(block.get("port") or 3389)
    user, password = wanted_credentials(context, record, root)
    env = session_environ(environ)
    current = current_credentials(env, run=run) == (user, password)
    up = is_listening(port)
    if current and up:
        print(f"remote desktop login for {user} is current and port {port} is listening")
        return 0
    if check:
        if not current:
            print(f"remote desktop login for {user} differs from the inventory; a refresh would set it")
        if not up:
            print(f"nothing listens on port {port}; a refresh would restart gnome-remote-desktop")
        return 0
    if not current:
        set_credentials(user, password, env, run=run)
        print(f"remote desktop login for {user} set from {block['password_env']}")
    # The daemon reads the RDP settings, certificate and login when it starts;
    # a change it hears about while running (the deploy's dconf update lands
    # before the certificate links do) leaves RDP off until a restart.
    restart_daemon(env, run=run)
    if not is_listening(port):
        time.sleep(3)
    if not is_listening(port):
        print(
            f"gnome-remote-desktop restarted, but nothing listens on port {port}; "
            "see journalctl --user -u gnome-remote-desktop"
        )
        return 1
    print(f"gnome-remote-desktop restarted, rdp listening on port {port}")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Set this machine's GNOME Remote Desktop login from its inventory.")
    parser.add_argument("--check", action="store_true", help="report whether the keyring matches, change nothing")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="directory holding the sibling repos")
    parser.add_argument("--hostname", default=None, help="host to act as (defaults to this machine)")
    args, _ = parser.parse_known_args(argv)
    return args


# %%
# Main #

if __name__ == "__main__":
    args = parse_args()
    exit_code = sync(args.hostname or socket.gethostname(), args.root, check=args.check)
    if exit_code:
        sys.exit(exit_code)

# %%
