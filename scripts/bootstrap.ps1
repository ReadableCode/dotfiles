# Bare Windows machine -> cloned, synced, deployed, packages installed.
#
# Every step is idempotent, so this doubles as a repair tool: a second run on a
# working machine should change nothing.
#
# From a bare machine (elevated PowerShell):
#   iwr -useb https://raw.githubusercontent.com/ReadableCode/dotfiles/master/scripts/bootstrap.ps1 | iex
#
# From an existing clone:
#   .\scripts\bootstrap.ps1 -DryRun
#
# Parameters:
#   -Credentials URL[]  clone these credentials repos. They are ssh working repos on
#                       specific machines, so the URLs are not stored here - see
#                       cloning_credentials_repos.md in the personal credentials repo.
#   -Root DIR           repos root (default: $HOME\GitHub)
#   -DryRun             report what would happen and change nothing
#   -AssumeYes          never prompt
#   -SkipApps           skip the package install step
#   -ChocoList PATH     which choco profile to install (default: the personal list)

param(
    [string[]]$Credentials = @(),
    [string]$Root,
    [switch]$DryRun,
    [switch]$AssumeYes,
    [switch]$SkipApps,
    [string]$ChocoList
)

$DotfilesUrl = 'https://github.com/ReadableCode/dotfiles.git'
$script:ManualNotes = @()

# %%
# Output helpers #

function Write-Step { param($m) Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-Ok   { param($m) Write-Host "    ok      $m" -ForegroundColor Green }
function Write-Skip { param($m) Write-Host "    skip    $m" -ForegroundColor Green }
function Write-Todo { param($m) Write-Host "    would   $m" -ForegroundColor Yellow }
function Write-Warn { param($m) Write-Host "    warn    $m" -ForegroundColor Yellow }
function Write-Fail { param($m) Write-Host "    fail    $m" -ForegroundColor Red }
function Add-Manual { param($m) $script:ManualNotes += $m }

function Confirm-Step {
    param($Question)
    if ($AssumeYes -or $DryRun) { return $true }
    $answer = Read-Host "    $Question [y/N]"
    return $answer -match '^\s*[Yy]'
}

function Test-Have { param($Name) return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

# %%
# Environment #

Write-Step "Platform"
Write-Ok "windows $([System.Environment]::OSVersion.Version) / PowerShell $($PSVersionTable.PSVersion)"
if ($DryRun) { Write-Warn "dry run: nothing will be changed" }

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    Write-Ok "elevated shell"
} else {
    # Say so now rather than failing halfway through the package step.
    Write-Warn "not elevated - chocolatey install and the choco package step will be skipped"
    Add-Manual "re-run this script from an elevated PowerShell to install chocolatey packages"
}

# deploy_configs.py falls back to hard links without Developer Mode, but symlinks
# are the intended result, so surface it here.
$devModeKey = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock'
$devMode = (Get-ItemProperty -Path $devModeKey -Name AllowDevelopmentWithoutDevLicense -ErrorAction SilentlyContinue).AllowDevelopmentWithoutDevLicense
if ($devMode -eq 1) {
    Write-Ok "developer mode on (symlinks available)"
} else {
    Write-Warn "developer mode off - deploy_configs will fall back to hard links"
    Add-Manual "enable Developer Mode (Settings > System > For developers) so configs deploy as symlinks"
}

# %%
# Repos root #

Write-Step "Repos root"
if (-not $Root) { $Root = Join-Path $HOME 'GitHub' }
if (Test-Path $Root) {
    Write-Skip "$Root exists"
} elseif ($DryRun) {
    Write-Todo "create $Root"
} else {
    New-Item -ItemType Directory -Force -Path $Root | Out-Null
    Write-Ok "created $Root"
}
$DotfilesDir = Join-Path $Root 'dotfiles'

# %%
# Prerequisites #

Write-Step "Package managers"
if (Test-Have winget) { Write-Skip "winget present" } else { Write-Warn "winget missing - install App Installer from the Microsoft Store"; Add-Manual "install winget (App Installer) from the Microsoft Store" }

if (Test-Have choco) {
    Write-Skip "chocolatey present"
} elseif (-not $isAdmin) {
    Write-Warn "chocolatey missing and shell is not elevated - skipping"
} elseif ($DryRun) {
    Write-Todo "install chocolatey"
} elseif (Confirm-Step "install chocolatey?") {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))
    Write-Ok "chocolatey installed"
}

Write-Step "git"
if (Test-Have git) {
    Write-Skip "git present ($(git --version))"
} elseif ($DryRun) {
    Write-Todo "winget install --id Git.Git"
} elseif (Test-Have winget) {
    winget install --id Git.Git --exact --accept-package-agreements --accept-source-agreements
} else {
    Write-Fail "cannot install git without winget"
}

