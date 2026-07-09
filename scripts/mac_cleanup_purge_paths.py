#!/usr/bin/env python3
"""Purge known regrowing junk paths (updater staging dirs, stale caches).

These are directories that apps regenerate as needed and never clean up:
Squirrel/ShipIt auto-updater payloads are dead the moment an update applies.
Safe to remove at any time; worst case an app re-downloads a pending update.
Runs as the regular user — no root required.
"""

import argparse
import shutil
from pathlib import Path

HOME = Path.home()
PURGE_PATHS = [
    HOME / "Library" / "Caches" / "com.microsoft.VSCode.ShipIt",
    HOME / "Library" / "Caches" / "com.tinyspeck.slackmacgap.ShipIt",
    HOME / "Library" / "Caches" / "bitwarden-updater",
]


def dir_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--delete", action="store_true", help="actually delete (default: dry run)"
    )
    args = parser.parse_args()

    found = [(p, dir_size(p)) for p in PURGE_PATHS if p.exists()]
    if not found:
        print("no purge targets present")
        return

    total = 0
    for path, size in sorted(found, key=lambda kv: -kv[1]):
        total += size
        action = "deleting" if args.delete else "would delete"
        print(f"{action}: {path} ({size / 1024**2:.0f} MB)")
        if args.delete:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)

    print(f"total: {total / 1024**2:.0f} MB")


if __name__ == "__main__":
    main()
