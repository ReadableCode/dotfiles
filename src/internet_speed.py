# %%
# Imports #

import os

import matplotlib.pyplot as plt
import pandas as pd
from config import data_dir
from src.utils.display_tools import pprint_df
from src.utils.s3_tools import download_file_from_s3  # noqa F401

# %%
# Variables #

STORAGE_BUCKET_NAME = "dotfiles"


log_file = os.path.join(data_dir, "speed.csv")
# Download the CSV file if it exists
download_file_from_s3(
    STORAGE_BUCKET_NAME,
    os.path.basename(log_file),
    log_file,
)

# %%
# Load the CSV file #

df = pd.read_csv(log_file)
# set columns
df.columns = [
    "Timestamp",
    "Ping (ms)",
    "Download (Mbps)",
    "Upload (Mbps)",
]
pprint_df(df.tail(20))

# %%
# Data Cleaning #

# Convert 'Timestamp' to datetime format
df["Timestamp"] = pd.to_datetime(df["Timestamp"])

# %%
# Data Processing #


def plot_and_show(df):
    # Plot the data
    plt.figure(figsize=(10, 5))
    plt.plot(
        df["Timestamp"],
        df["Ping (ms)"],
        label="Ping (ms)",
        linestyle="dashed",
        marker="o",
        color="red",
    )
    plt.plot(
        df["Timestamp"],
        df["Download (Mbps)"],
        label="Download (Mbps)",
        linestyle="-",
        marker="s",
        color="blue",
    )
    plt.plot(
        df["Timestamp"],
        df["Upload (Mbps)"],
        label="Upload (Mbps)",
        linestyle="-.",
        marker="^",
        color="green",
    )

    # Format the graph
    plt.xlabel("Time")
    plt.ylabel("Speed / Ping")
    plt.title("Internet Speed Over Time")
    plt.legend()
    plt.xticks(rotation=45)
    plt.grid(True)

    # Show the plot
    plt.show()


print("Plotting the entire dataset...")
plot_and_show(df)

print("Plotting the last 50 entries...")
plot_and_show(df.tail(50))

# %%
