#!/usr/bin/env python3
"""
The packages this machine's app lists name, per package manager.

Two sources, the same split every other declaration in this repo follows:

- ``app_lists/`` in dotfiles: what every machine of a platform gets.
- ``<context>_app_lists.yaml`` at the root of each overlay repo this machine is
  a member of: what only that context's machines get - a client's cloud CLI,
  its chat app. Same discovery and membership gate as the overlay manifests
  (``deploy_configs.member_overlay_dirs``), so a credentials repo a box holds
  only as its git hub adds nothing.

The overlay file is a mapping of manager to package names::

    choco: [slack, awscli]
    cask: [slack]

A brew name may be a third-party tap's formula in full (``user/repo/formula``):
``install_mac_apps.sh`` taps it and trusts that one formula before installing.

Every installer in ``scripts/`` appends ``--overlay <manager>`` to the list it
already reads, and ``app_removals.py`` asks ``wanted_packages`` so a package any
of them names is never offered for removal. One answer to "what should this
machine have", whichever direction asks.

One machine can turn an app down for good: ``~/.dotfiles_ignored_apps`` holds
``manager:package`` lines, written when an installer's question about an app
is answered ``i``. A listed app is therefore offered at
least once, and after that an ignored one is never offered or reported missing
again on that machine; every place that leaves one out names the file, so
deleting its line is how to be offered it again. Machine state and not a
committed list, because it is the answer one person gave at one desk, and the
lists stay the record of what a machine of that kind should have.
"""

# %%
# Imports #

import argparse
import os
import platform
import re
import shutil
import sys

import yaml

from deploy_configs import REPO_ROOT, member_overlay_dirs
from utils.inventory_tools import overlay_context

APP_LISTS = os.path.join(REPO_ROOT, "app_lists")

# The dotfiles app lists each manager reads. A manager with several files reads
# every one of them here: this is the "named anywhere" question removals ask,
# not the one profile an installer happens to be installing.
BASE_LISTS = {
    "brew": ("Brewfile",),
    "cask": ("Brewfile",),
    "apt": ("linux_apps.txt", "linux_apps_wsl.txt"),
    "dnf": ("linux_apps_dnf.txt",),
    "flatpak": ("linux_apps_flatpak.txt",),
    "choco": ("windows_apps_personal_choco.txt", "windows_apps_base_choco.txt"),
    "winget": ("windows_apps_personal_winget.txt",),
}

MANAGERS = tuple(BASE_LISTS)

# The list each installer reads when nobody passes it another one: what this
# machine is supposed to have, as opposed to BASE_LISTS' "named anywhere".
INSTALLER_LISTS = {
    "brew": ("Brewfile",),
    "cask": ("Brewfile",),
    "apt": ("linux_apps.txt",),
    "dnf": ("linux_apps_dnf.txt",),
    "flatpak": ("linux_apps_flatpak.txt",),
    "choco": ("windows_apps_personal_choco.txt",),
    "winget": ("windows_apps_personal_winget.txt",),
}

# The executable whose presence means this machine uses the manager.
MANAGER_COMMANDS = {
    "brew": "brew",
    "cask": "brew",
    "apt": "apt-get",
    "dnf": "dnf",
    "flatpak": "flatpak",
    "choco": "choco",
    "winget": "winget",
}

# %%
# Dotfiles app lists #

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


def base_packages(manager, app_lists=APP_LISTS, filenames=None):
    """Every package the dotfiles app lists name for this manager (``filenames`` narrows which lists)."""
    names = set()
    for filename in BASE_LISTS[manager] if filenames is None else filenames:
        path = os.path.join(app_lists, filename)
        if not os.path.exists(path):
            continue
        if filename == "Brewfile":
            names.update(read_brewfile(path, manager))
        else:
            names.update(read_app_list(path))
    return names


# %%
# Context app lists #


def discover_app_lists():
    """``<context>_app_lists.yaml`` from each overlay repo this machine is a member of."""
    files = []
    for overlay_dir in member_overlay_dirs()[0]:
        path = os.path.join(overlay_dir, f"{overlay_context(overlay_dir)}_app_lists.yaml")
        if os.path.exists(path):
            files.append(path)
    return files


