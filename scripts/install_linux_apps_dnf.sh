#!/bin/bash
# Install the dnf entries of the app lists (src/app_lists.py --packages dnf).
# Usage: install_linux_apps_dnf.sh

SCRIPT_DIR="$(dirname "$(realpath "$0")")"

source "$SCRIPT_DIR/app_install_lib.sh"

if ! command -v dnf >/dev/null 2>&1; then
    echo "dnf not found - this script is for Fedora-family machines." >&2
    exit 1
fi

# Run by hand, upgrade first. Under myupdater (APP_PHASE set, see
# app_install_lib.sh) the upgrade already ran a step earlier.
[ -n "$APP_PHASE" ] || sudo dnf -y upgrade --refresh

list_installed() { rpm -qa --qf '%{NAME}\n'; }
install_apps() { sudo dnf install -y "$@"; }

install_from_list "dnf" dnf
