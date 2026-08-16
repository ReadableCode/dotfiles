# ensure_autohotkey_v2.ps1 - make this machine's AutoHotkey match what the
# repo's startup scripts need: v2 installed, owning the .ahk association, and
# no v1 left behind.
#
# Every .ahk in scripts/ is v2 now (app_jumping, sheets and desktop_numbers all
# declare #Requires AutoHotkey v2.0), and deploy_manifest.yaml links all three
# into the Startup folder, so a machine still on v1 silently gets a "this script
# requires v2" prompt at every login instead of working hotkeys.
#
# Idempotent by design: on a correct machine it changes nothing and, with
# -Check, prints nothing at all. It is safe to run on every login or from
# gitpullall.
#
# Usage:
#   .\ensure_autohotkey_v2.ps1            # report, then offer to fix
#   .\ensure_autohotkey_v2.ps1 -Check     # report only, never prompt (exit 1 = work to do)
#   .\ensure_autohotkey_v2.ps1 -Yes       # fix without confirming (the elevated re-run)
#
# Installing and uninstalling need admin. Rather than silently failing (or
# self-elevating behind your back and losing the output), an unelevated run
# prints the exact command to paste into an admin window and waits for you.

[CmdletBinding()]
param(
    [switch]$Check,
    [switch]$Yes
)

$ErrorActionPreference = 'Stop'

# Roots an AutoHotkey install can occupy. ProgramFiles(x86) matters on the old
# machines - a 32-bit v1 install landed there.
$script:InstallRoots = @(
    (Join-Path $env:ProgramFiles 'AutoHotkey'),
    (Join-Path ${env:ProgramFiles(x86)} 'AutoHotkey'),
    (Join-Path $env:LOCALAPPDATA 'Programs\AutoHotkey')
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique

function Get-FileMajorVersion {
    # Major version of a PE file, or 0 when it carries no usable version info.
    param([string]$Path)
    try {
        $raw = (Get-Item -LiteralPath $Path).VersionInfo.ProductVersion
        if ($raw -match '^\s*(\d+)') { return [int]$Matches[1] }
    } catch { }
    return 0
}

function Get-AhkState {
    $v2Exes = @()
    $v1Files = @()
    foreach ($root in $script:InstallRoots) {
        foreach ($file in Get-ChildItem -LiteralPath $root -Recurse -Include '*.exe', '*.dll' -File -ErrorAction SilentlyContinue) {
            switch (Get-FileMajorVersion $file.FullName) {
                2 { $v2Exes += $file }
                1 { $v1Files += $file }
            }
        }
    }

    # Registry uninstall entries, so a v1 installed the normal way is removed by
    # its own uninstaller rather than by deleting files out from under it.
    $uninstallKeys = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    $entries = Get-ItemProperty $uninstallKeys -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -like '*AutoHotkey*' }
    $v1Entry = $entries | Where-Object { $_.DisplayVersion -like '1.*' } | Select-Object -First 1

    # Chocolatey packages still pinned to a v1 line.
    $v1Package = $null
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        foreach ($line in (choco list --limit-output 2>$null)) {
            $parts = $line -split '\|'
            if ($parts.Count -ge 2 -and $parts[0] -like 'autohotkey*' -and $parts[1] -like '1.*') {
                $v1Package = $parts[0]
            }
        }
    }

    # Who currently owns .ahk. An old machine can have v1 wired in here, and
    # deleting v1 without repointing it would stop EVERY .ahk from launching -
    # including the three the deploy just linked into Startup.
    $ftype = ''
    try { $ftype = (cmd /c ftype AutoHotkeyScript 2>$null) -join '' } catch { }
    $launcher = $null
    foreach ($root in $script:InstallRoots) {
        $candidate = Join-Path $root 'UX\AutoHotkeyUX.exe'
        if (Test-Path $candidate) { $launcher = $candidate; break }
    }
    $assocOk = $false
    if ($launcher -and $ftype -like "*$launcher*") { $assocOk = $true }

    $best = $v2Exes | Sort-Object { [version]((Get-Item $_.FullName).VersionInfo.ProductVersion -replace '[^\d.].*$', '') } -Descending |
        Select-Object -First 1
    $bestVersion = $null
    if ($best) { $bestVersion = (Get-Item $best.FullName).VersionInfo.ProductVersion }

    return [pscustomobject]@{
        V2Present   = [bool]$best
        V2Version   = $bestVersion
        V1Files     = $v1Files
        V1Entry     = $v1Entry
        V1Package   = $v1Package
        Launcher    = $launcher
        AssocOk     = $assocOk
        Elevated    = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    }
}

