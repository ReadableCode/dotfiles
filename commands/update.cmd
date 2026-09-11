# OS and package updates ONLY (repos live in pull.cmd, configs in
# deploy.cmd). What each step DOES lives in lib.sh / lib.ps1; this file only
# says what runs, where, and in what order. terminal: the step asks [y/N]
# before each repair it offers, so the TUI hands it the screen. The system
# info at the end is part of the step, the way the shells' myupdater ends.
description: upgrade OS packages, show system info
order: 30
platforms: darwin linux windows
steps:
  packages_upgrade terminal
