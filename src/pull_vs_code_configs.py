# %%
# Running Imports #

import os
import shutil

from config import grandparent_dir, parent_dir
from utils.display_tools import print_logger

# %%
# Variables #

host_operating_system = "Windows" if os.name == "nt" else "Linux"

if os.path.exists(os.path.join(grandparent_dir, "Our_Cash")):
    print_logger("Detected personal config")
    config_type = "personal"
else:
    print_logger("Detected work config")
    config_type = "hellofresh"


# %%
# Copying Files #


def pull_workspace_config():
    ls_possible_locations = [
        os.path.join(grandparent_dir, "myworkspace.code-workspace"),
        os.path.join(grandparent_dir, "MyWorkspace.code-workspace"),
    ]
    for possible_location in ls_possible_locations:
        if os.path.isfile(possible_location):
            src_file_path = possible_location
            break
    else:
        raise (
            FileNotFoundError(
                "No workspace file found in grandparent_dir. Please add one."
            )
        )
    dest_file_path = os.path.join(
        parent_dir,
        "application_configs",
        "vscode",
        f"vs_code_workspaces_{config_type}.json",
    )
    print_logger(f"Copying {src_file_path} to {dest_file_path}")
    shutil.copy(
        src_file_path,
        dest_file_path,
    )


def pull_vs_code_configs():
    # find vs_code configs based on os
    if host_operating_system == "Windows":
        vs_code_config_dir = os.path.join(
            os.path.expandvars("%APPDATA%"), "Code", "User"
        )
    else:
        vs_code_config_dir = os.path.join(
            os.path.expanduser("~"), ".config", "Code", "User"
        )

    # C:\Users\jason\AppData\Roaming\Code\User\settings.json
    # C:\Users\jason\AppData\Roaming\Code\User\User\settings.json
    path_to_vs_code_settings = os.path.join(
        vs_code_config_dir,
        "settings.json",
    )
    print(path_to_vs_code_settings)
    if os.path.isfile(path_to_vs_code_settings):
        print_logger(f"Copying {path_to_vs_code_settings} to {parent_dir}")
        shutil.copy(
            path_to_vs_code_settings,
            os.path.join(
                parent_dir,
                "application_configs",
                "vscode",
                f"vs_code_settings_{config_type}.json",
            ),
        )


# %%
# Main #


if __name__ == "__main__":
    pull_workspace_config()
    pull_vs_code_configs()
    print_logger("Done")


# %%
