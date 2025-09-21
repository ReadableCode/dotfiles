# %%
# Imports #

import os
import platform
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import paramiko
from config import grandparent_dir
from dotenv import load_dotenv
from utils.host_tools import get_uppercase_hostname

# %%
# Variables #

dotenv_path = os.path.join(grandparent_dir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

system = platform.system()

if system == "Windows":
    print("Running on Windows")
elif system == "Linux":
    print("Running on Linux")
elif system == "Darwin":
    print("Running on macOS")
else:
    print(f"Running on an unknown system: {system}")


# %%
# Variables #

HOSTNAME = get_uppercase_hostname()
HOSTNAME_LOWER = HOSTNAME.lower()

print(f"hostname: {HOSTNAME}")

# %%
# Functions #


def deploy_config(
    repo_path, system_path, ingest_system_if_exists=False, backup_into_repo=True
):
    """
    Keeps the real file in the repo and creates a symlink on linux or a hard link on windows in a locatoin 'system_path'
    options to ingest a file already on the system and to backup an existing system file into the repo
    """

    print(
        f"Deploying configs from {repo_path} to {system_path} with ingest={ingest_system_if_exists}, backup={backup_into_repo}"
    )
    repo_exists = os.path.exists(repo_path)
    system_exists = os.path.exists(system_path)
    print(f"Repo exists: {repo_exists}, System exists: {system_exists}")

    # case when repo exists, system doesnt exist
    if repo_exists and not system_exists:
        print("Case 1: Repo exists, system does not exist")
        if system == "Windows":
            os.link(repo_path, system_path)
            print(f"Created hard link from {repo_path} to {system_path}")
        else:
            os.symlink(repo_path, system_path)
            print(f"Created symlink from {repo_path} to {system_path}")
    elif not repo_exists and system_exists:
        print("Case 2: Repo does not exist, system exists")
        if ingest_system_if_exists:
            os.makedirs(os.path.dirname(repo_path), exist_ok=True)
            os.rename(system_path, repo_path)
            print(f"Moved {system_path} to {repo_path}")
            if system == "Windows":
                os.link(repo_path, system_path)
                print(f"Created hard link from {repo_path} to {system_path}")
            else:
                os.symlink(repo_path, system_path)
                print(f"Created symlink from {repo_path} to {system_path}")
        else:
            print(f"Skipping ingestion of existing system file {system_path} into repo")
    elif repo_exists and system_exists:
        print("Case 3: Both repo and system exist")
        if backup_into_repo:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            backup_path = f"{repo_path}.backup.{timestamp}"
            shutil.copy2(system_path, backup_path)
            print(f"Backed up {repo_path} to {backup_path}")
            os.rename(system_path, repo_path)
            print(f"Moved {system_path} to {repo_path}")
            if system == "Windows":
                os.link(repo_path, system_path)
                print(f"Created hard link from {repo_path} to {system_path}")
            else:
                os.symlink(repo_path, system_path)
                print(f"Created symlink from {repo_path} to {system_path}")
        else:
            print(
                f"Skipping backup of existing repo file {repo_path}. No changes made."
            )
    else:
        print("Case 4: Neither repo nor system exist. No action taken.")


# %%
# Main #

if __name__ == "__main__":
    print("Deploying configs")


# %%
