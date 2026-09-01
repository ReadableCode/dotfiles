# Setup Linux Workstation

## Start here: run bootstrap

Install the OS first (below), then one command takes it to cloned, synced, deployed and
packaged. It is idempotent, so it doubles as a repair tool on a machine that already
works:

```bash
curl -fsSL https://raw.githubusercontent.com/ReadableCode/dotfiles/master/scripts/bootstrap.sh | bash
```

Add `--dry-run` first to see what it would do without changing anything, and
`--credentials <ssh-url>` (repeatable) to clone the credentials repos — their URLs are
not in this public repo, see `cloning_credentials_repos.md` in the personal credentials
repo.

Bootstrap installs git and uv if missing, clones dotfiles to `~/GitHub`, runs `uv sync`,
`clone_repos.py` and `deploy_configs.py`, then installs packages with whichever manager
the machine has:

| Machine | List | Installer |
|---------|------|-----------|
| Debian/Ubuntu | `app_lists/linux_apps.txt` | `scripts/install_linux_apps.sh` |
| WSL | `app_lists/linux_apps_wsl.txt` | `scripts/install_linux_apps_wsl.sh` |
| Fedora | `app_lists/linux_apps_dnf.txt` | `scripts/install_linux_apps_dnf.sh` |
| any, if flatpak present | `app_lists/linux_apps_flatpak.txt` | `scripts/install_linux_apps_flatpak.sh` |

Each reports what is already installed and prompts once for the rest.

**What bootstrap does not do**, and you still need:

- install the OS itself (next section)
- `app_lists/linux_apps_non_apt.md` — the VS Code repo on Fedora, GPU drivers for Parsec,
  and enabling the gsconnect extension after install
- desktop environment settings: display, keyboard, power, autostart
- ssh keys for pushing (bootstrap clones dotfiles over https)

The rest of this page is the reference detail behind those steps.

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

## What `myupdater` Repairs Every Run

Beyond upgrading packages, `myupdater` re-checks three things a release upgrade
or a vendor installer silently breaks, and repairs each in place after a `[y/N]`.
All three are **no-ops once healthy**, so a normal run prints where it stands and
changes nothing. None of them is a manual step — that is the point. Every one of
these was a "run these commands after an upgrade" note in this document, and each
one had been skipped for years on the machine it was written for.

| Check | What it repairs |
|-------|-----------------|
| `check_apt_sources()` | Third-party apt sources the upgrader switched off (below) |
| `run_mapped_checks()` | Whatever check scripts this hostname is mapped to in a credentials repo's updater policy (below) |
| `check_release_upgrade()` | The distro release itself, capped per host by the same `updater` block (below) |

### Third-party apt sources

A release upgrade sets `Enabled: no` on **every** third-party source in
`/etc/apt/sources.list.d/` and rewrites the old `.list` files as deb822
`.sources`. Nothing re-enables them, so the app stops updating while apt keeps
exiting 0. On this machine `code` sat on 1.71.0 (Sept 2022) from the 21.10 →
24.04 upgrade until 2026-08-31 for exactly this reason.

The repair names **no packages**. A well-behaved third-party `.deb` registers its
own apt source and key from its `postinst`, so `myupdater` finds the owning
installed package by matching the dead source's URI host against the `postinst`
scripts under `/var/lib/dpkg/info/`, then re-runs that package's own hook and
lets the vendor write whatever it currently considers correct — current suite,
current key, current file format.

| Disabled source | What `myupdater` offers |
|-----------------|-------------------------|
| An installed package registers it | Re-run that package's own hook, then delete the stale file |
| No installed package registers it | Delete it — nothing can repair it, and it is already inert |
| `cdrom:` install-media source | Delete it — that's the ISO the machine was installed from |
| `*.save` / `*.distUpgrade` backups | Delete them — apt never reads these |

Re-running the hook is what makes this work offline: with the source disabled apt
has no candidate, so `apt-get install --reinstall` **cannot** fix it, while the
already-installed package's hook carries its own key inline. A source pinned to a
dead codename (`Suites: impish`) is flagged as such using `distro-info`'s local
data, and gets fixed by the same hook re-run, since the vendor writes the current
suite.

This runs **before** the package upgrade, so a source repaired this run is one
the upgrade in the same run actually reads.

### Host-mapped checks

Context-specific health checks — a work machine's tunnel client, say — never
live in `my_updater.sh`. A host's entry in its credentials repo's inventory
(`<context>_hosts.json`, the same files `ssh_aliases.py` and
`deploy_configs.py` already read) may carry an `updater` block mapping it to
check scripts by path relative to the GitHub parent dir:

```json
{
  "name": "Workstation-1",
  "updater": {
    "release_ceiling": { "ubuntu": "26.04" },
    "post_update_check": ["some-work-repo/scripts/check_client_health.sh"],
    "release_preflight": ["some-work-repo/scripts/check_client_health.sh"]
  }
}
```

