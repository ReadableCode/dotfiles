#!/bin/bash
# Install macOS apps: the brew and cask entries of app_lists/base_app_lists.yaml plus
# the formulae and casks this machine's contexts add, as src/app_lists.py
# --packages names them, with the already-installed report and the per-app
# questions.
# Usage: install_mac_apps.sh

SCRIPT_DIR="$(dirname "$(realpath "$0")")"

source "$SCRIPT_DIR/app_install_lib.sh"

if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew not found. Install it first: https://brew.sh" >&2
    exit 1
fi

# Run by hand, update first. Under myupdater (APP_PHASE set, see
# app_install_lib.sh) brew already updated a step earlier.
[ -n "$APP_PHASE" ] || brew update

# Formulae and casks are separate namespaces, so they are listed and installed apart.
#
# Versioned formulae install under a suffixed name (listed "python" lands as
# "python@3.14"), and a third-party tap's formula is named "user/repo/formula"
# only by --full-name, so report every spelling or such entries look missing.
list_installed() { brew list --formula --full-name | awk '{print; sub(/.*\//, ""); print; sub(/@.*/, ""); print}'; }

# A third-party tap's formula ("user/repo/formula", e.g. from a context app
# list) needs its tap, and Homebrew will not load it until it is trusted.
# Trusting just that formula, not the whole tap, keeps the rest of the tap
# untrusted. A licence prompt the formula asks is left to the person running
# this. Each installs on its own so one failing leaves the rest alone.
install_apps() {
    local name
    local -a plain=()
    for name in "$@"; do
        case "$name" in
            */*/*) brew tap "${name%/*}" && brew trust --formula "$name" && brew install "$name" ;;
            *) plain+=("$name") ;;
        esac
    done
    [ "${#plain[@]}" -eq 0 ] || brew install "${plain[@]}"
}
install_from_list "brew" brew

list_installed() { brew list --cask; }
install_apps() { brew install --cask "$@"; }
install_from_list "brew cask" cask
