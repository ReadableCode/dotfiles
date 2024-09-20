#!/bin/bash

# chmod +x install_apps_mac_python_environments.sh
# ./install_apps_mac_python_environments.sh

# Install Homebrew if it isn't already installed
if ! command -v brew &>/dev/null; then
    echo "Homebrew not installed. Installing Homebrew."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Attempt to set up Homebrew PATH automatically for this session
    if [ -x "/opt/homebrew/bin/brew" ]; then
        # For Apple Silicon Macs
        echo "Configuring Homebrew in PATH for Apple Silicon Mac..."
        export PATH="/opt/homebrew/bin:$PATH"
    fi
else
    echo "Homebrew is already installed."
fi

# Verify brew is now accessible
if ! command -v brew &>/dev/null; then
    echo "Failed to configure Homebrew in PATH. Please add Homebrew to your PATH manually."
    exit 1
fi

# Update Homebrew and Upgrade any already-installed formulae
brew update
brew upgrade
brew upgrade --cask
brew cleanup

# Install non-GUI Apps
app_list_path="../app_lists/mac_apps.txt"

while IFS= read -r app
do
    if brew list --formula | grep -q "^$app\$"; then
        echo "$app is already installed."
    else
        echo "Installing $app..."
        brew install "$app"
    fi
done < "$app_list_path"

# Install GUI Apps
app_list_path="../app_lists/mac_apps_cask.txt"

while IFS= read -r app
do
    if brew list --cask | grep -q "^$app\$"; then
        echo "$app is already installed."
    else
        echo "Installing $app..."
        brew install --cask "$app"
    fi
done < "$app_list_path"


# Update and clean up again for safe measure
brew update
brew upgrade
brew upgrade --cask
brew cleanup
