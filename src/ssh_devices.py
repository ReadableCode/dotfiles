# %%
# Imports #

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import paramiko
from config import grandparent_dir, parent_dir
from dotenv import load_dotenv
from utils.display_tools import pprint_df, pprint_dict, print_logger

# %%
# Variables #

dotenv_path = os.path.join(grandparent_dir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

ssh_password = os.getenv("SSH_PASSWORD")

with open(os.path.join(parent_dir, "hosts.json"), "r") as f:
    dict_systems = json.load(f)

dict_commands = {
    "cpu_usage": "top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\([0-9.]*\)%* id.*/\\1/' | awk '{print 100 - $1}'",  # noqa E501
    "free_disk_space": "df -h | grep '/dev/sda1' | awk '{print $4}'",
}

# if log level is defined in environment
if "LOG_LEVEL" in os.environ:
    LOG_LEVEL = os.environ["LOG_LEVEL"]
else:
    LOG_LEVEL = "info"


# %%
# Functions #


def run_command_on_host(host, username, port, password, command):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username=username, password=password, port=port, timeout=10)

        stdin, stdout, stderr = ssh.exec_command(command)
        cpu_usage = stdout.read().decode().strip()
        ssh.close()
        return host, cpu_usage
    except Exception as e:
        return host, str(e)


def run_commands_on_hosts(dict_systems, dict_commands, password):
    rows = []
    if not dict_systems or not dict_commands:
        return rows

    max_workers = max(1, min(len(dict_systems), 16))
    future_to_meta = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for command_name, command_text in dict_commands.items():
            for system_name, system_config in dict_systems.items():
                host = system_config["hostname"]
                user = system_config["username"]
                port = system_config.get("ssh_port", 22)
                meta = {
                    "system_name": system_name,
                    "hostname": host,
                    "username": user,
                    "port": port,
                    "command_name": command_name,
                }
                fut = executor.submit(
                    run_command_on_host, host, user, port, password, command_text
                )
                future_to_meta[fut] = meta

        for fut in as_completed(future_to_meta):
            meta = future_to_meta[fut]
            output = fut.result()
            rows.append(
                {
                    "hostname": meta["hostname"],
                    "command": meta["command_name"],
                    "system": meta["system_name"],
                    "port": meta["port"],
                    "username": meta["username"],
                    "result": output,
                }
            )

    return rows


# %%
# Main #

if __name__ == "__main__":
    # override host for testing
    # keep_host = "192.168.86.31"
    # dict_systems = {k: v for k, v in dict_systems.items() if v["hostname"] == keep_host}

    pprint_dict(dict_systems)
    pprint_dict(dict_commands)

    rows = run_commands_on_hosts(dict_systems, dict_commands, ssh_password)

    df = pd.DataFrame(
        rows, columns=["hostname", "command", "system", "port", "username", "result"]
    )

    pprint_df(df)


# %%
