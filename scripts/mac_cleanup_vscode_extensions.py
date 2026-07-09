#!/usr/bin/env python3
"""Remove outdated versions of VS Code extensions, keeping only the newest of each."""

import argparse
import re
import shutil
from collections import defaultdict
from pathlib import Path

EXT_DIR = Path.home() / ".vscode" / "extensions"
# publisher.name-1.2.3 or publisher.name-1.2.3-darwin-arm64
PATTERN = re.compile(
    r"^(?P<ext_id>.+?)-(?P<version>\d+(?:\.\d+)+)(?P<platform>-[a-z0-9-]+)?$"
)


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def find_outdated(ext_dir: Path) -> list[Path]:
    groups: dict[str, list[tuple[tuple[int, ...], Path]]] = defaultdict(list)

    for entry in ext_dir.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        match = PATTERN.match(entry.name)
        if not match:
            continue
        key = match["ext_id"] + (match["platform"] or "")
        groups[key].append((version_key(match["version"]), entry))

    outdated: list[Path] = []
    for versions in groups.values():
        if len(versions) > 1:
            versions.sort(reverse=True)
            outdated.extend(path for _, path in versions[1:])
    return outdated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--delete", action="store_true", help="actually delete (default: dry run)"
    )
    args = parser.parse_args()

    if not EXT_DIR.is_dir():
        raise SystemExit(f"extensions dir not found: {EXT_DIR}")

    outdated = find_outdated(EXT_DIR)
    if not outdated:
        print("no outdated extension versions found")
        return

    total = 0
    for path in sorted(outdated):
        size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        total += size
        action = "deleting" if args.delete else "would delete"
        print(f"{action}: {path.name} ({size / 1024 / 1024:.0f} MB)")
        if args.delete:
            shutil.rmtree(path)

    print(f"\ntotal: {total / 1024 / 1024:.0f} MB")


# %%
# Main #

if __name__ == "__main__":
    main()


# %%