def load_overlay(paths=None):
    """
    ``{manager: [(package, source file), ...]}`` across every discovered file.

    An unknown manager or a value that is not a list of names is a hard error:
    a typo here would otherwise quietly install nothing on every machine of
    that context.
    """
    found: dict = {}
    for path in discover_app_lists() if paths is None else paths:
        with open(path, "r", encoding="utf-8") as handle:
            parsed = yaml.safe_load(handle) or {}
        if not isinstance(parsed, dict):
            raise ValueError(f"App lists file {path} must be a mapping of manager to package names")
        for manager, names in parsed.items():
            if manager not in BASE_LISTS:
                raise ValueError(f"Unknown manager '{manager}' in {path}; expected one of {', '.join(MANAGERS)}")
            if not isinstance(names, list) or not all(isinstance(name, str) and name.strip() for name in names):
                raise ValueError(f"'{manager}' in {path} must be a list of package names")
            found.setdefault(manager, []).extend((name.strip(), path) for name in names)
    return found


def overlay_packages(manager, paths=None):
    """
    The package names this machine's contexts add for one manager, in file
    order, without repeats. Two contexts may name the same app (a machine in
    both is offered it once, under the first spelling); every manager here
    treats names case-insensitively, so the repeat check does too.
    """
    names, seen = [], set()
    for name, _ in load_overlay(paths).get(manager, []):
        if name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return names


def wanted_packages(manager, app_lists=APP_LISTS, overlay_paths=None):
    """Every package any app list names for this manager on this machine."""
    return base_packages(manager, app_lists) | set(overlay_packages(manager, overlay_paths))


# %%
# Ignored on this machine #

IGNORE_FILE = os.path.join(os.path.expanduser("~"), ".dotfiles_ignored_apps")

_IGNORE_HEADER = """\
# Apps this machine was offered and turned down, one manager:package per line.
# Written by the dotfiles installers when an app's question is answered i,
# and read by them and by myupdater's closing summary, neither of which offer
# or report these again here.
# Delete a line to be offered that app again, or run installmissing, which
# offers these too and deletes the line of each one you say yes to.
"""


def read_ignored(path=None):
    """Every ``manager:package`` this machine ignores, lowercased."""
    path = path or IGNORE_FILE
    if not os.path.exists(path):
        return set()
    return {line.lower() for line in read_app_list(path) if ":" in line}


def ignored_packages(manager, names, path=None):
    """The subset of ``names`` this machine ignores for one manager, in their order."""
    ignored = read_ignored(path)
    return [name for name in names if f"{manager}:{name}".lower() in ignored]


def record_ignored(manager, names, path=None):
    """Add ``manager:name`` lines for the names not already there. Returns the lines added."""
    path = path or IGNORE_FILE
    ignored = read_ignored(path)
    added = [f"{manager}:{name}" for name in names if f"{manager}:{name}".lower() not in ignored]
    if not added:
        return []
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as handle:
        if new:
            handle.write(_IGNORE_HEADER)
        handle.writelines(line + "\n" for line in added)
    return added


