#!/bin/bash

echo "#################   Running System Update   #####################"

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

# Install fastfetch (preferred) or neofetch as fallback
install_sysinfo() {
    echo "Installing fastfetch..."
    case "$OS" in
      "Linux")
        sudo apt install -y fastfetch || sudo apt install -y neofetch
        ;;
      "Darwin")
        brew install fastfetch || brew install neofetch
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
    if command -v apt &> /dev/null; then
        update_apt
    else
        echo "apt not found, skipping package updates."
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

# Prefer fastfetch, fall back to neofetch
if command -v fastfetch &> /dev/null; then
    fastfetch
elif command -v neofetch &> /dev/null; then
    neofetch
else
    echo "fastfetch not found. Attempting to install..."
    install_sysinfo
    if command -v fastfetch &> /dev/null; then
        fastfetch
    elif command -v neofetch &> /dev/null; then
        neofetch
    else
        echo "Failed to install fastfetch."
    fi
fi

echo "############ Done ############"
