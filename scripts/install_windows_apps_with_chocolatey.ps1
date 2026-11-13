# May need this command to trust running file, run in admin powershell window
# Set-ExecutionPolicy RemoteSigned
# run by either double clicking or running the following command in an elevated powershell prompt
#
# Usage: .\install_windows_apps_with_chocolatey.ps1 [-OfferIgnored] [-AssumeYes] [-DryRun]
# Installs the choco entries of app_lists/base_app_lists.yaml plus the ones this
# machine's contexts add (src/app_lists.py --packages choco).

param(
    [switch]$OfferIgnored,
    [switch]$AssumeYes,
    [switch]$DryRun
)

# Check for administrative privileges
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Please run this script as an Administrator."
    exit 1
}

. (Join-Path $PSScriptRoot 'AppInstallLib.ps1')

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
        exit 1
    }
}

Install-FromList -Label 'choco' -Manager choco -OfferIgnored:$OfferIgnored -AssumeYes:$AssumeYes -DryRun:$DryRun `
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
