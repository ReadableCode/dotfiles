# Setup Windows Workstation

## Update and Rename System

* Update Windows (don't restart)
* Open Windows App Store and update "app installer"
* Change name of system to something useful and update and restart

## Enable Powershell Scripts

* Open powershell as admin and run command:

  ```bash
  Set-ExecutionPolicy RemoteSigned
  ```

## Source Powershell Profile

* Find the location of your powershell profile by running:

```bash
# do not run in vscode terminal, run in powershell directly
$PROFILE
```

* Find the location of the config you want to apply, for example:

```bash
# cd to this directory
Resolve-Path ..\\application_configs\\powershell\\powershell_aliases.ps1
```

* Open the powershell profile file in a text editor:

```bash
notepad $PROFILE
```

* Add the following line to the end of the file:

```bash
. <resolved-path>
```

## Activate Windows with Script if unliscensed

* Open powershell and run command:

  ```bash
  irm https://get.activated.win | iex
  ```

## Set some windows settings

* Uninstall unneeded apps
* Make sure windows defender is on
* Set up clipboard history by pressing win+v
  * Turn on clipboard history by searching for clipboard in the windows button and turning it on
  * Turn on sync across devices if desired
* Show file extensions
  * Open file explorer and click on view and check file name extensions
* Show hidden files
  * Open file explorer and click on view and check hidden items
* Sign into OneDrive
  * Turn on selective sync and download wanted files (do this before moving targets to onedrive)
* Move docs and pictures locations to OneDrive
  * Right click on each one and select a new folder in OneDrive to move them to and click yes to move and confirm

## Git Setup

* Follow instructions in [setup_git.md](./setup_git.md)

## Install Apps

### Install Package Managers

#### Install Chocolatey

##### Install Chocolatey Manually

* Follow instructions in [setup_windows_chocolatey.md](setup_windows_chocolatey.md)

##### Or Use Bootstrap Script to Automatically Install Chocolatey and Install Apps From: [windows_apps.txt](../app_lists/windows_apps.txt)

* Open powershell as admin in the directory where you have the script saved and run command to use bootstrap script to install apps:

  ```bash
  .\install_windows_apps_with_chocolatey.ps1
  ```

#### Install WinGet

* Enter command in powershell to check if winget is installed:

```bash
winget
```

* If instructions for winget do not pop up:
  * update windows
  * open windows app store and update "app installer"

* You should see "winget.exe" in following location:

  ```bash
  %LOCALAPPDATA%\Microsoft\WindowsApps
  ```

* If the command does not work after restarting powershell and the file is where epxected, check PATH variable and add the above location to it expanded

## Google Chrome

* If not using bootstrap script, install google chrome with winget:

  ```bash
  winget install -e --id Google.Chrome
  ```
  
* Open chrome and sign in and sync
* Allow chrome to set itself as default browser
* If want to add another chrome account:
  * Click on profile and add another account to chrome and sign in
  * Pin the second instance of chrome with the small symbol on it to the task bar, and pin chrome to the taskbar
  * Then change the target of the default shortcut to:

    ```bash
    "C:\Program Files\Google\Chrome\Application\chrome.exe" --profile-directory="Default"
    ```

  * The second account shortcut should automatically be something like this:

    ```bash
    "C:\Program Files\Google\Chrome\Application\chrome.exe" --profile-directory="Profile 1"
    ```

## Syncthing Setup

* Follow instructions in [setup_syncthing.md](./setup_syncthing.md)

## Setting Up SSH Server

* Follow instructions in [setup_windows_ssh_server.md](./setup_windows_ssh_server.md)

## Terminal Configuration and Settings

### Use gsudo to elevate commands in a normal powershell session

* Install gsudo with Chocolatey

```bash
# elevated powershell
choco install gsudo
```

* Restart VSCode to bring in new system path

* To elevate a command:

```bash
gsudo <command>
```

* To check if you are elevated

```bash
[bool]([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator") # returns true if elevated
```

## Install and Set Up Programming Tools

### VSCode Setup

* Follow instructions in [setup_vscode.md](./setup_vscode.md)

### Docker Setup

* Follow instructions in [setup_docker.md](./setup_docker.md)

### Python Setup

* Follow instructions in [setup_python.md](./setup_python.md)

### Rust Setup

* Follow instructions in [setup_rust.md](./setup_rust.md)

### Go Setup

* Follow instructions in [setup_go.md](./setup_go.md)

## Install Node and Clasp

* If not using bootstrap script, install nodejs with chocolatey:

  ```bash
  choco install nodejs-lts
  ```
  
* restart powershell to be able to access npm
  
* Install clasp with npm:

  ```bash
  npm install -g @google/clasp
  ```

## WSL

* Open Microsoft App Store and install Ubuntu
* Turn on feature by running this in an admin powershell window:

  ```bash
  Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux
  ```
  
  * Hit Y or manually restart

* Check version of WSL
  
    ```bash
    wsl --list --verbose
    ```

  * Open Ubuntu and set up user and password

* If issues, may need to enable Windows features for "Virtual Machine Platform" and "Windows Hypervisor Platform"

  * To do this with powershell might be possible (untested):

  ```bash
  Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform
  Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux
  Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All
  ```

## VNC

### VNC Connect (Viewer)

* If not using bootstrap script, install vnc-connect with winget:
  * winget install -e --id RealVNC.VNC-Connect
* Open vnc-connect and sign in if need to connect through their service, local may not need sign in (using tiger vnc or tight vnc servers)

### VNC Server (Server)

* Follow instructions in [setup_vnc_server.md](./setup_vnc_server.md)
