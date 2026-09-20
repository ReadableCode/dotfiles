#!/usr/bin/env python3
"""Cross-shell ssh/vnc alias generator for the *_credentials host inventories.

One implementation of the alias logic for every shell. It reads each sibling
``*_credentials`` repo's host inventory and prints ready-to-eval alias
definitions in the caller's syntax:

    python3 ~/GitHub/dotfiles/src/ssh_aliases.py --format bash --root ~/GitHub
    python3 ~/GitHub/dotfiles/src/ssh_aliases.py --format powershell --root ~/GitHub

``application_configs/bash/.shared_aliases`` evals the bash output and
``application_configs/powershell/powershell_aliases.ps1`` invokes the
PowerShell output, so jump-host resolution, port handling, user selection and
vnc aliases exist ONCE instead of in two hand-synced twins. ``--format json``
prints the same alias set as data, for debugging and tests.

Stdlib-only on purpose (like ``src/ticket_pr.py``): it runs at shell startup
with a bare ``python3``, before any venv exists.

A host record may carry ``"jump": "<name-or-alias>"`` naming another host in
the SAME inventory that can reach it - the pattern for a machine only routable
from inside a VPN a different box holds. The hop is baked into the alias as
``ssh -J user@jump:port``, so the chain lives in the inventory and NOT in any
machine's ~/.ssh/config: nothing outside this repo constellation needs editing,
and every machine that clones the credentials repo gets it. This mirrors what
``build_ssh_argv`` in the sibling status_board repo does for its ssh_command
panels. Raw-IP tools that never see aliases (rsync shelling out to ssh) get the
same hop from the deployed ~/.ssh/config.d fragments instead - see
docs/repo_client_credentials.md.

The hop is dropped when the alias is built ON the jump machine itself - there
it is already inside the VPN and the target is direct. Needs non-interactive
key auth to both hops and AllowTcpForwarding on the jump's sshd (the default,
and true of Windows OpenSSH Server).

vnc aliases are DERIVED from the ssh ones rather than declared: every
``ssh<stem>`` alias on a host that can run a screen server gets a matching
``vnc<stem>``, so ``sshryzenwhite`` implies ``vncryzenwhite`` and nothing has to
be listed twice. A host may tune the target with ``vnc_hostname`` (when the
screen server answers on a different address from ssh, e.g. a Tailscale name)
and ``vnc_port`` (when it is not on 5900, as with a headless Xtigervnc on :1).

Every platform gets these, and they all launch TigerVNC's ``vncviewer``. They
used to be macOS-only and run ``open vnc://``, which hands the connection to
Screen Sharing - and Screen Sharing cannot talk to the fleet any more. wayvnc,
which every Pi now runs, offers only VeNCrypt, RSA-AES and RA2; Screen Sharing
speaks only VNC Auth and Apple ARD, so it fails at negotiation before it ever
asks for a password (proven against pi4a, 2026-09-20). TigerVNC speaks all of
them, so one viewer covers wayvnc on the Pis, TightVNC on the Windows boxes and
Screen Sharing on the Macs.

Anything wrong with an inventory - a file that will not parse, an alias name
that is not a bare word - raises and exits non-zero, so the shells define
NOTHING and say why. There is no partial-success mode on purpose: these are
tracked files, and a machine quietly missing some of its aliases is how a
broken inventory survives unnoticed for months.
"""

import argparse
import json
import os
import re
import socket
import sys

from utils.inventory_tools import find_inventory_paths

# Alias names are eval'd by the calling shell, so only accept ones that are a
# bare word in both bash and PowerShell. Anything else is a HARD failure (see
# the module docstring): the generator raises, exits non-zero, and every shell
# that asked gets no ssh aliases at all until the inventory is fixed. Note the
# blast radius - a bad name in a client's inventory costs that machine its
# personal aliases too, which is what forces the fix.
ALIAS_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------- inventory


def host_names(host):
    """Every name a host answers to: its ``name`` plus its ``aliases``."""
    return [name for name in [host.get("name", "")] + list(host.get("aliases") or []) if name]


def short_name(name):
    """Lowercase pre-dot form of a hostname, the form machines are compared by."""
    return str(name).split(".")[0].lower()


# ssh aliases are named ``ssh<stem>``; the vnc alias for the same box is the same
# stem behind ``vnc``. Deriving instead of declaring is why no host carries a
# vnc alias list: the two can no longer disagree, and a new machine gets its vnc
# alias the moment it gets an ssh one.
SSH_ALIAS_PREFIX = "ssh"
VNC_ALIAS_PREFIX = "vnc"

