#!/bin/bash
# Install the termux entries of the app lists (src/app_lists.py --packages termux).
# Usage: install_android_termux_apps.sh

SCRIPT_DIR="$(dirname "$(realpath "$0")")"

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

install_from_list "termux" termux
