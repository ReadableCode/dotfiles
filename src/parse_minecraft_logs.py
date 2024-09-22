# %%
# Imports #

import glob
import gzip
import hashlib
import json
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
from scp import SCPClient
from dotenv import load_dotenv
from utils.display_tools import pprint_df, print_logger

# %%
# Variables #


dotenv_path = os.path.join(parent_dir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


# Example usage
ssh_host = os.getenv("UNRAID_IP")
ssh_port = 22  # Default SSH port
ssh_username = os.getenv("UNRAID_USERNAME")
ssh_password = os.getenv("UNRAID_PASSWORD")

already_cloned = False

# Colors
pink = "\033[35m"
blue = "\033[34m"
reset = "\033[0m"

MINECRAFT_SERVER_USER_CONFIGS = json.loads(os.getenv("MINECRAFT_SERVER_USER_CONFIGS"))

# replace color strings with color vars in dict
for user_name_pattern, user_config in MINECRAFT_SERVER_USER_CONFIGS.items():
    user_config["color"] = eval(user_config["color"])

print(MINECRAFT_SERVER_USER_CONFIGS)

# %%
# Functions #


def clone_minecraft_logs(
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
    print_logger(f"Copying {remote_path} to {local_path}")
    scp.get(remote_path, local_path, recursive=True)

    # Close SCP Client
    scp.close()

    # Close SSH connection
    ssh_client.close()

    print_logger("Cloned Minecraft logs")


def parse_minecraft_log_line(line):
    if line[0] != "[":
        return "", "", "", "", ""

    # Find the first set of []
    first_open_bracket = line.find("[")
    first_close_bracket = line.find("]", first_open_bracket)

    # Extract the timestamp from the first set of []
    timestamp = line[first_open_bracket + 1 : first_close_bracket]  # noqa: E203

    # Find the second set of []
    second_open_bracket = line.find("[", first_close_bracket)
    second_close_bracket = line.find("]", second_open_bracket)

    # Extract the log item type from the second set of []
    log_item_type = line[second_open_bracket + 1 : second_close_bracket]  # noqa: E203

    col_space = line.find(": ")
    log_message = line[col_space + 2 :]  # noqa: E203

    player_name = log_message.split(" ")[0]

    player_action = ""
    if "joined the game" in log_message:
        player_action = "joined"
    elif "left the game" in log_message:
        player_action = "left"
    elif "<" in log_message and ">" in log_message:
        player_action = "chat"
    else:
        player_action = "unknown"

    return timestamp, log_item_type, log_message, player_name, player_action


def get_log_df_from_file_path(file_path):
    file_name = os.path.basename(file_path)

    # if latest in the name of the file then use today date for date
    if "latest" in file_name:
        date = datetime.now().strftime("%Y-%m-%d")
    else:
        date = file_name.split(".")[0].split("-")[:-1]
        date = "-".join(date)

    if file_name.endswith(".gz"):
        print_logger(f"Decompressing and reading {file_name}")
        with open(file_path, "rb") as f:
            with gzip.open(f, "rt", encoding="utf-8") as g:
                file_contents = g.read()
    else:
        print_logger(f"Reading {file_name}")
        with open(file_path, "r", encoding="utf-8") as f:
            file_contents = f.read()

    # Create a list to hold parsed log data
    log_data = []
    # Split the input log contents by newlines
    log_lines = file_contents.strip().split("\n")

    # Process each line in the log
    for line in log_lines:
        # Parse the log line
        (
            timestamp,
            log_item_type,
            log_message,
            player_name,
            player_action,
        ) = parse_minecraft_log_line(line)

        if timestamp == "":
            continue

        datestamp = f"{date} {timestamp}"

        # Append the parsed data to the log_data list
        log_data.append(
            [
                datestamp,
                date,
                timestamp,
                log_item_type,
                player_name,
                player_action,
                log_message,
                file_name,
            ]
        )

    # Convert the list to a pandas DataFrame
    df = pd.DataFrame(
        log_data,
        columns=[
            "Datestamp",
            "Date",
            "Timestamp",
            "Log Item Type",
            "Player",
            "Action",
            "Message",
            "Log_Filename",
        ],
    )

    return df


def get_minecraft_logs_df(ls_log_file_names_globs):
    global already_cloned
    local_path = os.path.join(data_dir, "minecraft_logs")

    if already_cloned:
        print_logger("Already cloned")
    else:
        remote_path = "/mnt/user/appdata/binhex-minecraftserver/minecraft/logs/"
        os.makedirs(local_path, exist_ok=True)
        clone_minecraft_logs(
            ssh_host,
            ssh_port,
            ssh_username,
            ssh_password,
            remote_path,
            local_path,
        )
        already_cloned = True

    df_all_logs = pd.DataFrame()

    for log_file_names_glob in ls_log_file_names_globs:
        log_file_paths = glob.glob(
            os.path.join(local_path, "logs", log_file_names_glob)
        )
        for log_file_path in log_file_paths:
            print_logger(f"Processing {log_file_path}", as_break=True)
            df = get_log_df_from_file_path(log_file_path)
            df_all_logs = pd.concat([df_all_logs, df], ignore_index=True)

    # sort by datestamp
    df_all_logs["Datestamp"] = pd.to_datetime(df_all_logs["Datestamp"])
    df_all_logs = df_all_logs.sort_values("Datestamp")

    return df_all_logs


# %%


def get_color_from_name(name):
    hash_object = hashlib.md5(name.encode())
    hex_color = hash_object.hexdigest()[:6]
    return f"#{hex_color}"


def get_player_intervals(df_logs):
    df_logs["Datestamp"] = pd.to_datetime(df_logs["Datestamp"])
    df_logs = df_logs.sort_values(["Datestamp", "Player"])

    min_timestamp = df_logs["Datestamp"].min()
    max_timestamp = pd.Timestamp.now()

    print(f"Min Timestamp: {min_timestamp}")
    print(f"Max Timestamp: {max_timestamp}")

    player_intervals = []

    for player, group in df_logs.groupby("Player"):
        group = group.sort_values("Datestamp")
        in_game = None

        for _, row in group.iterrows():
            if row["Action"] == "joined":
                in_game = row["Datestamp"]
            elif row["Action"] == "left" and in_game is not None:
                player_intervals.append((player, in_game, row["Datestamp"]))
                in_game = None

        # If the player has joined but not left yet
        if in_game is not None:
            player_intervals.append((player, in_game, max_timestamp))

    print("Player Intervals:", player_intervals)
    return player_intervals, min_timestamp, max_timestamp


def plot_player_activity(player_intervals, min_timestamp, max_timestamp):
    fig, ax = plt.subplots(figsize=(12, 8))

    for player, start, end in player_intervals:
        ax.plot(
            [start, end],
            [player, player],
            color=get_color_from_name(player),
            lw=2,
            label=player if player not in ax.get_legend_handles_labels()[1] else "",
        )

    ax.set_xlabel("Datestamp")
    ax.set_ylabel("Player")
    ax.set_title("Player Activity Over Time")
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, labels, loc="upper left", bbox_to_anchor=(1, 1))
    ax.grid(True)

    ax.xaxis.set_major_locator(mdates.HourLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))

    plt.xticks(rotation=90)
    plt.tight_layout()

    # Set the x-axis limit to the current time
    ax.set_xlim(min_timestamp, max_timestamp)

    plt.show()


