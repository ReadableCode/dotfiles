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
# every pending app at once: install them all, not now, or ignore some or all of
# them on this machine. An ignored app is written to ~/.dotfiles_ignored_apps
# (src/app_lists.py owns that file) and never offered here again; every run
# that leaves one out names the file at its end, since deleting the line is
# how to be offered it again. Ignoring needs -Manager.
#
# Parameters:
#   -Manager     the package manager as src/app_lists.py names it (choco, winget);
#                with it, the names this machine's contexts add for that manager
#                (each member context's <context>_app_lists.yaml) join the list.
#                A lookup that fails installs nothing rather than a list that
#                only looks complete.
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

function Invoke-AppListsPy {
    # src/app_lists.py with the given arguments (context app lists and the
    # ignore file), piping -InputLines to it. $null when it could not run, so
    # the caller can tell a failure from an empty answer.
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [string[]]$InputLines = @()
    )

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Error "uv not found, so this machine's context app lists cannot be read"
        return $null
    }
    $dotfiles = Split-Path $PSScriptRoot -Parent
    $script = Join-Path $dotfiles 'src\app_lists.py'
    $lines = @($InputLines | uv run --project $dotfiles python $script @Arguments)
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    return , @($lines | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
}

function Write-IgnoredNote {
    # The apps left out because this machine ignores them, and where to undo that.
    param([string[]]$Names)
    if (-not $Names -or $Names.Count -eq 0) { return }
    $path = @(Invoke-AppListsPy -Arguments @('--ignore-path'))[0]
    Write-Host ""
    Write-Host "Not offered, ignored on this machine by $path (delete a line there to be offered it again):"
    $Names | ForEach-Object { Write-Host "  $_" }
}

function Install-FromList {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$AppList,
        [Parameter(Mandatory = $true)][scriptblock]$ListInstalled,
        [Parameter(Mandatory = $true)][scriptblock]$InstallApps,
        [string]$Manager,
        [switch]$AssumeYes,
        [switch]$DryRun
    )

    if (-not (Test-Path $AppList)) {
        Write-Error "App list not found: $AppList"
        return
    }

    $apps = @(Read-AppList -AppList $AppList)
    $source = Split-Path $AppList -Leaf
    if ($Manager) {
        $extra = Invoke-AppListsPy -Arguments @('--overlay', $Manager)
        if ($null -eq $extra) {
            Write-Error "Could not read this machine's context app lists for $Manager; installing nothing."
            return
        }
        $apps = @($apps + @($extra | Where-Object { $apps -notcontains $_ }))
        $source = "$source plus the context app lists"
    }
    if ($apps.Count -eq 0) {
        Write-Host "No apps listed in $AppList - nothing to do."
        return
    }

    $already = @(& $ListInstalled)
    $installed = @($apps | Where-Object { $already -contains $_ })
    $pending = @($apps | Where-Object { $already -notcontains $_ })

    Write-Host ""
    Write-Host "########## $Label`: $($apps.Count) apps in $source ##########"

    if ($installed.Count -gt 0) {
        Write-Host ""
        Write-Host "Already installed ($($installed.Count)):"
        $installed | ForEach-Object { Write-Host "  $_" }
    }

    $ignoredHere = @()
    if ($Manager -and $pending.Count -gt 0) {
        $skipped = Invoke-AppListsPy -Arguments @('--ignored', $Manager) -InputLines $pending
        if ($null -eq $skipped) {
            Write-Error "Could not read this machine's ignore file; installing nothing."
            return
        }
        $ignoredHere = @($pending | Where-Object { $skipped -contains $_ })
        $pending = @($pending | Where-Object { $skipped -notcontains $_ })
    }

    if ($pending.Count -eq 0) {
        Write-Host ""
        $suffix = if ($ignoredHere.Count -gt 0) { ' or ignored here' } else { '' }
        Write-Host "Everything on the list is already installed$suffix."
        Write-IgnoredNote $ignoredHere
        return
    }

    Write-Host ""
    Write-Host "Not installed ($($pending.Count)):"
    for ($i = 0; $i -lt $pending.Count; $i++) {
        Write-Host ("  {0,3}) {1}" -f ($i + 1), $pending[$i])
    }

    $chosen = $pending
    $toIgnore = @()

    if (-not $AssumeYes) {
        Write-Host ""
        if ($Manager) {
            $answer = Read-Host "Install all $($pending.Count)? [Y]es / [n]ot now / [i]gnore all here / numbers to ignore here (e.g. 3 7)"
        }
        else {
            $answer = Read-Host "Install all $($pending.Count)? [Y]es / [n]o / numbers to skip (e.g. 3 7)"
        }

        if ($answer -match '^\s*[Nn]') {
            Write-Host "Skipping $Label for now; it is offered again next time."
            Write-IgnoredNote $ignoredHere
            return
        }
        elseif ($Manager -and $answer -match '^\s*[Ii]') {
            $toIgnore = $pending
            $chosen = @()
        }
        elseif ($answer -match '\d') {
            $skip = @($answer -split '[^\d]+' | Where-Object { $_ -ne '' } | ForEach-Object { [int]$_ })
            $chosen = @(for ($i = 0; $i -lt $pending.Count; $i++) {
                if ($skip -notcontains ($i + 1)) { $pending[$i] }
            })
            if ($Manager) {
                $toIgnore = @($pending | Where-Object { $chosen -notcontains $_ })
            }
        }
    }

    if ($toIgnore.Count -gt 0) {
        if ($DryRun) {
            Write-Host "DryRun set - would ignore on this machine: $($toIgnore -join ', ')"
        }
        elseif ($null -ne (Invoke-AppListsPy -Arguments (@('--ignore', $Manager) + $toIgnore))) {
            $ignoredHere += $toIgnore
        }
        else {
            Write-Error "Could not write this machine's ignore file; $($toIgnore -join ', ') will be offered again."
        }
    }

    if ($chosen.Count -eq 0) {
        Write-Host "Nothing selected for $Label."
        Write-IgnoredNote $ignoredHere
        return
    }

    Write-Host ""
    Write-Host "Installing $($chosen.Count) apps: $($chosen -join ', ')"

    if ($DryRun) {
        Write-Host "DryRun set - not installing."
        Write-IgnoredNote $ignoredHere
        return
    }

    & $InstallApps $chosen
    Write-IgnoredNote $ignoredHere
}
