#!/bin/bash
# after: script of the dracut_config_rescue app removal (app_removals.yaml).
# Removing dracut-config-rescue stops new rescue images being made, but the one
# already in /boot is not owned by any package and stays. This deletes exactly
# that kernel, initramfs and boot entry, listed first.
set -euo pipefail

mapfile -t paths < <(sudo find /boot /boot/loader/entries -maxdepth 1 -type f \
    \( -name 'vmlinuz-0-rescue-*' -o -name 'initramfs-0-rescue-*.img' -o -name '*-0-rescue.conf' \))

if [ "${#paths[@]}" -eq 0 ]; then
    echo "No rescue boot images in /boot."
    exit 0
fi

printf 'Rescue boot files in /boot:\n'
printf '  %s\n' "${paths[@]}"
read -r -p "Delete exactly these? [y/N] " answer
if [ "$answer" != "y" ]; then
    echo "Left in place."
    exit 1
fi
sudo rm -- "${paths[@]}"
df -h /boot
