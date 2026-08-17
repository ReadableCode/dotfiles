#!/bin/bash
# Install Linux apps from an app list.
# Usage: install_linux_apps.sh [app_list_file]
# Defaults to app_lists/linux_apps.txt relative to the repo root.

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
APP_LIST="${1:-$SCRIPT_DIR/../app_lists/linux_apps.txt}"

source "$SCRIPT_DIR/app_install_lib.sh"

sudo apt -y update
sudo apt -y upgrade
sudo apt -y dist-upgrade
sudo apt -y autoremove
sudo apt -y full-upgrade

list_installed() { dpkg-query -W -f='${Package}\n' 2>/dev/null; }
install_apps() { sudo apt install -fy "$@"; }

install_from_list "apt" "$APP_LIST"
