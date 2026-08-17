#!/usr/bin/env python3
# %%
"""Run all mac cleanup tasks with before/after disk-usage bars.

Combines the standalone cleanups:
  1. purge_paths        — regrowing updater/cache junk in ~/Library (no root)
  2. vscode_extensions  — outdated VS Code extension versions (no root)
  3. brew_staging       — interrupted cask/keg installs brew cleanup can't see
  4. browser_caches     — Chrome/Edge caches, skipped while the browser runs
  5. app_logs           — rotated app logs (live log left alone)
  6. package_caches     — uv/npm/brew caches, via each tool's own prune command
  7. powerlog           — PerfPowerTelemetry DB leak (root required to delete)
  8. logstore           — unified-logging archive via `log erase` (root required)

Dry run by default. Enable deletion either way:
  script:   sudo python3 scripts/mac_cleanup_all.py --delete
  ipython:  set DELETE = True in the config cell and run the cells

Run with sudo so the powerlog and logstore purges can act; the user-home
cleanups still resolve the real user's home via SUDO_USER. Without sudo, those
two steps report what they would do (or can't read) and are skipped on delete.
package_caches is the mirror image: it shells out to uv/npm/brew, which must
run as the login user, so it is skipped under sudo — run once each way.
"""

import argparse
import os
import pwd
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from stat import S_ISREG

# %%
# Config — edit these when running as ipython cells (CLI flags override) #

DELETE = False               # False = dry run; True = actually delete
POWERLOG_THRESHOLD_GB = 2.0  # only purge powerlog DB above this size
LOGSTORE_THRESHOLD_GB = 2.0  # only erase the unified log store above this size
STAGING_AGE_DAYS = 1.0       # brew staging younger than this may be a live install
BAR_WIDTH = 50


# %%
# Shared helpers #

def real_home() -> Path:
    """User's home even under sudo (sudo python3 keeps HOME=/var/root)."""
    sudo_user = os.environ.get("SUDO_USER")
    if os.geteuid() == 0 and sudo_user:
        return Path(pwd.getpwnam(sudo_user).pw_dir)
    return Path.home()


HOME = real_home()
IS_ROOT = os.geteuid() == 0


def dir_size(path: Path) -> int:
    """What deleting this would actually give back to df, the way du counts it.

    Three ways the obvious version lies, all found by chasing a run that
    claimed 13.62 GB and freed 8.26 GB:
      - st_size is apparent size. APFS compresses this stuff, so a staged cask
        measured 4.01 GB and freed 2.5 GB. st_blocks is what is really on disk.
      - is_file() follows symlinks, so a link and its target both count. The
        Homebrew cache is symlinks into downloads/ and read 415 MB, not 244.
      - hardlinked files get counted once per link but freed once.
    lstat + S_ISREG covers the first two, the inode set the third — which is
    exactly how du arrives at its number.
    """
    seen: set[tuple[int, int]] = set()

    def blocks(entry: Path) -> int:
        stat_result = entry.lstat()
        if not S_ISREG(stat_result.st_mode):
            return 0
        if stat_result.st_nlink > 1:
            key = (stat_result.st_dev, stat_result.st_ino)
            if key in seen:
                return 0
            seen.add(key)
        return stat_result.st_blocks * 512

    if path.is_file():
        return blocks(path)
    total = 0
    for f in path.rglob("*"):
        try:
            total += blocks(f)
        except (PermissionError, OSError):
            continue
    return total


def human(nbytes: float) -> str:
    if abs(nbytes) >= 1024 ** 3:
        return f"{nbytes / 1024**3:.2f} GB"
    return f"{nbytes / 1024**2:.0f} MB"


def remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def process_running(name: str) -> bool:
    """True if a process with exactly this name is running."""
    result = subprocess.run(["pgrep", "-x", name], capture_output=True, text=True, check=False)
    return result.returncode == 0


def report(action: str, path: Path, size: int) -> None:
    print(f"{action}: {path} ({human(size)})")


