# %%
# Imports #

import argparse
import contextlib
import difflib
import io
import json
import os
import sys
import tempfile
import time

# %%
# Variables #

BASE_NAME = "personal_bookmarks"
# The repo copy keeps only what describes the tree. Chrome's guid, id,
# date_modified, date_last_used and meta_info change on every sync and differ
# between the duplicate copies, so keeping them makes every diff unreadable.
URL_KEYS = ("date_added", "name", "type", "url")
FOLDER_KEYS = ("children", "date_added", "name", "type")
ATTR_ESCAPES = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"))
TEXT_ESCAPES = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"))
# How much of the diff --check prints: enough to recognise what moved, not the
# whole export again.
DIFF_PREVIEW_LINES = 20


# %%
# Functions #


def get_default_bookmarks_file_path(profile="Default"):
    # sys.platform distinguishes macOS from Linux; os.name calls both "posix"
    if sys.platform == "darwin":
        return os.path.expanduser(
            f"~/Library/Application Support/Google/Chrome/{profile}/Bookmarks"
        )
    elif sys.platform.startswith("linux"):
        return os.path.expanduser(f"~/.config/google-chrome/{profile}/Bookmarks")
    elif os.name == "nt":
        return os.path.join(
            os.getenv("LOCALAPPDATA"), f"Google/Chrome/User Data/{profile}/Bookmarks"
        )
    else:
        raise OSError("Unsupported operating system")


def repo_bookmarks_dir():
    # personal_credentials is a sibling repo of dotfiles on every personal machine
    repo_parent = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    return os.path.join(repo_parent, "personal_credentials", "bookmarks")


def get_bookmarks_dir():
    bookmarks_dir = repo_bookmarks_dir()
    if not os.path.isdir(bookmarks_dir):
        raise FileNotFoundError(f"bookmarks folder not found at {bookmarks_dir}")
    return bookmarks_dir


def get_repo_json_path(bookmarks_dir=None):
    """The committed copy's path, whether or not personal_credentials is cloned."""
    return os.path.join(bookmarks_dir or repo_bookmarks_dir(), f"{BASE_NAME}.json")


