#!/bin/bash

# Start searching from one directory up
startDir="$(dirname "$(pwd)")"

# Define the patterns to search for
patterns=("sync-conflict" "~syncthing")

# Find matching files
files=()
while IFS= read -r file; do
    for pattern in "${patterns[@]}"; do
        if [[ "$file" == *"$pattern"* ]]; then
            files+=("$file")
            break
        fi
    done
done < <(find "$startDir" -type f)

# Output found files
if [[ ${#files[@]} -gt 0 ]]; then
    echo "Found files in $startDir:"
    printf '%s\n' "${files[@]}"

    # If -delete flag is provided, remove the files
    if [[ "$1" == "-delete" ]]; then
        for file in "${files[@]}"; do
            rm -f "$file"
        done
        echo "Deleted all matching files."
    fi
else
    echo "No matching files found in $startDir."
fi