# Only these can run a screen server. Everything else in the inventories - an
# android tablet, a network switch, a games console - would get an alias that
# could never connect.
VNC_CAPABLE_OS = ("macos", "windows", "linux")

# The port a vnc target means when it carries none.
DEFAULT_VNC_PORT = 5900

# How to launch TigerVNC's viewer per platform token. macOS needs the full path
# because the cask installs an .app rather than something on PATH; the choco and
# apt packages both put ``vncviewer`` on PATH.
VNC_VIEWERS = {
    "darwin": "/Applications/TigerVNC.app/Contents/MacOS/vncviewer",
    "linux": "vncviewer",
    "windows": "vncviewer",
}


def viewer_for_platform(platform_token):
    """The vncviewer command for a platform token, defaulting to a bare ``vncviewer``."""
    token = str(platform_token or "").lower()
    if token.startswith("darwin") or token == "mac":
        return VNC_VIEWERS["darwin"]
    if token.startswith("win"):
        return VNC_VIEWERS["windows"]
    return VNC_VIEWERS["linux"]


def host_user(host):
    """The ssh user for a host: ``ssh_user`` wins over the generic ``user``."""
    return host.get("ssh_user") or host.get("user") or ""


def host_target(host):
    """The address to connect to: explicit ``hostname``, else the host's name."""
    return host.get("hostname") or host.get("name", "")


def find_host(hosts, token):
    """The host in this inventory answering to ``token``, or None."""
    wanted = str(token).strip().lower()
    for host in hosts:
        if any(name.lower() == wanted for name in host_names(host)):
            return host
    return None


def jump_spec(host, hosts, local_short):
    """``-J`` destination for a host's ``jump`` hop, or "" when there is none to make."""
    token = host.get("jump")
    if not token:
        return ""
    # Resolved within THIS inventory only: a context's hosts live together in
    # one file, and each file is read on its own.
    jump = find_host(hosts, token)
    if jump is None:
        return ""
    # Already on the jump machine: it holds the VPN, so the target is direct.
    if local_short and local_short in [short_name(name) for name in host_names(jump)]:
        return ""
    user = host_user(jump)
    target = host_target(jump)
    spec = "{}@{}".format(user, target) if user else str(target)
    return "{}:{}".format(spec, jump["port"]) if jump.get("port") else spec


def ssh_command(host, hosts, local_short):
    """The full ``ssh ...`` command line an alias for this host should run."""
    parts = ["ssh"]
    spec = jump_spec(host, hosts, local_short)
    if spec:
        parts += ["-J", spec]
    if host.get("port"):
        parts += ["-p", str(host["port"])]
    parts.append("{}@{}".format(host_user(host), host_target(host)))
    return " ".join(parts)


def load_hosts(inventory_path):
    """
    The ``hosts`` list of one hosts.json-style inventory.

    An unreadable or malformed file raises, same as a malformed alias name: a
    tracked inventory that no longer parses is a bug to fix now, not something
    to work around by silently handing the shell a shorter alias list.
    """
    try:
        with open(inventory_path, "r", encoding="utf-8") as file_handle:
            inventory = json.load(file_handle)
    except (OSError, ValueError) as error:
        raise ValueError("{}: unreadable host inventory: {}".format(inventory_path, error)) from error
    if not isinstance(inventory, dict):
        raise ValueError("{}: host inventory must be an object with a 'hosts' list".format(inventory_path))
    return inventory.get("hosts", [])


def checked_alias_name(name, inventory_path):
    """The alias name, or ValueError if the shells could not safely eval it."""
    if not ALIAS_NAME_PATTERN.match(str(name)):
        raise ValueError(
            "{}: alias name {!r} is not a bare word (expected {}). These definitions are eval'd by "
            "the shell, so fix the inventory - until then this machine gets no ssh aliases at "
            "all.".format(inventory_path, name, ALIAS_NAME_PATTERN.pattern)
        )
    return str(name)


def vnc_alias_for(ssh_alias):
    """``sshenvy`` -> ``vncenvy``; None for an alias not named after the ssh convention."""
    name = str(ssh_alias)
    if not name.startswith(SSH_ALIAS_PREFIX) or len(name) == len(SSH_ALIAS_PREFIX):
        return None
    return VNC_ALIAS_PREFIX + name[len(SSH_ALIAS_PREFIX) :]


