Write-Host "Sourced: $PSCommandPath" -ForegroundColor Cyan

## Path Mods ###

if ($env:COMPUTERNAME -eq 'FFLAP-2229') {
    $paths = @(
        'C:\Windows\System32',
        'C:\Users\jason.christiansen\userapps\nvim-win64\bin',
        'C:\Users\jason.christiansen\userapps\node',
        'C:\Users\jason.christiansen\userapps\ripgrep',
        'C:\Users\jason.christiansen\userapps\fd',
        'C:\Users\jason.christiansen\userapps\WPy64-31350\python',
        'C:\Users\jason.christiansen\userapps\WPy64-31350\python\Scripts',
        'C:\Users\jason.christiansen\userapps\PortableGit\bin',
        'C:\Users\jason.christiansen\userapps\fzf-0.66.1-windows_amd64',
        'C:\Users\jason.christiansen\userapps\rust\cargo\bin',
        'C:\msys64\mingw64\bin',
        'C:\msys64\usr\bin'
    )
    $curr = ($env:Path -split ';') | Where-Object { $_ }
    foreach ($p in $paths) {
        if ( (Test-Path -LiteralPath $p) -and -not ($curr -contains $p) ) {
            $env:Path = "$p;$env:Path"
        }
    }
    Remove-Item Env:\GIT_SSH -ErrorAction SilentlyContinue

    # Set CC to gcc for any builds that might need it
    $env:CC = "gcc"

    # Tell rustup/cargo to keep their state under userapps instead of the home dir
    $env:RUSTUP_HOME = "$env:USERPROFILE\userapps\rust\rustup"
    $env:CARGO_HOME = "$env:USERPROFILE\userapps\rust\cargo"

    # print that we ran custom config for 14
    Write-Host "14 Foods custom config loaded" -ForegroundColor Green
}

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
    # Reload the PowerShell profile
    . $PROFILE
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

# Find the git projects directory across different machine setups
$basePath = $HOME
if (Test-Path "$basePath\GitHub\") {
    $gitDir = "$basePath\GitHub\"
}
elseif (Test-Path "$basePath\GitHubWSL\") {
    $gitDir = "$basePath\GitHubWSL\"
}
elseif (Test-Path "$basePath\HelloFreshProjects\") {
    $gitDir = "$basePath\HelloFreshProjects\"
}
else {
    $gitDir = ''
}

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
function fourdir { Set-Location 'C:\Users\jason\OneDrive - Fourteen Foods\code' }
function myscripts {
    if (-not (Test-GitDir)) { return }
    Set-Location (Join-Path $gitDir 'dotfiles\scripts')
}
function datatoolpack {
    if (-not (Test-GitDir)) { return }
    Set-Location (Join-Path $gitDir 'Data_Tool_Pack_Py')
}

# alias finance='cd ~/HelloFresh/GDrive/Projects/na-finops/'
function finance {
    if (-not (Test-GitDir)) { return }
    Set-Location (Join-Path $gitDir 'na-finops')
}


### Python ###

function venvactivate {
    # Set the path to the virtual environment's Activate.ps1 script
    $venvPath = Join-Path (Get-Location) '.venv\Scripts\activate.ps1'

    # Check if the script exists
    if (Test-Path $venvPath) {
        Write-Host "Activating virtual environment..." -ForegroundColor Green
        # Source the script to activate the environment
        & $venvPath
    }
    else {
        Write-Host "Virtual environment activation script not found at: $venvPath" -ForegroundColor Red
    }
}

function venvdeactivate { deactivate }

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

    Write-Host "Running Python script: $scriptPath"

    # Resolve to an absolute path so it still points at the right file after we
    # change directories below.
    $resolvedScript = Resolve-Path -Path $scriptPath -ErrorAction SilentlyContinue
    if (-not $resolvedScript) {
        Write-Host "Script not found: $scriptPath"
        return 1
    }
    $scriptPath = $resolvedScript.Path

    # Extract the directory from the resolved file path
    $scriptDir = Split-Path -Parent $scriptPath

    # Change to the script directory with Push-Location so the change is undone
    # in the finally block and does not leak into the caller's session.
    Write-Host "Changing to script directory: $scriptDir"
    Push-Location -Path $scriptDir
    try {
        # Look for a .venv one level up from the script (standard project layout)
        if (Test-Path "..\.venv") {
            Write-Host "Project .venv detected at: ..\.venv"

            # Activate the venv environment
            ..\.venv\Scripts\Activate.ps1

            # Run the script using the venv environment, passing through any extra args
            python $scriptPath @scriptArgs

            # Deactivate the environment afterward
            deactivate
            return 0
        }
        else {
            Write-Host "No project .venv found in parent directory. Running the script with system Python."
        }

        # Run the script using the system Python as a fallback
        python $scriptPath @scriptArgs
    }
    finally {
        Pop-Location
    }
}

