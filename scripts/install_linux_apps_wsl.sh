#!/bin/bash

apt -y update
apt -y upgrade
apt -y dist-upgrade
apt -y autoremove
apt -y full-upgrade

# Read the list of applications from the linux_apps_wsl.txt file in the parent directory
mapfile -t apps < <(cat ../app_lists/linux_apps_wsl.txt | tr -d '\r')

# Print the list of applications being installed (for debugging)
echo "Installing the following applications: ${apps[@]}"

# Install the applications
for app in "${apps[@]}"; do
  echo "Installing $app"
  sudo apt install -y "$app"
done
