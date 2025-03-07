#!/usr/bin/env python3

# %%
# Imports #


import csv
import os
import speedtest
from datetime import datetime
from config_scripts import parent_dir

# %%
# Variables #

base_dir = os.path.join(parent_dir, "data")
os.makedirs(base_dir, exist_ok=True)

log_file = os.path.join(base_dir, "speed.csv")
debug_log = os.path.join(base_dir, "speedtest_debug.log")


# %%
# Script #

# Run Speedtest
print(f"Running speedtest at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
try:
    st = speedtest.Speedtest()
    st.get_best_server()
    ping = round(st.results.ping, 2)
    download = round(st.download() / 1_000_000, 2)  # Convert to Mbps
    upload = round(st.upload() / 1_000_000, 2)  # Convert to Mbps

    # Append data to CSV
    with open(log_file, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ping, download, upload])

    # Print latest entry to console
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')},{ping},{download},{upload}")

    # Log debug info
    with open(debug_log, "a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Speedtest ran, logged to {log_file}\n")

except Exception as e:
    with open(debug_log, "a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Speedtest failed: {e}\n")
    print(f"Speedtest failed: {e}")

# %%
