"""
Keep this machine advertising the subnet routes its inventory record names.

Tailscale holds advertised routes only in its own state (``tailscale set``);
there is no config file a deploy could place, and its system policies have no
key for them. So the record declares them:

    "tailscale": {"advertise_routes": ["10.0.0.0/24"]}

on the host in ``<context>_hosts.json``, and this hands them to
``scripts/tailscale_subnet_router.sh``, which changes the prefs only when they
differ (routes advertised, accept-routes off). A refresh step runs it after the
deploy; a server with no refresh loop runs it from its declared crontab
(``python3 .../tailscale_routes.py``, stdlib only), and a host with no checkout
gets the routes rendered into its cron by its own deploy. A host with no
``tailscale`` block is not a router and nothing runs.

``--check`` reports whether the prefs match and writes nothing.
"""

# %%
# Imports #

import argparse
import os
import socket
import subprocess
import sys

from utils.inventory_tools import find_host_record

# %%
# Variables #

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "tailscale_subnet_router.sh"
)

# %%
# Functions #


def advertise_routes(record):
    """The routes the host's record says it advertises, or [] when it is not a router."""
    block = (record or {}).get("tailscale")
    if not isinstance(block, dict):
        return []
    return [str(route) for route in block.get("advertise_routes") or []]


def sync(hostname, root, check=False, run=subprocess.run):
    """Bring this host's advertised routes in line with its inventory record. Returns an exit code."""
    _, record = find_host_record(hostname, root)
    routes = advertise_routes(record)
    if not routes:
        return 0
    argv = ["bash", SCRIPT] + (["--check"] if check else []) + [",".join(routes)]
    result = run(argv)
    if check:
        # Drift is a finding for the check, not a failure of it.
        return 0
    return result.returncode


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Advertise the tailscale subnet routes this machine's record names.")
    parser.add_argument("--check", action="store_true", help="report whether the prefs match, change nothing")
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