def disk_bar(label: str) -> shutil._ntuple_diskusage:
    """Print a usage bar for / and return the disk_usage snapshot."""
    usage = shutil.disk_usage("/")
    filled = round(BAR_WIDTH * usage.used / usage.total)
    bar = "█" * filled + "░" * (BAR_WIDTH - filled)
    pct = 100 * usage.used / usage.total
    print(f"{label:<7}[{bar}] {pct:.1f}% used — {human(usage.free)} free of {human(usage.total)}")
    return usage


# %%
# Cleanup 1: purge regrowing junk paths (updater staging dirs, stale caches) #

PURGE_PATHS = [
    HOME / "Library" / "Caches" / "com.microsoft.VSCode.ShipIt",
    HOME / "Library" / "Caches" / "com.tinyspeck.slackmacgap.ShipIt",
    HOME / "Library" / "Caches" / "com.anthropic.claudefordesktop.ShipIt",
    HOME / "Library" / "Caches" / "bitwarden-updater",
    HOME / "Library" / "Caches" / "t3code-updater",
]


def cleanup_purge_paths(delete: bool) -> int:
    print("\n── purge_paths ──")
    found = [(p, dir_size(p)) for p in PURGE_PATHS if p.exists()]
    if not found:
        print("no purge targets present")
        return 0

    total = 0
    action = "deleting" if delete else "would delete"
    for path, size in sorted(found, key=lambda kv: -kv[1]):
        total += size
        report(action, path, size)
        if delete:
            remove(path)
    print(f"subtotal: {human(total)}")
    return total


# %%
# Cleanup 2: outdated VS Code extension versions (keep newest of each) #

EXT_DIR = HOME / ".vscode" / "extensions"
# publisher.name-1.2.3 or publisher.name-1.2.3-darwin-arm64
EXT_PATTERN = re.compile(r"^(?P<ext_id>.+?)-(?P<version>\d+(?:\.\d+)+)(?P<platform>-[a-z0-9-]+)?$")


def find_outdated_extensions(ext_dir: Path) -> list[Path]:
    groups: dict[str, list[tuple[tuple[int, ...], Path]]] = defaultdict(list)
    for entry in ext_dir.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        match = EXT_PATTERN.match(entry.name)
        if not match:
            continue
        key = match["ext_id"] + (match["platform"] or "")
        version = tuple(int(part) for part in match["version"].split("."))
        groups[key].append((version, entry))

    outdated: list[Path] = []
    for versions in groups.values():
        if len(versions) > 1:
            versions.sort(reverse=True)
            outdated.extend(path for _, path in versions[1:])
    return outdated


def cleanup_vscode_extensions(delete: bool) -> int:
    print("\n── vscode_extensions ──")
    if not EXT_DIR.is_dir():
        print(f"extensions dir not found: {EXT_DIR}")
        return 0

    outdated = find_outdated_extensions(EXT_DIR)
    if not outdated:
        print("no outdated extension versions found")
        return 0

    total = 0
    action = "deleting" if delete else "would delete"
    for path in sorted(outdated):
        size = dir_size(path)
        total += size
        print(f"{action}: {path.name} ({human(size)})")
        if delete:
            shutil.rmtree(path)
    print(f"subtotal: {human(total)}")
    return total


# %%
# Cleanup 3: homebrew staging left behind by interrupted installs #

BREW_STAGING = Path("/opt/homebrew/var/homebrew/tmp")
BREW_STAGING_ROOTS = (".caskroom", ".cellar")  # brew unpacks casks/kegs into these dot-dirs


def gather_brew_staging(age_days: float) -> list[Path]:
    """Per-cask/keg staging dirs from installs that died partway through.

    These sit inside dot-dirs under tmp/, which is why `brew cleanup` never
    reclaims them. Anything younger than age_days might be a live install.
    """
    if not BREW_STAGING.is_dir():
        return []

    cutoff = time.time() - age_days * 86400
    stale: list[Path] = []
    for entry in BREW_STAGING.iterdir():
        staged = list(entry.iterdir()) if entry.is_dir() and entry.name in BREW_STAGING_ROOTS else [entry]
        for path in staged:
            try:
                if path.stat().st_mtime < cutoff:
                    stale.append(path)
            except OSError:
                continue
    return stale


