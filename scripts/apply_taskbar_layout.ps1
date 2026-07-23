<#
.SYNOPSIS
    Apply the documented taskbar pin order (the Windows translation of the macOS
    dock order) from application_configs/windows_taskbar/LayoutModification.xml.

.DESCRIPTION
    Windows 11 has no supported "pin in this order" API. The one mechanism that
    takes an explicit ordered list is the taskbar layout XML
    (<CustomTaskbarLayoutCollection>), which Explorer reads per user from
    %LOCALAPPDATA%\Microsoft\Windows\Shell\LayoutModification.xml. Explorer only
    reads it when the user has no pin state yet, so this script:

      1. backs up the current pins (shortcut folder + Taskband registry key),
      2. rescues any shortcut the layout references that only exists as a pin
         today (Chrome web apps pinned straight from Chrome, e.g. ChatGPT),
      3. copies the layout XML into place,
      4. clears the existing pin state,
      5. restarts Explorer so the layout is read.

    Apps listed in the XML that are not installed are skipped by Windows — no
    placeholder icon, nothing to clean up — so the same file works on every
    machine. -DryRun prints exactly which entries would resolve and which would
    be skipped without touching anything.

    Run as the normal user (NOT elevated): taskbar pins are per-user HKCU state.

.PARAMETER LayoutFile
    Path to the layout XML. Defaults to the copy in this repo.

.PARAMETER DryRun
    Report resolution of every entry and the planned actions; change nothing.

.PARAMETER RestoreFrom
    Path to a backup folder created by an earlier run; restores those pins
    instead of applying the layout.

.PARAMETER RemovePolicy
    Removes the Start Layout policy values written by an apply run. Do this
    after the layout has come up at sign-in: the pins persist, the Start menu
    unlocks, and the pins become editable again. Needs elevation (gsudo).

.EXAMPLE
    .\apply_taskbar_layout.ps1 -DryRun

.EXAMPLE
    .\apply_taskbar_layout.ps1

.EXAMPLE
    .\apply_taskbar_layout.ps1 -RestoreFrom "$env:LOCALAPPDATA\dotfiles\taskbar_backups\20260722-201500"
#>

[CmdletBinding()]
param(
    [string]$LayoutFile = (Join-Path $PSScriptRoot "..\application_configs\windows_taskbar\LayoutModification.xml"),
    [switch]$DryRun,
    [string]$RestoreFrom,
    [switch]$RemovePolicy
)

$ErrorActionPreference = "Stop"

$PinDir = Join-Path $env:APPDATA "Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"
$ShellDir = Join-Path $env:LOCALAPPDATA "Microsoft\Windows\Shell"
$TaskbandKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Taskband"
$PolicyKey = "HKCU:\SOFTWARE\Policies\Microsoft\Windows\Explorer"
$BackupRoot = Join-Path $env:LOCALAPPDATA "dotfiles\taskbar_backups"


