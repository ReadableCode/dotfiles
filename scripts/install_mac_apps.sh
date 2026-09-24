#!/bin/bash
# Install macOS apps from app_lists/Brewfile.
# Usage: install_mac_apps.sh [brewfile]
#
# The Brewfile stays a real Brewfile, so `brew bundle --file=app_lists/Brewfile`
# still works for a straight install-everything run of what every Mac gets.
# This script adds the already-installed report, the single prompt, and the
# formulae and casks this machine's contexts add (src/app_lists.py).

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
BREWFILE="${1:-$SCRIPT_DIR/../app_lists/Brewfile}"

source "$SCRIPT_DIR/app_install_lib.sh"

if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew not found. Install it first: https://brew.sh" >&2
    exit 1
fi

brew update

# Formulae and casks are separate namespaces, so they are read and installed apart.
BREW_LIST="$(mktemp)"
CASK_LIST="$(mktemp)"
trap 'rm -f "$BREW_LIST" "$CASK_LIST"' EXIT

sed -n 's/^brew "\([^"]*\)".*/\1/p' "$BREWFILE" > "$BREW_LIST"
sed -n 's/^cask "\([^"]*\)".*/\1/p' "$BREWFILE" > "$CASK_LIST"

# Versioned formulae install under a suffixed name (Brewfile "python" lands as
# "python@3.14"), so report both spellings or every such entry looks missing.
list_installed() { brew list --formula | awk '{print; sub(/@.*/, ""); print}'; }
install_apps() { brew install "$@"; }
install_from_list "brew" "$BREW_LIST" brew

list_installed() { brew list --cask; }
install_apps() { brew install --cask "$@"; }
install_from_list "brew cask" "$CASK_LIST" cask
