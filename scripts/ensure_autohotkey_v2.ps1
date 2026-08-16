# ensure_autohotkey_v2.ps1 - make this machine's AutoHotkey match what the
# repo's startup scripts need: v2 installed, owning the .ahk association, and
# no v1 left behind.
#
# Every .ahk in scripts/ is v2 now (app_jumping, sheets and desktop_numbers all
# declare #Requires AutoHotkey v2.0), and deploy_manifest.yaml links all three
# into the Startup folder, so a machine still on v1 silently gets a "this script
# requires v2" prompt at every login instead of working hotkeys.
#
# This runs from powershell_aliases.ps1 on every interactive shell - it is NOT
# something to remember to run. Which is why the default probe is the cheap one:
#
#   file scan of the AutoHotkey roots   ~90 ms
#   .ahk association (registry read)    ~5 ms
#   registry uninstall scan             ~470 ms   -Full only
#   choco list                          ~1840 ms  -Full only
#
# The fast probe catches every real-world case (a v1 install puts files in one of
# the standard roots); -Full additionally catches a v1 installed to a custom
# directory or still owned by a chocolatey package, and runs from gitpullall
# where two seconds does not matter.
#
# Usage:
#   .\ensure_autohotkey_v2.ps1                # report, then offer to fix
#   .\ensure_autohotkey_v2.ps1 -Check         # report only (exit 1 = work to do)
#   .\ensure_autohotkey_v2.ps1 -AutoFix       # fix, elevating as needed; silent when correct
#   .\ensure_autohotkey_v2.ps1 -Full          # add the slow probes
#   .\ensure_autohotkey_v2.ps1 -Yes           # apply now, no prompts (the elevated re-run)

[CmdletBinding()]
param(
    [switch]$Check,
    [switch]$AutoFix,
    [switch]$Full,
    [switch]$Yes
)

$ErrorActionPreference = 'Stop'

# How long to wait before trying to raise UAC again, so a declined prompt does
# not turn into a prompt on every new shell for the rest of the day.
$script:RetryAfterMinutes = 120
$script:StampFile = Join-Path $env:LOCALAPPDATA 'dotfiles\ahk_autofix_last_attempt.txt'

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
    param([switch]$Deep)

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

    $v1Entry = $null
    $v1Package = $null
    if ($Deep) {
        # A v1 installed the normal way should be removed by its own uninstaller
        # rather than by deleting files out from under it.
        $uninstallKeys = @(
            'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
            'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
            'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
        )
        $v1Entry = Get-ItemProperty $uninstallKeys -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -like '*AutoHotkey*' -and $_.DisplayVersion -like '1.*' } |
            Select-Object -First 1

        if (Get-Command choco -ErrorAction SilentlyContinue) {
            foreach ($line in (choco list --limit-output 2>$null)) {
                $parts = $line -split '\|'
                if ($parts.Count -ge 2 -and $parts[0] -like 'autohotkey*' -and $parts[1] -like '1.*') {
                    $v1Package = $parts[0]
                }
            }
        }
    }

    # Who currently owns .ahk. An old machine can have v1 wired in here, and
    # deleting v1 without repointing it would stop EVERY .ahk from launching -
    # including the three the deploy just linked into Startup. Read the registry
    # rather than shelling out to `ftype`: same answer, no process spawn, and
    # this runs on every shell.
    $openCommand = ''
    try {
        $openCommand = (Get-ItemProperty -LiteralPath 'Registry::HKEY_CLASSES_ROOT\AutoHotkeyScript\shell\open\command' -ErrorAction SilentlyContinue).'(default)'
    } catch { }
    $launcher = $null
    foreach ($root in $script:InstallRoots) {
        $candidate = Join-Path $root 'UX\AutoHotkeyUX.exe'
        if (Test-Path $candidate) { $launcher = $candidate; break }
    }
    $assocOk = ($launcher -and $openCommand -and $openCommand.ToLower().Contains($launcher.ToLower()))

    $best = $v2Exes | Sort-Object { [version]((Get-Item $_.FullName).VersionInfo.ProductVersion -replace '[^\d.].*$', '') } -Descending |
        Select-Object -First 1
    $bestVersion = $null
    if ($best) { $bestVersion = (Get-Item $best.FullName).VersionInfo.ProductVersion }

    return [pscustomobject]@{
        V2Present = [bool]$best
        V2Version = $bestVersion
        V1Files   = @($v1Files)
        V1Entry   = $v1Entry
        V1Package = $v1Package
        Launcher  = $launcher
        AssocOk   = [bool]$assocOk
        Deep      = [bool]$Deep
        Elevated  = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    }
}

function Test-Compliant {
    # "Nothing to do" deliberately ignores the always-available upgrade step: a
    # machine with v2, no v1 and a correct association is already right, and must
    # not nag on every shell just because a newer build exists upstream.
    param($State)
    return ($State.V2Present -and $State.V1Files.Count -eq 0 -and -not $State.V1Entry -and -not $State.V1Package -and $State.AssocOk)
}

