# Only announce in interactive sessions. `ssh host '<command>'` launches
# powershell.exe with /c, and scp/sftp do the same, so an unconditional banner
# lands in the output of every remote command. Same reason .shared_aliases
# guards its echo with [[ $- == *i* ]].
$global:IsInteractiveShell = -not ([Environment]::GetCommandLineArgs() -match '(?i)^[-/](c|command|e|ec|encodedcommand|f|file)$')
if ($global:IsInteractiveShell) {
    Write-Host "Sourced: $PSCommandPath" -ForegroundColor Cyan
}

## Path Mods ###

# Point Neovim and gh at the repo config dir on any Windows machine (no symlink or hard link needed)
if ($env:OS -eq 'Windows_NT') {
    $env:XDG_CONFIG_HOME = "$env:USERPROFILE\GitHub\dotfiles\application_configs"
}


### Terminal Config ###

function cataliases {
    if (-not (Test-GitDir)) { return }
    Get-Content $(Join-Path $gitDir 'dotfiles\application_configs\powershell\powershell_aliases.ps1')
}

function editaliases {
    if (-not (Test-GitDir)) { return }
    nvim $(Join-Path $gitDir 'dotfiles\application_configs\powershell\powershell_aliases.ps1')
}

function srcaliases {
    # Reload the PowerShell profile. Dot-sourcing inside a function traps the
    # re-defined functions in this function's scope, so promote them to the
    # global scope afterwards or the session keeps the old definitions.
    . $PROFILE
    foreach ($fn in Get-ChildItem function:) {
        Set-Item -Path "function:global:$($fn.Name)" -Value $fn.ScriptBlock -Force
    }
}

if (Test-Path "C:\ProgramData\chocolatey\lib\diffutils\tools\bin\diff.exe") {
    if (Get-Alias diff -ErrorAction SilentlyContinue) {
        Remove-Item alias:diff -Force
    }
    function diff {
        & "C:\ProgramData\chocolatey\lib\diffutils\tools\bin\diff.exe" @args
    }
}

function treed {
    & "$env:SystemRoot\System32\tree.com" /f @args
}

Remove-Item alias:tree -ErrorAction SilentlyContinue
Set-Alias tree treed

# Prefer fastfetch over neofetch if available (matches bash config)
if (Get-Command fastfetch -ErrorAction SilentlyContinue) {
    Set-Alias neofetch fastfetch
}

### Paths ###

# $myDocumentsPath = [Environment]::GetFolderPath('MyDocuments')
# Write-Host "myDocumentsPath is: $myDocumentsPath"

# Ordered candidates for the git projects directory. First one that EXISTS wins —
# a candidate whose directory is absent is skipped, so a machine without ~\GitHub
# falls through to a later one. $PROFILE dot-sources this file straight out of
# the repo checkout, so the grandparent of this file's dotfiles clone is always
# a valid root — the fallback for machines whose clone lives somewhere
# nonstandard (tried after the personal roots, which must keep winning).
$global:gitDirCandidates = @(
    "$HOME\GitHub\",
    "$HOME\GitHubWSL\",
    (Split-Path (Split-Path (Split-Path $PSScriptRoot)))
)

# Context shards call this to add their own root; they must never assign $gitDir
# directly. Appended candidates are tried last, so a client root can never win on
# a machine that also has a personal one.
function Add-GitDirFallback {
    param([Parameter(Mandatory)][string]$Path)
    $global:gitDirCandidates += $Path
}

### Context shards ###

# Context-specific aliases live in per-context shard files deployed by each
# *_credentials overlay manifest into ~\.powershell_local.d\ (one shard per
# context, so a machine with several contexts cloned sources them all).
# Dot-sourced BEFORE $gitDir is resolved so a shard can register a root candidate
# via Add-GitDirFallback; $gitDir is resolved once afterwards, then used by
# everything below (down to the ssh alias loader at the end of this file).
if (Test-Path "$HOME\.powershell_local.d") {
    foreach ($shard in Get-ChildItem "$HOME\.powershell_local.d\*.ps1" | Sort-Object Name) {
        . $shard.FullName
    }
}

