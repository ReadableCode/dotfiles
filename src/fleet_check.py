#!/usr/bin/env python3
"""Ask every machine in the inventories the same read-only question, over ssh.

Hosts and their ssh command lines come from ``src/ssh_aliases.py --format
hosts``, the single implementation of the inventory's ssh rules (jumps, ports,
users), so this never re-derives them.

Read-only by design: the default question is ``gitpullall --check`` and nothing
here can apply anything. A fleet-wide apply from one keypress is not a feature,
and a machine that needs a repair is repaired on that machine.

Stdlib-only, like ``src/ssh_aliases.py``: a bare ``python3`` runs it.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import terminal_style

HELP_PAGE = """# fleet_check

> ask every machine in the inventories the same read-only question, at once, and print one row per host.
> hosts and their ssh lines come from `src/ssh_aliases.py`, so jumps, ports and users stay defined in one place.
> this machine is skipped, and so is anything that is not macos, linux or windows: a phone has no shell for it.
> nothing is ever applied. the exit code is 1 when any host reported drift or could not be answered.

## what happens

1. ask `src/ssh_aliases.py --format hosts` for every ssh-reachable machine in the cloned inventories
   the ssh line per host is whatever its alias uses, jump hosts included
2. run the question on every host at once, 8 at a time
   `BatchMode=yes` so a host that would prompt for a password is reported instead of hanging
3. print one row per host: `ok`, `drift`, `unreachable`, `failed`, or `no command` when the shell has no such command
   each host's full output goes to `~/logs/fleet/<host>-<timestamp>.log`

## examples

- what is behind, stale or undeployed across the fleet:

`fleetcheck`

- ask a different read-only question:

`fleetcheck --command "deployconfigs status --problems"`

- list the hosts it would ask, without asking:

`fleetcheck --list`
"""

DEFAULT_COMMAND = "gitpullall --check"
SHELL_HOSTS = ("macos", "linux", "windows")
NOT_FOUND = ("command not found", "is not recognized as the name")


def short_name(name):
    return name.split(".")[0].lower()


def load_hosts(git_dir, local_hostname=None, run=subprocess.run):
    """Every ssh-reachable machine with a shell, this one excluded."""
    script = os.path.join(git_dir, "dotfiles", "src", "ssh_aliases.py")
    listed = run(
        ["python3", script, "--format", "hosts", "--root", git_dir], capture_output=True, text=True
    )
    if listed.returncode:
        raise RuntimeError("listing hosts via {} failed: {}".format(script, listed.stderr.strip()))
    local = short_name(local_hostname if local_hostname is not None else socket.gethostname())
    hosts = [h for h in json.loads(listed.stdout) if h["os"] in SHELL_HOSTS]
    return sorted((h for h in hosts if short_name(h["host"]) != local), key=lambda h: h["host"].lower())


def remote_command(host_os, command):
    """The question as that host's own shell must receive it."""
    if host_os == "windows":
        return 'powershell -NoLogo -Command "{}"'.format(command)
    # An interactive shell: the commands are functions the rc files define.
    return "$SHELL -ic '{}' 2>&1".format(command)


def ssh_argv(host, command):
    """The host's own ssh line, with batch-mode options, asking the question."""
    words = host["command"].split()
    options = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=8"]
    return words[:1] + words[1:-1] + options + words[-1:] + [remote_command(host["os"], command)]


def classify(returncode, output):
    if returncode == 0:
        return "ok"
    if any(marker in output for marker in NOT_FOUND) or returncode == 127:
        return "no command"
    if returncode == 255:
        return "unreachable"
    if returncode == 1:
        return "drift"
    return "failed"


def log_dir():
    return os.path.join(os.path.expanduser("~"), "logs", "fleet")


def write_log(host_name, text, stamp=None):
    """Each host's full answer, kept so a row that says drift can be read in full."""
    try:
        os.makedirs(log_dir(), exist_ok=True)
        stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
        path = os.path.join(log_dir(), "{}-{}.log".format(host_name.lower(), stamp))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path
    except OSError:
        return ""


