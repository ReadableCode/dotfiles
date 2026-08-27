# OS and package updates ONLY (repos live in pull.cmd, configs in
# deploy.cmd). What each step DOES lives in lib.sh / lib.ps1; this file only
# says what runs, where, and in what order.
description: upgrade OS packages, show system info
order: 30
platforms: darwin linux windows
steps:
  packages_upgrade
  sysinfo requires=fastfetch
