#!/bin/bash

HOSTNAME=$(hostname)
# Get the directory of the script
script_dir=$(cd "$(dirname "$0")" && pwd)
echo "script_dir: $script_dir"

# Set the relative directory path based on the script's location
directory_path=$(realpath "$script_dir/../triggers")
echo "directory_path: $directory_path"

FILENAME="crontab_extraction_${HOSTNAME}.txt"

# Define save location
save_path="${directory_path}/${FILENAME}"

echo "$(date +"%Y-%m-%d %H:%M:%S") Starting crontab extraction, storing in $save_path"

crontab -l > "$save_path"

echo "$(date +"%Y-%m-%d %H:%M:%S") Completed crontab extraction"
