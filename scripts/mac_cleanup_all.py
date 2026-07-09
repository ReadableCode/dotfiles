#!/usr/bin/env python3
# %%
"""Run all mac cleanup tasks with before/after disk-usage bars.

Combines the three standalone cleanups:
  1. purge_paths        — regrowing updater/cache junk in ~/Library (no root)
  2. vscode_extensions  — outdated VS Code extension versions (no root)
  3. powerlog           — PerfPowerTelemetry DB leak (root required to delete)

Dry run by default. Enable deletion either way:
  script:   sudo python3 scripts/mac_cleanup_all.py --delete
  ipython:  set DELETE = True in the config cell and run the cells

Run with sudo so the powerlog purge can act; the user-home cleanups still
resolve the real user's home via SUDO_USER. Without sudo, the powerlog step
reports what it would do (or can't read) and is skipped on delete.
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

# %%
# Config — edit these when running as ipython cells (CLI flags override) #

DELETE = False               # False = dry run; True = actually delete
POWERLOG_THRESHOLD_GB = 2.0  # only purge powerlog DB above this size
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
    if path.is_file():
        return path.stat().st_size
    total = 0
    for f in path.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
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
    HOME / "Library" / "Caches" / "bitwarden-updater",
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
        print(f"{action}: {path} ({human(size)})")
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
# Cleanup 3: powerlog telemetry DB leak (root required to delete) #

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
# Main: disk snapshot -> run all cleanups -> disk snapshot -> reclaimed delta #

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delete", action="store_true", help="actually delete (default: dry run)")
    parser.add_argument(
        "--threshold-gb", type=float, default=POWERLOG_THRESHOLD_GB,
        help=f"powerlog: only act above this size (default: {POWERLOG_THRESHOLD_GB})",
    )
    # parse_known_args so this also runs inside an ipython kernel (which adds its own argv)
    args, _ = parser.parse_known_args()
    delete = args.delete or DELETE

    mode = "DELETE" if delete else "DRY RUN"
    print(f"mac cleanup — mode: {mode}, root: {IS_ROOT}, home: {HOME}")
    if delete and not IS_ROOT:
        print("note: not root — powerlog purge will be skipped (use: sudo python3 ...)")

    before = disk_bar("before")

    reported = 0
    reported += cleanup_purge_paths(delete)
    reported += cleanup_vscode_extensions(delete)
    reported += cleanup_powerlog(delete, args.threshold_gb)

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
