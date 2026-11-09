"""
Keep this machine answering RustDesk on the direct IP port its record names.

RustDesk holds its settings in ``RustDesk2.toml`` beside its own runtime state
(the negotiated ``nat_type``, ``serial``, ``local-ip-addr``), and the app
rewrites that file whenever it changes anything. A deployed symlink would
therefore hand the app a repo file to write into, so the settings are declared
instead:

    "rustdesk": {"direct_access_port": 21118}

on the host in ``<context>_hosts.json``. This ensures ``direct-server = 'Y'``
and that port under ``[options]``, leaving every other key alone, and a refresh
step runs it after the deploy. A host with no ``rustdesk`` block serves nothing
and this changes no file - which is how the macs other than the one that
answers stay clients only.

Direct IP is the whole point: with it the phone connects straight to the host
and RustDesk's public ID and relay servers are never in the path, so nothing
here depends on a service that company runs. The permanent password is NOT
touched. It is stored next to the machine's key pair in ``RustDesk.toml`` as a
derived value plus a salt, the way ``~/.vnc/passwd`` is, and it stays
machine-local and out of every repo.

``--check`` reports whether the file already matches and writes nothing.
"""

# %%
# Imports #

import argparse
import os
import platform
import re
import socket
import sys

from utils.inventory_tools import find_host_record

# %%
# Variables #

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Where RustDesk keeps RustDesk2.toml, per platform. Windows is deliberately
# absent: the boxes that serve a screen there run TightVNC, and nothing has
# asked RustDesk to replace it.
CONFIG_PATHS = {
    "Darwin": "~/Library/Preferences/com.carriez.RustDesk/RustDesk2.toml",
    "Linux": "~/.config/rustdesk/RustDesk2.toml",
}

DEFAULT_PORT = 21118

# %%
# Functions #


def wanted_options(record):
    """``{key: value}`` the host's record asks for under ``[options]``, or {} when it serves nothing."""
    block = (record or {}).get("rustdesk")
    if not isinstance(block, dict):
        return {}
    port = block.get("direct_access_port", DEFAULT_PORT)
    return {"direct-server": "Y", "direct-access-port": str(port)}


def config_path(system=None, environ=None):
    """The RustDesk2.toml path for this platform, or None where RustDesk is not placed by this tool."""
    system = system or platform.system()
    raw = CONFIG_PATHS.get(system)
    if not raw:
        return None
    environ = os.environ if environ is None else environ
    home = environ.get("HOME") or os.path.expanduser("~")
    return raw.replace("~", home, 1)


def _read_option(text, key):
    """The value of ``key`` under ``[options]``, or None when it is not set there."""
    body = text.split("[options]", 1)
    if len(body) != 2:
        return None
    # Stop at the next section header so a key of the same name elsewhere is not read.
    section = re.split(r"^\[", body[1], maxsplit=1, flags=re.MULTILINE)[0]
    found = re.search(rf"^{re.escape(key)}\s*=\s*'([^']*)'", section, flags=re.MULTILINE)
    return found.group(1) if found else None


def apply_options(text, options):
    """``RustDesk2.toml`` text with ``options`` set under ``[options]``, every other key untouched."""
    if "[options]" not in text:
        text = text.rstrip("\n") + "\n\n[options]\n"
    for key, value in options.items():
        current = _read_option(text, key)
        if current == value:
            continue
        if current is None:
            text = text.replace("[options]\n", f"[options]\n{key} = '{value}'\n", 1)
        else:
            text = re.sub(
                rf"^{re.escape(key)}\s*=\s*'[^']*'",
                f"{key} = '{value}'",
                text,
                count=1,
                flags=re.MULTILINE,
            )
    return text


def sync(hostname, root, check=False, system=None, environ=None):
    """Bring this host's RustDesk options in line with its record. Returns an exit code."""
    _, record = find_host_record(hostname, root)
    options = wanted_options(record)
    if not options:
        return 0
    path = config_path(system=system, environ=environ)
    if not path:
        print(f"rustdesk: no config path known for {system or platform.system()}, nothing changed")
        return 0
    if not os.path.exists(path):
        # RustDesk writes this on first run. Nothing to repair until it has.
        print(f"rustdesk: {path} does not exist yet - start RustDesk once, then run this again")
        return 0
    with open(path, "r", encoding="utf-8") as handle:
        before = handle.read()
    after = apply_options(before, options)
    wanted = ", ".join(f"{key}={value}" for key, value in sorted(options.items()))
    if after == before:
        print(f"rustdesk: {wanted} already set in {path}")
        return 0
    if check:
        print(f"rustdesk: {path} would be changed to {wanted}")
        return 0
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(after)
    print(f"rustdesk: set {wanted} in {path}")
    print("rustdesk: restart RustDesk for it to re-read the file")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Set the RustDesk direct IP options this machine's record names.")
    parser.add_argument("--check", action="store_true", help="report whether the file matches, change nothing")
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