# Assigned at global scope for the same reason srcaliases promotes functions:
# a plain assignment during an in-function re-source would die with the
# function scope, leaving the session on the stale value from shell startup.
$global:gitDir = ''
foreach ($candidate in $gitDirCandidates) {
    if (Test-Path $candidate) {
        $global:gitDir = $candidate
        break
    }
}
# Exported so child processes (cmdr, scripts) see the same resolution the
# shell made - they must never re-derive this themselves.
$env:gitDir = $gitDir

# Write-Host "gitDir is: $gitDir"

function Test-GitDir {
    if ([string]::IsNullOrEmpty($gitDir)) {
        Write-Host "gitDir is not set" -ForegroundColor Red
        return $false
    }
    return $true
}

function githubdir {
    if (-not (Test-GitDir)) { return }
    Set-Location $gitDir
}
function myscripts {
    if (-not (Test-GitDir)) { return }
    Set-Location (Join-Path $gitDir 'dotfiles\scripts')
}
function datatoolpack {
    if (-not (Test-GitDir)) { return }
    Set-Location (Join-Path $gitDir 'Data_Tool_Pack_Py')
}


### Python ###

function venvactivate {
    # Walk upward from the current directory looking for a .venv folder
    $dir = Get-Item -Path (Get-Location)
    while ($null -ne $dir) {
        $venvPath = Join-Path $dir.FullName '.venv\Scripts\activate.ps1'
        if (Test-Path $venvPath) {
            Write-Host "Activating virtual environment: $venvPath" -ForegroundColor Green
            & $venvPath
            return
        }
        $dir = $dir.Parent
    }
    Write-Host "venvactivate: no .venv found in $(Get-Location) or any parent directory" -ForegroundColor Red
}

function venvdeactivate { deactivate }

# Run a python script with the right interpreter for ITS project, from any cwd.
#
# Walks up from the script's own directory for the nearest ancestor that looks
# like a project root (declares a pyproject.toml or carries a .venv), then:
#   uv run   - root has a pyproject.toml and uv is installed. uv creates and
#              syncs .venv on first use, so a fresh clone just works.
#   .venv    - root has one but is not a uv project.
#   system python - neither.
#
# The bash twin (run_python_script in application_configs/bash/.shared_aliases)
# resolves the same three ways. The two had drifted: bash had the walk-up
# search and its subshell isolation, this side had the uv branch (be3bfd4,
# 2026-08-11). Merged 2026-08-15 - change both or neither.
function run-python-script {
    param (
        [string]$scriptPath,
        # Capture any extra arguments to pass through to the Python script
        [Parameter(ValueFromRemainingArguments)]
        [string[]]$scriptArgs
    )

    if (-not $scriptPath) {
        Write-Host "Usage: run-python-script <python_script_path> [args...]"
        return 1
    }

    # Resolve to an absolute path so it still points at the right file after we
    # change directories below.
    $resolvedScript = Resolve-Path -Path $scriptPath -ErrorAction SilentlyContinue
    if (-not $resolvedScript) {
        Write-Host "Script not found: $scriptPath" -ForegroundColor Red
        return 1
    }
    $scriptPath = $resolvedScript.Path
    $scriptDir = Split-Path -Parent $scriptPath

    Write-Host "Running Python script: $scriptPath"

    # Nearest ancestor holding either project marker, starting at the script's
    # own directory. Empty when there is no project above it. Replaces the old
    # hardcoded "..", which only ever found a project exactly one level up.
    $projectRoot = ''
    $dir = Get-Item -LiteralPath $scriptDir
    while ($null -ne $dir) {
        if ((Test-Path (Join-Path $dir.FullName 'pyproject.toml')) -or (Test-Path (Join-Path $dir.FullName '.venv'))) {
            $projectRoot = $dir.FullName
            break
        }
        $dir = $dir.Parent
    }

    # Stay in the script's directory, not the project root: scripts that open
    # files by relative path expect it, and uv finds the project by walking up
    # from here anyway. Push-Location so the change is undone in the finally
    # block and does not leak into the caller's session.
    Write-Host "Changing to script directory: $scriptDir"
    Push-Location -Path $scriptDir
    $activated = $false
    try {
        if ($projectRoot -and (Test-Path (Join-Path $projectRoot 'pyproject.toml')) -and
            (Get-Command uv -ErrorAction SilentlyContinue)) {
            Write-Host "uv project detected at: $projectRoot"
            uv run python $scriptPath @scriptArgs
            return
        }

        $venvActivate = if ($projectRoot) { Join-Path $projectRoot '.venv\Scripts\Activate.ps1' } else { '' }
        if ($venvActivate -and (Test-Path $venvActivate)) {
            Write-Host "Project .venv detected at: $(Join-Path $projectRoot '.venv')"
            & $venvActivate
            $activated = $true
            python $scriptPath @scriptArgs
            return
        }

        Write-Host "No uv project or .venv found. Running the script with system Python."
        python $scriptPath @scriptArgs
    }
    finally {
        # Deactivate HERE, not after the run: PowerShell activates in-process,
        # so a script that threw used to leave the venv live in the caller's
        # session. The bash twin gets this free from its subshell.
        if ($activated -and (Get-Command deactivate -ErrorAction SilentlyContinue)) { deactivate }
        Pop-Location
    }
}