def cleanup_brew_staging(delete: bool, age_days: float) -> int:
    print("\n── brew_staging ──")
    if not BREW_STAGING.is_dir():
        print(f"staging dir not found: {BREW_STAGING}")
        return 0
    if process_running("brew"):
        print("skipping: brew is running, staging may be in use")
        return 0

    stale = gather_brew_staging(age_days)
    if not stale:
        print(f"no staging older than {age_days:g} day(s)")
        return 0

    total = 0
    action = "deleting" if delete else "would delete"
    for path, size in sorted(((p, dir_size(p)) for p in stale), key=lambda kv: -kv[1]):
        total += size
        report(action, path, size)
        if delete:
            remove(path)
    print(f"subtotal: {human(total)}")
    return total


# %%
# Cleanup 4: browser caches (only while the browser is closed) #

BROWSER_CACHES = [
    ("Google Chrome", HOME / "Library" / "Caches" / "Google" / "Chrome"),
    ("Microsoft Edge", HOME / "Library" / "Caches" / "Microsoft Edge"),
]


def cleanup_browser_caches(delete: bool) -> int:
    """Pure cache, but only touched with the browser closed — a running Chrome
    holds these files open, so deleting them frees nothing and confuses it."""
    print("\n── browser_caches ──")
    total = 0
    action = "deleting" if delete else "would delete"
    for process, path in BROWSER_CACHES:
        if not path.exists():
            continue
        size = dir_size(path)
        if process_running(process):
            print(f"skipping: {process} is running ({human(size)} in {path})")
            continue
        total += size
        report(action, path, size)
        if delete:
            remove(path)
    print(f"subtotal: {human(total)}" if total else "nothing to do")
    return total


# %%
# Cleanup 5: rotated app logs #

# (dir, glob) — the glob must not match the live log: deleting an open file
# frees nothing until the writer closes it, which is the holder problem below.
LOG_GLOBS = [
    (HOME / "Library" / "Application Support" / "Google" / "DriveFS" / "Logs", "drive_fs_*.txt"),
]


def cleanup_app_logs(delete: bool) -> int:
    print("\n── app_logs ──")
    total = 0
    action = "deleting" if delete else "would delete"
    for directory, pattern in LOG_GLOBS:
        if not directory.is_dir():
            continue
        rotated = sorted(directory.glob(pattern))
        if not rotated:
            continue
        size = sum(dir_size(p) for p in rotated)
        total += size
        print(f"{action}: {len(rotated)} rotated logs in {directory} ({human(size)})")
        if delete:
            for path in rotated:
                remove(path)
    print(f"subtotal: {human(total)}" if total else "no rotated logs found")
    return total


# %%
# Cleanup 6: package manager caches, pruned by their own tooling #

# (label, cache dir, prune command) — never rm these by hand; only the tool
# knows which entries are still linked into an installed environment.
PACKAGE_CACHES = [
    ("uv", HOME / ".cache" / "uv", ["uv", "cache", "prune"]),
    ("npm", HOME / ".npm" / "_cacache", ["npm", "cache", "clean", "--force"]),
    ("homebrew", HOME / "Library" / "Caches" / "Homebrew", ["brew", "cleanup", "-s", "--prune=all"]),
]


def cleanup_package_caches(delete: bool) -> int:
    """Counts what the prune actually removed, by re-measuring afterwards.

    A prune keeps whatever is still linked into an installed environment, so
    the cache size is only an upper bound — reporting it as the win inflated
    the run total by ~3 GB the first time this step shipped. On a dry run
    there is nothing to measure, so the upper bound is all it can offer.
    """
    print("\n── package_caches ──")
    if delete and IS_ROOT:
        print("skipping delete: these tools must run as the login user, not root (rerun without sudo)")
        return 0

    total = 0
    for label, path, command in PACKAGE_CACHES:
        if not path.exists():
            continue
        before = dir_size(path)
        if shutil.which(command[0]) is None:
            print(f"skipping {label}: {command[0]} not on PATH ({human(before)} cached)")
            continue
        if not delete:
            total += before
            print(f"would run: {' '.join(command)} — {label} cache is {human(before)} (upper bound)")
            continue

        print(f"running: {' '.join(command)} — {label} cache is {human(before)}")
        subprocess.run(command, capture_output=True, check=False)
        freed = before - (dir_size(path) if path.exists() else 0)
        total += freed
        print(f"  freed {human(freed)} of {human(before)}")
    if not total:
        print("no package caches present")
    elif delete:
        print(f"subtotal: {human(total)}")
    else:
        print(f"subtotal: {human(total)} (upper bound)")
    return total