def get_last_x_days_glob_pattern(num_days):
    today_date = datetime.now().strftime("%Y-%m-%d")
    date_list = [today_date]

    for i in range(1, num_days):
        date = datetime.now() - timedelta(days=i)
        date_list.append(date.strftime("%Y-%m-%d"))

    return [f"{date}*" for date in date_list] + ["latest*"]


def stream_logs():
    logfile_path = "/mnt/user/appdata/binhex-minecraftserver/minecraft/logs/latest.log"

    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(
        hostname=ssh_host, port=ssh_port, username=ssh_username, password=ssh_password
    )

    print_logger(f"Connected to {ssh_host}")

    # Run tail command
    command = f"tail -f {logfile_path} -n 1000"
    stdin, stdout, stderr = ssh_client.exec_command(command)

    try:
        while True:
            line = stdout.readline()
            if not line:
                time.sleep(1)
                continue
            # Highlight lines based on patterns
            for user_name_pattern, user_config in MINECRAFT_SERVER_USER_CONFIGS.items():
                color = user_config["color"]
                if re.search(user_name_pattern, line):
                    line = re.sub(user_name_pattern, f"{color}\\g<0>{reset}", line)
                    break
            print(line, end="")
    except KeyboardInterrupt:
        print("Stopped by user.")
    finally:
        ssh_client.close()


# %%
# Main #

# to follow logs in real time:
# ssh into box and run:
# tail -f /mnt/user/appdata/binhex-minecraftserver/minecraft/logs/latest.log

if __name__ == "__main__":
    if "ipykernel" in sys.argv[0]:
        print("Running in IPython kernel")
        df_all_logs = get_minecraft_logs_df(get_last_x_days_glob_pattern(7))
        pprint_df(df_all_logs)

        print_logger("Chat", as_break=True)
        pprint_df(df_all_logs[df_all_logs["Action"] == "chat"])

        print_logger("Joined or Left", as_break=True)
        pprint_df(df_all_logs[df_all_logs["Action"].isin(["joined", "left"])])

        print_logger("Player Activity", as_break=True)
        player_intervals, min_timestamp, max_timestamp = get_player_intervals(
            df_all_logs
        )
        plot_player_activity(player_intervals, min_timestamp, max_timestamp)
    else:
        print("Running in Python script")
        stream_logs()


# %%
