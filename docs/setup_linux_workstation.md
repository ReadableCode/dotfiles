# Setup Linux Workstation

## Install OS

### Ubuntu/Xubuntu

* Install Xubuntu from <https://xubuntu.org/download/>

### Fedora

* Download and install Fedora Workstation from <https://fedoraproject.org/>

### Raspberry Pi

* Download Raspberry Pi Imager from <https://www.raspberrypi.com/software/>
* Flash Raspberry Pi OS (64-bit recommended) to SD card
* Use Imager's advanced options (gear icon) to pre-configure:
  * hostname
  * SSH enabled
  * WiFi credentials
  * username and password
* Boot and connect via SSH or attach monitor/keyboard

## Set Default Editor

### Ubuntu/Debian/Raspberry Pi

* Make sure the editor you want is installed:

  ```bash
  sudo apt install neovim
  ```

* Select the editor:

  ```bash
  select-editor
  ```

### Fedora

```bash
sudo dnf install -y neovim
echo 'export EDITOR=nvim' >> ~/.bashrc
```

## Power Settings (if laptop)

### Ubuntu/Xubuntu

* screen saver - Settings Manager -> Light Locker Settings
* power settings - Settings Manager -> Power Manager
* open session and startup and disable screensaver locker

### Fedora

* GNOME Settings -> Power

### Raspberry Pi

* Not applicable for headless setups
* For desktop: Raspberry Pi Configuration -> Display -> Screen Blanking

## OpenSSH Server

### Ubuntu/Debian

```bash
sudo apt install openssh-server
sudo systemctl enable ssh
sudo systemctl start ssh
```

### Fedora

```bash
sudo dnf install -y openssh-server
sudo systemctl enable sshd
sudo systemctl start sshd
sudo firewall-cmd --add-service=ssh --permanent
sudo firewall-cmd --reload
```

### Raspberry Pi

* SSH can also be enabled via `raspi-config`:

  ```bash
  sudo raspi-config  # Interface Options -> SSH -> Enable
  ```

## SSH Keys

* To copy SSH keys linux to linux:

  ```bash
  ssh-copy-id user@host
  ```

* Setting up SSH access:

  ```bash
  sudo systemctl status ssh
  sudo ufw allow ssh  # Ubuntu/Debian (may be unneeded even on these)
  ```

* To generate keys on client and deploy to server:
  * Make sure you can SSH in
  * Exit back to client and generate keys

  ### Linux/Raspberry Pi

  ```bash
  ssh-keygen -t rsa -b 4096
  ```

  ### Windows

  * Open PowerShell:

    ```bash
    cd ~/.ssh  # create if not exists
    ssh-keygen -t rsa -b 4096
    type ./id_rsa.pub
    ```

  * Copy output to `~/.ssh/authorized_keys` on the server, one key per line

## Git Setup

* Follow instructions in [setup_git.md](./setup_git.md)

## Clone Dotfiles

```bash
cd ~
mkdir GitHub
cd GitHub
git clone git@github.com:ReadableCode/dotfiles.git
```

## Link bash_aliases and bashrc

Optionally link the repo itself into the home directory for convenience:

```bash
ln -s ~/GitHub/dotfiles/ ~/
```

The `.bashrc` / `.bash_aliases` links are manifest-driven (entries `bashrc`
and `bash_aliases` in `deploy_manifest.yaml` — see
[deploy_configs.md](./deploy_configs.md)). Existing files are backed up to
`data/config_backups/` and replaced by links to the repo versions:

```bash
cd ~/GitHub/dotfiles
uv run python src/deploy_configs.py status      # preview / drift report
uv run python src/deploy_configs.py             # deploy
source ~/.bashrc
```

## Update System

### Ubuntu/Debian/Raspberry Pi

```bash
sudo apt -y update
sudo apt -y upgrade
sudo apt -y dist-upgrade
sudo apt -y autoremove
sudo apt full-upgrade
```

### Fedora

```bash
sudo dnf upgrade --refresh
sudo dnf autoremove
```

## Install Apps from Dotfiles Repo

### Ubuntu/Debian

Install all apps listed in `app_lists/linux_apps.txt`:

```bash
xargs sudo apt install -y < ~/GitHub/dotfiles/app_lists/linux_apps.txt
```

### Raspberry Pi

Same as above, but some packages may not be available for ARM (e.g. `steam`, `golang-go`). Skip those as needed:

```bash
xargs sudo apt install -y < ~/GitHub/dotfiles/app_lists/linux_apps.txt
```

### Fedora

Many packages have different names on Fedora. Install equivalents manually:

```bash
sudo dnf install -y curl fzf gh git htop iperf3 mailx ncdu neovim net-tools npm \
  pandoc ripgrep syncthing tmux tree unzip rsync golang cargo gcc-c++ make
```

* `gcc-c++` is not optional on a machine that runs npm tools with native
  addons — Fedora ships `gcc` but not the C++ compiler, and a package like
  node-pty (pulled in by the T3 Code server) has no linux-x64 prebuild, so
  npm compiles it from source and fails with a bare `Error 127`. See
  [setup_t3_code.md](./setup_t3_code.md).
