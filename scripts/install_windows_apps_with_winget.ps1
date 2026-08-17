# Install Windows apps from a winget package id list.
# Set-ExecutionPolicy RemoteSigned may be needed to trust running this file.
#
# Usage: .\install_windows_apps_with_winget.ps1 [-AppList <path>] [-AssumeYes] [-DryRun]
# Defaults to app_lists\windows_apps_personal_winget.txt relative to the repo root.
#
# winget does not need an elevated shell for most packages, but individual
# installers may still prompt for elevation.

param(
    [string]$AppList,
    [switch]$AssumeYes,
    [switch]$DryRun
)

. (Join-Path $PSScriptRoot 'AppInstallLib.ps1')

if (-not $AppList) {
    $AppList = Join-Path $PSScriptRoot '..\app_lists\windows_apps_personal_winget.txt'
}

if (!(Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Error "winget not found. Install App Installer from the Microsoft Store."
    exit
}

Install-FromList -Label 'winget' -AppList $AppList -AssumeYes:$AssumeYes -DryRun:$DryRun `
    -ListInstalled {
        # winget list is fixed-width columns, so the Id is read by column offset taken
        # from the header. Pattern matching a dotted token instead picks up versions in
        # the Name column ("T3 Code (Alpha) 0.0.33" yields "0.0.33", not the real id).
        $raw = winget list --disable-interactivity
        $header = $raw | Where-Object { $_ -match '^Name\s+Id\s+Version' } | Select-Object -First 1
        if (-not $header) {
            Write-Error "Could not find the winget list header - is the console locale English?"
            return @()
        }
        $idStart = $header.IndexOf('Id')
        $verStart = $header.IndexOf('Version')
        $raw | ForEach-Object {
            if ($_.Length -gt $idStart -and $_ -ne $header -and $_ -notmatch '^-+$') {
                $end = [Math]::Min($verStart, $_.Length)
                $_.Substring($idStart, $end - $idStart).Trim()
            }
        } | Where-Object { $_ -ne '' }
    } `
    -InstallApps {
        param($apps)
        foreach ($app in $apps) {
            Try {
                winget install --id $app --exact --accept-package-agreements --accept-source-agreements
            }
            Catch {
                Write-Error "Failed to install $app. Error: $_"
            }
        }
    }
