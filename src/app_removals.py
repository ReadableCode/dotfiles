#!/usr/bin/env python3
"""
Uninstall the packages a removals file says must not be on this machine.

The app-list twin of ``deploy_configs.py prune``. The ``app_lists/`` files name
what should be installed; they are not an inventory of everything that may
legitimately exist, so "not in the Brewfile" can never mean "uninstall it" -
most of ``brew list`` is dependencies nobody named, and whole platforms keep
their manual installs in ``linux_apps_non_apt.md`` / ``mac_apps_non_brew.md``.
Retiring an app is therefore an explicit, committed line, exactly like retiring
a config path.

Why a committed list and not per-machine state, same reasoning as
``deploy_removals.yaml``: the machine that drops a package from an app list is
almost never the only machine that installed it, so the list travels with the
repo and every other machine offers the same removal on its next run.

A package some app list still names is never a candidate, so re-adding it to an
app list beats a stale line here instead of the two fighting each other.

Nothing is ever uninstalled without being agreed to one package at a time: the
manager's own dry run is printed first, because unlike a pruned symlink (which
the next deploy recreates) an uninstall can take dependents with it. A run with
no terminal reports and removes nothing.
"""

# %%
# Imports #

import argparse
import os
import platform
import re
import subprocess
import sys
from dataclasses import dataclass, field

import yaml
from readable_utils.host_tools import get_uppercase_hostname

from deploy_configs import REPO_ROOT, host_allowed, member_overlay_dirs
from utils.inventory_tools import overlay_context

APP_LISTS = os.path.join(REPO_ROOT, "app_lists")

# %%
# Output formatting #

_COLOR_CODES = {
    "green": "32",
    "red": "31",
    "yellow": "33",
    "cyan": "36",
    "dim": "2",
}


def use_color():
    """Color when writing to a real terminal and NO_COLOR is not set."""
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def paint(text, color):
    if not use_color() or color not in _COLOR_CODES:
        return text
    return f"\033[{_COLOR_CODES[color]}m{text}\033[0m"


# %%
# Managers #


@dataclass(frozen=True)
class Manager:
    """One package manager: how to list, dry-run and uninstall, and which app lists name its packages.

    ``installed`` deliberately repeats the ``list_installed`` command each
    installer in ``scripts/`` already uses, so "is it installed" has one answer
    per manager rather than one per direction.
    """

    name: str
    system: str  # platform.system() where this manager exists
    installed: list  # argv listing every installed package
    remove: list  # argv + package uninstalls it
    lists: tuple = ()  # app_lists files naming packages for this manager
    simulate: list = field(default_factory=list)  # argv + package dry-runs the removal
    separator: str = ""  # split each installed line on this and keep the first field


MANAGERS = {
    "brew": Manager(
        name="brew",
        system="Darwin",
        installed=["brew", "list", "--formula"],
        simulate=["brew", "uses", "--installed"],
        remove=["brew", "uninstall"],
        lists=("Brewfile",),
    ),
    "cask": Manager(
        name="cask",
        system="Darwin",
        installed=["brew", "list", "--cask"],
        remove=["brew", "uninstall", "--cask"],
        lists=("Brewfile",),
    ),
    "apt": Manager(
        name="apt",
        system="Linux",
        installed=["dpkg-query", "-W", "-f=${Package}\n"],
        simulate=["apt-get", "-s", "remove"],
        remove=["sudo", "apt-get", "remove", "-y"],
        lists=("linux_apps.txt", "linux_apps_wsl.txt"),
    ),
    "dnf": Manager(
        name="dnf",
        system="Linux",
        installed=["rpm", "-qa", "--qf", "%{NAME}\n"],
        simulate=["dnf", "remove", "--assumeno"],
        remove=["sudo", "dnf", "remove", "-y"],
        lists=("linux_apps_dnf.txt",),
    ),
    "flatpak": Manager(
        name="flatpak",
        system="Linux",
        installed=["flatpak", "list", "--app", "--columns=application"],
        remove=["flatpak", "uninstall", "-y"],
        lists=("linux_apps_flatpak.txt",),
    ),
    "choco": Manager(
        name="choco",
        system="Windows",
        installed=["choco", "list", "--limit-output"],
        simulate=["choco", "uninstall", "--noop"],
        remove=["choco", "uninstall", "-y"],
        lists=(
            "windows_apps_personal_choco.txt",
            "windows_apps_base_choco.txt",
            "windows_apps_aws_choco.txt",
        ),
        separator="|",
    ),
    "winget": Manager(
        name="winget",
        system="Windows",
        # winget list is fixed-width columns; --id --exact turns the question
        # into an exit code instead, which needs no column parsing.
        installed=[],
        remove=["winget", "uninstall", "--disable-interactivity", "--exact", "--id"],
        lists=("windows_apps_personal_winget.txt",),
    ),
}


