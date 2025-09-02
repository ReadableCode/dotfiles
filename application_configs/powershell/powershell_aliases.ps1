## Path Mods ###

if ($env:COMPUTERNAME -eq 'FFLAP-2229') {
    $paths = @(
        'C:\Users\jason.christiansen\userapps\nvim-win64\bin',
        'C:\Users\jason.christiansen\userapps\WPy64-31350\python',
        'C:\Users\jason.christiansen\userapps\WPy64-31350\python\Scripts',
        'C:\Users\jason.christiansen\userapps\PortableGit\bin'
    )
    $curr = ($env:Path -split ';') | Where-Object { $_ }
    foreach ($p in $paths) {
        if ( (Test-Path -LiteralPath $p) -and -not ($curr -contains $p) ) {
            $env:Path = "$p;$env:Path"
        }
    }
}


### Terminal Config ###

function cataliases {
    Get-Content $(Join-Path $gitDir 'dotfiles\application_configs\powershell\powershell_aliases.ps1')
}

function editaliases {
    nvim $(Join-Path $gitDir 'dotfiles\application_configs\powershell\powershell_aliases.ps1')
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

### Paths ###

# $myDocumentsPath = [Environment]::GetFolderPath('MyDocuments')
# Write-Host "myDocumentsPath is: $myDocumentsPath"

$basePath = $HOME
if (Test-Path "$basePath\GitHub\") {
    $gitDir = "$basePath\GitHub\"
}
elseif (Test-Path "$basePath\HelloFreshProjects\") {
    $gitDir = "$basePath\HelloFreshProjects\"
}

# Write-Host "gitDir is: $gitDir"

function githubdir { Set-Location $gitDir }
function fourdir { Set-Location 'C:\Users\jason\OneDrive - Fourteen Foods\code' }

# alias finance='cd ~/HelloFresh/GDrive/Projects/na-finops/'
function finance { Set-Location (Join-Path $gitDir 'na-finops') }


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
        [string]$scriptPath
    )

    if (-not $scriptPath) {
        Write-Host "Usage: run-python-script <python_script_path>"
        return 1
    }

    Write-Host "Running Python script: $scriptPath"

    # Extract the directory from the provided file path
    $scriptDir = Split-Path -Parent $scriptPath

    # Change to the script directory
    Write-Host "Changing to script directory: $scriptDir"
    Set-Location -Path $scriptDir

    # Check if the venv folder exists in the project directory
    if (Test-Path "..\.venv") {
        Write-Host "Project venv detected at: ./venv"

        # Activate the venv environment
        ..\.venv\Scripts\Activate.ps1

        # Run the script using the venv environment
        python $scriptPath

        # Deactivate the environment afterward
        deactivate
        return 0
    }
    else {
        Write-Host "No project venv found. Running the script with system Python."
    }

    # Run the script using the system Python as a fallback
    python $scriptPath
}

function deploytools {
    # Run the deploy_tools.py script using run-python-script
    $scriptPath = (Join-Path $gitDir 'Data_Tool_Pack_Py\src\deploy_tools.py')
    run-python-script $scriptPath
}

function todo {
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

    # Get the list of files changed between master and the current branch
    $changedFiles = git diff --name-only master...HEAD

    if (-not $changedFiles) {
        Write-Host "No differences between master and HEAD." -ForegroundColor Yellow
        return
    }

    # Open each changed file in VSCode
    $changedFiles | ForEach-Object { code $_ }
}

function gitpullall {
    $binary = Join-Path $gitDir "dotfiles/go_apps/git_puller/git_puller.exe"
    & $binary -path $gitDir -r
}

### Servers ###

function startjupyterlab {
    # Change to the directory defined by $gitDir
    Set-Location $gitDir

    # Run the jupyter lab command
    jupyter-lab --ip=0.0.0.0 --port=8181
}

### AI Shortcuts ###

function startstablediffusion {
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


### SSH Shortcuts ###

# Workstations #
function sshryzenwhite { ssh jason@192.168.86.94 }
function sshspectre { ssh jason@Spectre }
function sshzephyrus { ssh jason@JasonZephyrus }
function sshmac { ssh jason@MacbookPro12 }

# Upstairs Rack #
function sshelite { ssh jason@192.168.86.179 }
function sshnuk { ssh jason@nukbuntu }
function sshopti { ssh jason@Optiplex9020 }
function sshpav5 { ssh jason@Pavilioni5 }

# Servers #
function sshbehemoth { ssh root@192.168.86.31 }

# Appliancs #
function sshpi4 { ssh pi@raspberrypi4 }
function sshpi4a { ssh pi@raspberrypi4a }
function sshpi3 { ssh pi@raspberrypi3 }
function sshpi3a { ssh pi@raspberrypi3a }
function sshpi0 { ssh pi@raspberrypi0 }

# Rebeca #
function sshshelly { ssh rebeca@Shelly }

# HelloFresh #
function sshhello { ssh jason@192.168.86.4 }
function sshhellowin { ssh HELLOFRESH\\16937827583938060798@HelloFreshWindows }

# Fourteen Foods #
function ssh14 { ssh jason.christiansen@192.168.86.126 }

# Android #
function sshtabs7p { ssh u0_a1053@GalaxyTabS7P -p 8022 }