function todo {
    if (-not (Test-GitDir)) { return }
    # Run the main.py script using run-python-script
    $scriptPath = (Join-Path $gitDir 'Terminal_To_Do\src\main.py')
    run-python-script $scriptPath
}

function statusboard {
    if (-not (Test-GitDir)) { return }
    $scriptPath = (Join-Path $gitDir 'status_board\src\status_board.py')
    run-python-script $scriptPath @args
}

function cashflow {
    if (-not (Test-GitDir)) { return }
    $scriptPath = (Join-Path $gitDir 'Cash_Flow_Commander\src\cfc_tui.py')
    run-python-script $scriptPath @args
}


### Command Shortcuts ###

function ll {
    Get-ChildItem -Force
}

function which {
    Get-Command $args
}

function openbranchdiffs {
    # Navigate to the root of the Git repository
    $repoRoot = git rev-parse --show-toplevel 2>$null
    if (-not $repoRoot) {
        Write-Host "Not a Git repository." -ForegroundColor Red
        return
    }
    Set-Location -Path $repoRoot

    # Fetch to ensure the remote default branch is up to date before diffing
    git fetch -q

    # Detect the remote default branch instead of assuming origin/master
    $base = git symbolic-ref --short refs/remotes/origin/HEAD 2>$null
    if (-not $base) { $base = 'origin/master' }

    # base...HEAD diffs from the merge-base, so only this branch's own commits count;
    # --diff-filter=d drops files deleted on this branch, Test-Path drops renamed-away paths
    $changedFiles = git diff --name-only --diff-filter=d "$base...HEAD" | Where-Object { Test-Path -LiteralPath $_ }

    if (-not $changedFiles) {
        Write-Host "No files changed on this branch relative to $base." -ForegroundColor Yellow
        return
    }

    # Open all changed files in one VSCode invocation
    code @($changedFiles)
}

# Fuzzy-pick a branch (most recently committed first, remotes included) and switch to it.
# Esc aborts; picking a remote-only branch creates the local tracking branch via git switch.
function gsw {
    if (-not (Get-Command fzf -ErrorAction SilentlyContinue)) {
        Write-Host "fzf is not installed" -ForegroundColor Red
        return
    }
    git rev-parse --git-dir 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Not a Git repository." -ForegroundColor Red
        return
    }
    $branch = git branch -a --sort=-committerdate --format='%(refname:short)' |
        ForEach-Object { $_ -replace '^origin/', '' } |
        Where-Object { $_ -ne 'HEAD' } |
        Select-Object -Unique |
        fzf --preview 'git log --oneline --color=always -10 {}' --ansi
    if ($branch) { git switch $branch }
}

# pullrepos: pull every repo under $gitDir in parallel via the committed
# git_puller binary. Never aborts the caller: repos that cannot be pulled
# (WIP protected, failed, auth required) get a summary warning so later steps
# knowingly run from those repos' current, possibly stale, checkouts.
function pullrepos {
    if (-not (Test-GitDir)) { return }
    $binary = Join-Path $gitDir "dotfiles/go_apps/git_puller/git_puller.exe"
    & $binary -path $gitDir -r | Tee-Object -Variable pullOutput
    $unpulled = @($pullOutput | Where-Object { $_ -match '^\[(WIP PROTECTED|FAILED|AUTH REQUIRED)\]' }).Count
    if ($unpulled -gt 0) {
        Write-Host "WARNING: $unpulled repo(s) could not be pulled (tagged above) - later steps run from their current, possibly stale, checkouts." -ForegroundColor Yellow
    }
}

