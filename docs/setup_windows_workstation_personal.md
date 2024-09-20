# Setup Windows Workstation

## Update and Rename System

* Update Windows (don't restart)
* Open Windows App Store and update "app installer"
* Change name of system to something useful and update and restart

## Set some windows settings

* Uninstall unneeded apps and make sure windows defender is on
* Set up clipboard history by pressing win+v
  * Turn on clipboard history by searching for clipboard in the windows button and turning it on
* Sign into OneDrive to sync or configure git to pull dotfiles
  * Turn on selective sync and download wanted files (do this before moving targets to onedrive)
* Move docs and pictures locations to OneDrive
  * Right click on each one and select a new folder in OneDrive to move them to and click yes to move and confirm
* Enasble scripts in powershell
  * Open powershell as admin and run command:

    ```bash
    Set-ExecutionPolicy RemoteSigned
    ```

## Git Setup

* Follow instructions in [setup_git.md](./setup_git.md)

## Install Apps

### Automatically Install Chocolatey and Install Apps From: [windows_apps.txt](../app_lists/windows_apps.txt)

* Open powershell as admin in the directory where you have the script saved and run command to use bootstrap script to install apps:

  ```bash
  .\install_windows_apps.ps1
  ```

### Just Install Chocolatey

* Follow instructions in [setup_windows_chocolatey.md](setup_windows_chocolatey.md)

### Just Install WinGet

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

## Setting Up SSH Server

* open elevated powershell window
* run commands:
  
  ```bash
  winget install "openssh beta"
  ```

  * if not using bootstrap script:
  
    ```bash
    winget install -e --id Notepad++.Notepad++
    ```

* run command:

  ```bash
  New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
  ```
  
* run command:

  ```bash
  Set-Service sshd -StartupType Automatic
  ```
  
* run command:
  
  ```bash
  net start sshd
  ```
  
  * (might say already started, thats OK)
* get rsa.pub from ansible server using this command executed client machine:

  ```bash
  cat ~/.ssh/id_rsa.pub
  ```

* make directory if doesnt exist: "$env:USERPROFILE\\.ssh\" by running this:

  ```bash
  if (!(Test-Path -Path "$env:USERPROFILE\.ssh\")) { New-Item -ItemType Directory -Path "$env:USERPROFILE\.ssh\" }
  ```
  
* Pick one of the following to get ssh pub key onto new windows client:
  * Using admin powershell on remote machine or some ssh connection already set up (password pased or from machine with key already set up) NOTE: both of these fail to add a newline at the end of the line
  
    ```bash
    Add-Content -Path "$env:USERPROFILE\.ssh\authorized_keys" -Value "CONTENTS_OF_ID_RSA_PUB"
    Add-Content -Path "C:\ProgramData\ssh\administrators_authorized_keys" -Value "CONTENTS_OF_ID_RSA_PUB"
    ```

  * Using notepad++ on the client:
  
    ```bash
    Start-Process "notepad++.exe" "$env:USERPROFILE\.ssh\authorized_keys"
    Start-Process "notepad++.exe" "C:\ProgramData\ssh\administrators_authorized_keys" -Verb "runas"
    ```

  * Using admin powershell on remote machine or some ssh connection already set up (password pased or from machine with key already set up)(might replace existing file):

    ```bash
    echo "CONTENTS_OF_ID_RSA_PUB" | Out-File -FilePath "$env:USERPROFILE\.ssh\authorized_keys" -Encoding ASCII -Force
    echo "CONTENTS_OF_ID_RSA_PUB" | Out-File -FilePath "C:\ProgramData\ssh\administrators_authorized_keys" -Encoding ASCII -Force
    ```

* Change persmissions for the administrators_authorized_keys file:

  ```bash
  icacls C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r
  icacls C:\ProgramData\ssh\administrators_authorized_keys /grant SYSTEM:`(F`)
  icacls C:\ProgramData\ssh\administrators_authorized_keys /grant BUILTIN\Administrators:`(F`)
  ```
  
* Change settings in sshd_config file:

  ```bash
  Start-Process "notepad++.exe" "C:\ProgramData\ssh\sshd_config" -Verb "runas"
  ```
  
  * Uncomment and change the following lines, adding if they dont exist:

    ```bash
    StrictModes no
    PubkeyAuthentication yes
    ```

* Run these commands in admin powershell to set the default shell to powershell:

  ```bash
  New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -PropertyType String -Force
  New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShellCommandOption -Value "/c" -PropertyType String -Force
  ```
  
* Run these commands in admin powershell to restart ssh-server and apply changes:

  ```bash
  net stop sshd
  net start sshd
  ```

### Python Setup

* Follow instructions in [setup_python.md](./setup_python.md)

### VSCode Setup

* Follow instructions in [setup_vscode.md](./setup_vscode.md)

### Docker Setup

* Follow instructions in [setup_docker.md](./setup_docker.md)

## Using as an Ansible Client

* run the playbook to install ansible apps for windows from the ansible server:

  ```bash
  ansible-playbook playbooks/install_windows_apps.yml --ask-become-pass -i ./inventory/hosts
  ```

## Syncthing Setup

* Follow instructions in [setup_syncthing.md](./setup_syncthing.md)

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
  
## VNC-Connect

* If not using bootstrap script, install vnc-connect with winget:
  * winget install -e --id RealVNC.VNC-Connect
* Open vnc-connect and sign in

## VNC Server

* Install using winget:
  * winget install -e --id RealVNC.VNC-Server
* Open vnc-server and sign in

## OneDrive

* Sign into windows/onedrive and set which folders are going to sync
  