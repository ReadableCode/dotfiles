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
``clone_repos.py`` offers a missing repo: found, not declared. It also offers
to reinstall through choco an app a choco list names that was installed some
other way (see "Installed another way" below).
"""

# %%
# Imports #

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

import yaml
from readable_utils.host_tools import get_uppercase_hostname

import app_lists
from deploy_configs import REPO_ROOT, host_allowed, member_overlay_dirs
from utils import taskbar_tools
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
            if entry.get("after"):
                after_argv(entry, path)
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
    wanted = app_lists.wanted_packages(manager.name, lists_dir, overlay_paths)
    if manager.name == "brew":
        # A tap formula is listed as "user/repo/formula" but installed, and
        # named in a removal, as its last segment.
        wanted |= {name.rsplit("/", 1)[-1] for name in wanted}
    return wanted


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
    available: str = ""  # the version on offer, in `winget upgrade` output


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
    available_at = header.find("Available")
    source_at = header.find("Source") if header.find("Source") > available_at else None
    rows = []
    for line in lines[header_at + 1 :]:
        if not line.strip() or set(line.strip()) == {"-"} or len(line) <= version_at:
            continue
        rows.append(
            Install(
                name=line[:id_at].strip(),
                id=line[id_at:version_at].strip(),
                version=line[version_at:version_end].strip(),
                available=line[available_at:source_at].strip() if available_at > version_at else "",
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


# A web app a Chromium browser installed (Chrome, Edge, Brave: "install this
# site as an app") is registered for uninstall like any program, so `winget
# list` shows it, under the site's name and an ARP id ending in its registry
# key. A web app named Messenger is not the messenger an app list names, and
# matching it by name made the listed app look installed. They are told apart
# by how they uninstall: the browser itself, with --uninstall-app-id.
WEB_APP_FLAG = "--uninstall-app-id"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"


def browser_web_apps():
    """Lowercased uninstall key names of the web apps a browser installed for this user."""
    if sys.platform != "win32":
        return set()
    import winreg

    keys = set()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as parent:
            for index in range(winreg.QueryInfoKey(parent)[0]):
                name = winreg.EnumKey(parent, index)
                try:
                    with winreg.OpenKey(parent, name) as key:
                        command = str(winreg.QueryValueEx(key, "UninstallString")[0])
                except OSError:
                    continue
                if WEB_APP_FLAG in command:
                    keys.add(name.lower())
    except OSError:
        return set()
    return keys


def without_web_apps(rows):
    """The rows that are programs: every ``ARP\\...\\<key>`` row a browser web app owns is dropped."""
    web_apps = browser_web_apps()
    if not web_apps:
        return rows
    return [
        row
        for row in rows
        if not (row.id.upper().startswith("ARP\\") and row.id.rsplit("\\", 1)[-1].lower() in web_apps)
    ]


# What installers add around an app's name in Add/Remove Programs: a bracketed
# edition, "version 2.2.0.0", the CPU architecture, a version number.
NAME_DECORATION = re.compile(
    r"\([^)]*\)|\bversion\b.*$|\b(x64|x86|amd64|arm64|64-bit|32-bit)\b|\bv?\d+(\.\d+)+\S*", re.IGNORECASE
)


def names_row(package, row):
    """
    Whether a package name is this row's app. It is when it equals the row's
    name, with or without what the installer added around it ("SyncTrayzor
    (x64) version 2.2.0.0" is synctrayzor), any part of its winget id (golang:
    GoLang.Go) or the whole id (googlechrome: Google.Chrome). Always the whole
    name, never a prefix: claude is not Claude Code.
    """
    key = name_key(package)
    names = {name_key(row.name), name_key(NAME_DECORATION.sub(" ", row.name)), name_key(row.id)}
    return key in names | {name_key(part) for part in row.id.split(".")}


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
        # disagree, and removing either would fight the next myupdater install offer.
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


# winget refuses to uninstall a per-user copy from an elevated shell ("The
# package installed for user scope cannot be uninstalled when running with
# administrator privileges"), and myupdater runs elevated because choco needs
# it. The extra copy is usually exactly that: the one an app's own installer
# left in AppData. It is therefore uninstalled through the logged-in user's own
# unelevated token: a one-off scheduled task at the Limited run level, which is
# the one way an elevated process can start something without admin and wait
# for its exit code. Its output goes to a file that is printed afterwards.
UNELEVATED_TASK = "dotfiles app_removals unelevated"
# LastTaskResult while the task has not started yet, and while it runs
TASK_PENDING = {267011, 267009}


def is_elevated():
    if sys.platform != "win32":
        return False
    import ctypes

    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def user_scoped(package_id, run=run_capture):
    """Whether winget files this id under the per-user scope."""
    code, _ = run(["winget", "list", "--exact", "--id", package_id, "--scope", "user", "--disable-interactivity"])
    return code == 0


def powershell_quote(text):
    return "'" + str(text).replace("'", "''") + "'"


def run_unelevated(argv, run=subprocess.run):
    """Run argv as the logged-in user without admin, wait for it, print its output. True when it exited 0."""
    workdir = tempfile.mkdtemp(prefix="app_removals_")
    try:
        output = os.path.join(workdir, "output.txt")
        script = os.path.join(workdir, "run.ps1")
        with open(script, "w", encoding="utf-8") as handle:
            command = " ".join(powershell_quote(arg) for arg in argv)
            handle.write(f"& {command} *>&1 | Out-File -Encoding utf8 {powershell_quote(output)}\n")
            handle.write("exit $LASTEXITCODE\n")
        task = powershell_quote(UNELEVATED_TASK)
        arguments = powershell_quote(f'-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{script}"')
        pending = ", ".join(str(code) for code in sorted(TASK_PENDING))
        driver = f"""
