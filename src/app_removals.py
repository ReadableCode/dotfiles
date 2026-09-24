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

On Windows it also looks for the same app installed twice by two routes (see
"Duplicate installs" below) and offers the copy no app list owns, the way
``clone_repos.py`` offers a missing repo: found, not declared.
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

import app_lists
from deploy_configs import REPO_ROOT, host_allowed, member_overlay_dirs
from utils.inventory_tools import overlay_context

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
    """One package manager: how to list, dry-run and uninstall its packages.

    ``installed`` deliberately repeats the ``list_installed`` command each
    installer in ``scripts/`` already uses, so "is it installed" has one answer
    per manager rather than one per direction. Which app lists name its
    packages is ``app_lists.py``'s answer, not this table's.
    """

    name: str
    system: str  # platform.system() where this manager exists
    installed: list  # argv listing every installed package
    remove: list  # argv + package uninstalls it
    simulate: list = field(default_factory=list)  # argv + package dry-runs the removal
    separator: str = ""  # split each installed line on this and keep the first field
    # False where the query failing means "could not tell", not "no such
    # manager here": Windows capabilities always exist, and listing them needs
    # an elevated shell, so a failure is reported instead of reading as absent.
    absent_ok: bool = True


MANAGERS = {
    "brew": Manager(
        name="brew",
        system="Darwin",
        installed=["brew", "list", "--formula"],
        simulate=["brew", "uses", "--installed"],
        remove=["brew", "uninstall"],
    ),
    "cask": Manager(
        name="cask",
        system="Darwin",
        installed=["brew", "list", "--cask"],
        remove=["brew", "uninstall", "--cask"],
    ),
    "apt": Manager(
        name="apt",
        system="Linux",
        installed=["dpkg-query", "-W", "-f=${Package}\n"],
        simulate=["apt-get", "-s", "remove"],
        remove=["sudo", "apt-get", "remove", "-y"],
    ),
    "dnf": Manager(
        name="dnf",
        system="Linux",
        installed=["rpm", "-qa", "--qf", "%{NAME}\n"],
        simulate=["dnf", "remove", "--assumeno"],
        remove=["sudo", "dnf", "remove", "-y"],
    ),
    "flatpak": Manager(
        name="flatpak",
        system="Linux",
        installed=["flatpak", "list", "--app", "--columns=application"],
        remove=["flatpak", "uninstall", "-y"],
    ),
    "choco": Manager(
        name="choco",
        system="Windows",
        installed=["choco", "list", "--limit-output"],
        simulate=["choco", "uninstall", "--noop"],
        remove=["choco", "uninstall", "-y"],
        separator="|",
    ),
    "winget": Manager(
        name="winget",
        system="Windows",
        # winget list is fixed-width columns; --id --exact turns the question
        # into an exit code instead, which needs no column parsing.
        installed=[],
        remove=["winget", "uninstall", "--disable-interactivity", "--exact", "--id"],
    ),
    # Windows optional features (Features on Demand), such as the in-box
    # OpenSSH server. Not a package manager an app list installs through, so
    # no app list names these; they are only ever retired, usually for a
    # package that replaces them (see replaced_by).
    "capability": Manager(
        name="capability",
        system="Windows",
        installed=[
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-WindowsCapability -Online | Where-Object State -eq Installed | ForEach-Object Name",
        ],
        remove=["powershell", "-NoProfile", "-Command", "Remove-WindowsCapability -Online -Name"],
        absent_ok=False,
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
            if entry.get("replaced_by"):
                split_replacement(entry["replaced_by"])
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
# Queries #


def run_capture(argv):
    """
    (exit code, stdout+stderr) for a manager query, or (None, '') when it cannot run.

    Decoded as UTF-8 whatever the console code page: winget writes UTF-8 and
    truncates long columns with an ellipsis, which read as cp1252 turns into
    three characters and shifts every column after it.
    """
    try:
        done = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError:
        return None, ""
    return done.returncode, done.stdout + done.stderr


def installed_packages(manager, run=run_capture):
    """
    Every package this manager reports installed, lowercased for comparison.
    ``None`` means the manager could not answer: for most that is simply not
    being on this machine - a box with no flatpak has no flatpak removals to
    make - and a manager with ``absent_ok`` False gets it reported instead.
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


def wanted_packages(manager, lists_dir=app_lists.APP_LISTS, overlay_paths=None):
    """Every package an app list names for this manager on this machine, which no removal may touch."""
    if manager.name not in app_lists.BASE_LISTS:
        return set()
    return app_lists.wanted_packages(manager.name, lists_dir, overlay_paths)


def split_replacement(value):
    """``manager:package`` from a ``replaced_by`` value, as (manager name, package)."""
    manager, sep, package = str(value).partition(":")
    if not sep or not package:
        raise ValueError(f"replaced_by must be 'manager:package', got '{value}'")
    manager_for(manager)
    return manager, package


def package_present(entry, cache=None, run=run_capture):
    """
    Whether this entry's package is installed right now.

    ``cache`` is a dict the caller reuses to ask each manager once across many
    entries. Pass None to force a fresh query, which is what the removal loop
    does: two entries can name the SAME underlying package (homebrew keeps the
    old name as an alias of a renamed cask, and lists both), so one uninstall
    can take the other entry's package with it. Acting on a set collected
    before the first removal then tries to uninstall something already gone.
    """
    manager = manager_for(entry["manager"])
    if manager.name == "winget":
        return winget_present(entry["package"], run=run)
    if cache is None:
        names = installed_packages(manager, run=run)
    else:
        if manager.name not in cache:
            cache[manager.name] = installed_packages(manager, run=run)
        names = cache[manager.name]
    return None if names is None else entry["package"].lower() in names


@dataclass
class Candidates:
    """What a run found for this machine, one list per outcome."""

    removable: list = field(default_factory=list)  # installed, and nothing protects it
    protected: list = field(default_factory=list)  # an app list still names it; the app list wins
    waiting: list = field(default_factory=list)  # its replaced_by package is not installed yet
    unknown: list = field(default_factory=list)  # the manager could not say whether it is installed


def candidates(entries, system=None, hostname=None, lists_dir=app_lists.APP_LISTS, overlay_paths=None, run=run_capture):
    """
    Sort this machine's entries into ``Candidates``.

    ``protected`` is reported so a contradiction between an app list and a
    removal is visible rather than silent. ``waiting`` holds entries whose
    ``replaced_by`` package is not installed here: retiring the in-box OpenSSH
    server on a box that has nothing else serving ssh would lock the machine
    out, so the removal is offered only where its replacement already runs.
    """
    system = system or platform.system()
    hostname = hostname or get_uppercase_hostname()
    found = Candidates()
    cache: dict = {}
    for entry in entries:
        manager = manager_for(entry["manager"])
        if manager.system != system or not host_allowed(entry, hostname):
            continue
        if entry["package"] in wanted_packages(manager, lists_dir, overlay_paths):
            found.protected.append(entry)
            continue
        present = package_present(entry, cache, run=run)
        if present is None and not manager.absent_ok:
            found.unknown.append(entry)
            continue
        if not present:
            continue
        if entry.get("replaced_by"):
            other_manager, other_package = split_replacement(entry["replaced_by"])
            replacement = {"manager": other_manager, "package": other_package}
            if not package_present(replacement, cache, run=run):
                found.waiting.append(entry)
                continue
        found.removable.append(entry)
    return found


def describe(entry):
    return f"{entry['manager']}:{entry['package']} ({entry['name']})"


# %%
# Duplicate installs (Windows) #
#
# The same app installed twice, by two different routes: Chocolatey's Slack
# (an MSIX package) next to a per-user copy Slack's own installer dropped in
# AppData. Each starts itself at logon and updates itself, and only one of
# them is the copy an app list asked for. `winget list` is the one view that
# sees every route - Add/Remove Programs entries, MSIX packages, per-user
# installs - and it files both copies under the same winget id, so a winget id
# listed twice is the signal.
#
# The copy to keep is the one an app list owns. Chocolatey records the version
# it installed, so a choco app list entry whose name matches the group and
# whose version matches exactly one row owns that row, and every other row is
# offered for removal, like a repo to clone is offered: no committed line per
# copy. When no app list owns a row (a winget id on the winget list, where
# both rows answer to it, or an app on no list at all) the group is reported
# and left alone, because guessing which copy is foreign is how the wrong one
# gets uninstalled.


@dataclass(frozen=True)
class Install:
    """One row of `winget list`."""

    name: str
    id: str
    version: str


@dataclass
class DuplicateGroup:
    """Every row sharing one winget id, and the one an app list owns if any."""

    id: str
    rows: list
    owner: object = None  # the Install an app list owns, or None
    owned_by: str = ""  # "manager:package" of that app list entry
    reason: str = ""  # why nothing is offered
    listed: bool = False  # some app list names this app
    offers: list = field(default_factory=list)  # (Install, argv) per copy offered for removal


def parse_winget_list(output):
    """
    The rows of `winget list`. Its columns are fixed-width, so each row is cut
    at the offsets of the header's column names (the same approach the winget
    installer takes); winget redraws a progress spinner with carriage returns,
    so only the text after the last one on each line counts.
    """
    lines = [line.split("\r")[-1] for line in output.splitlines()]
    header_at = next((i for i, line in enumerate(lines) if re.match(r"^Name\s+Id\s+Version", line)), None)
    if header_at is None:
        return []
    header = lines[header_at]
    id_at = header.index("Id")
    version_at = header.index("Version")
    after_version = [header.find(column) for column in ("Available", "Source") if header.find(column) > version_at]
    version_end = min(after_version) if after_version else None
    rows = []
    for line in lines[header_at + 1 :]:
        if not line.strip() or set(line.strip()) == {"-"} or len(line) <= version_at:
            continue
        rows.append(
            Install(
                name=line[:id_at].strip(),
                id=line[id_at:version_at].strip(),
                version=line[version_at:version_end].strip(),
            )
        )
    return rows


def version_key(version):
    """``4.51.191.0`` and ``4.51.191`` are one version: drop trailing zero parts."""
    parts = version.strip().lower().split(".")
    while len(parts) > 1 and parts[-1] == "0":
        parts.pop()
    return ".".join(parts)


def name_key(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def choco_versions(run=run_capture):
    """``{package: version}`` Chocolatey says it installed, or {} without Chocolatey."""
    code, output = run(["choco", "list", "--limit-output"])
    if code != 0:
        return {}
    versions = {}
    for line in output.splitlines():
        name, sep, version = line.strip().partition("|")
        if sep:
            versions[name.lower()] = version
    return versions


def winget_uninstall(package_id, version):
    """Uninstall one copy by id and version, so winget cannot pick the one to keep."""
    return ["winget", "uninstall", "--disable-interactivity", "--exact", "--id", package_id, "--version", version]


def names_row(package, row):
    """Whether a package name is this row's app: the row's name or any part of its winget id (golang: GoLang.Go)."""
    key = name_key(package)
    return key == name_key(row.name) or key in {name_key(part) for part in row.id.split(".")}


def names_group(package, group):
    return any(names_row(package, row) for row in group.rows)


def choco_row(group, installed_choco):
    """
    The one row Chocolatey installed, as (package, row), or (None, None).

    Matched by name - the choco package name against the row's name or the
    last part of its winget id - and by the version Chocolatey recorded, which
    must pick out exactly one row.
    """
    for package, version in sorted(installed_choco.items()):
        if not names_group(package, group):
            continue
        owned = [row for row in group.rows if version_key(row.version) == version_key(version)]
        if len(owned) == 1:
            return package, owned[0]
    return None, None


def find_owner(group, installed_choco, wanted_choco, wanted_winget):
    """
    Decide what to offer in one group, or say why nothing is.

    Which list owns an app is the list's decision, made once per app for the
    source that offers the newer version; this only follows it. The copy the
    owning manager did not install is the extra, and each extra is removed by
    the manager that put it there, so Chocolatey's own records stay true.
    """
    on_winget_list = group.id.lower() in {package.lower() for package in wanted_winget}
    package, row = choco_row(group, installed_choco)
    choco_listed = package is not None and package in {name.lower() for name in wanted_choco}
    if choco_listed and on_winget_list:
        # Both lists install it, so both copies are the repo's: the lists
        # disagree, and removing either would fight the next installmissing.
        group.listed = True
        group.reason = f"two app lists install it (choco:{package} and winget:{group.id}); drop it from one"
    elif choco_listed:
        group.listed = True
        group.owner, group.owned_by = row, f"choco:{package}"
        group.offers = [(other, winget_uninstall(group.id, other.version)) for other in group.rows if other is not row]
    elif package is not None and on_winget_list:
        # The winget list owns this app; the copy Chocolatey installed is left
        # over from before the app moved lists, and choco removes its own.
        group.listed = True
        rest = [other for other in group.rows if other is not row]
        group.owner = rest[0] if len(rest) == 1 else None
        group.owned_by = f"winget:{group.id}"
        group.offers = [(row, ["choco", "uninstall", package, "-y"])]
    elif on_winget_list:
        group.listed = True
        group.reason = "every copy answers to the winget list's id, so which one winget installed is unknown"
    elif any(names_group(name, group) for name in wanted_choco):
        group.listed = True
        group.reason = "the version Chocolatey recorded matches no copy; myupdater upgrades it first"
    else:
        group.reason = "no app list names this app, so neither copy is the repo's"
    return group


def duplicate_groups(run=run_capture, lists_dir=app_lists.APP_LISTS, overlay_paths=None):
    """Every winget id installed more than once, each with its owner when an app list names one."""
    code, output = run(["winget", "list", "--disable-interactivity", "--accept-source-agreements"])
    if code is None:
        return []
    by_id: dict = {}
    for row in parse_winget_list(output):
        by_id.setdefault(row.id.lower(), []).append(row)
    groups = [DuplicateGroup(id=rows[0].id, rows=rows) for rows in by_id.values() if len(rows) > 1]
    if not groups:
        return []
    installed_choco = choco_versions(run=run)
    wanted_choco = wanted_packages(MANAGERS["choco"], lists_dir, overlay_paths)
    wanted_winget = wanted_packages(MANAGERS["winget"], lists_dir, overlay_paths)
    return [find_owner(group, installed_choco, wanted_choco, wanted_winget) for group in groups]


def report_duplicates(groups, show_all=False):
    """
    Every duplicate an app list is involved in, in full. The rest - runtime
    frameworks Windows installs once per CPU architecture, versions kept side
    by side on purpose - are one summary line unless ``show_all`` asks.
    """
    shown = [group for group in groups if group.listed or show_all]
    hidden = len(groups) - len(shown)
    if shown:
        print(paint("Installed more than once:", "cyan"))
    for group in shown:
        offered = {id(row): argv for row, argv in group.offers}
        print(f"  {group.id}: {len(group.rows)} copies")
        for row in group.rows:
            if row is group.owner:
                print(f"    keep   {row.version}  ({group.owned_by}, from an app list)")
            elif id(row) in offered:
                print(f"    extra  {row.version}  {row.name}  (removed with {offered[id(row)][0]})")
            else:
                print(f"    copy   {row.version}  {row.name}")
        if not group.offers:
            print(paint(f"    left alone: {group.reason}", "yellow" if group.listed else "dim"))
    if hidden:
        print(
            paint(
                f"{hidden} more ids are installed more than once and no app list names them"
                " (runtime frameworks, side-by-side versions); left alone, --all lists them",
                "dim",
            )
        )


def remove_duplicate(argv, run=subprocess.run):
    try:
        return run(argv).returncode == 0
    except OSError:
        return False


def offer_duplicates(groups, assume_yes):
    """Ask per extra copy and uninstall the agreed ones. Returns the number that failed."""
    failures = 0
    for group in groups:
        for row, argv in group.offers:
            print()
            if argv[0] == "winget":
                print(paint("  winget has no dry run; this uninstalls that one copy", "dim"))
            question = f"Uninstall the extra {group.id} {row.version} with {argv[0]} (keeping {group.owned_by})?"
            answer = "y" if assume_yes else prompt_yes_no_quit(question)
            if answer == "q":
                print(paint("Stopping; remaining copies left installed.", "dim"))
                return failures
            if answer == "n":
                print(paint(f"  kept {group.id} {row.version}", "dim"))
                continue
            if remove_duplicate(argv):
                print(paint(f"  removed {group.id} {row.version}", "green"))
            else:
                failures += 1
                print(paint(f"  FAILED to remove {group.id} {row.version} (see output above)", "red"))
    return failures


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


def report(found):
    """Print what this machine has to act on, and what it was told to leave alone."""
    for entry in found.protected:
        print(paint(f"skipping {describe(entry)}: an app list still names it, so the app list wins", "yellow"))
    for entry in found.waiting:
        other = entry["replaced_by"]
        print(paint(f"keeping {describe(entry)}: its replacement {other} is not installed here", "dim"))
    for entry in found.unknown:
        manager = manager_for(entry["manager"])
        print(paint(f"could not ask {manager.name} whether {entry['package']} is installed (elevated shell?)", "red"))
    if not found.removable:
        print(paint("No listed apps to remove are installed on this machine.", "green"))
        return
    print(paint("Installed here but listed for removal:", "cyan"))
    for entry in found.removable:
        note = entry.get("note")
        print(f"  {describe(entry)}")
        if note:
            print(paint(f"    {' '.join(str(note).split())}", "dim"))


def offer_removals(removable, assume_yes):
    """Ask per entry and uninstall the agreed ones. Returns (failures, quit)."""
    failures = 0
    for entry in removable:
        print()
        # Re-ask, because an earlier answer in this same loop may already have
        # taken this package: `vnc-viewer` was homebrew's alias for the renamed
        # `realvnc-connect-viewer`, listed separately but one cask, so removing
        # either emptied both. Uninstalling what is already gone is an error the
        # person then has to read and dismiss.
        if not package_present(entry):
            print(paint(f"  {entry['package']} is already gone (an earlier removal took it)", "dim"))
            continue
        show_simulation(entry)
        answer = "y" if assume_yes else prompt_yes_no_quit(f"Uninstall {describe(entry)}?")
        if answer == "q":
            print(paint("Stopping; remaining apps left installed.", "dim"))
            return failures, True
        if answer == "n":
            print(paint(f"  kept {entry['package']}", "dim"))
            continue
        if remove_package(entry):
            print(paint(f"  removed {entry['package']}", "green"))
        else:
            failures += 1
            print(paint(f"  FAILED to remove {entry['package']} (see output above)", "red"))
    return failures, False


def run(
    list_only=False, assume_yes=False, entries=None, system=None, hostname=None, run_query=run_capture, show_all=False
):
    system = system or platform.system()
    entries = load_app_removals() if entries is None else entries
    if entries:
        found = candidates(entries, system=system, hostname=hostname, run=run_query)
        report(found)
    else:
        found = Candidates()
        print(paint("No app removals declared; nothing to check.", "dim"))
    groups = duplicate_groups(run=run_query) if system == "Windows" else []
    report_duplicates(groups, show_all)
    offers = [group for group in groups if group.offers]
    problems = len(found.unknown)
    if list_only or not (found.removable or offers):
        return 1 if problems else 0
    if not assume_yes and not sys.stdin.isatty():
        print(paint("stdin is not a terminal; removing nothing (run src/app_removals.py directly).", "yellow"))
        return 1 if problems else 0
    failures, stopped = offer_removals(found.removable, assume_yes)
    if not stopped:
        failures += offer_duplicates(offers, assume_yes)
    return 1 if failures or problems else 0


# %%
# Main #


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Offer to uninstall the packages an app removals file says must not be on this machine, "
            "and on Windows the extra copies of apps an app list installs."
        )
    )
    parser.add_argument("--list", action="store_true", help="only report, never prompt or uninstall")
    parser.add_argument("--yes", action="store_true", help="uninstall everything offered without prompting")
    parser.add_argument("--all", action="store_true", help="also list duplicate installs no app list names (Windows)")
    args = parser.parse_args()
    return run(list_only=args.list, assume_yes=args.yes, show_all=args.all)


if __name__ == "__main__":
    sys.exit(main())

# %%
