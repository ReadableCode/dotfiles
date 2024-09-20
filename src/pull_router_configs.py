# %%
# Imports #

import glob
import gzip
import hashlib
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import paramiko
from config import data_dir, parent_dir
from dotenv import load_dotenv
from scp import SCPClient
from utils.display_tools import pprint_df, print_logger

# %%
# Variables #

# TODO URGENT: not working because router doesnt have sftp installed

dotenv_path = os.path.join(parent_dir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


# Example usage
ssh_host = os.getenv("ROUTER_IP")
ssh_port = 22  # Default SSH port
ssh_username = os.getenv("ROUTER_USERNAME")

already_cloned = False


# %%
# Functions #


def clone_router_config(
    ssh_host, ssh_port, ssh_username, ssh_password, remote_path, local_path
):
    key_file_path = os.path.expanduser("~/.ssh/id_rsa")
    os.makedirs(local_path, exist_ok=True)

    # Load RSA private key
    private_key = paramiko.RSAKey.from_private_key_file(key_file_path)

    # Establish SSH connection
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(
        hostname=ssh_host,
        port=ssh_port,
        username=ssh_username,
        pkey=private_key,
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
    print_logger(f"Copying {remote_path} to {local_path}")
    scp.get(remote_path, local_path, recursive=True)

    # Close SCP Client
    scp.close()

    # Close SSH connection
    ssh_client.close()

    print_logger("Cloned router configs")


# %%
# Main #

if __name__ == "__main__":
    print("Running in IPython kernel")
    df_all_logs = clone_router_config(
        ssh_host,
        ssh_port,
        ssh_username,
        None,
        "/tmp/nc/",
        os.path.join(
            parent_dir,
            "application_configs",
            "router",
            "asus",
        ),
    )
    # list dest dir
    print_logger("Listing destination directory")
    print_logger(
        os.listdir(os.path.join(parent_dir, "application_configs", "router", "asus"))
    )


# %%