* See [linux_apps_non_apt.md](../app_lists/linux_apps_non_apt.md) for tools not in the package manager

## Python Setup

* Follow instructions in [setup_python.md](./setup_python.md)

## Visual Studio Code Setup

* Follow instructions in [setup_vscode.md](./setup_vscode.md)

> **Raspberry Pi / Fedora:** See [linux_apps_non_apt.md](../app_lists/linux_apps_non_apt.md) for distro-specific VSCode install instructions

## Docker Setup

* Follow instructions in [setup_docker.md](./setup_docker.md)

## Install Chrome

### Ubuntu/Debian (x64)

Install via the apt repo so `myupdater` keeps it current automatically. The
installer `.deb` approach works once but leaves Chrome orphaned from the package
manager.

```bash
# 1. Add Google's signing key
curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
  | sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/google-chrome.gpg

# 2. Add the apt source (DEB822 format — works on Ubuntu 24.04 Noble+)
#    Pinning Architectures: amd64 is required — without it apt also tries i386,
#    which Google doesn't ship, causing the entire source to be silently skipped.
sudo tee /etc/apt/sources.list.d/google-chrome.sources > /dev/null << 'EOF'
Enabled: yes
Types: deb
URIs: https://dl.google.com/linux/chrome/deb/
Suites: stable
Components: main
Architectures: amd64
Signed-By: /etc/apt/trusted.gpg.d/google-chrome.gpg
EOF

# 3. Install
sudo apt update
sudo apt install -y google-chrome-stable
```

* Sign in to sync data