# clonerepos: offer clones of entitled-but-missing repos, driven by the
# <context>_repos.yaml configs in the *_credentials repos (which a preceding
# pullrepos refreshes). Runs from anywhere via --project, like deployconfigs.
function clonerepos {
    if (-not (Test-GitDir)) { return }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "clonerepos: uv is not installed (wanted to run src/clone_repos.py)"
        return
    }
    $repo = Join-Path $gitDir 'dotfiles'
    uv run --project $repo python (Join-Path $repo 'src\clone_repos.py')
}

# updatepackages: OS package updates only (winget, then choco) - no repo
# pulls, no config deploy.
function updatepackages {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Updating via winget..." -ForegroundColor Green
        winget upgrade --all
    }
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        Write-Host "Updating via Chocolatey..." -ForegroundColor Green
        choco upgrade all -y
    }
}

# The shared tail of gitpullall and myupdater. Clone check first (a fresh
# clone may be a deploy target), then deploy (idempotent, and re-links the
# hard links the pulls just orphaned on no-symlink machines like work
# laptops), then prune with --apply: the removals files are a committed list
# of paths that must not exist, so every machine has to act on them for the
# list to ever be finished. A dry run here would reprint the same dead links
# forever and still need a second command by hand. Safe after the deploy
# because prune only removes a path a removals entry names AND no live
# manifest entry wants (see docs/deploy_configs.md). The slow AutoHotkey
# probes (registry scan, choco list) ride along last - too expensive for
# shell startup, cheap here where seconds do not matter. Silent on a correct
# machine.
function _FleetRefreshConfigs {
    Write-Host "==============  Checking for repos to clone  ==============" -ForegroundColor Cyan
    clonerepos
    Write-Host ""
    Write-Host "==============  Deploying configs  ==============" -ForegroundColor Cyan
    deployconfigs
    Write-Host ""
    Write-Host "==============  Pruning removed configs  ==============" -ForegroundColor Cyan
    deployconfigs prune --apply
    $ensureAhk = Join-Path $gitDir 'dotfiles\scripts\ensure_autohotkey_v2.ps1'
    if (Test-Path $ensureAhk) { & $ensureAhk -AutoFix -Full }
}

function gitpullall {
    if (-not (Test-GitDir)) { return }
    pullrepos
    Write-Host ""
    _FleetRefreshConfigs
}

# Bring this machine's AutoHotkey install in line with the repo's v2 scripts:
# installs/upgrades v2, removes v1, repoints the .ahk association. Idempotent -
# does nothing on a machine that is already correct. Pass -Check for a
# read-only report.
function ensureahk {
    if (-not (Test-GitDir)) { return }
    & (Join-Path $gitDir 'dotfiles\scripts\ensure_autohotkey_v2.ps1') @args
}

# Keep AutoHotkey on the radar without anyone having to remember a command:
# every interactive shell runs the CHEAP probe (~100 ms) and stays completely
# silent when the machine is already v2-only. When it is not, it REPORTS and
# points at `ensureahk` - it deliberately does not fix from here.
#
# -Check, not -AutoFix: fixing needs admin, and raising UAC from a profile
# means every new shell hangs on a modal prompt until it is answered (a
# declined-looking prompt cost 60 s of profile load on a work laptop,
# 2026-08-17). The fixing pass belongs where a wait is expected - `ensureahk`,
# or `gitpullall`, which runs -AutoFix -Full further down.
#
# Interactive only: `ssh host '<command>'`, scp and every -File/-Command run
# skip it, so remote commands neither pay the probe nor print a nag nobody is
# sitting in front of.
if ($global:IsInteractiveShell -and $gitDir) {
    $ensureAhkOnStart = Join-Path $gitDir 'dotfiles\scripts\ensure_autohotkey_v2.ps1'
    if (Test-Path $ensureAhkOnStart) {
        # A broken probe must never take the profile (and the shell) with it.
        try { & $ensureAhkOnStart -Check } catch {
            Write-Host "ensure_autohotkey_v2.ps1 failed: $_" -ForegroundColor DarkYellow
        }
    }
}

### Script Shortcuts ###

