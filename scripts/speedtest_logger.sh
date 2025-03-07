#!/bin/bash

# Define log file paths
LOG_FILE=~/dotfiles/data/speed.csv
TEMP_LOG=~/dotfiles/data/speedtest_temp.log
DEBUG_LOG=~/dotfiles/data/speedtest_debug.log

# Ensure the data directory exists
mkdir -p ~/dotfiles/data

# Run Speedtest and log output
date=$(date "+%Y-%m-%d %H:%M:%S")
/usr/bin/speedtest-cli --simple --no-pre-allocate > "$TEMP_LOG" 2>&1

# Extract Ping, Download, and Upload speeds
awk -v date="$date" '
    BEGIN {printf "%s,", date}
    /Ping/ {printf "%s,", $2}
    /Download/ {printf "%s,", $2}
    /Upload/ {printf "%s\n", $2}
' "$TEMP_LOG" >> "$LOG_FILE"

# Print latest entry to console
tail -n 1 "$LOG_FILE"

# Log debug info
echo "[$date] Speedtest ran, logged to $LOG_FILE" >> "$DEBUG_LOG"
