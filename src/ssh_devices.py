# %%
# Imports #

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import paramiko
from config import grandparent_dir
from dotenv import load_dotenv

# %%
# Variables #

dotenv_path = os.path.join(grandparent_dir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

ssh_password = os.getenv("SSH_PASSWORD")

# if log level is defined in environment
if "LOG_LEVEL" in os.environ:
    LOG_LEVEL = os.environ["LOG_LEVEL"]
else:
    LOG_LEVEL = "info"


# %%
# Functions #


def run_command_on_host(host, username, password, command):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username=username, password=password)

        stdin, stdout, stderr = ssh.exec_command(command)
        cpu_usage = stdout.read().decode().strip()
        ssh.close()
        return host, cpu_usage
    except Exception as e:
        return host, str(e)


def run_command_on_hosts(ls_hosts, ls_usernames, password, command):
    results = {}
    with ThreadPoolExecutor(max_workers=len(ls_hosts)) as executor:
        futures = [
            executor.submit(run_command_on_host, host, username, password, command)
            for host, username in zip(ls_hosts, ls_usernames)
        ]
        for future in as_completed(futures):
            host, cpu_usage = future.result()
            results[host] = cpu_usage
    return results


# %%
# Main #

if __name__ == "__main__":
    # Define your hosts, username and password here
    systems = [
        {
            "hostname": "EliteDesk",
            "username": "jason",
        },
        {
            "hostname": "Optiplex9020",
            "username": "jason",
        },
        {
            "hostname": "Pavilioni5",
            "username": "jason",
        },
        {
            "hostname": "raspberrypi0",
            "username": "pi",
        },
        {
            "hostname": "raspberrypi3",
            "username": "pi",
        },
        {
            "hostname": "raspberrypi3a",
            "username": "pi",
        },
        {
            "hostname": "raspberrypi4",
            "username": "pi",
        },
        {
            "hostname": "raspberrypi4a",
            "username": "pi",
        },
        {
            "hostname": "HelloFreshJason",
            "username": "jason",
        },
    ]

    # Cpu Usage
    cpu_usage_command = "top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\([0-9.]*\)%* id.*/\\1/' | awk '{print 100 - $1}'"  # noqa E501

    cpu_usages = run_command_on_hosts(
        [system["hostname"] for system in systems],
        [system["username"] for system in systems],
        ssh_password,
        cpu_usage_command,
    )
    for host, cpu_usage in cpu_usages.items():
        print(f"{host}: {cpu_usage}% CPU usage")

    # Disk Usage
    free_disk_space_command = "df -h | grep '/dev/sda1' | awk '{print $4}'"
    disk_usages = run_command_on_hosts(
        [system["hostname"] for system in systems],
        [system["username"] for system in systems],
        ssh_password,
        cpu_usage_command,
    )
    for host, disk_usage in disk_usages.items():
        print(f"{host}: {disk_usage}% Disk usage")


# %%