Write-Step "uv"
if (Test-Have uv) {
    Write-Skip "uv present ($(uv --version))"
} elseif ($DryRun) {
    Write-Todo "install uv"
} elseif (Confirm-Step "install uv?") {
    Invoke-Expression (Invoke-RestMethod https://astral.sh/uv/install.ps1)
    $uvBin = Join-Path $HOME '.local\bin'
    if (Test-Path $uvBin) { $env:PATH = "$uvBin;$env:PATH" }
}

# %%
# dotfiles #

Write-Step "dotfiles clone"
if (Test-Path (Join-Path $DotfilesDir '.git')) {
    Write-Skip "$DotfilesDir already cloned"
} elseif ($DryRun) {
    Write-Todo "git clone $DotfilesUrl $DotfilesDir"
} else {
    # https, not ssh: a bare machine has no GitHub key yet.
    git clone $DotfilesUrl $DotfilesDir
    if ($LASTEXITCODE -ne 0) { Write-Fail "could not clone dotfiles"; exit 1 }
    Write-Ok "cloned dotfiles"
    Add-Manual "dotfiles remote is https; switch to ssh to push from this machine"
}

# %%
# Credentials repos #

Write-Step "Credentials repos"
$foundAny = $false
Get-ChildItem -Path $Root -Directory -Filter '*_credentials' -ErrorAction SilentlyContinue | ForEach-Object {
    if (Test-Path (Join-Path $_.FullName '.git')) { Write-Skip "$($_.Name) already cloned"; $foundAny = $true }
}
foreach ($url in $Credentials) {
    $name = [IO.Path]::GetFileNameWithoutExtension($url)
    $dest = Join-Path $Root $name
    if (Test-Path (Join-Path $dest '.git')) { continue }
    if ($DryRun) { Write-Todo "git clone $url $dest" } else { git clone $url $dest; Write-Ok "cloned $name" }
    $foundAny = $true
}
if (-not $foundAny -and $Credentials.Count -eq 0) {
    Write-Warn "no credentials repo cloned - configs and repo lists that ride them will be missing"
    Add-Manual "clone your credentials repo(s): bootstrap.ps1 -Credentials <ssh-url> (see cloning_credentials_repos.md)"
}

# %%
# Python tooling #

function Test-UvReady {
    if (-not (Test-Have uv)) { Write-Warn "skipped (uv unavailable)"; return $false }
    if (-not (Test-Path $DotfilesDir)) { Write-Warn "skipped (no dotfiles clone yet)"; return $false }
    return $true
}

Write-Step "Dependencies"
if (Test-UvReady) {
    if ($DryRun) {
        Write-Todo "uv sync (in $DotfilesDir)"
    } else {
        Push-Location $DotfilesDir; uv sync; Pop-Location
        if ($LASTEXITCODE -eq 0) { Write-Ok "dependencies synced" } else { Write-Fail "uv sync failed - the steps below will not work" }
    }
}

# The read-only reports are run for real even in a dry run - that report is the
# point of the dry run.
Write-Step "Sibling repos"
if (Test-UvReady) {
    Push-Location $DotfilesDir
    if ($DryRun) { uv run python src/clone_repos.py --list }
    elseif ($AssumeYes) { uv run python src/clone_repos.py --yes }
    else { uv run python src/clone_repos.py }
    if ($LASTEXITCODE -ne 0) {
        # In a dry run this usually just means dependencies are not synced yet.
        if ($DryRun) { Write-Warn "could not list repos (are dependencies synced?)" }
        else { Write-Fail "clone_repos failed - sibling repos may be missing" }
    }
    Pop-Location
}

Write-Step "Deploy configs"
if (Test-UvReady) {
    Push-Location $DotfilesDir
    # status exits non-zero when there is drift; that is a report, not a failure.
    if (-not $DryRun) { uv run python src/deploy_configs.py }
    uv run python src/deploy_configs.py status
    Pop-Location
}

# %%
# Packages #

Write-Step "Packages"
if ($SkipApps) {
    Write-Skip "-SkipApps given"
} elseif (-not (Test-Path $DotfilesDir)) {
    Write-Warn "skipped (no dotfiles clone yet)"
} else {
    $chocoScript = Join-Path $DotfilesDir 'scripts\install_windows_apps_with_chocolatey.ps1'
    $wingetScript = Join-Path $DotfilesDir 'scripts\install_windows_apps_with_winget.ps1'

    # Check before calling: a stale clone silently produced nothing here, because
    # invoking a missing script only writes to the error stream.
    if (-not (Test-Path $chocoScript)) {
        Write-Fail "installer not found: $chocoScript (is this clone up to date?)"
    } elseif (-not $isAdmin) {
        Write-Warn "choco packages skipped (needs an elevated shell)"
    } else {
        $chocoArgs = @{ AssumeYes = $AssumeYes; DryRun = $DryRun }
        if ($ChocoList) { $chocoArgs['AppList'] = $ChocoList }
        & $chocoScript @chocoArgs
    }

    if (-not (Test-Path $wingetScript)) {
        Write-Fail "installer not found: $wingetScript (is this clone up to date?)"
    } else {
        & $wingetScript -AssumeYes:$AssumeYes -DryRun:$DryRun
    }
}

# %%
# What is left #

Write-Step "Still manual"
Add-Manual "OS settings (keyboard, display, power) are not managed - see docs/setup_windows_workstation_personal.md"
if ($script:ManualNotes.Count -eq 0) {
    Write-Ok "nothing outstanding"
} else {
    $script:ManualNotes | ForEach-Object { Write-Host "    - $_" -ForegroundColor Yellow }
}

Write-Step "Done"
if ($DryRun) {
    Write-Ok "dry run complete - re-run without -DryRun to apply"
} else {
    Write-Ok "bootstrap complete. Open a new shell to pick up the deployed profile."
}
