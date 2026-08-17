#!/bin/bash
# Install MSYS2 packages from an app list. Run inside an MSYS2 shell.
# Usage: install_msys2_packages.sh [app_list_file]
# Defaults to app_lists/msys2_packages.txt relative to the repo root.

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
APP_LIST="${1:-$SCRIPT_DIR/../app_lists/msys2_packages.txt}"

source "$SCRIPT_DIR/app_install_lib.sh"

if ! command -v pacman >/dev/null 2>&1; then
    echo "pacman not found — run this from an MSYS2 shell." >&2
    exit 1
fi

pacman -Syu --noconfirm

list_installed() { pacman -Qq; }
install_apps() { pacman -S --needed --noconfirm "$@"; }

install_from_list "msys2" "$APP_LIST"
