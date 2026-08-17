#!/bin/bash
# Install Termux apps from an app list.
# Usage: install_android_termux_apps.sh [app_list_file]
# Defaults to app_lists/android_termux_apps.txt relative to the repo root.

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
APP_LIST="${1:-$SCRIPT_DIR/../app_lists/android_termux_apps.txt}"

source "$SCRIPT_DIR/app_install_lib.sh"

pkg update -y && pkg upgrade -y

list_installed() { dpkg-query -W -f='${Package}\n' 2>/dev/null; }
install_apps() {
    local app
    for app in "$@"; do
        echo "########## Installing $app ##########"
        pkg install -y "$app"
    done
}

install_from_list "termux" "$APP_LIST"
