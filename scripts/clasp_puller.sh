#!/bin/bash

# add this at end of crontab entry to disable emailing every time it runs: 2>&1

# Get the directory of the script
script_dir=$(cd "$(dirname "$0")" && pwd)
echo "script_dir: $script_dir"

# Set the relative directory path based on the script's location
directory_path=$(realpath "$script_dir/../google_apps_scripts")
echo "directory_path: $directory_path"

echo "$(date +"%Y-%m-%d %H:%M:%S") Starting Clasp pull for all directories in $directory_path"

# Loop through each subfolder in the directory
for folder in "$directory_path"/*; do
  # Check if the item is a directory
  if [ -d "$folder" ]; then
    # Change to the folder
    cd "$folder" || exit
    # echo the folder name
    echo "$folder"
    # Run clasp pull
    clasp pull
    # Return to the parent directory
    cd "$directory_path" || exit
  fi
done

echo "$(date +"%Y-%m-%d %H:%M:%S") Completed Clasp pull for all directories"
