# %%
# Imports #

import os

import matplotlib.pyplot as plt
import pandas as pd
from config import grandparent_dir


# %%
# Variables #

base_dir = os.path.join(grandparent_dir, "Syncthing_Synced", "dotfiles_data")
os.makedirs(base_dir, exist_ok=True)

csv_file = os.path.join(base_dir, "speed.csv")


# %%
# Load the CSV file #

df = pd.read_csv(csv_file)

# %%
# Data Cleaning #

# Convert 'Timestamp' to datetime format
df["Timestamp"] = pd.to_datetime(df["Timestamp"])


# %%
# Data Processing #

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

# %%