def ask(host, command, run=subprocess.run, log=write_log):
    """Ask one host, returning its row."""
    try:
        answered = run(ssh_argv(host, command), capture_output=True, text=True)
        output = (answered.stdout or "") + (answered.stderr or "")
        code = answered.returncode
    except OSError as error:
        output, code = str(error), 255
    lines = [line for line in output.strip().splitlines() if line.strip()]
    last = lines[-1].strip() if lines else ""
    return {
        "host": host["host"],
        "os": host["os"],
        "status": classify(code, output),
        "last": last[:70] + "..." if len(last) > 70 else last,
        "log": log(host["host"], output),
    }


def ask_all(hosts, command, jobs=8, run=subprocess.run, log=write_log):
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        return list(pool.map(lambda host: ask(host, command, run=run, log=log), hosts))


STATUS_ROLE = {"ok": "green", "drift": "amber"}


def render(rows, color):
    """One aligned row per host, coloured by status."""
    if not rows:
        return "no other ssh-reachable hosts in the inventories\n"
    host_width = max(len(row["host"]) for row in rows)
    os_width = max(len(row["os"]) for row in rows)
    out = []
    for row in rows:
        status = terminal_style.paint(row["status"].ljust(11), STATUS_ROLE.get(row["status"], "red"), color, bold=True)
        out.append(
            "  {}  {}  {}  {}".format(
                row["host"].ljust(host_width),
                terminal_style.paint(row["os"].ljust(os_width), "muted", color),
                status,
                terminal_style.paint(row["last"], "muted", color),
            ).rstrip()
        )
    return "\n".join(out) + "\n"


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="fleet_check.py", add_help=False)
    terminal_style.add_help_page(parser, HELP_PAGE)
    parser.add_argument(
        "--command", default=DEFAULT_COMMAND, help="the read-only question to ask (default: %(default)s)"
    )
    parser.add_argument("--list", action="store_true", help="print the hosts it would ask, and stop")
    parser.add_argument("--jobs", type=int, default=8, help="how many hosts to ask at once (default: %(default)s)")
    return parser.parse_args(argv)


def main(argv=None, environ=None):
    args = parse_args(argv)
    environ = os.environ if environ is None else environ
    git_dir = (environ.get("gitDir") or os.path.join(os.path.expanduser("~"), "GitHub")).rstrip("/\\")
    out = sys.stdout
    color = terminal_style.use_color(out, environ)
    try:
        hosts = load_hosts(git_dir)
    except (OSError, RuntimeError, ValueError) as error:
        print("fleet_check: {}".format(error), file=sys.stderr)
        return 1
    if args.list:
        host_width = max((len(h["host"]) for h in hosts), default=0)
        os_width = max((len(h["os"]) for h in hosts), default=0)
        for host in hosts:
            out.write(
                "  {}  {}  {}\n".format(
                    host["host"].ljust(host_width),
                    terminal_style.paint(host["os"].ljust(os_width), "muted", color),
                    terminal_style.paint(host["command"], "muted", color),
                )
            )
        return 0
    if not hosts:
        out.write("no other ssh-reachable hosts in the inventories\n")
        return 0
    out.write(terminal_style.section("asking {} hosts: {}".format(len(hosts), args.command), color) + "\n")
    out.flush()
    rows = ask_all(hosts, args.command, jobs=args.jobs)
    out.write(render(rows, color))
    unhappy = [row for row in rows if row["status"] != "ok"]
    out.write("\n" + terminal_style.section("done", color) + "\n")
    if unhappy:
        text = "   {} of {} hosts need attention: {}".format(
            len(unhappy), len(rows), ", ".join(row["host"] for row in unhappy)
        )
        out.write(terminal_style.paint(text, "amber", color, bold=True) + "\n")
        out.write(terminal_style.paint("   full answers: {}".format(log_dir()), "muted", color) + "\n")
        return 1
    out.write(terminal_style.paint("   all {} hosts ok".format(len(rows)), "green", color, bold=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
