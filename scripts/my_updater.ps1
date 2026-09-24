# OS package updates for Windows: the `updatepackages` step, nothing more.
# winget first, then Chocolatey, each only when it is installed. Repo pulls and
# config deploys live in src/refresh_machine.py, which runs this between the
# pull and the deploy when called with --packages (the myupdater command). The
# macOS/Linux twin is scripts/my_updater.sh.
#
# Modes: no arguments is the full upgrade run. --check is the read-only twin,
# listing what winget and choco would upgrade and which Windows settings differ
# from the inventory, and exiting 1 when anything does, so anything that only
# wants the answer can ask for it. --help prints the modes. The flags are
# spelled with two dashes, not PowerShell's own single dash, so both twins are
# called the same way.
#
# Windows settings come from this host's `updater` block in its
# <context>_hosts.json inventory, the block my_updater.sh reads its release
# ceiling from, looked up by src/updater_policy.py:
#
#   "updater": {"windows": {"preview_updates": false, "restart_sign_on": true}}
#
#   preview_updates  Settings > Windows Update > "Get the latest updates as
#                    soon as they're available". On, the box also takes the
#                    optional preview update each month and restarts for it.
#   restart_sign_on  sign in and lock the last user after an update restart
#                    (ARSO), so the logon apps start with nobody at the desk.
#                    true means "always", BitLocker or not, which keeps the
#                    sign-in secret on disk until that logon: a desktop that
#                    stays home, never a laptop.
#
# A key the entry leaves out is left alone, as is every setting on a machine
# no inventory names. No uv or a broken inventory means the policy is unknown,
# and unknown means don't touch the settings; the package updates still run.

function Show-Usage {
    Write-Host @'
usage: my_updater.ps1 [--check | --help]

  (no arguments)  Set the Windows settings this host's inventory entry names
                  (updater.windows), then upgrade this machine's packages with
                  winget and Chocolatey, each only when it is installed.
  --check         Read-only: list what winget and Chocolatey would upgrade and
                  which Windows settings differ from this host's inventory
                  entry, exit 1 when anything does and 0 when nothing does.
  --help          This page.

The no-argument form is what myupdater runs, through
src/refresh_machine.py --packages. The macOS/Linux twin is scripts/my_updater.sh.
'@
}

