# %%
# Imports #

import json
import os

from config import data_dir
from utils.host_tools import get_uppercase_hostname

# %%
# Variables #

HOSTNAME = get_uppercase_hostname()
HOSTNAME_LOWER = HOSTNAME.lower()


# %%
# Functions #


# Get the default Chrome bookmarks file path based on the operating system
def get_default_bookmarks_file_path():
    if os.name == "posix":  # Unix-based system (Linux, macOS)
        return os.path.expanduser("~/.config/google-chrome/Default/Bookmarks")
    elif os.name == "nt":  # Windows
        return os.path.join(
            os.getenv("LOCALAPPDATA"), "Google/Chrome/User Data/Default/Bookmarks"
        )
    else:
        raise OSError("Unsupported operating system")


def get_chrome_bookmarks_as_json():
    # Get the default Chrome bookmarks file path
    bookmarks_file_path = get_default_bookmarks_file_path()

    # Check if the bookmarks file exists
    if not os.path.exists(bookmarks_file_path):
        print("Chrome bookmarks file not found.")
        return None

    # Open the bookmarks file
    with open(bookmarks_file_path, "r", encoding="utf-8") as f:
        # Load the bookmarks file as JSON
        bookmarks = json.load(f)

    return bookmarks


def export_bookmarks_as_json(output_file_path):
    bookmarks = get_chrome_bookmarks_as_json()

    # Export the bookmarks as JSON
    with open(output_file_path, "w", encoding="utf-8") as f:
        json.dump(bookmarks, f, ensure_ascii=False, indent=4)


# %%
# Main Run #

if __name__ == "__main__":
    export_bookmarks_as_json(
        os.path.join(data_dir, f"chrome_bookmarks_{HOSTNAME_LOWER}.json")
    )


# %%