def vnc_command(host, platform_token):
    """
    The vncviewer command line for a host, or None if it cannot serve a screen.

    The port is always explicit as ``host::port``. TigerVNC reads a single colon
    as a DISPLAY NUMBER, so ``host:5900`` would mean display 5900 rather than the
    port, which is why the doubled form is not optional. No user is passed: the
    viewer prompts, and wayvnc's PAM auth wants the box's own login.
    """
    if str(host.get("os", "")).lower() not in VNC_CAPABLE_OS:
        return None
    target = host.get("vnc_hostname") or host_target(host)
    if not target:
        return None
    port = int(host.get("vnc_port") or DEFAULT_VNC_PORT)
    return "{} {}::{}".format(viewer_for_platform(platform_token), target, port)


def inventory_aliases(inventory_path, local_short, platform_token):
    """
    Alias definitions from one hosts.json-style inventory, as
    ``[(name, command), ...]`` in inventory order.
    """
    hosts = load_hosts(inventory_path)
    definitions = []
    for host in hosts:
        screen = vnc_command(host, platform_token)
        for alias in host.get("aliases") or []:
            name = checked_alias_name(alias, inventory_path)
            # A host with no user cannot make an ssh alias; its vnc alias still can.
            if host_user(host):
                definitions.append((name, ssh_command(host, hosts, local_short)))
            vnc_name = vnc_alias_for(name)
            if screen and vnc_name:
                definitions.append((checked_alias_name(vnc_name, inventory_path), screen))
    return definitions


def collect_aliases(root, local_short, platform_token):
    """
    Every alias definition contributed by every ``*_credentials`` inventory
    under ``root``. Later definitions win on a name collision, matching what a
    shell does when the same alias is defined twice.
    """
    definitions = []
    for inventory_path in find_inventory_paths(root):
        definitions += inventory_aliases(inventory_path, local_short, platform_token)

    deduped = {}
    for name, command in definitions:
        deduped[name] = command
    return sorted(deduped.items())


# ---------------------------------------------------------------- hosts (for checks over ssh)


def collect_hosts(root, local_short):
    """
    One record per ssh-reachable host across every inventory under ``root``:
    ``{"host", "os", "command"}`` with the same ``ssh ...`` line its aliases
    get, for running one check on every host over ssh, so the inventory's ssh
    rules (jumps, ports, users) stay implemented here alone. Later
    inventories win a name collision, like aliases do.
    """
    records = {}
    for inventory_path in find_inventory_paths(root):
        hosts = load_hosts(inventory_path)
        for host in hosts:
            name = host.get("name", "")
            if not name or not host_user(host):
                continue
            records[short_name(name)] = {
                "host": name,
                "os": host.get("os", ""),
                "command": ssh_command(host, hosts, local_short),
            }
    return [records[key] for key in sorted(records)]


# ---------------------------------------------------------------- rendering


def render_bash(definitions):
    lines = []
    for name, command in definitions:
        lines.append("alias {}='{}'".format(name, command.replace("'", "'\\''")))
    return "\n".join(lines)


def render_powershell(definitions):
    lines = []
    for name, command in definitions:
        # Functions, not Set-Alias: a PowerShell alias is a bare command name
        # and cannot carry arguments. Explicitly global so the definitions
        # survive being made inside the profile's own scope.
        body = command.replace("'", "''")
        lines.append(
            "Set-Item -Path 'function:global:{}' -Value ([scriptblock]::Create('{}')) -Force".format(name, body)
        )
    return "\n".join(lines)


def render_json(definitions):
    return json.dumps([{"alias": name, "command": command} for name, command in definitions], indent=2)


RENDERERS = {"bash": render_bash, "powershell": render_powershell, "json": render_json}
HOSTS_FORMAT = "hosts"  # json, one record per host rather than per alias


# ---------------------------------------------------------------- entrypoint


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--format", choices=sorted(RENDERERS) + [HOSTS_FORMAT], required=True, help="output syntax")
    parser.add_argument(
        "--root",
        default=DEFAULT_ROOT,
        help="directory holding the sibling repos (defaults to this checkout's parent)",
    )
    parser.add_argument(
        "--local-hostname",
        default=None,
        help="this machine's name, used to drop a jump hop when run ON the jump host",
    )
    parser.add_argument(
        "--platform",
        default=sys.platform,
        help="platform token picking the vncviewer path for vnc aliases (defaults to sys.platform)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    local_short = short_name(args.local_hostname if args.local_hostname is not None else socket.gethostname())
    if args.format == HOSTS_FORMAT:
        print(json.dumps(collect_hosts(args.root, local_short), indent=2))
        return 0
    definitions = collect_aliases(args.root, local_short, args.platform)
    rendered = RENDERERS[args.format](definitions)
    if rendered:
        print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
