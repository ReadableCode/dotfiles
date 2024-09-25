# for some of the below commands to work, you will need a sym link to the dotfiles repo you cloned or synced
# Can be made like this (might need admin powershell window)
# cmd /c mklink /D "$HOME\GitHub\dotfiles" "C:\Users\16937827583938060798\HelloFreshProjects\dotfiles"
# or
# cmd /c mklink /D "$HOME\GitHub\dotfiles" "C:\Users\jason\GitHub\dotfiles"

# To manually source this file, cd to containing directory and run:
# . .\powershell_aliases.ps1

# To set up auto sourcing, deploy this to the file located at $PROFILE by running:
# notepad.exe $PROFILE
# Then paste the contents below into the file and save it.

######################

# $myDocumentsPath = [Environment]::GetFolderPath('MyDocuments')

# if (Test-Path 'C:\Users\jason\GitHub\dotfiles\application_configs\powershell\powershell_aliases.ps1') {
#     . 'C:\Users\jason\GitHub\dotfiles\application_configs\powershell\powershell_aliases.ps1'
# }
# elseif (Test-Path 'C:\Users\16937827583938060798\HelloFreshProjects\dotfiles\application_configs\powershell\powershell_aliases.ps1') {
#     . 'C:\Users\16937827583938060798\HelloFreshProjects\dotfiles\application_configs\powershell\powershell_aliases.ps1'
# }

######################

# to see this path run:
# $myDocumentsPath

# to set it if it is incorrect:
# go to "This PC" and right click documents and set location

# May need this command to trust sourcing file, run in admin powershell window
# Set-ExecutionPolicy RemoteSigned

### Path Modification ###

# $PathToAdd = "C:\Users\jason\AppData\Local\Programs\Python\Python311\Scripts"
# $CurrentPath = [Environment]::GetEnvironmentVariable("PATH", [EnvironmentVariableTarget]::User)
# [Environment]::SetEnvironmentVariable("PATH", $CurrentPath + ";" + $PathToAdd, [EnvironmentVariableTarget]::User)


### Variables ###

# $myDocumentsPath = [Environment]::GetFolderPath('MyDocuments')
# Write-Host "myDocumentsPath is: $myDocumentsPath"

if (Test-Path 'C:\Users\jason\GitHub\') {
    $gitDir = 'C:\Users\jason\GitHub\'
}
elseif (Test-Path 'C:\Users\16937827583938060798\HelloFreshProjects\') {
    $gitDir = 'C:\Users\16937827583938060798\HelloFreshProjects\'
}

# Write-Host "gitDir is: $gitDir"

function githubdir { Set-Location $gitDir }

# alias finance='cd ~/HelloFresh/GDrive/Projects/na-finops/'
function finance { Set-Location (Join-Path $gitDir 'na-finops') }


### Command Shortcuts ###

function ll {
    Get-ChildItem -Force
}

function cataliases {
    Get-Content $(Join-Path $gitDir '\dotfiles\application_configs\powershell\powershell_aliases.ps1')
}

function editaliases {
    nvim $(Join-Path $gitDir '\dotfiles\application_configs\powershell\powershell_aliases.ps1')
}

function deploytools {
    # run script at gitDir/Terminal_To_Do/src/main.py
    python $(Join-Path $gitDir 'Data_Tool_Pack_Py\src\deploy_tools.py')
}

function todo {
    # run script at gitDir/Terminal_To_Do/src/main.py
    python $(Join-Path $gitDir 'Terminal_To_Do\src\main.py')
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


### AI ###


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


### Jupyter ###

function startjupyterlab {
    # Change to the directory defined by $gitDir
    Set-Location $gitDir

    # Run the jupyter lab command
    jupyter-lab --ip=0.0.0.0 --port=8181
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
function sshryzenwhite { ssh jason@RyzenWhite }
function sshspectre { ssh jason@Spectre }
function sshzephyrus { ssh jason@JasonZephyrus }
function sshmac { ssh jason@MacbookPro12 }

# Upstairs Rack #
function sshelite { ssh jason@EliteDesk }
function sshnuk { ssh jason@nukbuntu }
function sshopti { ssh jason@Optiplex9020 }
function sshpav5 { ssh jason@Pavilioni5 }

# Servers #
function sshbehemoth { ssh root@behemoth }

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

# Android #
function sshtabs7p { ssh u0_a1053@GalaxyTabS7P -p 8022 }

