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

    # The actual interpreter to run scripts with - NOT $best, which can land on
    # UX\AutoHotkeyUX.exe (the launcher shim carries the same version number).
    $v2Interpreter = $null
    foreach ($name in @('AutoHotkey64.exe', 'AutoHotkey32.exe', 'AutoHotkey.exe')) {
        $hit = $v2Exes | Where-Object { $_.Name -eq $name -and $_.FullName -notlike '*\UX\*' } | Select-Object -First 1
        if ($hit) { $v2Interpreter = $hit.FullName; break }
    }

    return [pscustomobject]@{
        V2Present = [bool]$best
        V2Version = $bestVersion
        V2Exe     = $v2Interpreter
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
    # Order matters: install v2 before repointing .ahk at it, and repoint before
    # deleting v1, because the delete step relaunches the scripts it stopped and
    # they must land on the v2 launcher.
    param($State)
    $plan = @()
    if (-not $State.V2Present) {
        $plan += [pscustomobject]@{ Kind = 'install'; What = 'install AutoHotkey v2' }
    } else {
        $plan += [pscustomobject]@{ Kind = 'upgrade'; What = "upgrade AutoHotkey v2 to latest (have $($State.V2Version))" }
    }
    if (-not $State.AssocOk) {
        $plan += [pscustomobject]@{ Kind = 'assoc'; What = 'point the .ahk file association at the v2 launcher' }
    }
    if ($State.V1Package) {
        $plan += [pscustomobject]@{ Kind = 'chocov1'; What = "uninstall chocolatey package $($State.V1Package) (v1)" }
    }
    if ($State.V1Entry) {
        $plan += [pscustomobject]@{ Kind = 'uninstallv1'; What = "run the v1 uninstaller for $($State.V1Entry.DisplayName) $($State.V1Entry.DisplayVersion)" }
    }
    if ($State.V1Files.Count -gt 0) {
        $plan += [pscustomobject]@{ Kind = 'deletev1'; What = "stop any running v1 scripts, delete $($State.V1Files.Count) orphaned v1 file(s), restart the scripts under v2" }
    }
    return $plan
}

function Get-ScriptFromCommandLine {
    # The .ahk a running interpreter was started with. Deliberately not named
    # $matches - that is an automatic variable the -match operator owns.
    param([string]$CommandLine)
    if (-not $CommandLine) { return $null }
    $found = [regex]::Matches($CommandLine, '"([^"]+\.ahk)"|(\S+\.ahk)')
    if ($found.Count -eq 0) { return $null }
    $last = $found[$found.Count - 1]
    if ($last.Groups[1].Success) { return $last.Groups[1].Value }
    return $last.Groups[2].Value
}