$ErrorActionPreference = 'Stop'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument {arguments}
$user = "$env:USERDOMAIN\\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName {task} -Action $action -Principal $principal -Force | Out-Null
try {{
    Start-ScheduledTask -TaskName {task}
    do {{
        Start-Sleep -Milliseconds 500
        $result = (Get-ScheduledTaskInfo -TaskName {task}).LastTaskResult
    }} while ($result -in @({pending}))
}} finally {{
    Unregister-ScheduledTask -TaskName {task} -Confirm:$false
}}
if ($result -ne 0) {{ exit 1 }}
"""
        print(paint("  per-user copy: uninstalling it without admin, as winget requires", "dim"))
        ok = remove_duplicate(["powershell", "-NoProfile", "-NonInteractive", "-Command", driver], run=run)
        if os.path.isfile(output):
            # Windows PowerShell 5 writes utf8 with a BOM
            with open(output, encoding="utf-8-sig", errors="replace") as handle:
                print(handle.read(), end="")
        return ok
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def uninstall_copy(row, argv):
    """Run one copy's uninstall, without admin when winget would refuse it from this elevated shell."""
    if argv[0] == "winget" and is_elevated() and user_scoped(row.id):
        return run_unelevated(argv)
    return remove_duplicate(argv)


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
            if uninstall_copy(row, argv):
                print(paint(f"  removed {group.id} {row.version}", "green"))
            else:
                failures += 1
                print(paint(f"  FAILED to remove {group.id} {row.version} (see output above)", "red"))
    return failures


# %%
# Installed another way #
#
# A choco-listed app that `winget list` shows but Chocolatey never installed
# (app_lists.missing_packages calls it "elsewhere"): put there by hand or by
# winget, so choco never upgrades it and `choco install` would lay a second
# copy beside it, which is why the choco installer leaves it out. The offer
# here is to uninstall every copy that is there, then install it through
# choco, leaving the one copy the list says choco manages. Uninstall first:
# the same vendor installer run twice can share one product code, so
# uninstalling after the choco install could take choco's copy too.
#
# Two things are settled before anything is offered, because the first version
# of this uninstalled a Messenger that could never be put back:
# - a web app a browser installed (browser_web_apps) is never the choco app,
#   however alike the names, so it is never one of the copies.
# - choco must have the package. A list naming one Chocolatey no longer carries
#   is reported as a list to fix, and nothing is uninstalled for it.
#
# Uninstalling unpins an app from the taskbar and installing does not pin it
# back, so the pins are saved before the first uninstall and the lost ones put
# back at the end (utils/taskbar_tools.py).