# cmdr: the fleet CLI/TUI (go_apps/cmdr). Its binary is built per machine and
# never committed, so it builds itself on first use - including installing the
# go toolchain when the machine has none, because "install go by hand first" is
# not something a fleet command may ask for. A release install will replace
# this shim eventually (docs/unified_cli_tui.md).
function cmdr {
    if (-not (Test-GitDir)) { return }
    $dir = Join-Path $gitDir 'dotfiles\go_apps\cmdr'
    $bin = Join-Path $dir 'cmdr.exe'
    # cargo-run semantics: rebuild only when a source file is newer than the
    # binary (a git pull freshens mtimes, so the next run after a pull
    # rebuilds itself).
    $stale = -not (Test-Path $bin)
    if (-not $stale) {
        $binTime = (Get-Item $bin).LastWriteTime
        $newer = Get-ChildItem $dir -File | Where-Object {
            ($_.Extension -eq '.go' -or $_.Name -in 'go.mod', 'go.sum') -and $_.LastWriteTime -gt $binTime
        }
        $stale = [bool]$newer
    }
    if ($stale) {
        Write-Host "cmdr: building (no binary yet, or sources are newer)..."
        # ensure_go.ps1 emits the go path and nothing else, installing a
        # toolchain first if the machine has none. It is re-run on every stale
        # invocation rather than remembering a failure: you only get here by
        # typing cmdr, so a retry is what you asked for.
        $ensure = Join-Path $gitDir 'dotfiles\scripts\ensure_go.ps1'
        $goBin = $null
        if (Test-Path $ensure) {
            # Select-Object -Last 1 and a Test-Path guard: an installer that
            # narrates to the success stream would otherwise hand back its own
            # output with the path buried in it (dnf did exactly this on the
            # bash side, 2026-09-01).
            $goBin = & $ensure | Select-Object -Last 1
            if ($LASTEXITCODE -ne 0 -or -not ($goBin -and (Test-Path -LiteralPath $goBin))) { $goBin = $null }
        } else {
            # clone predates ensure_go.ps1
            $onPath = Get-Command go -ErrorAction SilentlyContinue
            if ($onPath) { $goBin = $onPath.Source }
        }
        if ($goBin) {
            Push-Location $dir
            & $goBin build .
            Pop-Location
            if (-not (Test-Path $bin)) { return }
        } elseif (Test-Path $bin) {
            Write-Host "cmdr: no go toolchain and none could be installed - running the existing binary"
        } else {
            Write-Host "cmdr: no go toolchain and none could be installed, so $bin cannot be built (see docs/setup_go.md)"
            return
        }
    }
    & $bin @args
}

# deployconfigs: run the dotfiles config deploy from anywhere (uv resolves the
# repo venv via --project, so no cd needed). Args pass straight through and the
# script itself defaults to `deploy`, so bare `deployconfigs` deploys and
# `deployconfigs prune --apply` / `deployconfigs status` work as written.
function deployconfigs {
    if (-not (Test-GitDir)) { return }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "deployconfigs: uv is not installed (wanted to run src/deploy_configs.py)"
        return
    }
    $repo = Join-Path $gitDir 'dotfiles'
    uv run --project $repo python (Join-Path $repo 'src\deploy_configs.py') @args
}

function ntfyme {
    if (-not (Test-GitDir)) { return }
    & (Join-Path $gitDir 'dotfiles\.venv\Scripts\python.exe') (Join-Path $gitDir 'dotfiles\scripts\ntfyme.py') @args
}

# myupdater: gitpullall plus package updates. The packages run between the
# pull and the deploy so anything an upgrade clobbers gets re-linked.
function myupdater {
    if (-not (Test-GitDir)) { return }
    Write-Host "#################   Running System Update   #####################" -ForegroundColor Cyan
    pullrepos
    Write-Host ""
    Write-Host "==============  Updating packages  ==============" -ForegroundColor Cyan
    updatepackages
    Write-Host ""
    _FleetRefreshConfigs
}

function weather {
    Invoke-RestMethod "https://wttr.in"
}

function getpubip {
    (Invoke-WebRequest -Uri "https://ifconfig.me/ip" -UseBasicParsing).Content.Trim()
}

function speed { speedtest }

### Servers ###

function startjupyterlab {
    if (-not (Test-GitDir)) { return }
    # Change to the directory defined by $gitDir
    Set-Location $gitDir

    # Run the jupyter lab command
    jupyter-lab --ip=0.0.0.0 --port=8181
}