function Get-RunningAhkScripts {
    # Script paths of every running AutoHotkey interpreter, whatever version.
    $paths = @()
    foreach ($proc in (Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) {
        if ($proc.Name -like 'AutoHotkey*') {
            $script = Get-ScriptFromCommandLine $proc.CommandLine
            if ($script) { $paths += $script.ToLower() }
        }
    }
    return $paths
}

function Restart-StartupAhkScripts {
    # Bring the Startup folder's scripts back up after v1 was removed, without
    # waiting for a logout. Deliberately runs in the ORIGINAL session rather
    # than inside the elevated child: a script started from the elevated run
    # would keep running as admin, which is not what a login launch does.
    param($State)
    $startup = [Environment]::GetFolderPath('Startup')
    if (-not $startup -or -not (Test-Path $startup)) { return }
    $running = Get-RunningAhkScripts
    foreach ($file in (Get-ChildItem -LiteralPath $startup -Filter '*.ahk' -File -ErrorAction SilentlyContinue)) {
        if ($running -contains $file.FullName.ToLower()) { continue }
        # A symlinked Startup entry reports the resolved repo path on the
        # interpreter's command line, so compare that form too. .Target is a
        # string ARRAY on Windows PowerShell 5.1, hence the explicit [0].
        $target = @((Get-Item -LiteralPath $file.FullName).Target) | Select-Object -First 1
        if ($target -and ($running -contains ([string]$target).ToLower())) { continue }
        $head = (Get-Content -LiteralPath $file.FullName -TotalCount 5 -ErrorAction SilentlyContinue) -join "`n"
        if ($head -notmatch '(?i)#Requires\s+AutoHotkey\s+v2') {
            Write-Host ("  not started, still v1 syntax: {0}" -f $file.Name) -ForegroundColor Yellow
            continue
        }
        # Hand the interpreter the RESOLVED path: a login launch reports the
        # repo path on the command line, so A_ScriptDir is scripts/ - which is
        # how desktop_numbers.ahk finds VirtualDesktopAccessor.dll instead of
        # re-downloading it into the Startup folder.
        $scriptPath = $file.FullName
        if ($target) { $scriptPath = [string]$target }
        if ($State -and $State.V2Exe) {
            # Directly, not through the .ahk association: the UX launcher shim
            # stays resident as a parent process when started that way, leaving
            # two processes per script instead of one.
            Start-Process -FilePath $State.V2Exe -ArgumentList "`"$scriptPath`""
        } else {
            Start-Process -FilePath $scriptPath
        }
        Write-Host ("  started under v2: {0}" -f $file.Name) -ForegroundColor Green
    }
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
    # Returns $false only when elevation was actually declined or unavailable -
    # never on a merely unreadable result, because the caller's re-probe is the
    # authority on whether the work happened.
    Set-RetryStamp
    try {
        if (Get-Command gsudo -ErrorAction SilentlyContinue) {
            & gsudo powershell -NoProfile -ExecutionPolicy Bypass -File "$PSCommandPath" -Yes
            return ($LASTEXITCODE -eq 0)
        }
        $proc = Start-Process powershell -Verb RunAs -PassThru -Wait -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", '-Yes'
        )
        # An unelevated parent cannot always read the exit code of the elevated
        # child it started - on a machine where UAC prompts for a DIFFERENT
        # account's credentials the child runs as that user and .ExitCode comes
        # back $null. Treating $null as a failure reported "elevation declined"
        # over a run that had just installed v2 correctly (seen 2026-08-17), so
        # unknown means unknown: say it ran and let the re-probe judge.
        $code = $null
        try { $code = $proc.ExitCode } catch { }
        return ($null -eq $code -or $code -eq 0)
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
                # A running v1 interpreter holds its own exe open, so deleting
                # it while the Startup hotkey scripts are running fails with
                # "file in use" - which is the normal state of any machine that
                # has been logged in for a while. Stop those processes first,
                # remember what they were running, and start them again through
                # the (now v2) association afterwards, so the hotkeys come back
                # without needing a logout.
                $v1Paths = @($State.V1Files | ForEach-Object { $_.FullName.ToLower() })
                $running = @()
                foreach ($proc in (Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) {
                    if ($proc.ExecutablePath -and $v1Paths -contains $proc.ExecutablePath.ToLower()) {
                        $running += [pscustomobject]@{
                            ProcessId = $proc.ProcessId
                            Script    = Get-ScriptFromCommandLine $proc.CommandLine
                        }
                    }
                }
                foreach ($r in $running) {
                    Write-Host ("   stopping v1 process {0} ({1})" -f $r.ProcessId, $r.Script)
                    Stop-Process -Id $r.ProcessId -Force -ErrorAction SilentlyContinue
                }
                if ($running.Count -gt 0) { Start-Sleep -Milliseconds 500 }  # let the handles close

                # Only files this run identified as major version 1 - never a
                # whole directory, so a v2 file sharing the root is untouched.
                foreach ($f in $State.V1Files) {
                    Write-Host ("   removing {0}" -f $f.FullName)
                    Remove-Item -LiteralPath $f.FullName -Force -ErrorAction Continue
                    if (Test-Path -LiteralPath $f.FullName) {
                        Write-Host ("   COULD NOT remove {0} - something still holds it open" -f $f.FullName) -ForegroundColor Red
                    }
                }

                # Restarting happens back in the caller's session (see
                # Restart-StartupAhkScripts) so the scripts do not inherit this
                # run's elevation.
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

# Dot-source (". .\ensure_autohotkey_v2.ps1") to load the functions without
# doing anything - used to exercise the probes in isolation.
if ($MyInvocation.InvocationName -eq '.') { return }

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

$elevationOk = $true
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
    # Deliberately no early exit on a failed-looking elevation: the machine is
    # what it is regardless of what the child reported, so fall through to the
    # re-probe below and let the state decide what to print.
    $elevationOk = Invoke-Elevated
}

# Re-probe rather than trusting the steps above: an uninstaller can succeed and
# still leave files, and choco can fail without throwing.
$after = Get-AhkState -Deep
Write-Host ""
if (Test-Compliant $after) {
    Write-Host ("AutoHotkey is now v2-only ({0})." -f $after.V2Version) -ForegroundColor Green
    # -Yes means this IS the elevated child; leave the restart to the session
    # that spawned it, so the scripts do not end up running as administrator.
    if (-not $Yes) { Restart-StartupAhkScripts $after }
    exit 0
}
if (-not $elevationOk) {
    Write-Host "Elevation was declined or unavailable. To do it by hand:" -ForegroundColor Yellow
    Write-Host ("    {0}" -f (Get-ElevatedCommand))
    exit 1
}
Write-Host "Still not right:" -ForegroundColor Red
Show-State $after
exit 1
