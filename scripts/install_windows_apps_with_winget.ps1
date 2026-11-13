# Install the winget entries of app_lists/base_app_lists.yaml plus the ones this
# machine's contexts add (src/app_lists.py --packages winget).
# Set-ExecutionPolicy RemoteSigned may be needed to trust running this file.
#
# Usage: .\install_windows_apps_with_winget.ps1 [-OfferIgnored] [-AssumeYes] [-DryRun]
#
# winget does not need an elevated shell for most packages, but individual
# installers may still prompt for elevation.

param(
    [switch]$OfferIgnored,
    [switch]$AssumeYes,
    [switch]$DryRun
)

. (Join-Path $PSScriptRoot 'AppInstallLib.ps1')

if (!(Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Error "winget not found. Install App Installer from the Microsoft Store."
    exit 1
}

Install-FromList -Label 'winget' -Manager winget -OfferIgnored:$OfferIgnored -AssumeYes:$AssumeYes -DryRun:$DryRun `
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
