#!/bin/bash
# Install the apt entries of the app lists (src/app_lists.py --packages apt).
# On WSL that is only the entries marked wsl: true.
# Usage: install_linux_apps.sh

SCRIPT_DIR="$(dirname "$(realpath "$0")")"

source "$SCRIPT_DIR/app_install_lib.sh"

# Run by hand, upgrade first. Under myupdater (APP_PHASE set, see
# app_install_lib.sh) the upgrade already ran a step earlier.
if [ -z "$APP_PHASE" ]; then
    sudo apt -y update
    sudo apt -y full-upgrade
    sudo apt -y autoremove
fi

list_installed() { dpkg-query -W -f='${Package}\n' 2>/dev/null; }
# every package name this machine's apt sources carry, so a name the release
# lacks is reported instead of failing the batch it is installed with
list_available() { apt-cache pkgnames 2>/dev/null; }
install_apps() { sudo apt install -fy "$@"; }

install_from_list "apt" apt
