#!/bin/bash
# Install the msys2 entries of the app lists (src/app_lists.py --packages msys2).
# Run inside an MSYS2 shell.
# Usage: install_msys2_packages.sh

SCRIPT_DIR="$(dirname "$(realpath "$0")")"

source "$SCRIPT_DIR/app_install_lib.sh"

if ! command -v pacman >/dev/null 2>&1; then
    echo "pacman not found — run this from an MSYS2 shell." >&2
    exit 1
fi

pacman -Syu --noconfirm

list_installed() { pacman -Qq; }
install_apps() { pacman -S --needed --noconfirm "$@"; }

install_from_list "msys2" msys2
