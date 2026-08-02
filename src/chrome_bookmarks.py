# %%
# Imports #

import argparse
import html
import json
import os
import sys
import time

from config import data_dir
from readable_utils.host_tools import get_uppercase_hostname

# %%
# Variables #

HOSTNAME = get_uppercase_hostname()
HOSTNAME_LOWER = HOSTNAME.lower()


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


def get_personal_credentials_dir():
    # personal_credentials is a sibling repo of dotfiles on every personal machine
    repo_parent = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    personal_credentials_dir = os.path.join(repo_parent, "personal_credentials")
    if os.path.isdir(personal_credentials_dir):
        return personal_credentials_dir
    print(
        f"personal_credentials not found at {personal_credentials_dir}, "
        f"falling back to data_dir"
    )
    return data_dir


def get_chrome_bookmarks_as_json(profile="Default"):
    bookmarks_file_path = get_default_bookmarks_file_path(profile)

    if not os.path.exists(bookmarks_file_path):
        print(f"Chrome bookmarks file not found at: {bookmarks_file_path}")
        return None

    with open(bookmarks_file_path, "r", encoding="utf-8") as f:
        bookmarks = json.load(f)

    return bookmarks


def export_bookmarks_as_json(output_file_path, profile="Default"):
    bookmarks = get_chrome_bookmarks_as_json(profile)
    if bookmarks is None:
        return False

    with open(output_file_path, "w", encoding="utf-8") as f:
        json.dump(bookmarks, f, ensure_ascii=False, indent=4)
    print(f"Exported raw bookmarks JSON to: {output_file_path}")
    return True


def _chrome_time_to_unix(chrome_timestamp):
    # Chrome timestamps are microseconds since 1601-01-01
    try:
        return str(int(int(chrome_timestamp) / 1_000_000 - 11644473600))
    except (TypeError, ValueError):
        return str(int(time.time()))


def _emit_netscape_node(node, depth, lines):
    indent = "    " * depth
    if node.get("type") == "url":
        href = html.escape(node["url"], quote=True)
        add_date = _chrome_time_to_unix(node.get("date_added", "0"))
        name = html.escape(node.get("name", ""))
        lines.append(f'{indent}<DT><A HREF="{href}" ADD_DATE="{add_date}">{name}</A>')
    else:
        add_date = _chrome_time_to_unix(node.get("date_added", "0"))
        name = html.escape(node.get("name", ""))
        lines.append(f'{indent}<DT><H3 ADD_DATE="{add_date}">{name}</H3>')
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
    """
    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
        "<DL><p>",
    ]
    for child in bookmarks["roots"]["bookmark_bar"]["children"]:
        _emit_netscape_node(child, 1, lines)
    lines.append("</DL><p>")

    with open(output_file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Exported importable HTML to: {output_file_path}")


# %%
# Main Run #

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Back up Chrome bookmarks to the personal_credentials repo. "
            "Default action exports the raw Bookmarks JSON; --html additionally "
            "writes a Netscape HTML file for sync-safe re-import through the "
            "Bookmark Manager."
        )
    )
    parser.add_argument(
        "--profile",
        default="Default",
        help='Chrome profile directory name (e.g. "Default", "Profile 3")',
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="also write a Netscape-format HTML import file next to the JSON",
    )
    parser.add_argument(
        "--input",
        help=(
            "convert an existing bookmarks JSON (e.g. one edited in the repo) "
            "instead of reading the live Chrome file; implies --html"
        ),
    )
    parser.add_argument(
        "--output-dir",
        help="override output directory (default: personal_credentials repo)",
    )
    args = parser.parse_args()

    output_dir = args.output_dir or get_personal_credentials_dir()
    base_name = f"chrome_bookmarks_{HOSTNAME_LOWER}"

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            bookmarks = json.load(f)
        html_path = os.path.splitext(args.input)[0] + ".html"
        export_bookmarks_as_html(bookmarks, html_path)
    else:
        json_path = os.path.join(output_dir, f"{base_name}.json")
        if export_bookmarks_as_json(json_path, args.profile) and args.html:
            bookmarks = get_chrome_bookmarks_as_json(args.profile)
            export_bookmarks_as_html(
                bookmarks, os.path.join(output_dir, f"{base_name}.html")
            )


# %%
