# %%
# Running Imports #

import os

import paramiko
from config import parent_dir
from scp import SCPClient
from dotenv import load_dotenv
from utils.display_tools import print_logger

# %%
# Variables #


dotenv_path = os.path.join(parent_dir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


# Example usage
ssh_host = os.getenv("HOME_ASSISTANT_IP")
ssh_port = 22  # Default SSH port
ssh_username = os.getenv("HOME_ASSISTANT_USERNAME")
ssh_password = os.getenv("HOME_ASSISTANT_PASSWORD")


# %%
# Functions #


def backup_storage_via_ssh(
    ssh_host, ssh_port, ssh_username, ssh_password, remote_path, local_path
):
    # Establish SSH connection
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(
        hostname=ssh_host, port=ssh_port, username=ssh_username, password=ssh_password
    )

    print_logger(f"Connected to {ssh_host}")

    # cd to remote_path
    stdin, stdout, stderr = ssh_client.exec_command(
        f"cd {remote_path} && pwd && ls -al"
    )
    print_logger(stdout.read().decode("utf-8"))

    # SCPCLient takes a paramiko transport as its only argument
    scp = SCPClient(ssh_client.get_transport())

    # Use the SCPClient get method to copy the remote file at 'remote_path'
    # to the local file at 'local_path'. If you're copying a directory,
    # you need to use the recursive option:
    scp.get(remote_path, local_path, recursive=True)

    # Close SCP Client
    scp.close()

    # Close SSH connection
    ssh_client.close()

    print_logger(f"Backup of {remote_path} to {local_path} complete")


# %%
# Main #


if __name__ == "__main__":
    remote_path = "/root/homeassistant/configuration.yaml"  # Remote path of configuration.yaml file
    local_path = os.path.join(
        parent_dir, "application_configs", "homeassistant", "behemoth"
    )
    os.makedirs(local_path, exist_ok=True)
    backup_storage_via_ssh(
        ssh_host,
        ssh_port,
        ssh_username,
        ssh_password,
        remote_path,
        local_path,
    )


# %%
