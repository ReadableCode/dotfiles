# %%
# Imports #

import json
import os
import shutil
import subprocess

from config import data_dir, parent_dir
from dotenv import load_dotenv
from utils.date_tools import get_current_datetime, get_datetime_format_string
from utils.display_tools import print_logger
from utils.host_tools import get_uppercase_hostname

# %%
# Imports #

dotenv_path = os.path.join(parent_dir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


HOSTNAME = get_uppercase_hostname()
print_logger(f"HOSTNAME: {HOSTNAME}")

HOSTNAME_LOWER = HOSTNAME.lower()
CURRENT_DT = get_current_datetime(get_datetime_format_string("%Y%m%d%H%M%S"))

# read bitwarden url from env os.getenv("BITWARDEN_URL")
BITWARDEN_URL = os.getenv("BITWARDEN_URL")
# read org configs from env os.getenv("BITWARDEN_ORG_CONFIGS") as json item
BITWARDEN_ORG_CONFIGS = json.loads(os.getenv("BITWARDEN_ORG_CONFIGS"))


# %%
# Imports #


def login(bitwarden_username, bitwarden_password):
    # set server
    bw_config_command = f"bw config server {BITWARDEN_URL}"
    try:
        subprocess.run(bw_config_command, shell=True, check=True)
        print("Bitwarden server set.")
    except subprocess.CalledProcessError as e:
        print("Error setting Bitwarden server:", e)

    login_command = f"bw login {bitwarden_username} {bitwarden_password}"
    try:
        # Run the login command and capture its output
        result = subprocess.run(
            login_command,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

        # Check if the command was successful and the session key is in the output
        if "To unlock your vault, set your session key to the" in result.stdout:
            # Extract the session key from the output
            session_key = result.stdout.split("BW_SESSION=")[1].strip()

            # Set the session key as an environment variable
            os.environ["BW_SESSION"] = session_key

            print("Logged in to Bitwarden.")
            print(f"Session key: {session_key}")
        else:
            print("Error logging in. Session key not found in output.")
    except subprocess.CalledProcessError as e:
        print("Error logging in:", e)


def export_file(file_type, username, org=None):
    if org:
        org_id = BITWARDEN_ORG_CONFIGS[org]
        org_command = f"--organizationid {org_id} "
    # get filename with hostname from env
    output_file_name = f"bitwarden_backup_{username}_{HOSTNAME_LOWER}{(f'_{org}' if org else '')}.{file_type}"
    output_file_path = os.path.join(data_dir, output_file_name)
    export_command = f'bw export {(org_command if org else "")}--output "{output_file_path}" --format {file_type}'
    try:
        subprocess.run(export_command, shell=True, check=True)
        print("Export command executed successfully.")
    except subprocess.CalledProcessError as e:
        print("Error executing export command:", e)

    # copy output file to archive folder with datetime on it
    archive_output_file_name = f"bitwarden_backup_{username}_{HOSTNAME_LOWER}_{CURRENT_DT}{(f'_{org}' if org else '')}.{file_type}"  # noqa E501
    archive_output_file_path = os.path.join(
        data_dir, "archive", archive_output_file_name
    )
    shutil.copy2(output_file_path, archive_output_file_path)
    print(f"Exported {file_type} file copied to archive folder.")


def export_file_types(username, org=None):
    file_types = ["json", "csv"]
    for file_type in file_types:
        print_logger(f"Exporting {file_type} file.")
        export_file(file_type, username, org=org)


def logout():
    logout_command = "bw logout"
    try:
        subprocess.run(logout_command, shell=True, check=True)
        print("Logged out of Bitwarden.")
    except subprocess.CalledProcessError as e:
        print("Error logging out:", e)


def backup_bitwarden():
    # primary user
    bitwarden_username = os.getenv("BITWARDEN_USERNAME")
    bitwarden_password = os.getenv("BITWARDEN_PASSWORD")
    print_logger(f"Primary user {bitwarden_username} running", as_break=True)
    login(bitwarden_username, bitwarden_password)
    export_file_types(username=bitwarden_username)

    for org, org_id in BITWARDEN_ORG_CONFIGS.items():
        print_logger(f"Exporting {org} org", as_break=True)
        export_file_types(username=bitwarden_username, org=org)

    logout()

    # secondary user
    bitwarden_username = os.getenv("BITWARDEN_USERNAME_SECONDARY")
    bitwarden_password = os.getenv("BITWARDEN_PASSWORD_SECONDARY")
    print_logger(f"Secondary user {bitwarden_username} running", as_break=True)
    login(bitwarden_username, bitwarden_password)
    export_file_types(username=bitwarden_username)
    logout()


# %%
# Main #

if __name__ == "__main__":
    print_logger("Starting Bitwarden backup")
    backup_bitwarden()
    print_logger("Done")


# %%
