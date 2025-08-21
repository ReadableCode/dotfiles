<#
.SYNOPSIS
    A simplified script to install 'uv' and Visual Studio Code if they are not already installed.

.DESCRIPTION
    This script provides functions to:
    1. Check for and install 'uv' (a fast Python package manager) if it's not found in the PATH.
    2. Check for and install Visual Studio Code silently using Winget if it's not found.

    It's designed to be idempotent, meaning it can be run multiple times without re-installing
    already present software.

.NOTES
    - Requires internet connectivity for downloads.
    - May require Administrator privileges for Visual Studio Code installation depending on the
      installation scope (user vs. system). 'uv' typically installs per-user and may not require admin.
    - 'uv' is a standalone binary and does not require Python to be pre-installed for its own installation.
    - Visual Studio Code installation now uses Winget, the Windows Package Manager. Ensure Winget
      is installed and available on your system (it's typically pre-installed on modern Windows 10/11).
#>

function Test-CommandExists {
    <#
    .SYNOPSIS
        Checks if a specified command or executable exists in the system's PATH.
    .PARAMETER CommandName
        The name of the command or executable to check (e.g., 'uv', 'code', 'winget').
    .RETURNS
        $true if the command exists, $false otherwise.
    #>
    param (
        [Parameter(Mandatory=$true)]
        [string]$CommandName
    )
    # Get-Command will throw an error if the command doesn't exist,
    # so we redirect stderr to null and check if anything was returned.
    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    return -not ($null -eq $command)
}


function Install-VSCode {
    <#
    .SYNOPSIS
        Installs Visual Studio Code if it's not already present on the system using Winget.
    .DESCRIPTION
        This function checks for the existence of the 'code' command (VS Code's CLI).
        If 'code' is not found, it uses the 'winget' command to install Visual Studio Code.
        Winget is the official Windows Package Manager.
    #>
    Write-Host "Checking for Visual Studio Code installation..." -ForegroundColor Cyan
    if (Test-CommandExists -CommandName "code") {
        Write-Host "Visual Studio Code is already installed. Skipping installation." -ForegroundColor Green
        return
    }

    # Check if Winget is available before attempting to use it
    if (-not (Test-CommandExists -CommandName "winget")) {
        Write-Host "Winget (Windows Package Manager) not found." -ForegroundColor Red
        Write-Host "Please install Winget first, or ensure it's in your system's PATH." -ForegroundColor Red
        Write-Host "You can usually install Winget from the Microsoft Store (App Installer)." -ForegroundColor Red
        return
    }

    Write-Host "Visual Studio Code not found. Attempting to install using Winget..." -ForegroundColor Yellow
    try {
        # Use winget to install VS Code silently
        # The '--silent' flag ensures a non-interactive installation.
        # '--accept-source-agreements' accepts necessary agreements for the install.
        # '--accept-package-agreements' accepts specific package agreements.
        Start-Process -FilePath "winget.exe" -ArgumentList "install --id Microsoft.VisualStudioCode --silent --accept-source-agreements --accept-package-agreements" -Wait -NoNewWindow -ErrorAction Stop

        # After installation, verify if 'code' command is available.
        # It might take a moment for the PATH to update or require a new shell.
        Start-Sleep -Seconds 2 # Give it a moment for PATH to potentially update

        if (Test-CommandExists -CommandName "code") {
            Write-Host "Visual Studio Code installed successfully using Winget!" -ForegroundColor Green
        } else {
            Write-Host "VS Code installation completed via Winget, but 'code' command not found or verification failed." -ForegroundColor Yellow
            Write-Host "You might need to restart your terminal or manually verify VS Code installation." -ForegroundColor Yellow
        }
    }
    catch {
        Write-Host "An error occurred during VS Code installation via Winget: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "Ensure you have permissions to install software (run as administrator if needed)." -ForegroundColor Red
    }
}

function Install-UV {
    <#
    .SYNOPSIS
        Installs 'uv' if it's not already present on the system.
    .DESCRIPTION
        This function checks for the existence of the 'uv' command. If 'uv' is not found,
        it downloads and executes the official 'uv' PowerShell installation script.
    #>
    Write-Host "Checking for 'uv' installation..." -ForegroundColor Cyan
    if (Test-CommandExists -CommandName "uv") {
        Write-Host "'uv' is already installed. Skipping installation." -ForegroundColor Green
        return
    }

    Write-Host "'uv' not found. Attempting to install 'uv'..." -ForegroundColor Yellow
    try {
        # Execute the official UV PowerShell installer script
        & { irm https://astral.sh/uv/install.ps1 | iex }
    
        # Add UV bin path to PATH for this session
        $uvBinDir = "$env:USERPROFILE\.cargo\bin"
        if (Test-Path $uvBinDir -and -not ($env:PATH -split ";" | ForEach-Object { $_.Trim() }) -contains $uvBinDir) {
            $env:PATH += ";$uvBinDir"
        }

        # Verify installation by trying to run uv --version
        $uvVersionOutput = uv --version 2>$null
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($uvVersionOutput)) {
            Write-Host "'uv' installed successfully!" -ForegroundColor Green
            Write-Host "UV Version: $($uvVersionOutput)" -ForegroundColor Green
        } else {
            Write-Host "Installation command completed, but 'uv' command not found or verification failed." -ForegroundColor Yellow
            Write-Host "You might need to restart your terminal or manually add 'uv' to PATH." -ForegroundColor Yellow
        }
    }
    catch {
        Write-Host "An error occurred during 'uv' installation: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "Please check internet connection or run as administrator if needed." -ForegroundColor Red
    }
}


# --- Run the installation functions ---
Write-Host "`n--- Starting Software Installation ---`n" -ForegroundColor White

Install-VSCode
Install-UV

Write-Host "`n--- All installation checks complete ---`n" -ForegroundColor White