def manager_for(name):
    if name not in MANAGERS:
        raise ValueError(f"Unknown manager '{name}'; expected one of {', '.join(sorted(MANAGERS))}")
    return MANAGERS[name]


# %%
# Config discovery #


def discover_app_removals():
    """
    Every app removals file: an optional ``app_removals.yaml`` in dotfiles plus,
    for each overlay repo this machine is a member of, an optional
    ``<context>_app_removals.yaml``. Same discovery and same membership gate as
    ``deploy_configs.discover_removals``, so a credentials repo a box holds only
    as its git hub contributes nothing.
    """
    files = []
    base = os.path.join(REPO_ROOT, "app_removals.yaml")
    if os.path.exists(base):
        files.append(base)
    for overlay_dir in member_overlay_dirs()[0]:
        overlay = os.path.join(overlay_dir, f"{overlay_context(overlay_dir)}_app_removals.yaml")
        if os.path.exists(overlay):
            files.append(overlay)
    return files


def load_app_removals(paths=None):
    """Parse every discovered file into validated entries, rejecting duplicate names."""
    entries = []
    seen: dict = {}
    for path in discover_app_removals() if paths is None else paths:
        with open(path, "r", encoding="utf-8") as handle:
            parsed = yaml.safe_load(handle) or []
        if not isinstance(parsed, list):
            raise ValueError(f"App removals file {path} must be a YAML list of entries")
        for entry in parsed:
            if not isinstance(entry, dict):
                raise ValueError(f"App removal entry must be a mapping: {entry}")
            for key in ("name", "manager", "package"):
                if key not in entry:
                    raise ValueError(f"App removal entry in {path} is missing '{key}': {entry}")
            manager_for(entry["manager"])
            if entry["name"] in seen:
                raise ValueError(
                    f"Duplicate app removal entry name '{entry['name']}' in {path} "
                    f"(already defined in {seen[entry['name']]})"
                )
            seen[entry["name"]] = path
            entry["_file"] = path
            entries.append(entry)
    return entries


# %%
# App lists #

_BREWFILE_LINE = re.compile(r'^\s*(brew|cask)\s+"([^"]+)"')


def read_app_list(path):
    """
    The package names one app list holds. Strips CRs, blank lines, whole-line
    comments and trailing ``# ...`` comments - the same shape
    ``scripts/app_install_lib.sh`` reads, so a name commented out for one run is
    read the same way by both.
    """
    names = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.replace("\r", "").split("#", 1)[0].strip()
            if line:
                names.append(line)
    return names


def read_brewfile(path, kind):
    """The formula ('brew') or cask ('cask') names a Brewfile declares."""
    names = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            match = _BREWFILE_LINE.match(line)
            if match and match.group(1) == kind:
                names.append(match.group(2))
    return names


def wanted_packages(manager, app_lists=APP_LISTS):
    """Every package this manager's app lists still name, which no removal may touch."""
    names = set()
    for filename in manager.lists:
        path = os.path.join(app_lists, filename)
        if not os.path.exists(path):
            continue
        if filename == "Brewfile":
            names.update(read_brewfile(path, manager.name))
        else:
            names.update(read_app_list(path))
    return names


# %%
# Queries #