def forget_ignored(manager, names, path=None):
    """Take the ``manager:name`` lines out of the ignore file. Returns the lines removed."""
    path = path or IGNORE_FILE
    if not os.path.exists(path):
        return []
    drop = {f"{manager}:{name}".lower() for name in names}
    with open(path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()
    kept, removed = [], []
    for line in lines:
        entry = line.replace("\r", "").split("#", 1)[0].strip()
        if entry and entry.lower() in drop:
            removed.append(entry)
        else:
            kept.append(line)
    if removed:
        with open(path, "w", encoding="utf-8") as handle:
            handle.writelines(kept)
    return removed


# %%
# Missing apps #


def installer_lists(manager, release=None):
    """The dotfiles lists this machine's installer for one manager reads by default."""
    release = platform.release() if release is None else release
    if manager == "apt" and "microsoft" in release.lower():
        return ("linux_apps_wsl.txt",)
    return INSTALLER_LISTS[manager]


def installed_names(manager, run):
    """Lowercased names the manager reports installed, or None when it could not answer."""
    # The per-manager queries live with the removals, which import this module.
    import app_removals

    if manager == "winget":
        code, output = run(["winget", "list", "--disable-interactivity", "--accept-source-agreements"])
        if code != 0:
            return None
        return {row.id.lower() for row in app_removals.parse_winget_list(output)}
    names = app_removals.installed_packages(app_removals.MANAGERS[manager], run=run)
    if names is None or manager != "brew":
        return names
    # A versioned formula installs under a suffixed name (Brewfile "python" is
    # "python@3.14"), and a third-party tap's formula is listed as
    # "user/repo/formula" only by --full-name; install_mac_apps.sh makes the
    # same two allowances.
    code, output = run(["brew", "list", "--formula", "--full-name"])
    full = {line.strip().lower() for line in output.splitlines() if line.strip()} if code == 0 else set()
    return names | full | {name.split("@")[0] for name in names}


def elsewhere_packages(manager, names, which=shutil.which, run=None):
    """
    The ``names`` Chocolatey does not have but `winget list` shows under the
    same name: installed by hand or by another manager, so installing one
    through choco would make a second copy. The one answer both the closing
    summary and the installer's questions use. Only choco has this problem.
    A web app a browser installed is not that copy: it only shares the name.
    """
    import app_removals

    if manager != "choco" or not names or not which("winget"):
        return []
    run = run or app_removals.run_capture
    code, output = run(["winget", "list", "--disable-interactivity", "--accept-source-agreements"])
    rows = app_removals.without_web_apps(app_removals.parse_winget_list(output)) if code == 0 else []
    return [name for name in names if any(app_removals.names_row(name, row) for row in rows)]


UPGRADES_END = re.compile(r"^\d+ upgrades? available", re.MULTILINE)
RELEASE_NUMBER = re.compile(r"v?(\d+(?:\.\d+)*)")
CHOCO_VARIANT = re.compile(r"\.(install|portable)$", re.IGNORECASE)
WINDOWS_TERMINAL = "microsoft.windowsterminal"
UPGRADE_HOLDS = os.path.join(REPO_ROOT, "app_upgrade_holds.yaml")


def load_upgrade_holds(path=None):
    """``{(manager, package lowercased): reason}`` from app_upgrade_holds.yaml; {} when the file is absent."""
    path = path or UPGRADE_HOLDS
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        entries = yaml.safe_load(handle) or []
    holds = {}
    for entry in entries:
        missing = [key for key in ("name", "manager", "package", "reason") if not entry.get(key)]
        if missing:
            raise ValueError(f"Upgrade hold {entry.get('name', entry)} in {path} lacks {', '.join(missing)}")
        holds[(entry["manager"], entry["package"].lower())] = " ".join(str(entry["reason"]).split())
    return holds


def release_number(version):
    """The leading numbers of a version as a tuple, trailing zeros dropped, or None when it has none."""
    found = RELEASE_NUMBER.match(version.strip())
    if not found:
        return None
    parts = [int(part) for part in found.group(1).split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def at_or_past(installed, available):
    """
    Whether the installed version is already the one on offer, or newer.
    Barrier's ``2.4.0-release`` is at ``2.4.0``; ``2.7.701`` is past
    ``2.6.16.1``. A version with no leading number ("Unknown") cannot be
    compared and is never at or past.
    """
    numbers = release_number(installed), release_number(available)
    return None not in numbers and numbers[0] >= numbers[1]


def process_running(image, run=None):
    """Whether a process with this image name is running (tasklist prints a row for it)."""
    import app_removals

    run = run or app_removals.run_capture
    code, output = run(["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"])
    return code == 0 and image.lower() in output.lower()


def choco_name(package):
    """The app a choco package installs: ``git.install`` and ``putty.portable`` are git and putty."""
    return CHOCO_VARIANT.sub("", package)


def winget_upgrades(run=None, which=shutil.which, app_lists=APP_LISTS, overlay_paths=None, holds=None, versions=None):
    """
    ``(upgrade, held)`` for what `winget upgrade` offers, or None when winget
    could not be asked. ``upgrade`` is the winget ids to upgrade; ``held`` is
    ``(id, reason)`` for the ones winget must leave alone. A ``versions`` dict
    is filled with ``id -> (installed, available)`` for the ids to upgrade, so
    the updater can say what each upgrade moved from and to.

    winget upgrades an app only when a winget app list names it. `winget
    upgrade --all` goes for every installed program it can match to its
    source, whoever installed it: Chocolatey's apps (it put TightVNC 2.8.89
    over the 2.8.88 Chocolatey had recorded), a component another app
    installs and maintains for itself (Epic Online Services, which winget then
    refuses to replace), anything installed by hand. The list is what says an
    app is winget's, so nothing is guessed from names.

    A listed id is still held when it is on the holds file, when Chocolatey
    also installed it (the lists disagree), when the offer is the release
    already installed (winget cannot compare some version strings: Barrier
    registers ``2.4.0-release`` and is offered ``2.4.0`` forever), and for
    Windows Terminal while a Terminal window is open, which Windows refuses to
    replace and the Store updates once it is closed.
    """
    import app_removals

    run = run or app_removals.run_capture
    code, output = run(["winget", "upgrade", "--disable-interactivity", "--accept-source-agreements"])
    if code is None:
        return None
    # Only the first table: after its count winget lists what it cannot or will not upgrade.
    end = UPGRADES_END.search(output)
    rows = app_removals.parse_winget_list(output[: end.start()] if end else output)
    listed = {name.lower() for name in wanted_packages("winget", app_lists, overlay_paths)}
    holds = load_upgrade_holds() if holds is None else holds
    choco = sorted(app_removals.choco_versions(run=run)) if which("choco") and rows else []
    upgrade, held = [], []
    for row in rows:
        owner = next((name for name in choco if app_removals.names_row(choco_name(name), row)), None)
        if row.id.lower() not in listed:
            mine = f"chocolatey installed it (choco:{owner})" if owner else "no winget app list names it"
            held.append((row.id, f"{mine}, so winget does not upgrade it"))
        elif ("winget", row.id.lower()) in holds:
            held.append((row.id, holds[("winget", row.id.lower())]))
        elif owner:
            held.append((row.id, f"chocolatey also installed it (choco:{owner}); drop it from one app list"))
        elif at_or_past(row.version, row.available):
            held.append((row.id, f"{row.available} is the installed {row.version} under another name"))
        elif row.id.lower() == WINDOWS_TERMINAL and process_running("WindowsTerminal.exe", run):
            held.append((row.id, "a Terminal window is open; the Store updates it once Terminal is closed"))
        else:
            upgrade.append(row.id)
            if versions is not None:
                versions[row.id] = (row.version, row.available)
    return upgrade, held


def choco_upgrades(run=None, which=shutil.which, holds=None, versions=None):
    """
    ``(upgrade, held)`` for what `choco outdated` lists, or None when
    Chocolatey could not be asked. Chocolatey only ever lists what it
    installed itself, so every package is its own; ``held`` is ``(package,
    reason)`` for the ones it must still leave alone (``versions`` as in
    winget_upgrades):

    - a package on the holds file (apps that update themselves, whose package
      then fails its own checksum on every run).
    - a package whose app is really installed at or past the version
      Chocolatey offers: something else upgraded it, Chocolatey's record is
      behind, and its installer would push an older build over a newer one -
      OpenVPN 2.6.16 over 2.7.7 failed with MSI 1603 on every run.
    """
    import app_removals

    run = run or app_removals.run_capture
    code, output = run(["choco", "outdated", "--limit-output"])
    if code is None:
        return None
    outdated = [line.strip().split("|") for line in output.splitlines() if line.count("|") >= 3]
    holds = load_upgrade_holds() if holds is None else holds
    rows = []
    if outdated and which("winget"):
        code, listing = run(["winget", "list", "--disable-interactivity", "--accept-source-agreements"])
        rows = app_removals.parse_winget_list(listing) if code == 0 else []
    upgrade, held = [], []
    for package, current, available, pinned, *_ in outdated:
        # choco lists a pinned package, and one whose latest is what it has (messenger 205 -> 205).
        if pinned.lower() == "true" or app_removals.version_key(current) == app_removals.version_key(available):
            continue
        ahead = next(
            (
                row
                for row in rows
                if app_removals.names_row(choco_name(package), row) and at_or_past(row.version, available)
            ),
            None,
        )
        if ("choco", package.lower()) in holds:
            held.append((package, holds[("choco", package.lower())]))
        elif ahead:
            held.append((package, f"{ahead.version} is installed, at or past the {available} chocolatey offers"))
        else:
            upgrade.append(package)
            if versions is not None:
                versions[package] = (current, available)
    return upgrade, held


def print_upgrades(manager):
    """
    The plan as my_updater.ps1 reads it: ``upgrade <id>`` and ``held <id>
    <reason>`` per app, plus ``version <id> <installed> <available>`` for each
    upgrade so the closing page can draw the move.
    """
    versions: dict = {}
    plan = winget_upgrades(versions=versions) if manager == "winget" else choco_upgrades(versions=versions)
    if plan is None:
        print(f"could not ask {manager} what it would upgrade", file=sys.stderr)
        return 1
    upgrade, held = plan
    for package in upgrade:
        print(f"upgrade {package}")
        if package in versions:
            print(f"version {package} {versions[package][0]} {versions[package][1]}")
    for package, reason in held:
        print(f"held {package} {reason}")
    return 0


def missing_packages(
    which=shutil.which, run=None, app_lists=APP_LISTS, overlay_paths=None, release=None, ignore_file=None
):
    """
    ``(missing, elsewhere, unanswered, ignored)`` for this machine's lists.

    ``missing`` is ``manager:package`` for every listed app nothing has
    installed. ``elsewhere`` is a choco entry Chocolatey does not have but
    `winget list` shows under the same name - installed by hand or by another
    manager, so installing it through choco would make a second copy.
    ``unanswered`` names the managers that could not be asked, and
    ``ignored`` the uninstalled apps left out because this machine's ignore
    file names them. Only managers this machine has are consulted, so a Mac is
    never told it lacks every choco package.
    """
    import app_removals

    run = run or app_removals.run_capture
    missing, elsewhere, unanswered, ignored = [], [], [], []
    skip = read_ignored(ignore_file)
    for manager in MANAGERS:
        if not which(MANAGER_COMMANDS[manager]):
            continue
        base = base_packages(manager, app_lists, installer_lists(manager, release))
        wanted = sorted(base | set(overlay_packages(manager, overlay_paths)))
        if not wanted:
            continue
        installed = installed_names(manager, run)
        if installed is None:
            unanswered.append(manager)
            continue
        absent = [name for name in wanted if name.lower() not in installed]
        ignored += [f"{manager}:{name}" for name in absent if f"{manager}:{name}".lower() in skip]
        absent = [name for name in absent if f"{manager}:{name}".lower() not in skip]
        present = set(elsewhere_packages(manager, absent, which, run))
        elsewhere += [f"{manager}:{name}" for name in absent if name in present]
        absent = [name for name in absent if name not in present]
        missing += [f"{manager}:{name}" for name in absent]
    return missing, elsewhere, unanswered, ignored


# %%
# Main #


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Print the packages this machine's app lists name.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--overlay",
        metavar="MANAGER",
        choices=MANAGERS,
        help="print only what this machine's contexts add for one manager, one per line (what the installers read)",
    )
    mode.add_argument("--where", action="store_true", help="print the context app list files consulted")
    mode.add_argument(
        "--missing",
        action="store_true",
        help="print 'missing|elsewhere|ignored manager:package' per listed app not installed by its manager",
    )
    mode.add_argument(
        "--ignored",
        metavar="MANAGER",
        choices=MANAGERS,
        help="read package names on stdin, print the ones this machine ignores for that manager",
    )
    mode.add_argument(
        "--upgrades",
        metavar="MANAGER",
        choices=("winget", "choco"),
        help="print 'upgrade NAME' per app this manager should upgrade and 'held NAME reason' per one it must not",
    )
    mode.add_argument(
        "--elsewhere",
        metavar="MANAGER",
        choices=MANAGERS,
        help="read package names on stdin, print the ones installed here outside that manager",
    )
    mode.add_argument(
        "--ignore",
        nargs="+",
        metavar="ARG",
        help="MANAGER PACKAGE...: record these as ignored on this machine, printing each line added",
    )
    mode.add_argument(
        "--unignore",
        nargs="+",
        metavar="ARG",
        help="MANAGER PACKAGE...: stop ignoring these on this machine, printing each line removed",
    )
    mode.add_argument("--ignore-path", action="store_true", help="print this machine's ignore file path")
    args = parser.parse_args(argv)
    for flag, given in (("--ignore", args.ignore), ("--unignore", args.unignore)):
        if given and given[0] not in MANAGERS:
            parser.error(f"{flag} takes a manager first, one of {', '.join(MANAGERS)}")
    return args


def print_missing():
    missing, elsewhere, unanswered, ignored = missing_packages()
    for kind, lines in (("missing", missing), ("elsewhere", elsewhere), ("ignored", ignored)):
        for line in lines:
            print(f"{kind} {line}")
    if ignored:
        print(f"ignore-file {IGNORE_FILE}")
    for manager in unanswered:
        print(f"could not ask {manager} what is installed", file=sys.stderr)
    return 1 if unanswered else 0


def print_everything():
    overlay = load_overlay()
    for manager in MANAGERS:
        added = overlay.get(manager, [])
        names = sorted(base_packages(manager) | {name for name, _ in added})
        if not names:
            continue
        print(f"{manager}:")
        sources = {name: os.path.basename(path) for name, path in added}
        for name in names:
            print(f"  {name}" + (f"  ({sources[name]})" if name in sources else ""))
    return 0


def main(argv=None):
    args = parse_args(argv)
    if args.missing:
        return print_missing()
    if args.upgrades:
        return print_upgrades(args.upgrades)
    if args.ignored:
        names = [line.strip() for line in sys.stdin if line.strip()]
        lines = ignored_packages(args.ignored, names)
    elif args.elsewhere:
        names = [line.strip() for line in sys.stdin if line.strip()]
        lines = elsewhere_packages(args.elsewhere, names)
    elif args.ignore:
        lines = record_ignored(args.ignore[0], args.ignore[1:])
    elif args.unignore:
        lines = forget_ignored(args.unignore[0], args.unignore[1:])
    elif args.ignore_path:
        lines = [IGNORE_FILE]
    elif args.where:
        lines = discover_app_lists()
    elif args.overlay:
        lines = overlay_packages(args.overlay)
    else:
        return print_everything()
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())

# %%