# One row per registry value a key sets: key, path, value name, and the data
# for true and for false ($null leaves the value alone for that answer).
$WindowsSettings = @(
    @{ Key = 'preview_updates'; Path = 'HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings'; Name = 'IsContinuousInnovationOptedIn'; On = 1; Off = 0 },
    @{ Key = 'restart_sign_on'; Path = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'; Name = 'DisableAutomaticRestartSignOn'; On = 0; Off = 1 },
    @{ Key = 'restart_sign_on'; Path = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'; Name = 'AutomaticRestartSignOnConfig'; On = 1; Off = $null }
)

function Get-UpdaterPolicy {
    # The value at a dotted key in this host's updater block: $true, $false,
    # or $null when the entry does not set it. Throws when the lookup itself
    # fails, which the caller reports as "policy unknown".
    param([string]$Key)
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv not found, so src/updater_policy.py cannot run"
    }
    $dotfiles = Split-Path $PSScriptRoot -Parent
    $value = (uv run --project $dotfiles python (Join-Path $dotfiles 'src\updater_policy.py') $Key | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "src/updater_policy.py failed for $Key"
    }
    switch ($value) {
        ''      { return $null }
        'True'  { return $true }
        'False' { return $false }
        default { throw "updater.$Key is '$value'; expected true or false" }
    }
}

function Get-WindowsSettingDrift {
    # Every registry value this host's policy sets to something else, as
    # objects with the key, path, name, wanted and current data.
    $drift = @()
    $policy = @{}
    foreach ($key in ($WindowsSettings | ForEach-Object { $_.Key } | Select-Object -Unique)) {
        $policy[$key] = Get-UpdaterPolicy "windows.$key"
    }
    foreach ($setting in $WindowsSettings) {
        $wanted = $policy[$setting.Key]
        if ($null -eq $wanted) { continue }
        $data = if ($wanted) { $setting.On } else { $setting.Off }
        if ($null -eq $data) { continue }
        $current = (Get-ItemProperty -Path $setting.Path -Name $setting.Name -ErrorAction SilentlyContinue).($setting.Name)
        if ($current -ne $data) {
            $drift += [pscustomobject]@{
                Key = $setting.Key; Path = $setting.Path; Name = $setting.Name; Want = $data; Have = $current
            }
        }
    }
    return , $drift
}

function Show-Drift {
    param($Drift)
    foreach ($row in $Drift) {
        $have = if ($null -eq $row.Have) { 'unset' } else { $row.Have }
        Write-Host "  windows.$($row.Key): $($row.Name) is $have, inventory wants $($row.Want)"
    }
}

function Test-Elevated {
    ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

$mode = "update"
foreach ($arg in $args) {
    switch ($arg) {
        "--check" { $mode = "check" }
        "--help"  { $mode = "help" }
        "-h"      { $mode = "help" }
        default {
            Write-Host "my_updater.ps1: unknown option '$arg'"
            Show-Usage
            exit 2
        }
    }
}

if ($mode -eq "help") {
    Show-Usage
    exit 0
}

if ($mode -eq "check") {
    $outdated = 0
    $managers = 0
    Write-Host "checking windows settings..."
    try {
        $drift = Get-WindowsSettingDrift
        Show-Drift $drift
        $outdated += $drift.Count
        if ($drift.Count -eq 0) { Write-Host "  windows settings match the inventory." }
    }
    catch {
        Write-Host "  policy unknown, settings not checked: $_"
        $outdated += 1
    }
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        $managers += 1
        Write-Host "checking winget..."
        # `winget upgrade` without --all only lists. --include-unknown keeps the
        # packages whose installed version winget cannot read, which are exactly
        # the ones that otherwise look current forever. The trailing summary
        # line is what says whether anything is upgradable; winget's exit code
        # is nonzero when nothing is, which is not a failure of this check.
        $report = (winget upgrade --include-unknown | Out-String)
        Write-Host $report.TrimEnd()
        if ($report -match '(\d+)\s+upgrades?\s+available') {
            $outdated += [int]$Matches[1]
        }
    }
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        $managers += 1
        Write-Host "checking chocolatey..."
        # --limit-output prints one `name|installed|available|pinned` line per
        # outdated package and nothing else, so counting lines is the answer.
        $lines = @(choco outdated --limit-output | Where-Object { $_ -match '\|' })
        foreach ($line in $lines) { Write-Host $line }
        $outdated += $lines.Count
    }
    if ($managers -eq 0) {
        Write-Host "neither winget nor chocolatey found, so there are no packages to check."
    }
    if ($outdated -gt 0) {
        Write-Host "$outdated package(s) outdated."
        exit 1
    }
    Write-Host "all packages are current."
    exit 0
}

$settingsFailed = $false
Write-Host "applying windows settings..."
try {
    $drift = Get-WindowsSettingDrift
    if ($drift.Count -eq 0) {
        Write-Host "  windows settings match the inventory."
    }
    elseif (-not (Test-Elevated)) {
        Show-Drift $drift
        Write-Host "  not elevated, so these are left as they are; run myupdater from an elevated shell."
        $settingsFailed = $true
    }
    else {
        foreach ($row in $drift) {
            if (-not (Test-Path $row.Path)) { New-Item -Path $row.Path -Force | Out-Null }
            New-ItemProperty -Path $row.Path -Name $row.Name -Value $row.Want -PropertyType DWord -Force | Out-Null
            Write-Host "  windows.$($row.Key): set $($row.Name) to $($row.Want)"
        }
    }
}
catch {
    Write-Host "  policy unknown, settings left as they are: $_"
    $settingsFailed = $true
}

if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host "updating via winget..."
    winget upgrade --all
}
if (Get-Command choco -ErrorAction SilentlyContinue) {
    Write-Host "updating via chocolatey..."
    choco upgrade all -y
}

# winget exits nonzero when some package has no applicable upgrade, which is
# not a failure of this step; the upgrade output above is the report. A
# setting the inventory asks for and this run could not make is one.
if ($settingsFailed) { exit 1 }
exit 0