### AI Shortcuts ###

# On machines where Claude Code can't be installed directly (e.g. the work
# laptop), the VS Code Remote/server extension ships a full `claude` binary.
# Resolve it dynamically each call so it survives the extension's version-folder
# churn (a new anthropic.claude-code-<version> dir is created on every update).
# Only defined when there's no native `claude` on PATH, so it never shadows a
# real install on other machines.
# Intended to run from the VS Code integrated terminal: we invoke the binary
# plainly (no CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL), so it inherits VS Code's env
# for IDE integration and will auto-(re)install the extension if it's missing.
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    function claude {
        $extRoots = @(
            (Join-Path $env:USERPROFILE '.vscode-server\extensions'),
            (Join-Path $env:USERPROFILE '.vscode-server-insiders\extensions'),
            (Join-Path $env:USERPROFILE '.local\share\code-server\extensions')
        )
        $bin = $extRoots |
            Where-Object { Test-Path $_ } |
            ForEach-Object { Get-ChildItem $_ -Directory -Filter 'anthropic.claude-code-*' -ErrorAction SilentlyContinue } |
            ForEach-Object { Get-ChildItem $_.FullName -Recurse -Filter 'claude.exe' -ErrorAction SilentlyContinue } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if (-not $bin) {
            Write-Error "claude.exe not found under any VS Code extensions dir (is the Claude Code extension installed?)"
            return
        }
        & $bin.FullName @args
    }
}

function startollama {
    if (Get-Command ollama -ErrorAction SilentlyContinue) {
        ollama serve
    }
    else {
        Write-Host "ollama is not installed. Download from https://ollama.ai" -ForegroundColor Yellow
    }
}

function pullollamamodels { ollama pull llama2-uncensored }
function runollama { ollama run llama2-uncensored }
function stopollama { Stop-Process -Name "ollama" -ErrorAction SilentlyContinue }

function startstablediffusion {
    if (-not (Test-GitDir)) { return }
    $scriptPath = "~\GitHub\stable-diffusion-webui\webui.bat"
    $scriptDir = Split-Path $scriptPath

    # Define the path to the .env file (deployed from the credentials repo, absent on machines without it)
    $envFilePath = "$gitDir\dotfiles\.env"
    if (-not (Test-Path $envFilePath)) {
        Write-Host "No .env at $envFilePath" -ForegroundColor Red
        return
    }

    # Read the .env file and extract the password
    $envContent = Get-Content $envFilePath | Where-Object { $_ -match "^GRADIO_AUTH_PASSWORD=" }
    $password = $envContent -replace "GRADIO_AUTH_PASSWORD=", ""
    if ([string]::IsNullOrEmpty($password)) {
        Write-Host "GRADIO_AUTH_PASSWORD is not set in $envFilePath" -ForegroundColor Red
        return
    }

    # Change location to the script directory
    Set-Location $scriptDir

    & $scriptPath --listen --gradio-auth jason:$password
}

function startstablediffusionamd {
    if (-not (Test-GitDir)) { return }
    $scriptPath = "~\GitHub\stable-diffusion-webui-amdgpu\webui.bat"
    $scriptDir = Split-Path $scriptPath

    # Define the path to the .env file (deployed from the credentials repo, absent on machines without it)
    $envFilePath = "$gitDir\dotfiles\.env"
    if (-not (Test-Path $envFilePath)) {
        Write-Host "No .env at $envFilePath" -ForegroundColor Red
        return
    }

    # Read the .env file and extract the password
    $envContent = Get-Content $envFilePath | Where-Object { $_ -match "^GRADIO_AUTH_PASSWORD=" }
    $password = $envContent -replace "GRADIO_AUTH_PASSWORD=", ""
    if ([string]::IsNullOrEmpty($password)) {
        Write-Host "GRADIO_AUTH_PASSWORD is not set in $envFilePath" -ForegroundColor Red
        return
    }

    # Change location to the script directory
    Set-Location $scriptDir

    & $scriptPath --listen --gradio-auth jason:$password --skip-torch-cuda-test --no-half --use-directml --lowvram
}

### GPU Shortcuts ###

function gpustatus {
    # Windows equivalent of 'watch -n 0.5 nvidia-smi'
    while ($true) {
        Clear-Host
        nvidia-smi
        Start-Sleep -Milliseconds 500
    }
}