function Test-Elevated {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return ([Security.Principal.WindowsPrincipal]$id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}


function Backup-Pins {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $dest = Join-Path $BackupRoot $stamp
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    if (Test-Path $PinDir) {
        Copy-Item -Path (Join-Path $PinDir "*") -Destination $dest -Recurse -Force -ErrorAction SilentlyContinue
    }
    # reg.exe, not Export-Clixml: the Favorites blob must round-trip byte for byte
    & reg.exe export "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Taskband" `
        (Join-Path $dest "Taskband.reg") /y | Out-Null
    return $dest
}


function Get-LayoutEntries {
    param([string]$Path)

    [xml]$xml = Get-Content -Path $Path -Raw
    $ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
    $ns.AddNamespace("taskbar", "http://schemas.microsoft.com/Start/2014/TaskbarLayout")

    $entries = @()
    foreach ($node in $xml.SelectNodes("//taskbar:TaskbarPinList/*", $ns)) {
        $entries += [pscustomobject]@{
            Kind  = $node.LocalName                      # UWA | DesktopApp
            Id    = $node.GetAttribute("AppUserModelID")
            AppId = $node.GetAttribute("DesktopApplicationID")
            Link  = $node.GetAttribute("DesktopApplicationLinkPath")
        }
    }
    return $entries
}


function Resolve-Entry {
    param([pscustomobject]$Entry, [object[]]$StartApps)

    if ($Entry.Link) {
        $expanded = [Environment]::ExpandEnvironmentVariables($Entry.Link)
        $ok = Test-Path -LiteralPath $expanded
        return [pscustomobject]@{ Name = $expanded; Installed = $ok }
    }

    $id = $Entry.Id
    if (-not $id) { $id = $Entry.AppId }
    $ok = [bool]($StartApps | Where-Object { $_.AppID -eq $id })
    return [pscustomobject]@{ Name = $id; Installed = $ok }
}


# Chrome web apps pinned directly from Chrome have no Start menu shortcut — the
# only copy on disk is the pin itself. Copy those into the Chrome Apps folder so
# the layout has a stable path to point at before the pins are cleared.
function Save-ReferencedShortcuts {
    param([pscustomobject[]]$Entries, [switch]$WhatIf)

    $rescued = @()
    foreach ($entry in $Entries | Where-Object { $_.Link }) {
        $target = [Environment]::ExpandEnvironmentVariables($entry.Link)
        if (Test-Path -LiteralPath $target) { continue }

        $candidate = Join-Path $PinDir (Split-Path -Leaf $target)
        if (-not (Test-Path -LiteralPath $candidate)) { continue }

        $rescued += $target
        if (-not $WhatIf) {
            New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
            Copy-Item -LiteralPath $candidate -Destination $target -Force
        }
    }
    return $rescued
}


# HKCU\Software\Policies is admin-writable only, so these go through gsudo. The
# elevated session is the same user, so it writes the same HKCU hive.
function Invoke-Elevated {
    param([string]$Body)

    if (-not (Get-Command gsudo -ErrorAction SilentlyContinue)) {
        Write-Warning "gsudo not found - run this in an elevated powershell:"
        Write-Host $Body
        return $false
    }

    $tmp = Join-Path $env:TEMP ("taskbar_policy_{0}.ps1" -f ([guid]::NewGuid().ToString("N")))
    Set-Content -Path $tmp -Value $Body -Encoding UTF8
    try {
        & gsudo powershell -NoProfile -ExecutionPolicy Bypass -File $tmp | Out-Host
        return $true
    }
    finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
}


function Set-LayoutPolicy {
    param([string]$Path)

    $body = @"
`$pol = '$PolicyKey'
if (-not (Test-Path `$pol)) { New-Item -Path `$pol -Force | Out-Null }
New-ItemProperty -Path `$pol -Name StartLayoutFile -Value '$Path' -PropertyType ExpandString -Force | Out-Null
New-ItemProperty -Path `$pol -Name LockedStartLayout -Value 1 -PropertyType DWord -Force | Out-Null
"@
    return (Invoke-Elevated -Body $body)
}


function Clear-LayoutPolicy {
    $body = @"
`$pol = '$PolicyKey'
if (Test-Path `$pol) {
    Remove-ItemProperty -Path `$pol -Name StartLayoutFile -Force -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path `$pol -Name LockedStartLayout -Force -ErrorAction SilentlyContinue
}
"@
    return (Invoke-Elevated -Body $body)
}


function Restart-Explorer {
    Get-Process explorer -ErrorAction SilentlyContinue | Stop-Process -Force
    # Explorer as shell restarts itself; start one only if it did not come back
    $deadline = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $deadline) {
        if (Get-Process explorer -ErrorAction SilentlyContinue) { return }
        Start-Sleep -Milliseconds 500
    }
    Start-Process explorer.exe
}


# --- remove policy mode -----------------------------------------------------

if ($RemovePolicy) {
    if (Clear-LayoutPolicy) {
        Write-Host "Start Layout policy removed - pins stay, Start menu unlocks." -ForegroundColor Green
    }
    return
}


# --- restore mode -----------------------------------------------------------

