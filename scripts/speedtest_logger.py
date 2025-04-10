# %%
# Imports #

import csv
import os
from datetime import datetime

import speedtest
from config_scripts import data_dir
from src.utils.s3_tools import (  # noqa F401
    download_file_from_s3,
    ensure_bucket_exists,
    upload_file_to_s3,
)

# %%
# Variables #

STORAGE_BUCKET_NAME = "dotfiles"


log_file = os.path.join(data_dir, "speed.csv")
debug_log = os.path.join(data_dir, "speedtest_debug.log")


# %%
# S3 Integration #

# Ensure the bucket exists
ensure_bucket_exists(STORAGE_BUCKET_NAME)

# Download the CSV file if it exists
download_file_from_s3(
    STORAGE_BUCKET_NAME,
    os.path.basename(log_file),
    log_file,
)

# Download the debug log file if it exists
download_file_from_s3(
    STORAGE_BUCKET_NAME,
    os.path.basename(debug_log),
    debug_log,
)


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
        writer.writerow(
            [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ping, download, upload]
        )

    # Print latest entry to console
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')},{ping},{download},{upload}")

    # Log debug info
    with open(debug_log, "a") as f:
        f.write(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Speedtest ran, logged to {log_file}\n"
        )

    # Upload the CSV file to S3
    upload_file_to_s3(log_file, STORAGE_BUCKET_NAME, os.path.basename(log_file))
    # Upload the debug log file to S3
    upload_file_to_s3(debug_log, STORAGE_BUCKET_NAME, os.path.basename(debug_log))

except Exception as e:
    with open(debug_log, "a") as f:
        f.write(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Speedtest failed: {e}\n"
        )
    print(f"Speedtest failed: {e}")
    # Upload the debug log file to S3
    upload_file_to_s3(debug_log, STORAGE_BUCKET_NAME, os.path.basename(debug_log))


# %%