def read_bookmarks(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def merge_children(children, path="", report=None):
    """Collapse the duplication Chrome Sync leaves behind.

    Same-name sibling folders become one folder holding both children lists (the
    additions made to either copy survive); a url already present in the same
    folder is dropped. First-seen order is kept, then the merge recurses. ``report``
    collects one line per merge or drop so the run can show what it did.
    """
    merged = []
    folders_by_name = {}
    seen_urls = set()
    for child in children:
        if child.get("type") == "folder":
            name = child.get("name", "")
            if name in folders_by_name:
                folders_by_name[name]["children"].extend(child.get("children", []))
                if report is not None:
                    report.append(f"merged folder {path}/{name}")
                continue
            folder = dict(child)
            folder["children"] = list(child.get("children", []))
            folders_by_name[name] = folder
            merged.append(folder)
        else:
            url = child.get("url", "")
            if url in seen_urls:
                if report is not None:
                    report.append(f"dropped duplicate {path}/{child.get('name', '')}")
                continue
            seen_urls.add(url)
            merged.append(child)
    for folder in folders_by_name.values():
        folder["children"] = merge_children(
            folder["children"], f"{path}/{folder.get('name', '')}", report
        )
    return merged


def normalize_node(node):
    """Keep only the tree-describing keys, recursively, in a fixed key order."""
    if node.get("type") == "url":
        return {key: node.get(key, "") for key in URL_KEYS}
    normalized = {key: node.get(key, "") for key in FOLDER_KEYS if key != "children"}
    normalized["children"] = [normalize_node(child) for child in node.get("children", [])]
    return normalized


def dedupe_bookmarks(bookmarks, report=None):
    """Return a roots+version document with every root deduped and normalized.

    Chrome's checksum and sync_metadata are dropped: they describe the live
    file, not the tree. Bookmark order is Chrome's own order, never sorted.
    """
    roots = {}
    for root_name, root in bookmarks["roots"].items():
        if not isinstance(root, dict):
            continue
        deduped = dict(root)
        deduped["children"] = merge_children(root.get("children", []), root_name, report)
        roots[root_name] = normalize_node(deduped)
    return {"roots": roots, "version": bookmarks.get("version", 1)}


def _chrome_time_to_unix(chrome_timestamp):
    # Chrome timestamps are microseconds since 1601-01-01
    try:
        return str(int(int(chrome_timestamp) / 1_000_000 - 11644473600))
    except (TypeError, ValueError):
        return str(int(time.time()))


def _escape(value, escapes):
    # html.escape(quote=True) turns ' into &#x27;, which Chrome's importer does
    # not decode - the 2026-08 import left names reading "Charlie&#x27;s Site".
    for raw, escaped in escapes:
        value = value.replace(raw, escaped)
    return value


def _emit_netscape_node(node, depth, lines, toolbar=False):
    indent = "    " * depth
    add_date = _chrome_time_to_unix(node.get("date_added", "0"))
    name = _escape(node.get("name", ""), TEXT_ESCAPES)
    if node.get("type") == "url":
        href = _escape(node["url"], ATTR_ESCAPES)
        lines.append(f'{indent}<DT><A HREF="{href}" ADD_DATE="{add_date}">{name}</A>')
        return
    toolbar_attr = ' PERSONAL_TOOLBAR_FOLDER="true"' if toolbar else ""
    lines.append(f'{indent}<DT><H3 ADD_DATE="{add_date}"{toolbar_attr}>{name}</H3>')
    lines.append(f"{indent}<DL><p>")
    for child in node.get("children", []):
        _emit_netscape_node(child, depth + 1, lines)
    lines.append(f"{indent}</DL><p>")


def export_bookmarks_as_html(bookmarks, output_file_path):
    """Write a Netscape-format HTML file Chrome can import via the Bookmark Manager.

    Importing through the live Bookmark Manager goes through the bookmarks API,
    so the changes are real sync operations that propagate to all devices.
    Swapping the Bookmarks file on disk does NOT survive Chrome Sync - the
    server state wins on next launch. Always deploy via import, never file swap.

    Layout matches Chrome's own export: the bookmark bar is the folder flagged
    PERSONAL_TOOLBAR_FOLDER, everything from the other roots sits beside it and
    lands in Other Bookmarks.
    """
    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
        "<DL><p>",
    ]
    roots = bookmarks["roots"]
    _emit_netscape_node(roots["bookmark_bar"], 1, lines, toolbar=True)
    for root_name in ("other", "synced"):
        for child in roots.get(root_name, {}).get("children", []):
            _emit_netscape_node(child, 1, lines)
    lines.append("</DL><p>")

    with open(output_file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Exported importable HTML to: {output_file_path}")


def count_urls(children):
    total = 0
    for child in children:
        if child.get("type") == "folder":
            total += count_urls(child.get("children", []))
        else:
            total += 1
    return total


def write_outputs(bookmarks, output_dir):
    report = []
    before = sum(count_urls(r.get("children", [])) for r in bookmarks["roots"].values() if isinstance(r, dict))
    deduped = dedupe_bookmarks(bookmarks, report)
    after = sum(count_urls(r.get("children", [])) for r in deduped["roots"].values())
    for line in report:
        print(line)
    print(f"{before} bookmarks in, {after} out")

    json_path = os.path.join(output_dir, f"{BASE_NAME}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(deduped, f, ensure_ascii=False, indent=3, sort_keys=True)
        f.write("\n")
    print(f"Exported deduped bookmarks JSON to: {json_path}")
    export_bookmarks_as_html(deduped, os.path.join(output_dir, f"{BASE_NAME}.html"))


def check_drift(bookmarks, repo_json_path):
    """Report how the live bookmarks differ from the committed copy, writing nothing to the repo.

    The read-only twin of a normal run: the export goes to a temporary
    directory, so a probe never leaves a file in personal_credentials or
    updates it behind a real export. Returns the exit code - 1 when the two
    differ, 0 when they match and 0 when there is no committed copy to compare
    against (personal_credentials not cloned, or bookmarks never exported).
    """
    if not os.path.exists(repo_json_path):
        print(f"No committed copy at {repo_json_path}; nothing to compare against.")
        return 0
    with tempfile.TemporaryDirectory() as temp_dir:
        # The export names the temporary directory it wrote to, which is noise
        # in a drift report; the diff below is the report.
        with contextlib.redirect_stdout(io.StringIO()):
            write_outputs(bookmarks, temp_dir)
        with open(get_repo_json_path(temp_dir), "r", encoding="utf-8") as f:
            fresh = f.readlines()
    with open(repo_json_path, "r", encoding="utf-8") as f:
        committed = f.readlines()

    diff = list(difflib.unified_diff(committed, fresh, fromfile="repo copy", tofile="chrome now"))
    if not diff:
        print(f"Bookmarks match {repo_json_path}.")
        return 0
    print(f"Bookmarks differ from {repo_json_path} ({len(diff)} diff lines):")
    for line in diff[:DIFF_PREVIEW_LINES]:
        print(line.rstrip("\n"))
    if len(diff) > DIFF_PREVIEW_LINES:
        print(f"... and {len(diff) - DIFF_PREVIEW_LINES} more diff lines")
    print("Run this script with no arguments to update the repo copy.")
    return 1


# %%
# Main Run #

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Save Chrome bookmarks to the personal_credentials repo, collapsing the "
            "duplicate folders Chrome Sync creates when a device reconnects. Writes "
            f"{BASE_NAME}.json (the editable copy) and {BASE_NAME}.html (for re-import "
            "through the Bookmark Manager). --check writes nothing and only reports "
            "drift. See docs/repo_chrome_bookmarks.md."
        )
    )
    parser.add_argument(
        "--profile",
        default="Default",
        help='Chrome profile directory name (default "Default", the personal profile)',
    )
    parser.add_argument(
        "--input",
        help="read this bookmarks JSON (e.g. the repo copy after editing) instead of the live Chrome file",
    )
    parser.add_argument(
        "--output-dir",
        help="override output directory (default: personal_credentials/bookmarks)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; report how the live bookmarks differ from the repo copy and exit 1 if they do",
    )
    args = parser.parse_args()

    source = args.input or get_default_bookmarks_file_path(args.profile)
    if not os.path.exists(source):
        sys.exit(f"bookmarks file not found: {source}")
    bookmarks = read_bookmarks(source)
    if args.check:
        sys.exit(check_drift(bookmarks, get_repo_json_path()))
    write_outputs(bookmarks, args.output_dir or get_bookmarks_dir())


# %%