if ($RestoreFrom) {
    if (-not (Test-Path $RestoreFrom)) { throw "Backup folder not found: $RestoreFrom" }
    Write-Host "Restoring taskbar pins from $RestoreFrom" -ForegroundColor Cyan

    # otherwise the layout would reapply over the restored pins at next sign-in
    Clear-LayoutPolicy | Out-Null

    Get-Process explorer -ErrorAction SilentlyContinue | Stop-Process -Force
    Get-ChildItem -Path $PinDir -Filter *.lnk -ErrorAction SilentlyContinue | Remove-Item -Force
    Copy-Item -Path (Join-Path $RestoreFrom "*.lnk") -Destination $PinDir -Force -ErrorAction SilentlyContinue
    $regFile = Join-Path $RestoreFrom "Taskband.reg"
    if (Test-Path $regFile) { & reg.exe import $regFile | Out-Null }
    Restart-Explorer

    Write-Host "Restored." -ForegroundColor Green
    return
}


# --- apply mode -------------------------------------------------------------

if (-not (Test-Path $LayoutFile)) { throw "Layout file not found: $LayoutFile" }
$LayoutFile = (Resolve-Path $LayoutFile).Path

if (Test-Elevated) {
    Write-Warning "Running elevated - taskbar pins are per-user (HKCU). Run this as your normal user."
}

$entries = Get-LayoutEntries -Path $LayoutFile
$startApps = @(Get-StartApps)

Write-Host "Layout: $LayoutFile" -ForegroundColor Cyan
Write-Host "$($entries.Count) entries" -ForegroundColor Cyan
Write-Host ""

$rescued = Save-ReferencedShortcuts -Entries $entries -WhatIf:$DryRun
foreach ($path in $rescued) {
    Write-Host ("  rescued shortcut from current pins -> {0}" -f $path) -ForegroundColor Yellow
}
if ($rescued) { Write-Host "" }

$position = 0
$skipped = @()
foreach ($entry in $entries) {
    $resolved = Resolve-Entry -Entry $entry -StartApps $startApps
    # -DryRun does not perform the rescue copy, so credit it here
    if (-not $resolved.Installed -and $rescued -contains $resolved.Name) {
        $resolved.Installed = $true
    }
    if ($resolved.Installed) {
        $position++
        Write-Host ("  {0,2}. {1}" -f $position, $resolved.Name) -ForegroundColor Green
    }
    else {
        $skipped += $resolved.Name
        Write-Host ("   -- skipped (not installed): {0}" -f $resolved.Name) -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host ("{0} pins will be applied, {1} entries skipped." -f $position, $skipped.Count) -ForegroundColor Cyan

if ($DryRun) {
    Write-Host "Dry run - nothing changed." -ForegroundColor Yellow
    return
}

$backup = Backup-Pins
Write-Host "Backed up current pins to $backup" -ForegroundColor Cyan

New-Item -ItemType Directory -Path $ShellDir -Force | Out-Null
Copy-Item -LiteralPath $LayoutFile -Destination (Join-Path $ShellDir "LayoutModification.xml") -Force

# The per-user layout file alone is not enough on current builds - Explorer
# re-reads it on every restart and pins nothing. The Start Layout policy is what
# makes the layout apply, and only at sign-in.
Set-LayoutPolicy -Path $LayoutFile | Out-Null

Get-Process explorer -ErrorAction SilentlyContinue | Stop-Process -Force
Get-ChildItem -Path $PinDir -Filter *.lnk -ErrorAction SilentlyContinue | Remove-Item -Force
Remove-Item -Path $TaskbandKey -Recurse -Force -ErrorAction SilentlyContinue
Restart-Explorer

Write-Host ""
Write-Host "Staged. The taskbar has NO pins until you sign out and back in -" -ForegroundColor Yellow
Write-Host "Explorer only materializes the layout at sign-in." -ForegroundColor Yellow
Write-Host ""
Write-Host "After signing back in:" -ForegroundColor Green
Write-Host "  .\apply_taskbar_layout.ps1 -RemovePolicy    # unlock Start, keep the pins" -ForegroundColor Green
Write-Host ("Undo instead: .\apply_taskbar_layout.ps1 -RestoreFrom `"{0}`"" -f $backup) -ForegroundColor Green