### Kubectl ###

function k { kubectl @args }
function kgp { kubectl get pods -o wide @args }
function kgn { kubectl get nodes -o wide @args }

### WSL ###

function wsllistdistros {
    wsl --list
}

function wslbashinto {
    wsl
}

function wslbashintodistro {
    wsl -d $args
}

### WiFi ###

function getwifiname {
    (netsh wlan show interfaces) | ForEach-Object {
        if ($_ -match '^\s*SSID\s+:\s+(.*)') {
            return $matches[1]
        }
    } | Where-Object { $_ }
}


function getwifipass {
    $wifiName = getwifiname
    (netsh wlan show profile name="$wifiName" key=clear)  | ForEach-Object {
        if ($_ -match 'Key Content\s+:\s+(.*)') {
            return $matches[1]
        }
    } | Where-Object { $_ }
}


function showwifi {
    $wifiName = getwifiname
    $wifiPass = getwifipass
    Write-Host "WiFi Name: $wifiName"
    Write-Host "WiFi Pass: $wifiPass"
}


### SSH Shortcuts (generated from <gitDir>\*_credentials host inventories) ###

# First interpreter that can run a stdlib-only script, or '' when there is none.
#
# Two things make this more than a Get-Command call on Windows:
#   * "python3.exe"/"python.exe" under WindowsApps are App Execution Alias
#     STUBS that open the Microsoft Store instead of running anything, so they
#     are skipped by path.
#   * a real .exe is preferred over a shim, because `python3` often resolves to
#     a pyenv-win .bat that re-launches through cmd: measured on RyzenWhite
#     2026-08-15, the same generator run took ~610 ms through the shim and
#     ~110 ms through C:\Python314\python.exe. Shims are still used when
#     nothing else is installed - slow aliases beat no aliases.
# The dotfiles venv is the last resort, for a machine whose only Python is the
# one uv created.
function Get-PythonCommand {
    if ($global:resolvedPythonCommand) { return $global:resolvedPythonCommand }
    $candidates = @()
    foreach ($name in @('python3', 'python')) {
        $found = Get-Command $name -ErrorAction SilentlyContinue
        if ($found -and $found.Source -notmatch '\\WindowsApps\\') { $candidates += $found.Source }
    }
    if ($gitDir) { $candidates += (Join-Path $gitDir 'dotfiles\.venv\Scripts\python.exe') }
    # Real executables first, everything else (shims, and the extensionless
    # python3 of a macOS/Linux pwsh) in its original order after them.
    $ordered = @($candidates | Where-Object { $_ -like '*.exe' }) + @($candidates | Where-Object { $_ -notlike '*.exe' })
    foreach ($candidate in $ordered) {
        if (Test-Path $candidate) { $global:resolvedPythonCommand = $candidate; return $candidate }
    }
    return ''
}

# The ssh aliases are built by ONE cross-shell generator,
# <gitDir>\dotfiles\src\ssh_aliases.py: it reads every <gitDir>\*_credentials
# host inventory and prints ready-to-invoke definitions. .shared_aliases evals
# that same script's --format bash output, so jump-host resolution, port
# handling and user selection have a single implementation instead of two twins
# kept in step by hand. See its module docstring and
# docs/client_credentials_repos.md for the inventory schema.
#
# The generated definitions are `Set-Item function:global:<alias>` statements —
# functions, not Set-Alias, because a PowerShell alias is a bare command name
# and cannot carry the ssh arguments. vnc aliases are emitted on macOS only, so
# a Windows session gets none (nothing there handles vnc://).
#
# No usable Python (or no generator on disk) just means no ssh aliases; nothing
# else in this profile depends on them.
$sshAliasGenerator = if ($gitDir) { Join-Path $gitDir 'dotfiles\src\ssh_aliases.py' } else { '' }
if ($sshAliasGenerator -and (Test-Path $sshAliasGenerator)) {
    $pythonCommand = Get-PythonCommand
    if ($pythonCommand) {
        # Captured first and invoked only on a clean exit, so a generator that
        # dies mid-output can never leave the session running half a definition.
        $generatedAliases = & $pythonCommand $sshAliasGenerator --format powershell --root $gitDir
        if ($LASTEXITCODE -eq 0 -and $generatedAliases) {
            $generatedAliases | Out-String | Invoke-Expression
        }
    }
}
