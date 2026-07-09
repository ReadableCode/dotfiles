#!/usr/bin/env python3
"""Purge macOS powerlog telemetry DB when it exceeds a size threshold.

The PerfPowerTelemetry background-processing database leaks unboundedly on
some builds (observed 12-19 GB). Deleting alone is not enough: daemons
(PerfPowerServices, dasd) hold open file descriptors that pin the space, so
after unlinking, this script finds any process still holding a deleted file
under the telemetry dir and TERMs it. launchd relaunches the daemons and a
fresh, small DB is rebuilt. Requires root for --delete.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

TELEMETRY_DIR = Path("/private/var/db/powerlog/Library/PerfPowerTelemetry")
PURGE_TARGETS = [
    TELEMETRY_DIR / "BackgroundProcessing",  # directory variant of the leak
]
PURGE_GLOBS = [
    "CurrentBackgroundProcessingDB.BGSQL*",  # loose-file variant of the leak
]
DEFAULT_THRESHOLD_GB = 2.0
HOLDER_KILL_RETRIES = 3
HOLDER_RETRY_DELAY_S = 2


def dir_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def gather_targets() -> list[Path]:
    targets = [p for p in PURGE_TARGETS if p.exists()]
    for pattern in PURGE_GLOBS:
        targets.extend(TELEMETRY_DIR.glob(pattern))
    return [
        t
        for t in targets
        if not any(t != parent and parent in t.parents for parent in targets)
    ]


def find_holders(directory: Path) -> set[int]:
    """Return PIDs holding deleted (unlinked) files under directory."""
    result = subprocess.run(
        ["lsof", "+L1", "-Fpn"], capture_output=True, text=True, check=False
    )
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
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout.strip()
                or "unknown"
            )
            print(f"holder pinning space: {name} (pid {holder}) -> kill {signal_flag}")
            subprocess.run(["kill", signal_flag, str(holder)], check=False)
        time.sleep(HOLDER_RETRY_DELAY_S)

    remaining = find_holders(directory)
    if remaining:
        print(
            f"warning: PIDs still holding deleted files: {sorted(remaining)}",
            file=sys.stderr,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--delete", action="store_true", help="actually delete (default: dry run)"
    )
    parser.add_argument(
        "--threshold-gb",
        type=float,
        default=DEFAULT_THRESHOLD_GB,
        help=f"only act if total size exceeds this "
        f"(default: {DEFAULT_THRESHOLD_GB})",
    )
    args = parser.parse_args()

    if args.delete and os.geteuid() != 0:
        raise SystemExit("must run as root to delete (try: sudo)")

    if not TELEMETRY_DIR.is_dir():
        raise SystemExit(f"telemetry dir not found: {TELEMETRY_DIR}")

    targets = gather_targets()
    if not targets:
        print("no powerlog purge targets present")
        kill_holders(TELEMETRY_DIR) if args.delete else None
        return

    sizes = {t: dir_size(t) for t in targets}
    total_gb = sum(sizes.values()) / 1024**3

    for path, size in sorted(sizes.items(), key=lambda kv: -kv[1]):
        print(f"found: {path} ({size / 1024**2:.0f} MB)")
    print(f"total: {total_gb:.2f} GB (threshold: {args.threshold_gb} GB)")

    if total_gb < args.threshold_gb:
        print("below threshold, nothing to do")
        return

    if not args.delete:
        print("dry run — rerun with --delete to purge")
        return

    for path in sizes:
        print(f"deleting: {path}")
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)

    kill_holders(TELEMETRY_DIR)
    print("done — daemons relaunch via launchd and rebuild a fresh DB")


if __name__ == "__main__":
    main()
