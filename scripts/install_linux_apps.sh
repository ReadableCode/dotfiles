#!/bin/bash
# Install Linux apps from an app list.
# Usage: install_linux_apps.sh [app_list_file]
# Defaults to app_lists/linux_apps.txt relative to the repo root.

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
APP_LIST="${1:-$SCRIPT_DIR/../app_lists/linux_apps.txt}"

sudo apt -y update
sudo apt -y upgrade
sudo apt -y dist-upgrade
sudo apt -y autoremove
sudo apt -y full-upgrade

if [ ! -f "$APP_LIST" ]; then
    echo "App list not found: $APP_LIST — skipping app installation." >&2
    exit 0
fi

mapfile -t apps < <(tr -d '\r' < "$APP_LIST")

echo "Installing ${#apps[@]} apps from $APP_LIST: ${apps[*]}"
sudo apt install -fy "${apps[@]}"
