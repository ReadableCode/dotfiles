# Fleet update - the single source of step order (the thing the two alias
# files disagreed about). What each step DOES lives in lib.sh / lib.ps1;
# this file only says what runs, where, and in what order.
description: pull dotfiles, deploy configs, upgrade packages, show system info
platforms: darwin linux windows
steps:
  dotfiles_pull requires=git
  configs_deploy requires=uv
  packages_upgrade
  sysinfo requires=fastfetch