function Get-Plan {
    param($State)
    $plan = @()
    if (-not $State.V2Present) {
        $plan += [pscustomobject]@{ Kind = 'install'; What = 'install AutoHotkey v2' }
    } else {
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

function Show-State {
    param($State)
    if ($State.V2Present) {
        Write-Host ("  v2 installed:    {0}" -f $State.V2Version) -ForegroundColor Green
    } else {
        Write-Host "  v2 installed:    NO" -ForegroundColor Red
    }
    if ($State.V1Files.Count -gt 0) {
        Write-Host ("  v1 leftovers:    {0} file(s)" -f $State.V1Files.Count) -ForegroundColor Yellow
        foreach ($f in $State.V1Files) {
            Write-Host ("      {0}  ({1})" -f $f.FullName, (Get-Item -LiteralPath $f.FullName).VersionInfo.ProductVersion) -ForegroundColor DarkYellow
        }
    } else {
        Write-Host "  v1 leftovers:    none" -ForegroundColor Green
    }
    if ($State.V1Package) { Write-Host ("  v1 choco pkg:    {0}" -f $State.V1Package) -ForegroundColor Yellow }
    if ($State.V1Entry) { Write-Host ("  v1 installer:    {0} {1}" -f $State.V1Entry.DisplayName, $State.V1Entry.DisplayVersion) -ForegroundColor Yellow }
    if ($State.AssocOk) {
        Write-Host "  .ahk opens with: v2 launcher" -ForegroundColor Green
    } else {
        Write-Host "  .ahk opens with: NOT the v2 launcher" -ForegroundColor Red
    }
}

function Get-ElevatedCommand {
    # $PSCommandPath, not a name joined to $PSScriptRoot: the command has to
    # re-run THIS file, wherever it was invoked from.
    if (Get-Command gsudo -ErrorAction SilentlyContinue) {
        return "gsudo powershell -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Yes"
    }
    return "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','$PSCommandPath','-Yes'"
}

function Test-RetryAllowed {
    # True when we have not tried to raise UAC recently. Declining a prompt must
    # not produce a new prompt in every shell for the rest of the day.
    if (-not (Test-Path $script:StampFile)) { return $true }
    try {
        $last = [datetime]::Parse((Get-Content -LiteralPath $script:StampFile -Raw).Trim())
        return ((Get-Date) - $last).TotalMinutes -ge $script:RetryAfterMinutes
    } catch {
        return $true
    }
}

function Set-RetryStamp {
    try {
        $dir = Split-Path $script:StampFile
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        Set-Content -LiteralPath $script:StampFile -Value (Get-Date).ToString('o') -Encoding Ascii
    } catch { }
}

function Invoke-Elevated {
    # Re-run this script elevated and WAIT, so the caller can re-probe after.
    # Returns $false when elevation was declined or unavailable.
    Set-RetryStamp
    try {
        if (Get-Command gsudo -ErrorAction SilentlyContinue) {
            & gsudo powershell -NoProfile -ExecutionPolicy Bypass -File "$PSCommandPath" -Yes
            return ($LASTEXITCODE -eq 0)
        }
        $proc = Start-Process powershell -Verb RunAs -PassThru -Wait -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", '-Yes'
        )
        return ($proc.ExitCode -eq 0)
    } catch {
        # Cancelled UAC throws; that is a decision, not a failure to report loudly.
        return $false
    }
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

# Fast probe first. Only a machine that already looks wrong pays for the slow
# one, so the common case (correct machine, every shell) costs ~100 ms.
$state = Get-AhkState -Deep:($Full -or $Yes)

if (Test-Compliant $state) {
    if ($Check -or $AutoFix) { exit 0 }     # silent: this runs on every shell
    Write-Host "AutoHotkey state on $env:COMPUTERNAME" -ForegroundColor Cyan
    Show-State $state
    Write-Host "Nothing to do." -ForegroundColor Green
    exit 0
}

# Something is off - now it is worth the registry and choco probes, so the plan
# below is the complete one.
if (-not $state.Deep) { $state = Get-AhkState -Deep }

$plan = Get-Plan $state
Write-Host "AutoHotkey needs attention on $env:COMPUTERNAME" -ForegroundColor Yellow
Show-State $state
Write-Host ""
Write-Host "Planned:" -ForegroundColor Cyan
foreach ($step in $plan) { Write-Host ("  - {0}" -f $step.What) }

if ($Check) {
    Write-Host ""
    Write-Host "Fix it with:  ensureahk" -ForegroundColor Yellow
    Write-Host ("Or directly:  {0}" -f (Get-ElevatedCommand)) -ForegroundColor DarkGray
    exit 1
}

if ($state.Elevated -or $Yes) {
    if (-not ($Yes -or $AutoFix)) {
        $answer = Read-Host "Apply these changes now? (y/N)"
        if ($answer -ne 'y') { Write-Host "Skipped."; exit 1 }
    }
    Invoke-Plan $state $plan
} else {
    # Not elevated. Installing and deleting from Program Files needs admin, so
    # raise it here rather than printing homework - but never block a shell on
    # input, and never re-prompt in a tight loop if the prompt was declined.
    if ($AutoFix -and -not (Test-RetryAllowed)) {
        Write-Host ""
        Write-Host ("Elevation was declined recently; run 'ensureahk' when ready (retrying automatically after {0} min)." -f $script:RetryAfterMinutes) -ForegroundColor DarkGray
        exit 1
    }
    Write-Host ""
    Write-Host "This needs administrator rights - accept the prompt." -ForegroundColor Yellow
    if (-not (Invoke-Elevated)) {
        Write-Host "Elevation was declined or unavailable. To do it by hand:" -ForegroundColor Yellow
        Write-Host ("    {0}" -f (Get-ElevatedCommand))
        exit 1
    }
}

# Re-probe rather than trusting the steps above: an uninstaller can succeed and
# still leave files, and choco can fail without throwing.
$after = Get-AhkState -Deep
Write-Host ""
if (Test-Compliant $after) {
    Write-Host ("AutoHotkey is now v2-only ({0})." -f $after.V2Version) -ForegroundColor Green
    Write-Host "Scripts already running under v1 keep running until they are restarted or you log back in." -ForegroundColor DarkGray
    exit 0
}
Write-Host "Still not right:" -ForegroundColor Red
Show-State $after
exit 1
