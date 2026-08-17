# May need this command to trust running file, run in admin powershell window
# Set-ExecutionPolicy RemoteSigned
# run by either double clicking or running the following command in an elevated powershell prompt
#
# Usage: .\install_windows_apps_with_chocolatey.ps1 [-AppList <path>] [-AssumeYes] [-DryRun]
# Defaults to app_lists\windows_apps_personal_choco.txt relative to the repo root.
# The base and aws lists are installed by passing -AppList.

param(
    [string]$AppList,
    [switch]$AssumeYes,
    [switch]$DryRun
)

# Check for administrative privileges
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Please run this script as an Administrator."
    exit
}

. (Join-Path $PSScriptRoot 'AppInstallLib.ps1')

if (-not $AppList) {
    $AppList = Join-Path $PSScriptRoot '..\app_lists\windows_apps_personal_choco.txt'
}

# Check if Chocolatey is installed
if (!(Get-Command choco -ErrorAction SilentlyContinue)) {
    Try {
        # Set TLS 1.2 protocol
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

        # Download and run the Chocolatey installation script
        Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))
    }
    Catch {
        Write-Error "Failed to install Chocolatey. Error: $_"
        exit
    }
}

Install-FromList -Label 'choco' -AppList $AppList -AssumeYes:$AssumeYes -DryRun:$DryRun `
    -ListInstalled {
        # "choco list" output is "<id> <version>" lines plus a trailing summary line.
        choco list --limit-output | ForEach-Object { ($_ -split '\|')[0] }
    } `
    -InstallApps {
        param($apps)
        foreach ($app in $apps) {
            Try {
                choco install $app -y
            }
            Catch {
                Write-Error "Failed to install $app. Error: $_"
            }
        }
    }
