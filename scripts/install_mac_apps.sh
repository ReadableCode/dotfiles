#!/bin/bash
# Install macOS apps from app_lists/Brewfile.
# Usage: install_mac_apps.sh [brewfile]
#
# The Brewfile stays a real Brewfile, so `brew bundle --file=app_lists/Brewfile`
# still works for a straight install-everything run of what every Mac gets.
# This script adds the already-installed report, the per-app questions, and the
# formulae and casks this machine's contexts add (src/app_lists.py).

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
BREWFILE="${1:-$SCRIPT_DIR/../app_lists/Brewfile}"

source "$SCRIPT_DIR/app_install_lib.sh"

if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew not found. Install it first: https://brew.sh" >&2
    exit 1
fi

# Run by hand, update first. Under myupdater (APP_PHASE set, see
# app_install_lib.sh) brew already updated a step earlier.
[ -n "$APP_PHASE" ] || brew update

# Formulae and casks are separate namespaces, so they are read and installed apart.
BREW_LIST="$(mktemp)"
CASK_LIST="$(mktemp)"
trap 'rm -f "$BREW_LIST" "$CASK_LIST"' EXIT

sed -n 's/^brew "\([^"]*\)".*/\1/p' "$BREWFILE" > "$BREW_LIST"
sed -n 's/^cask "\([^"]*\)".*/\1/p' "$BREWFILE" > "$CASK_LIST"

# Versioned formulae install under a suffixed name (Brewfile "python" lands as
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
install_from_list "brew" "$BREW_LIST" brew

list_installed() { brew list --cask; }
install_apps() { brew install --cask "$@"; }
install_from_list "brew cask" "$CASK_LIST" cask
