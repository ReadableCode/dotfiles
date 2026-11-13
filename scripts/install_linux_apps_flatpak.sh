#!/bin/bash
# Install the flatpak entries of the app lists (src/app_lists.py --packages flatpak).
# Usage: install_linux_apps_flatpak.sh

SCRIPT_DIR="$(dirname "$(realpath "$0")")"

source "$SCRIPT_DIR/app_install_lib.sh"

if ! command -v flatpak >/dev/null 2>&1; then
    echo "flatpak not found - install it first (it is in the dnf list of app_lists/base_app_lists.yaml)." >&2
    exit 1
fi

# Idempotent: --if-not-exists leaves an already-configured remote alone.
# Remote and apps are system-wide, under sudo: polkit only lets a local
# desktop session change the system installation, so an ssh session
# (myupdater run remotely) is refused with "Deploy not allowed for user".
sudo flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo

list_installed() { flatpak list --app --columns=application; }
install_apps() { sudo flatpak install -y flathub "$@"; }

install_from_list "flatpak" flatpak