`src/updater_policy.py` (stdlib-only, bare `python3`, same bootstrap contract
as `ssh_aliases.py`) resolves the block for the current machine, matching its
short hostname against inventory names and aliases case-insensitively.

`post_update_check` scripts run after the package upgrade with no arguments;
`release_preflight` scripts run just before the release-upgrade `[y/N]` with
`--target <version>`. The scripts are standalone by contract: they print their
own findings, ask their own `[y/N]` before repairing anything, and no-op
quietly when healthy — so they stay runnable by hand, from cron, or by a
teammate who has only the repo that carries them and no dotfiles at all. A
mapped path whose repo is not cloned prints a loud skip, and a host with no
mapping runs nothing.

This is hostname gating, not repo-presence gating, on purpose: cloning a work
context's credentials repo onto a personal machine must not put that context's
checks (or any of their code) onto it. For the same reason the `updater` block
lives on the **host entry only** — no group-level or context-level defaults,
because "every machine in this group may run release X" vouches for machines
nobody has checked.

### Distro release upgrades

The release check moves the machine forward only as far as this host's ceiling
allows. Why a given host has a ceiling is that host's business — its
credentials repo's docs say what was vetted and what the cap protects (a work
machine typically caps at the newest release its mandatory client software is
known to survive).

The ceiling is `updater.release_ceiling.<distro>` on the host's inventory
entry, the distro key being the `ID=` field of `/etc/os-release`. Nothing in
dotfiles declares a ceiling, deliberately: this repo is cloned onto every
machine, so a ceiling here would vouch for machines nobody has checked, and a
host with no entry is simply never release-upgraded.

On every run the check does one of these and then gets out of the way:

| Situation | What `myupdater` does |
|-----------|----------------------|
| Already at the ceiling | Prints where it stands, changes nothing |
| Newer release out, at or under the ceiling | Prompts `[y/N]`; runs `do-release-upgrade` only on an explicit yes |
| Newer release out, above the ceiling | Prints a `NOTE` naming the release and the inventory file, every run, and offers the ceiling instead |
| Ceiling names a release that is already EOL | Prints a `WARNING` and does nothing — a stale ceiling is not a target |
| Ceiling names a release that never shipped | Prints a `WARNING` and does nothing |
| Machine somehow past the ceiling | Prints a `WARNING` — it is running a release nobody signed off on |
| This host, or this distro on this host, has no entry | Leaves the release alone (unknown ceiling means don't move) |
| No credentials repo cloned (or no `python3`), so no policy readable | Leaves the release alone, and says why |

It also reports, from `distro-info`'s local CSV so it works offline: the
newest stable release, and how many days the running release has before EOL
(loudly inside `eol_warn_days`, louder once past it). Just before the prompt
it runs this host's mapped `release_preflight` scripts, so a context can put
its own facts next to the question — client versions, known incompatibilities
with the target — without any of that code living here.

So you can't drift behind silently (the prompt and the day count keep coming
back) and you can't drift ahead of what was vetted silently (the ceiling is a
hard stop). Nothing upgrades or reboots without a yes at a terminal; with
stdin redirected it declines to prompt.

### Cadence: `Prompt=normal`, not `lts`

These are workstations, so a host's `updater` block sets
`"ubuntu_prompt": "normal"`
— the upgrader offers the next **supported** release whether or not it's an LTS,
which means an upgrade roughly every six months instead of sitting two years
behind on an LTS. Interim releases only carry nine months of support, so that
cadence is the trade being made deliberately.

`normal` does not drag the machine through dead releases. The upgrader skips any
release whose `Supported` flag is `0` in `changelogs.ubuntu.com/meta-release`
(the `if not dist.supported ... continue` in `_buildMetaRelease`,
`/usr/lib/python3/dist-packages/UpdateManager/Core/MetaRelease.py`), so from
24.04 it steps straight over the EOL 24.10/25.04/25.10 to 26.04.

This is also why `lts` is the setting that strands you: `meta-release-lts` gates
LTS→LTS upgrades until the `.1` point release, so a machine set to `lts` sees
nothing for months after a new LTS ships, while `normal` is offered it the day
the release goes stable.

`myupdater` never asks about this key as its own question — that would be a
question about a config file, not about the machine. It works out the target
release from `distro-info`'s local CSV instead of from `do-release-upgrade -c`,
precisely *because* that command is itself gated by `Prompt=` and reports
nothing on a machine set to `lts`, which is how this workstation sat on 24.04
while 26.04 was sitting right there. So there is one question — upgrade or not —
and the `Prompt=` edit is listed inside it as one of the things a yes will do,
applied only after you say yes.

### Raising the ceiling

1. Do whatever vetting this host's cap exists for, on **the release you are
   moving to** — not on the one you are leaving. "It works today" observed on
   the old release proves nothing about the new one: a vendor package that
   hard-depends on a library the new release dropped is removed by the upgrade
   outright. The host's credentials repo's docs say what has to be checked
   and record how it went last time; the host's `release_preflight` script
   prints the relevant facts at the prompt.