# %%
# Cleanup 7: powerlog telemetry DB leak (root required to delete) #

TELEMETRY_DIR = Path("/private/var/db/powerlog/Library/PerfPowerTelemetry")
POWERLOG_TARGETS = [
    TELEMETRY_DIR / "BackgroundProcessing",  # directory variant of the leak
]
POWERLOG_GLOBS = [
    "CurrentBackgroundProcessingDB.BGSQL*",  # loose-file variant of the leak
]
HOLDER_KILL_RETRIES = 3
HOLDER_RETRY_DELAY_S = 2


def gather_powerlog_targets() -> list[Path]:
    targets = [p for p in POWERLOG_TARGETS if p.exists()]
    for pattern in POWERLOG_GLOBS:
        targets.extend(TELEMETRY_DIR.glob(pattern))
    return [t for t in targets if not any(t != parent and parent in t.parents for parent in targets)]


def find_holders(directory: Path) -> set[int]:
    """Return PIDs holding deleted (unlinked) files under directory."""
    result = subprocess.run(["lsof", "+L1", "-Fpn"], capture_output=True, text=True, check=False)
    pid: int | None = None
    holders: set[int] = set()
    for line in result.stdout.splitlines():
        if line.startswith("p"):
            pid = int(line[1:])
        elif line.startswith("n") and str(directory) in line and pid is not None:
            holders.add(pid)
    return holders


def kill_holders(directory: Path) -> None:
    """TERM (then KILL) processes pinning deleted files under directory."""
    for attempt in range(HOLDER_KILL_RETRIES):
        holders = find_holders(directory)
        if not holders:
            return
        signal_flag = "-TERM" if attempt < HOLDER_KILL_RETRIES - 1 else "-KILL"
        for holder in sorted(holders):
            name = (
                subprocess.run(
                    ["ps", "-p", str(holder), "-o", "comm="],
                    capture_output=True, text=True, check=False,
                ).stdout.strip()
                or "unknown"
            )
            print(f"holder pinning space: {name} (pid {holder}) -> kill {signal_flag}")
            subprocess.run(["kill", signal_flag, str(holder)], check=False)
        time.sleep(HOLDER_RETRY_DELAY_S)

    remaining = find_holders(directory)
    if remaining:
        print(f"warning: PIDs still holding deleted files: {sorted(remaining)}", file=sys.stderr)


def cleanup_powerlog(delete: bool, threshold_gb: float) -> int:
    print("\n── powerlog ──")
    if not TELEMETRY_DIR.is_dir():
        print(f"telemetry dir not found (or unreadable): {TELEMETRY_DIR}")
        return 0

    targets = gather_powerlog_targets()
    if not targets:
        print("no powerlog purge targets present")
        if delete and IS_ROOT:
            kill_holders(TELEMETRY_DIR)
        return 0

    sizes = {t: dir_size(t) for t in targets}
    total = sum(sizes.values())
    for path, size in sorted(sizes.items(), key=lambda kv: -kv[1]):
        print(f"found: {path} ({human(size)})")
    print(f"subtotal: {human(total)} (threshold: {threshold_gb} GB)")

    if total / 1024 ** 3 < threshold_gb:
        print("below threshold, nothing to do")
        return 0
    if not delete:
        return total
    if not IS_ROOT:
        print("skipping delete: needs root (rerun with: sudo python3 scripts/mac_cleanup_all.py --delete)")
        return 0

    for path in sizes:
        print(f"deleting: {path}")
        remove(path)
    kill_holders(TELEMETRY_DIR)
    print("done — daemons relaunch via launchd and rebuild a fresh DB")
    return total