function Get-Plan {
    param($State)
    $plan = @()
    if (-not $State.V2Present) {
        $plan += [pscustomobject]@{ Kind = 'install'; What = 'install AutoHotkey v2' }
    } else {
        # Cheap and idempotent: choco upgrade is a no-op when already current,
        # and it is the only way to actually reach "newest" without a version
        # query on every check.
        $plan += [pscustomobject]@{ Kind = 'upgrade'; What = "upgrade AutoHotkey v2 to latest (have $($State.V2Version))" }
    }
    if ($State.V1Package) {
        $plan += [pscustomobject]@{ Kind = 'chocov1'; What = "uninstall chocolatey package $($State.V1Package) (v1)" }
    }
    if ($State.V1Entry) {
        $plan += [pscustomobject]@{ Kind = 'uninstallv1'; What = "run the v1 uninstaller for $($State.V1Entry.DisplayName) $($State.V1Entry.DisplayVersion)" }
    }
    if ($State.V1Files.Count -gt 0) {
        $plan += [pscustomobject]@{ Kind = 'deletev1'; What = "delete $($State.V1Files.Count) orphaned v1 file(s)" }
    }
    if (-not $State.AssocOk) {
        $plan += [pscustomobject]@{ Kind = 'assoc'; What = 'point the .ahk file association at the v2 launcher' }
    }
    return $plan
}

function Test-Compliant {
    # "Nothing to do" deliberately ignores the always-present upgrade step: a
    # machine with v2, no v1 and a correct association is already right, and
    # should not nag on every gitpullall just because a newer build exists.
    param($State)
    return ($State.V2Present -and -not $State.V1Files -and -not $State.V1Entry -and -not $State.V1Package -and $State.AssocOk)
}

function Show-State {
    param($State)
    if ($State.V2Present) {
        Write-Host ("  v2 installed:  {0}" -f $State.V2Version) -ForegroundColor Green
    } else {
        Write-Host "  v2 installed:  NO" -ForegroundColor Red
    }
    if ($State.V1Files.Count -gt 0) {
        Write-Host ("  v1 leftovers:  {0} file(s)" -f $State.V1Files.Count) -ForegroundColor Yellow
        foreach ($f in $State.V1Files) {
            Write-Host ("      {0}  ({1})" -f $f.FullName, (Get-Item -LiteralPath $f.FullName).VersionInfo.ProductVersion) -ForegroundColor DarkYellow
        }
    } else {
        Write-Host "  v1 leftovers:  none" -ForegroundColor Green
    }
    if ($State.V1Package) { Write-Host ("  v1 choco pkg:  {0}" -f $State.V1Package) -ForegroundColor Yellow }
    if ($State.V1Entry) { Write-Host ("  v1 installer:  {0} {1}" -f $State.V1Entry.DisplayName, $State.V1Entry.DisplayVersion) -ForegroundColor Yellow }
    if ($State.AssocOk) {
        Write-Host "  .ahk opens with: v2 launcher" -ForegroundColor Green
    } else {
        Write-Host "  .ahk opens with: NOT the v2 launcher" -ForegroundColor Red
    }
}

