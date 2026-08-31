#!/bin/bash

# OS package updates for macOS/Linux — the `updatepackages` step, nothing more.
# Repo pulls and config deploys live in the shell functions (.shared_aliases):
# `myupdater` runs pullrepos → clonerepos → updatepackages → deployconfigs →
# prune, deploying AFTER the package updates in case an upgrade clobbers a
# linked config.

echo "#################   Updating Packages   #####################"

# Function for updating & upgrading macOS with Brew and system updates
update_macos() {
    echo "Checking for macOS System Updates..."
    sudo softwareupdate -i -a
    echo "Updating Brew..."
    brew update
    echo "Upgrading Brew packages..."
    brew upgrade
    echo "Upgrading Brew casks..."
    brew upgrade --cask
    brew upgrade --cask --greedy
    echo "Cleaning up Brew..."
    brew cleanup
}

# Function for updating & upgrading a Debian/Ubuntu system with apt
update_apt() {
    echo "Updating apt repositories..."
    sudo apt update
    echo "Upgrading packages..."
    sudo apt -y upgrade
    echo "Running distribution upgrade..."
    sudo apt -y dist-upgrade
    echo "Removing unused packages..."
    sudo apt -y autoremove
    echo "Running full upgrade..."
    sudo apt -y full-upgrade
}

# Function for updating & upgrading a Fedora/RHEL system with dnf
update_dnf() {
    echo "Refreshing metadata and upgrading packages..."
    sudo dnf -y upgrade --refresh
    echo "Removing unused packages..."
    sudo dnf -y autoremove
}

# Install fastfetch
install_sysinfo() {
    echo "Installing fastfetch..."
    case "$OS" in
      "Linux")
        if command -v dnf &> /dev/null; then
            sudo dnf install -y fastfetch
        elif command -v apt &> /dev/null; then
            sudo apt install -y fastfetch
        else
            echo "Neither dnf nor apt found, cannot install fastfetch."
        fi
        ;;
      "Darwin")
        brew install fastfetch
        ;;
      *)
        echo "Unsupported OS for fastfetch installation."
        ;;
    esac
}

# Detect the operating system
OS="$(uname)"
case "$OS" in
  "Linux")
    # dnf first: Fedora ships both dnf and (sometimes) an apt shim.
    if command -v dnf &> /dev/null; then
        update_dnf
    elif command -v apt &> /dev/null; then
        update_apt
    else
        echo "Neither dnf nor apt found, skipping package updates."
    fi
    ;;
  "Darwin")
    if command -v brew &> /dev/null; then
        update_macos
    else
        echo "Homebrew not found, attempting macOS system updates without Homebrew."
        sudo softwareupdate -i -a
    fi
    ;;
  *)
    echo "Unsupported operating system: $OS"
    ;;
esac

echo "############ System Info ############"

if command -v fastfetch &> /dev/null; then
    fastfetch
else
    echo "fastfetch not found. Attempting to install..."
    install_sysinfo
    if command -v fastfetch &> /dev/null; then
        fastfetch
    else
        echo "Failed to install fastfetch."
    fi
fi
