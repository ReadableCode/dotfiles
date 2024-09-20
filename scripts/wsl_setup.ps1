# PowerShell script to enable features required for WSL 2

# --- Enable Windows Subsystem for Linux ---
Write-Host "Enabling Windows Subsystem for Linux..."
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart

# --- Enable Virtual Machine Platform feature ---
Write-Host "Enabling Virtual Machine Platform..."
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

# --- Set WSL 2 as the default version ---
Write-Host "Setting WSL 2 as the default version..."
wsl --set-default-version 2

Write-Host "All required features for WSL 2 are enabled. Please restart your computer."