def run_capture(argv):
    """(exit code, stdout+stderr) for a manager query, or (None, '') when it cannot run."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True, errors="replace")
    except OSError:
        return None, ""
    return done.returncode, done.stdout + done.stderr


def installed_packages(manager, run=run_capture):
    """
    Every package this manager reports installed, lowercased for comparison.
    ``None`` means the manager is not on this machine, which is not a failure -
    a box with no flatpak simply has no flatpak removals to make.
    """
    if not manager.installed:
        return None
    code, output = run(manager.installed)
    if code is None or code != 0:
        return None
    names = set()
    for line in output.splitlines():
        name = (line.split(manager.separator)[0] if manager.separator else line).strip()
        if name:
            names.add(name.lower())
    return names


def winget_present(package, run=run_capture):
    """Whether winget reports this exact id installed. Its list output is column-formatted, so ask per id."""
    code, _ = run(["winget", "list", "--disable-interactivity", "--exact", "--id", package])
    return None if code is None else code == 0


# %%
# Candidates #


def candidates(entries, system=None, hostname=None, app_lists=APP_LISTS, run=run_capture):
    """
    (removable, protected) for this machine.

    ``removable`` is the entries whose package this machine actually has;
    ``protected`` is the entries an app list still names, reported so a
    contradiction between the two files is visible rather than silent.
    """
    system = system or platform.system()
    hostname = hostname or get_uppercase_hostname()
    removable, protected = [], []
    cache: dict = {}
    for entry in entries:
        manager = manager_for(entry["manager"])
        if manager.system != system or not host_allowed(entry, hostname):
            continue
        if entry["package"] in wanted_packages(manager, app_lists):
            protected.append(entry)
            continue
        if manager.name == "winget":
            present = winget_present(entry["package"], run=run)
        else:
            if manager.name not in cache:
                cache[manager.name] = installed_packages(manager, run=run)
            names = cache[manager.name]
            present = None if names is None else entry["package"].lower() in names
        if present:
            removable.append(entry)
    return removable, protected


def describe(entry):
    return f"{entry['manager']}:{entry['package']} ({entry['name']})"


# %%
# Removal #


def prompt_yes_no_quit(question):
    """Return 'y', 'n' or 'q'. EOF or a plain Enter means no."""
    try:
        answer = input(f"{question} [y/N/q] ").strip().lower()
    except EOFError:
        return "q"
    if answer in ("y", "yes"):
        return "y"
    if answer in ("q", "quit"):
        return "q"
    return "n"


def show_simulation(entry, run=run_capture):
    """
    Print the manager's own dry run of this removal, so the answer covers what
    actually goes rather than the one package named. A manager with no dry run
    (cask, flatpak, winget) says so instead of implying the blast radius is one.
    """
    manager = manager_for(entry["manager"])
    if not manager.simulate:
        print(paint(f"  {manager.name} has no dry run; this uninstalls {entry['package']}", "dim"))
        return
    code, output = run(manager.simulate + [entry["package"]])
    if code is None:
        print(paint(f"  could not dry-run {manager.name}", "yellow"))
        return
    body = output.strip()
    print(paint(f"  {' '.join(manager.simulate)} {entry['package']}:", "dim"))
    for line in body.splitlines() or ["(no output)"]:
        print(f"    {line}")


def remove_package(entry, run=subprocess.run):
    """Uninstall one package with the real terminal, so a sudo or choco prompt reaches the person."""
    manager = manager_for(entry["manager"])
    try:
        return run(manager.remove + [entry["package"]]).returncode == 0
    except OSError:
        return False


# %%
# Run #


def run(list_only=False, assume_yes=False, entries=None, system=None, hostname=None):
    entries = load_app_removals() if entries is None else entries
    if not entries:
        print(paint("No app removals declared; nothing to check.", "dim"))
        return 0

    removable, protected = candidates(entries, system=system, hostname=hostname)
    for entry in protected:
        print(
            paint(
                f"skipping {describe(entry)}: an app list still names it, so the app list wins",
                "yellow",
            )
        )
    if not removable:
        print(paint("No listed apps to remove are installed on this machine.", "green"))
        return 0

    print(paint("Installed here but listed for removal:", "cyan"))
    for entry in removable:
        note = entry.get("note")
        print(f"  {describe(entry)}")
        if note:
            print(paint(f"    {' '.join(str(note).split())}", "dim"))
    if list_only:
        return 0
    if not assume_yes and not sys.stdin.isatty():
        print(paint("stdin is not a terminal; removing nothing (run src/app_removals.py directly).", "yellow"))
        return 0

    failures = 0
    for entry in removable:
        print()
        show_simulation(entry)
        answer = "y" if assume_yes else prompt_yes_no_quit(f"Uninstall {describe(entry)}?")
        if answer == "q":
            print(paint("Stopping; remaining apps left installed.", "dim"))
            break
        if answer == "n":
            print(paint(f"  kept {entry['package']}", "dim"))
            continue
        if remove_package(entry):
            print(paint(f"  removed {entry['package']}", "green"))
        else:
            failures += 1
            print(paint(f"  FAILED to remove {entry['package']} (see output above)", "red"))
    return 1 if failures else 0


# %%
# Main #


def main():
    parser = argparse.ArgumentParser(
        description="Offer to uninstall the packages an app removals file says must not be on this machine."
    )
    parser.add_argument("--list", action="store_true", help="only report which listed apps are installed")
    parser.add_argument("--yes", action="store_true", help="uninstall every listed app without prompting")
    args = parser.parse_args()
    return run(list_only=args.list, assume_yes=args.yes)


if __name__ == "__main__":
    sys.exit(main())

# %%
