#!/bin/bash

# If ../app_lists/android_termux_apps_personal.txt doesnt exist
if [ ! -f ../app_lists/android_termux_apps_personal.txt ]; then
    echo "The file ../app_lists/android_termux_apps_personal.txt does not exist. Exiting..."
    exit 1
fi


# Update and upgrade packages
pkg update -y && pkg upgrade -y

# Read the list of applications from the android_termux_apps_personal.txt file
# Adjust the path to the file as needed
mapfile -t apps < <(cat ../app_lists/android_termux_apps_personal.txt | tr -d '\r')

# Print the list of applications being installed (for debugging)
echo "Installing the following applications: ${apps[@]}"

# Install the applications
for app in "${apps[@]}"; do
    echo "########## Installing $app ##########"
    pkg install -y "$app"
done

echo "Installation complete."