@dataclass
class Elsewhere:
    """One choco-listed app and the `winget list` rows that are it."""

    package: str
    rows: list
    available: bool = True  # choco has a package by this name


def choco_has(package, run=run_capture):
    """Whether Chocolatey's sources carry a package by exactly this name."""
    code, output = run(["choco", "search", package, "--exact", "--limit-output"])
    return code == 0 and any(line.strip().lower().startswith(package.lower() + "|") for line in output.splitlines())


def elsewhere_installs(run=run_capture):
    """Every choco-listed app installed some other way, with the rows each prompt uninstalls."""
    _, elsewhere, _, _ = app_lists.missing_packages(run=run)
    if not elsewhere:
        return []
    code, output = run(["winget", "list", "--disable-interactivity", "--accept-source-agreements"])
    rows = without_web_apps(parse_winget_list(output)) if code == 0 else []
    found = []
    for item in elsewhere:
        package = item.partition(":")[2]
        matches = [row for row in rows if names_row(package, row)]
        if matches:
            found.append(Elsewhere(package=package, rows=matches, available=choco_has(package, run=run)))
    return found


def report_elsewhere(found):
    if not found:
        return
    print(paint("Installed, but not by choco, which their app list names:", "cyan"))
    for item in found:
        print(f"  {item.package}")
        for row in item.rows:
            print(f"    {row.version}  {row.name}  ({row.id})")
        if not item.available:
            text = f"    left alone: choco has no package named {item.package}; fix the app list that names it"
            print(paint(text, "yellow"))


def restore_pins(snap, assume_yes):
    """Offer to put back the taskbar pins the reinstalls cost. Explorer restarts, so it asks first."""
    back, gone = taskbar_tools.restorable(snap)
    for name in gone:
        print(paint(f"  taskbar pin {name} is not restored: its app is somewhere else now, pin it again", "yellow"))
    if not back:
        return
    print()
    print(paint(f"  the reinstalls unpinned from the taskbar: {', '.join(back)}", "dim"))
    question = "Put them back? Explorer restarts, which closes open folder windows."
    if not assume_yes and prompt_yes_no_quit(question) != "y":
        print(paint("  taskbar left as it is", "dim"))
        return
    taskbar_tools.restore(
        snap, back, restart=lambda: taskbar_tools.restart_explorer(start=lambda: run_unelevated(["explorer.exe"]))
    )
    print(paint(f"  put back {len(back)} taskbar pin(s)", "green"))


def offer_elsewhere(found, assume_yes):
    """Ask per app and reinstall the agreed ones through choco. Returns the number that failed."""
    found = [item for item in found if item.available]
    if not found:
        return 0
    workdir = tempfile.mkdtemp(prefix="app_removals_pins_")
    try:
        snap = taskbar_tools.snapshot(workdir)
        failures = reinstall_elsewhere(found, assume_yes)
        restore_pins(snap, assume_yes)
        return failures
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def reinstall_elsewhere(found, assume_yes):
    failures = 0
    for item in found:
        print()
        print(paint("  winget has no dry run; this uninstalls the copies above, then choco installs it", "dim"))
        answer = "y" if assume_yes else prompt_yes_no_quit(f"Reinstall {item.package} through choco?")
        if answer == "q":
            print(paint("Stopping; remaining apps left as they are.", "dim"))
            return failures
        if answer == "n":
            print(paint(f"  kept {item.package} as it is", "dim"))
            continue
        uninstalled = all(uninstall_copy(row, winget_uninstall(row.id, row.version)) for row in item.rows)
        if not uninstalled:
            failures += 1
            print(paint(f"  FAILED to uninstall {item.package} (see output above); choco install not run", "red"))
            continue
        if remove_duplicate(["choco", "install", item.package, "-y"]):
            print(paint(f"  reinstalled {item.package} through choco", "green"))
        else:
            failures += 1
            print(paint(f"  FAILED: {item.package} is uninstalled; run `choco install {item.package} -y`", "red"))
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