2. **Have installers downloaded before you start** for anything `myupdater`
   lists as having no apt source behind it. Those cannot be apt-installed
   back, and if the download point is only reachable through software the
   upgrade might break, waiting until after is too late.
3. Raise `updater.release_ceiling.<distro>` on this host's entry in that
   credentials repo's `<context>_hosts.json`, commit it there. `myupdater`
   names the file and the exact key in the message that told you the machine
   was capped.
4. Run `myupdater` and answer `y`. Read the list of packages it prints that have
   no apt source behind them — those are the ones exposed to removal.

To skip the check entirely for one run:

```bash
MYUPDATER_SKIP_RELEASE_UPGRADE=1 myupdater
```

### After a release upgrade

Re-run `myupdater` first. Disabled third-party sources and whatever this
host's mapped checks repair are both re-checked, so that run fixes them.

What no check can repair is a **package the upgrade removed outright**: one
from no apt source whose dependencies the new release stopped satisfying (apt
removes it in the same batch as ordinary cruft, and `--reinstall` has nothing
to reinstall from afterwards). That is what the pre-upgrade list of unsourced
packages exists to warn about. Recovery is per-package, per-release work — a
package built against the release you left can declare libraries the new one
no longer ships, some stale metadata nothing links and some real — so the
analysis and repair scripts live with the repo that owns the affected
software, reachable through the host's mapped checks, not here. Whatever the
procedure, install with `apt install ./file.deb` rather than `dpkg -i`:
`dpkg` won't pull dependencies and leaves a half-configured package behind.

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

Install Google's `.deb`. Don't hand-write an apt source for it:

```bash
curl -fsSLo /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y /tmp/chrome.deb
```

That package configures its **own** apt source and keyring, and ships
`/etc/cron.daily/google-chrome` (→ `/opt/google/chrome/cron/google-chrome`)
which recreates both every day — see `create_sources_lists()` and
`GPG_FILE=/usr/share/keyrings/google-chrome.gpg` in that script. So
`myupdater` keeps Chrome current with no special handling, and a
hand-written `google-chrome.sources` is not just redundant, it gets
**overwritten** — the live file says so in its own header
(`### THIS FILE IS AUTOMATICALLY CONFIGURED ###`).

* Sign in to sync data

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

### A third-party app stops updating after a distro upgrade

**Symptom:** `myupdater` runs without error but Chrome / VS Code / etc. stays on
an old version. `apt-cache policy <pkg>` shows only the locally installed
version with no remote candidate.

**Cause:** A release upgrade sets `Enabled: no` on every third-party source in
`/etc/apt/sources.list.d/` and converts the old `.list` files to deb822
`.sources`. Nothing re-enables them, so the app silently freezes at whatever
version it had. On this machine that went unnoticed for two years — `code` sat
at 1.71.0 (Sept 2022) from the 21.10 → 24.04 upgrade.

**Fix: run `myupdater`.** `check_apt_sources()` finds every disabled source,
identifies the owning package, and offers the repair per file — see
[Third-party apt sources](#third-party-apt-sources) above for how it decides.
You should not need anything below; it is here for a machine where the automatic
repair reported that it could not help.

Find them by hand with:

```bash
grep -rl 'Enabled: no' /etc/apt/sources.list.d/
```

**Do not hand-write the source file.** For a package that self-registers, re-run
its own hook — this works with the source still disabled and the network down,
which `apt-get install --reinstall` cannot, since a disabled source leaves apt
with no candidate to reinstall from:

```bash
# find the owner by URI host, then re-run its hook
grep -l packages.microsoft.com /var/lib/dpkg/info/*.postinst
sudo /var/lib/dpkg/info/code.postinst configure
sudo rm -f /etc/apt/sources.list.d/vscode.sources   # stale deb822 leftover
sudo apt update
```

Failing that, reinstall the vendor's `.deb`, which re-registers everything:

```bash
curl -fsSLo /tmp/code.deb 'https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64'
sudo apt install -y /tmp/code.deb
```

**Not every disabled source is worth restoring.** Check whether the package is
even installed (`dpkg -l <pkg>`) and whether the suite still exists. Sources
pinned to a dead codename (`Suites: impish`) will 404, and `cdrom:` sources from
the install ISO are pure cruft — delete those instead.

### A vendor service is dead after a reboot or its own upgrade

**Symptom:** A vendor-installed agent (a tunnel client, a sync daemon) works
until the next reboot, or stops working right after its own installer runs.
`systemctl status <service>` shows it inactive, and a reinstall fixes it only
until the next reboot.

**Cause:** Many vendor installers start their service for the current session
but never `systemctl enable` it, ship no restart policy, and reset both on
every upgrade of themselves — so a one-time manual fix does not hold.

**Fix: run `myupdater`.** If this host has a mapped `post_update_check` for
that vendor (see [Host-mapped checks](#host-mapped-checks)), it re-checks and
offers the repair on every run, which is the only thing that survives the next
installer. The check script itself lives in the repo of the context that owns
the vendor relationship; its header documents the by-hand version.
