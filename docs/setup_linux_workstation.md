# Setup Linux Workstation

## Install OS

* Install Xubuntu

## Set Default Editor

* Make sure the editor you want is installed:

```bash
sudo apt install neovim
```

* Select the editor:

```bash
select-editor
```

## Power Settings (if laptop)

* screen saver - Settings Manager -> Light Locker Settings
* power settings - Settings Manager -> Power Manager
* if linux xubuntu:
  * open session and startup and disable screensaver locker

## OpenSSH Server - may already be included in some distributions

* Installation

  ```bash
  sudo apt install openssh-server
  ```

## SSH Keys

* To copy SSH keys linux to linux:

  ```bash
  ssh-copy-id user@host
  ```

* Setting up SSH access (if not in distro by default):

  ```bash
  sudo systemctl status ssh
  sudo ufw allow ssh # (unneeded maybe)
  ```
  
* To install SSH keys from other client:
  * Make sure can SSH in
  * exit back to client
  * generate keys on client
  * if linux client generate with:

    ```bash
    ssh-keygen
    ```

  * if windows client:
    * open powershell:

      ```bash
      cd ~/.ssh # (create if not created)
      ssh-keygen
      type ./id_rsa.pub
      ```

    * copy output to ~/.ssh/authorized_keys on server machine on new line
    * save file and exit

## Git Setup

* Follow instructions in [setup_git.md](./setup_git.md)
  
## Link bash_aliases and bashrc to pulled down configs if needed

* If using same storage location as me, run these commands:

  ```bash
  rm ~/.bash_aliases
  rm ~/.bashrc
  ln -s GitHub/dotfiles
  ln -s dotfiles/application_configs/bash/.bash_aliases
  ln -s dotfiles/application_configs/bash/.bashrc
  source ~/.bashrc
  ```

## Update new sytem or run appropriate install_apps sh file from setup repo

  ```bash
  sudo apt -y update
  sudo apt -y upgrade
  sudo apt -y dist-upgrade
  sudo apt -y autoremove
  sudo apt full-upgrade
  ```

## Barrier

* if not using bootstrap script:
  * sudo apt install barrier
* launch with GUI on host
* type in IP address of server
* accept fingerprint
* works on arm and x64 systems

## Python Setup

* Follow instructions in [setup_python.md](./setup_python.md)

## Visual Studio Code Setup

* Follow instructions in [setup_vscode.md](./setup_vscode.md)

## Docker Setup

* Follow instructions in [setup_docker.md](./setup_docker.md)

## Install Chrome (if not using bootstrap script)

* Download from web or find in mounted folder
* cd to foler containing .deb file

  ```bash
  sudo dpkg -i google-chrome-stable_current_amd64.deb # change filename if needed
  ```
  
* sign in to sync data

## Install Clasp

```bash
sudo npm install @google/clasp -g
clasp login # will need gui access to the machine
```

## Mounting Google Drive

* install google-drive-ocamlfuse:

  ```bash
  sudo add-apt-repository ppa:alessandro-strada/ppa
  sudo apt update
  sudo apt install google-drive-ocamlfuse
  ```

* create folder for syncing to:

  ```bash
  mkdir ~/GoogleDrive
  ```
  
* if on local machine:
  * run empty app command to authorize:

    ```bash
    google-drive-ocamlfuse
    google-drive-ocamlfuse ~/GoogleDrive
    ```

  * Add this to startup applications in desktop settings:
  
      ```bash
    sh -c "google-drive-ocamlfuse ~/GoogleDrive"
    ```

* if need to do headless:
  * <https://github-wiki-see.page/m/astrada/google-drive-ocamlfuse/wiki/Headless-Usage-%26-Authorization>
  * Get client and secret from google cloud console or parse out of json file in project folder for OAuth
  
    ```bash
    google-drive-ocamlfuse -headless -label work -id ###YourIDHere###.apps.googleusercontent.com -secret ###YourSecretHere###
    ```

  * get verification code and enter it when prompted
  
    ```bash
    google-drive-ocamlfuse -label work ~/GoogleDrive
    ```
  
  * Tie start to boot with crontab:
  
    ```bash
    @reboot sleep 5 && google-drive-ocamlfuse ~/GoogleDrive
    ```

## Cron and Mail

  ```bash
  sudo nano /etc/ssmtp/ssmtp.conf
  ```

* Add to bottom of file, no tab begin of lines (if personal):

  ```bash
  DEBUG=YES
  AuthUser=emailaddress@gmail.com
  AuthPass=###password (and enable less secure apps) or app password if two factor###
  FromLineOverride=YES
  mailhub=smtp.gmail.com:587
  UseSTARTTLS=YES
  ```

* Add to bottom of file, no tab begin of lines (if work):

  ```bash
  DEBUG=YES
  AuthUser=emailaddress@gmail.com
  AuthPass=###password (and enable less secure apps) or app password if two factor no quotes around it, removve spaces from app password if included by google###
  FromLineOverride=YES
  mailhub=smtp.gmail.com:587
  UseSTARTTLS=YES
  ```

* Test:
  * Test mail with:

    ```bash
    echo "This is a test" | mail -s "Test" emailaddress@gmail.com
    ```

* Cron mailto setup:
  * crontab -e
  * add line to top of uncommented crontab:

      ```bash
      MAILTO=emailaddress@gmail.com
      ```

## VPN Setup

* create vpnauth.conf file in directory of ovpn file, email address on one line, password on next (no tabs):

  ```bash
  emailaddress@gmail.com
  ### VPN Password ###
  ```

* Import the configuration:

  ```bash
  openvpn3 config-import --config your_filename.ovpn
  ```
  
* You can start a new VPN session:
  
    ```bash
    openvpn3 session-start --config ~/your_filename.ovpn
    ```

## Syncthing Setup

* Follow instructions in [setup_syncthing.md](./setup_syncthing.md)

## Enable or Disable Swap on Ubuntu

* Check if swap is enabled:

  ```bash
  sudo swapon --show
  ```

* Change swap allocation:

```bash
sudo swapoff /swapfile
sudo fallocate -l 32G /swapfile # change size as needed
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
swapon --show
```

## Using Fedora

* update everything

```bash
sudo dnf upgrade --refresh
```

* search for a package

```bash
dnf search package-name
```

* install something

```bash
sudo dnf install package-name
```

* remove something

```bash
sudo dnf remove package-name
```
