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

Every installer in ``scripts/`` appends ``--overlay <manager>`` to the list it
already reads, and ``app_removals.py`` asks ``wanted_packages`` so a package any
of them names is never offered for removal. One answer to "what should this
machine have", whichever direction asks.

One machine can turn an app down for good: ``~/.dotfiles_ignored_apps`` holds
``manager:package`` lines, written when an installer's prompt is answered with
the numbers to ignore (or ``i`` for all). A listed app is therefore offered at
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
# Written by the dotfiles installers when their prompt is answered with the
# numbers to ignore (or i for all), and read by them, by installmissing and by
# myupdater's closing summary, none of which offer or report these again here.
# Delete a line to be offered that app again.
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
    # "python@3.14"), the same allowance install_mac_apps.sh makes.
    return names | {name.split("@")[0] for name in names}


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
    winget_rows = None
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
        if manager == "choco" and absent and which("winget"):
            if winget_rows is None:
                code, output = run(["winget", "list", "--disable-interactivity", "--accept-source-agreements"])
                winget_rows = app_removals.parse_winget_list(output) if code == 0 else []
            present = {name for name in absent if any(app_removals.names_row(name, row) for row in winget_rows)}
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
        "--ignore",
        nargs="+",
        metavar="ARG",
        help="MANAGER PACKAGE...: record these as ignored on this machine, printing each line added",
    )
    mode.add_argument("--ignore-path", action="store_true", help="print this machine's ignore file path")
    args = parser.parse_args(argv)
    if args.ignore and args.ignore[0] not in MANAGERS:
        parser.error(f"--ignore takes a manager first, one of {', '.join(MANAGERS)}")
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
    if args.ignored:
        names = [line.strip() for line in sys.stdin if line.strip()]
        lines = ignored_packages(args.ignored, names)
    elif args.ignore:
        lines = record_ignored(args.ignore[0], args.ignore[1:])
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
