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
# The list is shown as already-installed vs pending, then one question asks
# whether to go through the pending apps at all. Saying yes asks about each
# app in turn - install, not now, or ignore on this machine - and only after
# the last answer does anything install, all of it in one go. An ignored app is
# written to ~/.dotfiles_ignored_apps (src/app_lists.py owns that file) and
# never offered here again; every run that leaves one out names the file at its
# end, since deleting the line is how to be offered it again. Ignoring needs
# -Manager.
#
# $env:APP_PHASE and $env:APP_PLAN split the asking from the installing the
# same way as in app_install_lib.sh, which describes them.
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

function Install-Planned {
    # The install phase: install what the ask phase queued for this label.
    param([string]$Label, [scriptblock]$InstallApps, [switch]$DryRun)
    $planned = @()
    if ($env:APP_PLAN -and (Test-Path $env:APP_PLAN)) {
        $planned = @(Get-Content -Path $env:APP_PLAN | ForEach-Object {
            $queued, $app = $_ -split "`t", 2
            if ($queued -eq $Label -and $app) { $app }
        })
    }
    if ($planned.Count -eq 0) {
        Write-Host "Nothing chosen for $Label."
        return
    }
    Write-Host "Installing $($planned.Count) $Label apps: $($planned -join ', ')"
    if ($DryRun) {
        Write-Host "DryRun set - not installing."
        return
    }
    & $InstallApps $planned
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

    if ($env:APP_PHASE -eq 'install') {
        Install-Planned -Label $Label -InstallApps $InstallApps -DryRun:$DryRun
        return
    }

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
    $pending | ForEach-Object { Write-Host "  $_" }

    $chosen = $pending
    $toIgnore = @()

    if (-not $AssumeYes) {
        Write-Host ""
        $answer = Read-Host "Go through the $($pending.Count) $Label apps not installed? [y/N]"
        if ($answer -notmatch '^\s*[Yy]') {
            Write-Host "Skipping $Label for now; it is offered again next time."
            Write-IgnoredNote $ignoredHere
            return
        }
        # Enter means not now, and q leaves the rest for next time.
        $chosen = @()
        foreach ($app in $pending) {
            if ($Manager) {
                $answer = Read-Host "  $app`: [y]es / [N]ot now / [i]gnore here / [q]uit asking"
            }
            else {
                $answer = Read-Host "  $app`: [y]es / [N]o / [q]uit asking"
            }
            if ($answer -match '^\s*[Yy]') { $chosen += $app }
            elseif ($Manager -and $answer -match '^\s*[Ii]') { $toIgnore += $app }
            elseif ($answer -match '^\s*[Qq]') {
                Write-Host "  The rest are offered again next time."
                break
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

    if ($env:APP_PHASE -eq 'ask') {
        $chosen | ForEach-Object { "$Label`t$_" } | Add-Content -Path $env:APP_PLAN
        Write-Host "Queued $($chosen.Count) $Label apps to install after the last question: $($chosen -join ', ')"
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