> **After a distro upgrade (e.g. to Noble):** the upgrade process sets
> `Enabled: no` in `google-chrome.sources` and invalidates the signing key.
> Re-run steps 1–3 above to restore updates. See
> [Troubleshooting: Chrome won't update](#chrome-wont-update-after-a-distro-upgrade)
> below.

### Fedora

```bash
sudo dnf install -y fedora-workstation-repositories
sudo dnf config-manager --set-enabled google-chrome
sudo dnf install -y google-chrome-stable
```

### Raspberry Pi

* Chrome is not available for ARM — use Chromium instead:

  ```bash
  sudo apt install chromium-browser
  ```

## Install Clasp

```bash
sudo npm install @google/clasp -g
clasp login  # will need GUI access to the machine
```

## Mounting Google Drive

### Ubuntu/Debian/Raspberry Pi

* Install google-drive-ocamlfuse:

  ```bash
  sudo add-apt-repository ppa:alessandro-strada/ppa
  sudo apt update
  sudo apt install google-drive-ocamlfuse
  ```

* Create folder for syncing to:

  ```bash
  mkdir ~/GoogleDrive
  ```

* If on local machine, run empty app command to authorize:

  ```bash
  google-drive-ocamlfuse
  google-drive-ocamlfuse ~/GoogleDrive
  ```

  * Add this to startup applications in desktop settings:

    ```bash
    sh -c "google-drive-ocamlfuse ~/GoogleDrive"
    ```

* If headless:
  * <https://github-wiki-see.page/m/astrada/google-drive-ocamlfuse/wiki/Headless-Usage-%26-Authorization>
  * Get client ID and secret from Google Cloud Console or parse from the project OAuth JSON file

    ```bash
    google-drive-ocamlfuse -headless -label work -id ###YourIDHere###.apps.googleusercontent.com -secret ###YourSecretHere###
    ```

  * Enter the verification code when prompted:

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

* Add to bottom of file, no tab at beginning of lines (if personal):

  ```plaintext
  DEBUG=YES
  AuthUser=emailaddress@gmail.com
  AuthPass=###password (and enable less secure apps) or app password if two factor###
  FromLineOverride=YES
  mailhub=smtp.gmail.com:587
  UseSTARTTLS=YES
  ```

* Add to bottom of file, no tab at beginning of lines (if work):

  ```plaintext
  DEBUG=YES
  AuthUser=emailaddress@gmail.com
  AuthPass=###password (and enable less secure apps) or app password if two factor, no quotes, remove spaces from app password if included by google###
  FromLineOverride=YES
  mailhub=smtp.gmail.com:587
  UseSTARTTLS=YES
  ```

* Test mail with:

  ```bash
  echo "This is a test" | mail -s "Test" emailaddress@gmail.com
  ```

* Cron mailto setup:
  * `crontab -e`
  * Add line to top of uncommented crontab:

    ```
    MAILTO=emailaddress@gmail.com
    ```

## VPN Setup

* Create vpnauth.conf file in directory of ovpn file, email address on one line, password on next (no tabs):

  ```
  emailaddress@gmail.com
  ### VPN Password ###
  ```

* Import the configuration:

  ```bash
  openvpn3 config-import --config your_filename.ovpn
  ```

* Start a new VPN session:

  ```bash
  openvpn3 session-start --config ~/your_filename.ovpn
  ```

## Work VPN / Proxy Clients

Client-specific tunnel/proxy agent setup (installer location, systemd fixes,
verification) is documented in that context's private credentials repo, next to
the rest of its machine config.

## Syncthing Setup

* Follow instructions in [setup_syncthing.md](./setup_syncthing.md)

## Enable or Disable Swap

### Ubuntu/Debian

* Check if swap is enabled:

  ```bash
  sudo swapon --show
  ```

* Change swap allocation:

  ```bash
  sudo swapoff /swapfile
  sudo fallocate -l 32G /swapfile  # change size as needed
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  swapon --show
  ```

### Raspberry Pi

* Check current swap:

  ```bash
  sudo swapon --show
  free -h
  ```

* The default swap file is managed by `dphys-swapfile`:

  ```bash
  sudo nano /etc/dphys-swapfile
  # Set CONF_SWAPSIZE=2048 (for 2GB)
  sudo dphys-swapfile setup
  sudo dphys-swapfile swapon
  ```

### Samba host setup

* Install Samba:

  ```bash
  sudo apt install samba
  ```

* Add user to Samba:

  ```bash
  sudo smbpasswd -a pi  # replace 'pi' with your username
  ```

* Configure Samba shares:

  ```bash
  sudo nvim /etc/samba/smb.conf
  ```

* Add share definition at bottom of file:

```plaintext
[Media]
  path = /home/pi/Media
  browseable = yes
  read only = yes
  guest ok = no
  valid users = pi
```

* Restart Samba to apply changes:

  ```bash
  sudo systemctl restart smbd
  ```

## Raspberry Pi Specific Setup

### raspi-config

Run the configuration tool to set hostname, locale, timezone, and enable interfaces:

```bash
sudo raspi-config
```

* Set hostname
* Enable interfaces (SSH, VNC, I2C, SPI as needed)
* Set locale and timezone
* Expand filesystem

### Enable VNC

```bash
sudo raspi-config  # Interface Options -> VNC -> Enable
```

Or manually:

```bash
sudo apt install realvnc-vnc-server
sudo systemctl enable vncserver-x11-serviced
```

### GPIO and Hardware Tools

```bash
sudo apt install -y python3-gpiozero python3-rpi.gpio
```

### Temperature Monitoring

```bash
vcgencmd measure_temp
```

## Fedora Package Management Reference

* Update everything:

  ```bash
  sudo dnf upgrade --refresh
  ```

* Search for a package:

  ```bash
  dnf search package-name
  ```

* Install a package:

  ```bash
  sudo dnf install package-name
  ```

* Remove a package:

  ```bash
  sudo dnf remove package-name
  ```

---

## Troubleshooting

### Chrome won't update after a distro upgrade

**Symptom:** Chrome shows "Can't update Chrome" / `myupdater` runs without
error but Chrome stays on an old version. `apt-cache policy google-chrome-stable`
shows only the locally installed version with no remote candidate.

**Cause:** Upgrading Ubuntu (e.g. focal → noble) automatically sets
`Enabled: no` in `/etc/apt/sources.list.d/google-chrome.sources` and the old
signing key may no longer match. Additionally, if `Architectures: amd64` is
missing, apt silently skips the source because it can't find an i386 build.

**Fix:**

```bash
# Refresh the signing key
curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
  | sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/google-chrome.gpg

# Rewrite the source file with the correct flags
sudo tee /etc/apt/sources.list.d/google-chrome.sources > /dev/null << 'EOF'
Enabled: yes
Types: deb
URIs: https://dl.google.com/linux/chrome/deb/
Suites: stable
Components: main
Architectures: amd64
Signed-By: /etc/apt/trusted.gpg.d/google-chrome.gpg
EOF

sudo apt update
sudo apt install -y google-chrome-stable
```

### Zscaler disconnected after reboot (tunnel not running)

**Symptom:** After a reboot Zscaler shows as disconnected or the tray icon
indicates no tunnel. `systemctl status zstunnel` shows the service as inactive.
Reinstalling Zscaler fixes it temporarily but the problem returns on the next
reboot.

**Cause:** The Zscaler installer starts `zstunnel` for the current session but
never enables it in systemd. On the next boot `zsaservice` starts (it is
enabled) but `zstunnel` does not, leaving the VPN dead. The two services also
have no dependency wiring between them and `zstunnel` has no restart policy, so
a crash also leaves it dead until manual intervention.

**Fix (run once after install, survives future reboots):**

```bash
# Enable the tunnel service at boot
sudo systemctl enable zstunnel

# Drop in a restart policy so crashes self-heal
sudo mkdir -p /etc/systemd/system/zstunnel.service.d
sudo tee /etc/systemd/system/zstunnel.service.d/restart.conf > /dev/null << 'EOF'
[Service]
Restart=always
RestartSec=5s
EOF

sudo systemctl daemon-reload
sudo systemctl restart zstunnel
```

Verify:

```bash
systemctl is-enabled zsaservice zstunnel   # both: enabled
systemctl status zstunnel                  # active (running)
```

**If the tunnel is down right now** (without reinstalling):

```bash
sudo systemctl start zstunnel
```