def after_argv(entry, removals_file=None):
    """
    The argv of an entry's ``after:`` script, run once its removal succeeded.

    The path is relative to the repo holding the removals file, so an overlay's
    entry names a script of its own repo. A missing script or an extension
    with no known runner is a hard error when the file loads, not a surprise
    after something was already uninstalled.
    """
    base = os.path.dirname(removals_file or entry["_file"])
    path = os.path.normpath(os.path.join(base, entry["after"]))
    if not os.path.isfile(path):
        raise ValueError(f"after: script {entry['after']} of '{entry['name']}' not found at {path}")
    if path.endswith(".ps1"):
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path]
    if path.endswith(".sh"):
        return ["bash", path]
    raise ValueError(f"after: script {entry['after']} of '{entry['name']}' must be a .ps1 or .sh file")


def run_after(entry, run=subprocess.run):
    """Run an entry's ``after:`` script with the real terminal; True when it succeeded or there is none."""
    if not entry.get("after"):
        return True
    print(paint(f"  running {entry['after']}", "dim"))
    try:
        return run(after_argv(entry)).returncode == 0
    except OSError:
        return False


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
            if not run_after(entry):
                failures += 1
                print(paint(f"  FAILED: {entry['after']} after removing {entry['package']} (see output above)", "red"))
        else:
            failures += 1
            print(paint(f"  FAILED to remove {entry['package']} (see output above)", "red"))
    return failures, False


def run(
    list_only=False,
    assume_yes=False,
    entries=None,
    system=None,
    hostname=None,
    run_query=run_capture,
    show_all=False,
    duplicates_only=False,
):
    system = system or platform.system()
    entries = load_app_removals() if entries is None else entries
    if duplicates_only:
        found = Candidates()
    elif entries:
        found = candidates(entries, system=system, hostname=hostname, run=run_query)
        report(found)
    else:
        found = Candidates()
        print(paint("No app removals declared; nothing to check.", "dim"))
    groups = duplicate_groups(run=run_query) if system == "Windows" else []
    report_duplicates(groups, show_all)
    offers = [group for group in groups if group.offers]
    elsewhere = elsewhere_installs(run=run_query) if system == "Windows" and not duplicates_only else []
    report_elsewhere(elsewhere)
    problems = len(found.unknown)
    if list_only or not (found.removable or offers or any(item.available for item in elsewhere)):
        return 1 if problems else 0
    if not assume_yes and not sys.stdin.isatty():
        print(paint("stdin is not a terminal; removing nothing (run src/app_removals.py directly).", "yellow"))
        return 1 if problems else 0
    failures, stopped = offer_removals(found.removable, assume_yes)
    if not stopped:
        failures += offer_duplicates(offers, assume_yes)
        failures += offer_elsewhere(elsewhere, assume_yes)
    return 1 if failures or problems else 0


# %%
# Main #


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Offer to uninstall the packages an app removals file says must not be on this machine, "
            "and on Windows the extra copies of apps an app list installs and the choco-listed apps installed "
            "another way."
        )
    )
    parser.add_argument("--list", action="store_true", help="only report, never prompt or uninstall")
    parser.add_argument("--yes", action="store_true", help="uninstall everything offered without prompting")
    parser.add_argument("--all", action="store_true", help="also list duplicate installs no app list names (Windows)")
    parser.add_argument(
        "--duplicates",
        action="store_true",
        help="only the duplicate installs (Windows): what a refresh asks again right after it installs apps",
    )
    args = parser.parse_args()
    return run(list_only=args.list, assume_yes=args.yes, show_all=args.all, duplicates_only=args.duplicates)


if __name__ == "__main__":
    sys.exit(main())

# %%
