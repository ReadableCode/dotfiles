# %%
# Running Imports #

import os
import subprocess

from config import parent_dir
from dotenv import load_dotenv
from utils.display_tools import print_logger

# %%
# Variables #

host_operating_system = "Windows" if os.name == "nt" else "Linux"

dotenv_path = os.path.join(parent_dir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


UNRAID_IP = os.getenv("UNRAID_IP")
ELITEDESK_IP = os.getenv("ELITEDESK_IP")

# %%
# Main #


def get_mapped_server_path(ls_server_path):
    if host_operating_system == "Windows":
        path_prefix = "\\\\"
        server_path = path_prefix + "\\".join(ls_server_path)

    return server_path


def pull_configs_from_server(server_path, repo_path, copy_filter):
    print_logger(f"Pulling configs from {server_path} to {repo_path}")
    # Create the repo_path if it doesn't exist
    os.makedirs(repo_path, exist_ok=True)

    subprocess.run(
        [
            "robocopy",
            server_path,
            repo_path,
            copy_filter,  # Filter to only copy .conf files
            "/MIR",  # enable to mirror the source directory
            "/Z",  # enable to restartable mode
            "/R:5",  # number of retries on failed copies
            "/W:5",  # wait time between retries
        ]
    )


def push_configs_to_server(server_path, repo_path, copy_filter):
    print_logger(f"Pushing configs from {repo_path} to {server_path}")
    # Create the repo_path if it doesn't exist
    os.makedirs(server_path, exist_ok=True)

    subprocess.run(
        [
            "robocopy",
            repo_path,
            server_path,
            copy_filter,  # Filter to only copy .conf files
            "/MIR",  # enable to mirror the source directory
            "/Z",  # enable to restartable mode
            "/R:5",  # number of retries on failed copies
            "/W:5",  # wait time between retries
        ]
    )


def push_or_pull_configs(push_or_pull, server_path, repo_path, copy_filter):
    if push_or_pull == "pull":
        pull_configs_from_server(server_path, repo_path, copy_filter)
    elif push_or_pull == "push":
        push_configs_to_server(server_path, repo_path, copy_filter)


# %%
# behemoth: swag #

if __name__ == "__main__":
    push_or_pull = "pull"

    repo_path = os.path.join(
        parent_dir,
        "application_configs",
        "swag",
        "behemoth",
    )
    ls_server_path = [UNRAID_IP, "appdata", "swag", "nginx"]
    copy_filter = "ssl.conf"
    server_path = get_mapped_server_path(ls_server_path)

    push_or_pull_configs(push_or_pull, server_path, repo_path, copy_filter)

    repo_path = os.path.join(
        parent_dir, "application_configs", "swag", "behemoth", "proxy-confs"
    )
    ls_server_path = [UNRAID_IP, "appdata", "swag", "nginx", "proxy-confs"]
    copy_filter = "*.conf"
    server_path = get_mapped_server_path(ls_server_path)

    push_or_pull_configs(push_or_pull, server_path, repo_path, copy_filter)


# %%
# behemoth: nextcloud #

if __name__ == "__main__":
    push_or_pull = "pull"
    repo_path = os.path.join(parent_dir, "application_configs", "nextcloud", "behemoth")
    ls_server_path = [
        UNRAID_IP,
        "appdata",
        "nextcloud",
        "www",
        "nextcloud",
        "config",
    ]
    copy_filter = "*.php"
    server_path = get_mapped_server_path(ls_server_path)

    push_or_pull_configs(push_or_pull, server_path, repo_path, copy_filter)


# %%
# behemoth: nzbget #

if __name__ == "__main__":
    push_or_pull = "pull"
    repo_path = os.path.join(parent_dir, "application_configs", "nzbget", "behemoth")
    ls_server_path = [UNRAID_IP, "appdata", "binhex-nzbget"]
    copy_filter = "*.conf"

    server_path = get_mapped_server_path(ls_server_path)

    push_or_pull_configs(push_or_pull, server_path, repo_path, copy_filter)


# %%
# elitedesk: nzbget #

if __name__ == "__main__":
    push_or_pull = "pull"
    repo_path = os.path.join(parent_dir, "application_configs", "nzbget", "elitedesk")
    ls_server_path = [ELITEDESK_IP, "docker_app_data", "nzbget"]
    copy_filter = "*.conf"

    server_path = get_mapped_server_path(ls_server_path)

    push_or_pull_configs(push_or_pull, server_path, repo_path, copy_filter)


# %%
# Main #

if __name__ == "__main__":
    print_logger("Done")


# %%
