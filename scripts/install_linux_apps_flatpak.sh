#!/bin/bash
# Install flatpak applications from an app list.
# Usage: install_linux_apps_flatpak.sh [app_list_file]
# Defaults to app_lists/linux_apps_flatpak.txt relative to the repo root.

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
APP_LIST="${1:-$SCRIPT_DIR/../app_lists/linux_apps_flatpak.txt}"

source "$SCRIPT_DIR/app_install_lib.sh"

if ! command -v flatpak >/dev/null 2>&1; then
    echo "flatpak not found - install it first (it is in linux_apps_dnf.txt)." >&2
    exit 1
fi

# Idempotent: --if-not-exists leaves an already-configured remote alone.
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo

list_installed() { flatpak list --app --columns=application; }
install_apps() { flatpak install -y flathub "$@"; }

install_from_list "flatpak" "$APP_LIST"
