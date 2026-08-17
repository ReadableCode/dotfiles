#!/bin/bash
# Install Fedora apps from an app list.
# Usage: install_linux_apps_dnf.sh [app_list_file]
# Defaults to app_lists/linux_apps_dnf.txt relative to the repo root.

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
APP_LIST="${1:-$SCRIPT_DIR/../app_lists/linux_apps_dnf.txt}"

source "$SCRIPT_DIR/app_install_lib.sh"

if ! command -v dnf >/dev/null 2>&1; then
    echo "dnf not found - this script is for Fedora-family machines." >&2
    exit 1
fi

sudo dnf -y upgrade --refresh

list_installed() { rpm -qa --qf '%{NAME}\n'; }
install_apps() { sudo dnf install -y "$@"; }

install_from_list "dnf" "$APP_LIST"
