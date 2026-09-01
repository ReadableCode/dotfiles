#!/usr/bin/env python3
"""Per-host updater policy lookup over the *_credentials host inventories.

``scripts/my_updater.sh`` asks this script what THIS machine's inventory entry
says about updates - its distro release ceiling, its upgrade cadence, and the
check scripts mapped to it - instead of parsing anything in bash:

    python3 ~/GitHub/dotfiles/src/updater_policy.py release_ceiling.ubuntu
    python3 ~/GitHub/dotfiles/src/updater_policy.py post_update_check
    python3 ~/GitHub/dotfiles/src/updater_policy.py --where

The key is a dotted path inside the host's ``updater`` block in its inventory
(``<context>_hosts.json``, legacy ``hosts.json``), e.g.:

    {
      "name": "Workstation-1",
      "updater": {
        "release_ceiling": {"ubuntu": "26.04"},
        "ubuntu_prompt": "normal",
        "post_update_check": ["some-work-repo/scripts/check_client_health.sh"],
        "release_preflight": ["some-work-repo/scripts/check_client_health.sh"]
      }
    }

Scalars print as-is, lists print comma-joined (the shell side splits on
commas), and a missing host, block, or key prints nothing and exits 0 - an
unlisted machine is simply not governed. ``--where`` prints the inventory
files consulted, one per line, for the updater's "add it here" messages.

The block lives on the HOST entry only, deliberately: no group-level or
context-level defaults, because "every machine in this group may run release
X" vouches for machines nobody has checked. Each ceiling is a line someone
wrote for that one host.

Stdlib-only on purpose (like ``src/ssh_aliases.py``): the updater runs it with
a bare ``python3``, before any venv exists. A host is matched by its ``name``
or ``aliases`` against this machine's short hostname, case-insensitively -
the same comparison ``ssh_aliases.py`` uses. An inventory that will not parse
raises and exits non-zero, so the updater says why and treats the policy as
unknown (which means: don't move).
"""

import argparse
import json
import os
import socket
import sys

from utils.inventory_tools import find_inventory_paths

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def short_name(name):
    """Lowercase pre-dot form of a hostname, the form machines are compared by."""
    return str(name).split(".")[0].lower()


def host_names(host):
    """Every name a host answers to: its ``name`` plus its ``aliases``."""
    return [name for name in [host.get("name", "")] + list(host.get("aliases") or []) if name]


def load_hosts(inventory_path):
    with open(inventory_path, "r", encoding="utf-8") as handle:
        return json.load(handle).get("hosts", [])


def find_host_entry(root, local_short):
    """This machine's host record from the first inventory that names it, or None."""
    for path in find_inventory_paths(root):
        for host in load_hosts(path):
            if any(short_name(name) == local_short for name in host_names(host)):
                return host
    return None


def resolve(host, dotted_key):
    """The value at ``dotted_key`` inside the host's ``updater`` block, or None."""
    value = host.get("updater")
    for part in dotted_key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def render(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("key", nargs="?", help="dotted path inside the host's updater block")
    parser.add_argument(
        "--root",
        default=DEFAULT_ROOT,
        help="directory holding the sibling repos (defaults to this checkout's parent)",
    )
    parser.add_argument(
        "--local-hostname",
        default=None,
        help="this machine's name (defaults to the system hostname)",
    )
    parser.add_argument(
        "--where",
        action="store_true",
        help="print the inventory files consulted instead of a value",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.where:
        for path in find_inventory_paths(args.root):
            print(path)
        return 0
    if not args.key:
        print("a key is required unless --where is given", file=sys.stderr)
        return 2
    local_short = short_name(args.local_hostname if args.local_hostname is not None else socket.gethostname())
    host = find_host_entry(args.root, local_short)
    if host is None:
        return 0
    rendered = render(resolve(host, args.key))
    if rendered:
        print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
