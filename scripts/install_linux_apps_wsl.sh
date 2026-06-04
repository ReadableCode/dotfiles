#!/bin/bash
# Install WSL-specific Linux apps. Wrapper around install_linux_apps.sh.
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
bash "$SCRIPT_DIR/install_linux_apps.sh" "$SCRIPT_DIR/../app_lists/linux_apps_wsl.txt"
