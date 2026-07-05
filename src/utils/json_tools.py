# %%
# Imports #

import json
import os
import sys

# %%
# Functions #


def sort_json_for_diff(obj):
    """Recursively sort lists of objects by a stable identifier.

    Bitwarden's ``bw export --format json`` does not guarantee a stable order
    for the *items* inside lists, which produces huge, meaningless diffs in the
    credentials repo. Object *keys* are sorted at dump time via
    ``sort_keys=True``; this handles the list ordering that ``sort_keys`` does
    not touch (lists preserve their order).
    """
    if isinstance(obj, dict):
        return {key: sort_json_for_diff(value) for key, value in obj.items()}
    if isinstance(obj, list):
        items = [sort_json_for_diff(value) for value in obj]
        if items and all(isinstance(value, dict) for value in items):
            for stable_key in ("id", "name"):
                if all(value.get(stable_key) is not None for value in items):
                    items = sorted(items, key=lambda value: str(value[stable_key]))
                    break
        return items
    return obj


def normalize_json_file(path):
    """Rewrite ``path`` in place in a deterministic, diff-friendly form.

    Both the live Bitwarden export (the backup job lives in the local
    ``personal-automation`` repo, which vendors a copy of this module) and a
    one-off normalization of an existing baseline call this, so the output is
    byte-for-byte comparable across runs.
    """
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    data = sort_json_for_diff(data)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def _iter_json_paths(paths):
    for path in paths:
        if os.path.isdir(path):
            for root, _dirs, files in os.walk(path):
                for name in sorted(files):
                    if name.endswith(".json"):
                        yield os.path.join(root, name)
        elif path.endswith(".json"):
            yield path


def main(argv):
    """Normalize the given .json files / directories in place.

    Usage: ``python src/utils/json_tools.py <file-or-dir> [...]``
    """
    paths = argv or ["."]
    count = 0
    for json_path in _iter_json_paths(paths):
        normalize_json_file(json_path)
        print(f"normalized {json_path}")
        count += 1
    print(f"normalized {count} file(s)")


# %%
# Main #

if __name__ == "__main__":
    main(sys.argv[1:])