function Get-ElevatedCommand {
    # One line to paste. gsudo is in windows_apps_personal_choco.txt, so prefer
    # it when present; otherwise self-elevate a new PowerShell via UAC.
    # $PSCommandPath, not a name joined to $PSScriptRoot: the printed command has
    # to re-run THIS file, wherever it was invoked from.
    $self = $PSCommandPath
    if (Get-Command gsudo -ErrorAction SilentlyContinue) {
        return "gsudo powershell -NoProfile -ExecutionPolicy Bypass -File `"$self`" -Yes"
    }
    return "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','$self','-Yes'"
}

function Invoke-Plan {
    param($State, $Plan)
    foreach ($step in $Plan) {
        Write-Host ("-> {0}" -f $step.What) -ForegroundColor Cyan
        switch ($step.Kind) {
            { $_ -in 'install', 'upgrade' } {
                if (Get-Command choco -ErrorAction SilentlyContinue) {
                    # upgrade installs when absent and no-ops when current.
                    choco upgrade autohotkey -y
                } elseif (Get-Command winget -ErrorAction SilentlyContinue) {
                    winget install --id AutoHotkey.AutoHotkey --silent --accept-source-agreements --accept-package-agreements
                } else {
                    Write-Host "   neither choco nor winget found - install AutoHotkey v2 from https://www.autohotkey.com/ and re-run" -ForegroundColor Red
                }
            }
            'chocov1' { choco uninstall $State.V1Package -y }
            'uninstallv1' {
                $cmd = $State.V1Entry.QuietUninstallString
                if (-not $cmd) { $cmd = $State.V1Entry.UninstallString }
                Write-Host "   $cmd"
                cmd /c $cmd
            }
            'deletev1' {
                # Only files this run identified as major version 1 - never a
                # whole directory, so a v2 file sharing the root is untouched.
                foreach ($f in $State.V1Files) {
                    Write-Host ("   removing {0}" -f $f.FullName)
                    Remove-Item -LiteralPath $f.FullName -Force -ErrorAction Continue
                }
                # Tidy up any directory the deletions emptied (v1's Compiler\).
                foreach ($root in $script:InstallRoots) {
                    foreach ($dir in (Get-ChildItem -LiteralPath $root -Directory -Recurse -ErrorAction SilentlyContinue | Sort-Object { $_.FullName.Length } -Descending)) {
                        if (-not (Get-ChildItem -LiteralPath $dir.FullName -Force -ErrorAction SilentlyContinue)) {
                            Remove-Item -LiteralPath $dir.FullName -Force -ErrorAction SilentlyContinue
                        }
                    }
                }
            }
            'assoc' {
                $launcher = $State.Launcher
                if (-not $launcher) {
                    # Re-probe: the install step above may have just created it.
                    foreach ($root in $script:InstallRoots) {
                        $candidate = Join-Path $root 'UX\AutoHotkeyUX.exe'
                        if (Test-Path $candidate) { $launcher = $candidate; break }
                    }
                }
                if ($launcher) {
                    $launchScript = Join-Path (Split-Path $launcher) 'launcher.ahk'
                    cmd /c "assoc .ahk=AutoHotkeyScript" | Out-Null
                    cmd /c "ftype AutoHotkeyScript=`"$launcher`" `"$launchScript`" `"%1`" %*" | Out-Null
                } else {
                    Write-Host "   no v2 launcher found yet - re-run after the install step succeeds" -ForegroundColor Red
                }
            }
        }
    }
}

# --- main ---------------------------------------------------------------

$state = Get-AhkState
$compliant = Test-Compliant $state

if ($compliant -and $Check) { exit 0 }   # silent: the point of -Check in gitpullall

Write-Host "AutoHotkey state on $env:COMPUTERNAME" -ForegroundColor Cyan
Show-State $state

if ($compliant) {
    Write-Host "Nothing to do." -ForegroundColor Green
    if (-not $Check -and -not $Yes) {
        Write-Host "(pass -Yes to force a 'choco upgrade autohotkey' anyway)" -ForegroundColor DarkGray
    }
    exit 0
}

$plan = Get-Plan $state
Write-Host ""
Write-Host "Planned:" -ForegroundColor Cyan
foreach ($step in $plan) { Write-Host ("  - {0}" -f $step.What) }

if ($Check) {
    Write-Host ""
    Write-Host "Run this to fix it:" -ForegroundColor Yellow
    Write-Host ("  {0}" -f (Get-ElevatedCommand))
    exit 1
}

if ($state.Elevated) {
    if (-not $Yes) {
        $answer = Read-Host "Apply these changes now? (y/N)"
        if ($answer -ne 'y') { Write-Host "Skipped."; exit 1 }
    }
    Invoke-Plan $state $plan
} else {
    Write-Host ""
    Write-Host "This needs administrator rights. Copy and run this in any window:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host ("    {0}" -f (Get-ElevatedCommand)) -ForegroundColor White
    Write-Host ""
    Read-Host "Press Enter once that has finished (or Ctrl+C to leave it for later)" | Out-Null
}

# Re-probe rather than trusting the steps above: an uninstaller can succeed and
# still leave files, and choco can fail without a throw.
Write-Host ""
Write-Host "Re-checking..." -ForegroundColor Cyan
$after = Get-AhkState
Show-State $after
if (Test-Compliant $after) {
    Write-Host "AutoHotkey is now v2-only." -ForegroundColor Green
    Write-Host "Log out and back in (or double-click the scripts) to restart the Startup .ahk scripts under v2." -ForegroundColor DarkGray
    exit 0
}
Write-Host "Still not right - see the state above." -ForegroundColor Red
exit 1