# %%
# Cleanup 8: unified log store (root required to erase) #

LOGSTORE_PATHS = [
    Path("/private/var/db/diagnostics"),
    Path("/private/var/db/uuidtext"),
]
LOGSTORE_ERASE = ["log", "erase", "--all"]


def cleanup_logstore(delete: bool, threshold_gb: float) -> int:
    """Erased with `log erase`, never rm: the store is live, and the daemon
    rebuilds it. This drops local diagnostic history — `log show` goes empty.
    """
    print("\n── logstore ──")
    present = [(p, dir_size(p)) for p in LOGSTORE_PATHS if p.is_dir()]
    if not present:
        print("log store not found (or unreadable)")
        return 0

    total = sum(size for _, size in present)
    for path, size in sorted(present, key=lambda kv: -kv[1]):
        report("found", path, size)
    print(f"subtotal: {human(total)} (threshold: {threshold_gb} GB)")

    if total / 1024 ** 3 < threshold_gb:
        print("below threshold, nothing to do")
        return 0
    if not delete:
        return total
    if not IS_ROOT:
        print("skipping delete: needs root (rerun with: sudo python3 scripts/mac_cleanup_all.py --delete)")
        return 0

    print(f"running: {' '.join(LOGSTORE_ERASE)}")
    subprocess.run(LOGSTORE_ERASE, capture_output=True, check=False)
    return total


# %%
# Main: disk snapshot -> run all cleanups -> disk snapshot -> reclaimed delta #

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delete", action="store_true", help="actually delete (default: dry run)")
    parser.add_argument(
        "--threshold-gb", type=float, default=POWERLOG_THRESHOLD_GB,
        help=f"powerlog: only act above this size (default: {POWERLOG_THRESHOLD_GB})",
    )
    parser.add_argument(
        "--logstore-threshold-gb", type=float, default=LOGSTORE_THRESHOLD_GB,
        help=f"logstore: only erase above this size (default: {LOGSTORE_THRESHOLD_GB})",
    )
    parser.add_argument(
        "--staging-age-days", type=float, default=STAGING_AGE_DAYS,
        help=f"brew staging: only remove entries older than this (default: {STAGING_AGE_DAYS})",
    )
    # parse_known_args so this also runs inside an ipython kernel (which adds its own argv)
    args, _ = parser.parse_known_args()
    delete = args.delete or DELETE

    mode = "DELETE" if delete else "DRY RUN"
    print(f"mac cleanup — mode: {mode}, root: {IS_ROOT}, home: {HOME}")
    if delete and not IS_ROOT:
        print("note: not root — powerlog and logstore purges will be skipped (use: sudo python3 ...)")
    if delete and IS_ROOT:
        print("note: root — package cache prunes will be skipped (rerun without sudo)")

    before = disk_bar("before")

    reported = 0
    reported += cleanup_purge_paths(delete)
    reported += cleanup_vscode_extensions(delete)
    reported += cleanup_brew_staging(delete, args.staging_age_days)
    reported += cleanup_browser_caches(delete)
    reported += cleanup_app_logs(delete)
    reported += cleanup_package_caches(delete)
    reported += cleanup_powerlog(delete, args.threshold_gb)
    reported += cleanup_logstore(delete, args.logstore_threshold_gb)

    print(f"\ntotal {'deleted' if delete else 'deletable'}: {human(reported)}")

    after = disk_bar("after")
    if delete:
        reclaimed = after.free - before.free
        print(f"reclaimed: {human(reclaimed)} (free {human(before.free)} -> {human(after.free)})")
        if reported and reclaimed < reported // 2:
            print("note: free space grew less than deleted size — APFS purgeable space "
                  "or lingering file holders may release it shortly")
    else:
        print("dry run — rerun with --delete (or DELETE = True) to purge")


if __name__ == "__main__":
    main()

# %%
