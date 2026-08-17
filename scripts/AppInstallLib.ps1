# Shared helpers for the Windows app installers.
#
# A caller supplies two script blocks and then calls Install-FromList:
#
#   -ListInstalled   returns every already-installed package id
#   -InstallApps     installs the package ids passed to it as a string array
#
#   . (Join-Path $PSScriptRoot 'AppInstallLib.ps1')
#   Install-FromList -Label choco -AppList $path -ListInstalled {...} -InstallApps {...}
#
# The list is shown as already-installed vs pending, then a single prompt covers
# every pending app at once: accept them all, decline, or type the numbers to skip.
#
# Parameters:
#   -AssumeYes   install everything pending without prompting (used by bootstrap)
#   -DryRun      print what would be installed and change nothing

function Read-AppList {
    param(
        [Parameter(Mandatory = $true)][string]$AppList
    )

    # Strips blank lines, "#" comment lines and trailing "# ..." comments, so an app
    # can be commented out for one run and the file reverted afterwards.
    Get-Content -Path $AppList |
        ForEach-Object { ($_ -replace '#.*', '').Trim() } |
        Where-Object { $_ -ne '' }
}

function Install-FromList {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$AppList,
        [Parameter(Mandatory = $true)][scriptblock]$ListInstalled,
        [Parameter(Mandatory = $true)][scriptblock]$InstallApps,
        [switch]$AssumeYes,
        [switch]$DryRun
    )

    if (-not (Test-Path $AppList)) {
        Write-Error "App list not found: $AppList"
        return
    }

    $apps = @(Read-AppList -AppList $AppList)
    if ($apps.Count -eq 0) {
        Write-Host "No apps listed in $AppList - nothing to do."
        return
    }

    $already = @(& $ListInstalled)
    $installed = @($apps | Where-Object { $already -contains $_ })
    $pending = @($apps | Where-Object { $already -notcontains $_ })

    Write-Host ""
    Write-Host "########## $Label`: $($apps.Count) apps in $(Split-Path $AppList -Leaf) ##########"

    if ($installed.Count -gt 0) {
        Write-Host ""
        Write-Host "Already installed ($($installed.Count)):"
        $installed | ForEach-Object { Write-Host "  $_" }
    }

    if ($pending.Count -eq 0) {
        Write-Host ""
        Write-Host "Everything on the list is already installed."
        return
    }

    Write-Host ""
    Write-Host "Not installed ($($pending.Count)):"
    for ($i = 0; $i -lt $pending.Count; $i++) {
        Write-Host ("  {0,3}) {1}" -f ($i + 1), $pending[$i])
    }

    $chosen = $pending

    if (-not $AssumeYes) {
        Write-Host ""
        $answer = Read-Host "Install all $($pending.Count)? [Y]es / [n]o / numbers to skip (e.g. 3 7)"

        if ($answer -match '^\s*[Nn]') {
            Write-Host "Skipping $Label."
            return
        }
        elseif ($answer -match '\d') {
            $skip = @($answer -split '[^\d]+' | Where-Object { $_ -ne '' } | ForEach-Object { [int]$_ })
            $chosen = @(for ($i = 0; $i -lt $pending.Count; $i++) {
                if ($skip -notcontains ($i + 1)) { $pending[$i] }
            })
        }
    }

    if ($chosen.Count -eq 0) {
        Write-Host "Nothing selected for $Label."
        return
    }

    Write-Host ""
    Write-Host "Installing $($chosen.Count) apps: $($chosen -join ', ')"

    if ($DryRun) {
        Write-Host "DryRun set - not installing."
        return
    }

    & $InstallApps $chosen
}
