#!/bin/bash

# Start searching from one directory up
startDir="$(dirname "$(pwd)")"

# Define the patterns to search for
patterns=(
    "__pycache__"
    ".venv"
    "venv"
    "node_modules"
    ".mypy_cache"
    "target"
    "dist"
    "build"
    "builds"
    ".buildozer"
    "stable-diffusion-webui/models"
    "stable-diffusion-webui/extensions"
    "stable-diffusion-webui-amdgpu/models"
    "stable-diffusion-webui-amdgpu/extensions"
    "Something-Familiar/Library"
)

# Find matching directories
found_items=()
for pattern in "${patterns[@]}"; do
    while IFS= read -r item; do
        found_items+=("$item")
    done < <(find "$startDir" -type d -name "$pattern" 2>/dev/null)
done

# Output results
if [[ ${#found_items[@]} -gt 0 ]]; then
    echo "Found the following directories in $startDir:"
    printf '%s\n' "${found_items[@]}"

    # Ask for confirmation before deletion
    echo -e "\nType 'delete' to remove these directories, or press Enter to cancel:"
    read -r confirm

    if [[ "$confirm" == "delete" ]]; then
        for item in "${found_items[@]}"; do
            rm -rf "$item"
        done
        echo "Deleted all matching directories."
    else
        echo "Aborted. No directories were deleted."
    fi
else
    echo "No matching directories found in $startDir."
fi