function deploytools {
    if (-not (Test-GitDir)) { return }
    # Run the deploy_tools.py script using run-python-script
    $scriptPath = (Join-Path $gitDir 'Data_Tool_Pack_Py\src\deploy_tools.py')
    run-python-script $scriptPath
}

function todo {
    if (-not (Test-GitDir)) { return }
    # Run the main.py script using run-python-script
    $scriptPath = (Join-Path $gitDir 'Terminal_To_Do\src\main.py')
    run-python-script $scriptPath
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

    # Fetch to ensure origin/master is up to date before diffing
    git fetch -q

    # Get the list of files changed between origin/master and the current branch
    $changedFiles = git diff --name-only origin/master...HEAD

    if (-not $changedFiles) {
        Write-Host "No differences between origin/master and HEAD." -ForegroundColor Yellow
        return
    }

    # Open each changed file in VSCode
    $changedFiles | ForEach-Object { code $_ }
}

function gitpullall {
    if (-not (Test-GitDir)) { return }
    $binary = Join-Path $gitDir "dotfiles/go_apps/git_puller/git_puller.exe"
    & $binary -path $gitDir -r
}

### Script Shortcuts ###

function ntfyme {
    if (-not (Test-GitDir)) { return }
    & (Join-Path $gitDir 'dotfiles\.venv\Scripts\python.exe') (Join-Path $gitDir 'dotfiles\scripts\ntfyme.py') @args
}

function myupdater {
    Write-Host "#################   Running System Update   #####################" -ForegroundColor Cyan
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Updating via winget..." -ForegroundColor Green
        winget upgrade --all
    }
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        Write-Host "Updating via Chocolatey..." -ForegroundColor Green
        choco upgrade all -y
    }
    Write-Host "############ Done ############" -ForegroundColor Cyan
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

    # Define the path to the .env file
    $envFilePath = "$gitDir\dotfiles\.env"

    # Read the .env file and extract the password
    $envContent = Get-Content $envFilePath | Where-Object { $_ -match "^GRADIO_AUTH_PASSWORD=" }
    $password = $envContent -replace "GRADIO_AUTH_PASSWORD=", ""

    # Change location to the script directory
    Set-Location $scriptDir

    & $scriptPath --listen --gradio-auth jason:$password
}

function startstablediffusionamd {
    if (-not (Test-GitDir)) { return }
    $scriptPath = "~\GitHub\stable-diffusion-webui-amdgpu\webui.bat"
    $scriptDir = Split-Path $scriptPath

    # Define the path to the .env file
    $envFilePath = "$gitDir\dotfiles\.env"

    # Read the .env file and extract the password
    $envContent = Get-Content $envFilePath | Where-Object { $_ -match "^GRADIO_AUTH_PASSWORD=" }
    $password = $envContent -replace "GRADIO_AUTH_PASSWORD=", ""

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


### SSH Shortcuts (loaded from unified Ansible inventory) ###

$hostsFile = if ($gitDir) { Join-Path $gitDir 'dotfiles\inventory\hosts' } else { $null }
if ($hostsFile -and (Test-Path $hostsFile)) {
    Get-Content $hostsFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#') -and -not $line.StartsWith('[') -and $line -match 'ssh_alias=') {
            $parts = $line -split '\s+'
            $invHost = $parts[0]
            $vars = @{}
            foreach ($part in $parts[1..($parts.Length - 1)]) {
                if ($part -match '^([\w]+)=(.+)$') {
                    $vars[$matches[1]] = $matches[2]
                }
            }

            $alias = $vars['ssh_alias']
            $user = if ($vars.ContainsKey('ssh_user')) { $vars['ssh_user'] } elseif ($vars.ContainsKey('ansible_user')) { $vars['ansible_user'] } else { '' }
            $hostTarget = if ($vars.ContainsKey('ansible_host')) { $vars['ansible_host'] } else { $invHost }
            $port = if ($vars.ContainsKey('ansible_port')) { $vars['ansible_port'] } else { '' }

            $sshArgs = "$user@$hostTarget"
            if ($port) { $sshArgs = "-p $port $sshArgs" }

            if ($alias -and $user) {
                Set-Item -Path "function:global:$alias" -Value ([scriptblock]::Create("ssh $sshArgs")) -Force
            }
        }
    }
}
