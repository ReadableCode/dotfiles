# Setup Windows Workstation

## Start here: run bootstrap

Do the three things Windows needs first — update and rename the machine, allow scripts
(`Set-ExecutionPolicy RemoteSigned`), and turn on Developer Mode so configs deploy as
symlinks rather than hard links — then run this from an **elevated** PowerShell:

```powershell
iwr -useb https://raw.githubusercontent.com/ReadableCode/dotfiles/master/scripts/bootstrap.ps1 | iex
```

Add `-DryRun` first to see what it would do without changing anything, and
`-Credentials <ssh-url>` to clone the credentials repos — their URLs are not in this
public repo, see `notes/cloning_credentials_repos.md` in the personal credentials repo.

Bootstrap checks elevation and Developer Mode up front and tells you what will be
skipped rather than failing halfway through. It installs chocolatey, git and uv if
missing, clones dotfiles to `%USERPROFILE%\GitHub`, runs `uv sync`, `clone_repos.py` and
`deploy_configs.py`, then installs packages:

| List | Installer |
| ------ | ----------- |
| `app_lists\windows_apps_personal_choco.txt` (default) | `scripts\install_windows_apps_with_chocolatey.ps1` |
| `app_lists\windows_apps_base_choco.txt` | same, via `-ChocoList` |
| `app_lists\windows_apps_personal_winget.txt` | `scripts\install_windows_apps_with_winget.ps1` |
| `app_lists\windows_apps_personal_winget.shelly.txt` (Shelly) | same, via `-AppList` |

Each reports what is already installed and prompts once for the rest. Pass
`-ChocoList <path>` to bootstrap to pick a different choco profile. Whichever
list runs, the choco and winget apps this machine's contexts add (each member
context's `<context>_app_lists.yaml`, through `src/app_lists.py`) join it: a
client's cloud tools and chat app live there, not in these files.

**What bootstrap does not do**, and you still need from the rest of this document:

- Windows settings: display, keyboard, power, taskbar, startup apps
- signing in to accounts, and anything from the Microsoft Store
- licensed apps and their keys
- ssh keys for pushing (bootstrap clones dotfiles over https)

The rest of this page is the reference detail behind those steps.

## Update and Rename System

- Update Windows (don't restart)
- Change name of system to something useful and update and restart

## Enable Powershell Scripts

- Open powershell as admin and run command:

```bash
Set-ExecutionPolicy RemoteSigned
```

- Or if don't have admin rights, open powershell and run command:

```bash
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## Source Powershell Profile

- Find the location of your powershell profile by running (do not run in vscode terminal, run in powershell directly):

```bash
$PROFILE
```

- Find the location of the config you want to apply, for example:

```bash
# cd to this directory
Resolve-Path ..\\application_configs\\powershell\\powershell_aliases.ps1
```

- Open the powershell profile file in a text editor:

```bash
notepad $PROFILE
```

- If error that it cannot be opened:

```powershell
New-Item -ItemType Directory -Path (Split-Path -Parent $PROFILE) -Force
Add-Content -Path $PROFILE -Value 'path you found earlier'
```

- Add the following line to the end of the file or change the existing line to this:

```bash
. <resolved-path>
```

## Deploy Configs

Config deployment (VS Code settings, AutoHotkey startup scripts, ...) is
manifest-driven — see [repo_deploy_configs.md](./deploy_configs.md):

```powershell
cd ~\GitHub\dotfiles
uv run python src/deploy_configs.py status      # preview / drift report
uv run python src/deploy_configs.py             # deploy
```

Notes:

- Enable Developer Mode first (see "Set some windows settings" below) so real
  symlinks are created without admin. Without it the deploy falls back to
  **hard links** (never a copy). Hard links get orphaned when `git pull`
  rewrites a file — run `deploy_configs.py status` (or re-deploy) after
  pulling; it inode-checks them and re-links anything orphaned.
- The AutoHotkey startup entries (`app_jumping.ahk`, `sheets.ahk`,
  `desktop_numbers.ahk` → the Startup folder) are manifest entries — the deploy
  above is the only way to create them. The Startup folder runs a symlinked
  `.ahk` at login, so no `.lnk` shortcuts are involved.
- Neovim and the PowerShell profile intentionally use no links (config-path
  indirection) — see their `method: none` entries in `deploy_manifest.yaml`.

## AutoHotkey (v2 only)

All three startup scripts are AutoHotkey **v2** (`#Requires AutoHotkey v2.0`),
so a machine still holding v1 gets a version prompt at login instead of working
hotkeys. Nothing here is a command to remember: `powershell_aliases.ps1` runs
`scripts/ensure_autohotkey_v2.ps1 -Check` on **every interactive shell**, and
`gitpullall` runs it with `-AutoFix -Full`. A machine that is already v2-only
prints nothing at all; one that is not gets a report naming `ensureahk`, and is
fixed by the next `gitpullall` (or by running `ensureahk` there and then).

The script installs/upgrades v2 (`choco upgrade autohotkey`, winget as a
fallback), removes v1 — including the orphaned exes the v2 installer leaves
behind in `C:\Program Files\AutoHotkey\`, which carry no uninstall entry of
their own — and repoints the `.ahk` association at the v2 launcher. That last
step matters on old machines: v1 owning `.ahk` there means deleting v1 without
repointing would stop **every** startup script from launching.

Admin is required, so a fixing run from an unelevated shell raises UAC (via
`gsudo` when installed) and waits. Decline it and the script backs off for two
hours rather than prompting again. That wait is why the shell-startup pass is
read-only: a UAC prompt raised from a profile blocks the shell until it is
answered, and an unelevated parent cannot even read the elevated child's exit
code afterwards — so the fixing runs judge success by re-probing the machine,
never by what the child reported. Non-interactive sessions — `ssh host
'<command>'`, scp, any `-Command`/`-File` run — skip the check entirely, so
remote commands never pay the probe or raise a prompt nobody can answer.

Probe costs, which is why the startup pass is the cheap one:

| Probe | Cost | When |
| --- | --- | --- |
| AutoHotkey install dirs, file versions | ~90 ms | every shell |
| `.ahk` association (registry read) | ~5 ms | every shell |
| Uninstall-entry registry scan | ~470 ms | `-Full`, or once something looks wrong |
| `choco list` | ~1840 ms | `-Full`, or once something looks wrong |

Manual use, when you want to look rather than wait for a shell:

```powershell
ensureahk           # report, then offer to fix
ensureahk -Check    # read-only report; exit 1 means there is work to do
```

No logout is needed. A running v1 interpreter holds its own `.exe` open, so the
fix stops the running scripts before deleting v1, then starts every v2 script in
the Startup folder again from your own (unelevated) session — including any that
were linked since the last login and were never launched.

## Activate Windows with Script if unliscensed

- Open powershell and run command:

  ```bash
  irm https://get.activated.win | iex
  ```

## Set some windows settings

- Uninstall unneeded apps
- Make sure windows defender is on
- Enable Developer Mode (required for creating symlinks without admin)
  - Settings → System → For developers → Developer Mode ON
- Set up clipboard history by pressing win+v
  - Turn on clipboard history by searching for clipboard in the windows button and turning it on
  - Turn on sync across devices if desired
- Show file extensions
  - Open file explorer and click on view and check file name extensions
- Show hidden files
  - Open file explorer and click on view and check hidden items
- Sign into OneDrive
  - Turn on selective sync and download wanted files (do this before moving targets to onedrive)
- Move docs and pictures locations to OneDrive
  - Right click on each one and select a new folder in OneDrive to move them to and click yes to move and confirm

### Which manager an app goes on

An app sits on exactly one of `windows_apps_personal_choco.txt` and
`windows_apps_personal_winget.txt` (or one key of a context's
`<context>_app_lists.yaml`): the manager whose package offers the newer version.
A tie goes to winget, which ships with Windows 11, needs no admin for per-user
installs and no bootstrap; Chocolatey is kept where its package is ahead or
winget has none. The comparison is recorded next to the entry (as a trailing
comment in the list, or in the context file's header), dated, so the next look
starts from it. As of 2026-09-24: Claude and Claude Code on choco (2.7032.0 vs
1.44121.2, 2.1.273 vs 2.1.268), Slack, AWS CLI, Hoppscotch and Teams on winget,
DBeaver on choco. An app on both lists is reported by `app_removals.py` as a
conflict and never has a copy removed until one list lets go.  Two contexts
naming the same app on the same manager is fine: a machine in both is offered
it once, so a client's list can grow to a full profile without a clash.

The dotfiles lists hold what any Windows box gets; the home apps (games,
media, streaming, the VNC viewer and server) live in the personal context's
list.

### Windows settings from the inventory

A few Windows settings are per host, in the `updater` block of the
machine's entry in its `<context>_hosts.json` (the block Linux hosts keep their
release ceiling in). `myupdater` sets them, from an elevated shell, before it
upgrades packages; `myupdater --check` reports any that differ. A machine whose
entry leaves a key out keeps whatever it has.

```json
"updater": {
  "windows": {
    "preview_updates": false,
    "restart_sign_on": true,
    "parallel_logon_apps": true,
    "disabled_logon_apps": ["com.squirrel.slack.slack"]
  }
}
```

- `preview_updates` - "Get the latest updates as soon as they're available"
  (`IsContinuousInnovationOptedIn`). On, the box also takes the optional preview
  update each month and restarts for it, so a desktop that must stay up has it
  off.
- `restart_sign_on` - sign in and lock the last user after a Windows Update
  restart (ARSO: `DisableAutomaticRestartSignOn` 0 and
  `AutomaticRestartSignOnConfig` 1 under
  `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System`), so the
  logon apps (T3 Code, the AutoHotkey scripts) start with nobody at the desk.
  Config 1 is "always", BitLocker or not; without BitLocker the sign-in secret
  sits on disk until that logon, so this is for a desktop that stays home,
  never a laptop. Whether it worked shows in the LSA/Operational log (event 320
  configured, 322 failed) after the next update restart.
- `parallel_logon_apps` - start the logon apps without Explorer's startup delay
  and without waiting for each to go idle before the next
  (`StartupDelayInMSec` and `WaitForIdleState`, both 0, under
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize`).
  Explorer otherwise starts the Run-key apps one at a time, allowing each 30
  seconds, and the Startup folder only after them: on RyzenWhite that put T3
  Code and the AutoHotkey scripts 8 minutes after logon (2026-09-24). Windows
  updates are known to drop the `Serialize` key, which is why myupdater sets it
  on every run. The Shell-Core/Operational log (events 9707/9708 for Run keys,
  62408/62409 for the rest) shows each launch's start and finish.
- `disabled_logon_apps` - logon apps this host does not start, listed by the
  name Windows knows them by: a Run-key value name
  (`"com.squirrel.slack.slack"`), a Startup folder file name
  (`"Tailscale.lnk"`), or a Store app's `"PackageName/TaskId"`
  (`"AppleInc.iCloud/iCloudHomeStartupTask"`). Each is turned off the way Task
  Manager's Startup tab does it, so the app stays installed and can be switched
  back on there, and an app that turns its own autostart back on when it
  updates is turned off again by the next myupdater. A name the machine does
  not have is reported and skipped.

## Set app order on Taskbar

The Windows translation of the macOS dock order in
[setup_mac_workstation.md](./setup_mac_workstation.md) ("Set app order on
Dock"). Same sequence, left to right; the Start button, Search and Task View
are fixed taskbar elements on Windows and are not pins, so they are not in the
list.

| # | macOS dock | Windows pin | Pin identity |
| --- | ------------ | ------------- | -------------- |
| 1 | Finder | File Explorer | `Microsoft.Windows.Explorer` |
| - | Apps (Launchpad) | *(none — Start menu "All apps", not pinnable)* | — |
| 2 | App Store | Microsoft Store | `Microsoft.WindowsStore_8wekyb3d8bbwe!App` |
| 3 | Settings | Settings | `windows.immersivecontrolpanel_cw5n1h2txyewy!microsoft.windows.immersivecontrolpanel` |
| 4 | Terminal | Windows Terminal | `Microsoft.WindowsTerminal_8wekyb3d8bbwe!App` |
| 5 | Reminders | Microsoft To Do | `Microsoft.Todos_8wekyb3d8bbwe!App` |
| 6 | Notes | Sticky Notes | `Microsoft.MicrosoftStickyNotes_8wekyb3d8bbwe!App` |
| - | Bitwarden | *(not installed on Windows)* | — |
| 7 | Chrome | Google Chrome | `Chrome` |
| 8 | Edge | Microsoft Edge | `MSEdge` |
| 9 | Messages / Phone / Phone Mirroring | Phone Link (all three in one app) | `Microsoft.YourPhone_8wekyb3d8bbwe!App` |
| - | FaceTime | *(no Windows equivalent)* | — |
| 10 | Contacts | People | `Microsoft.M365Companions_8wekyb3d8bbwe!People` |
| 11 | Mail | Gmail web app | `Chrome Apps\Gmail (1).lnk` |
| 12 | Calendar / Personal Calendar | Google Calendar web app (both in one pin) | `Chrome Apps\Google Calendar (1).lnk` |
| 13 | Outlook (PWA) | Outlook web app (Edge) | `Outlook (PWA).lnk` (Edge web app — per-user Programs root, no subfolder) |
| 14 | Claude | Claude | `Anthropic\Claude.lnk` |
| 15 | T3 Code | T3 Code (Alpha) | `T3 Code (Alpha).lnk` |
| 16 | VSCode | Visual Studio Code | `Microsoft.VisualStudioCode` |
| 17 | Messenger | Messenger web app | Chrome web app `bbdeiblfgdokhlblpgeaokenkfknecgl` (pinned directly, no Start menu shortcut) |
| 18 | Discord | Discord | `com.squirrel.Discord.Discord` |
| 19 | Slack | Slack | `com.squirrel.slack.slack` |
| 20 | Meet | Google Meet web app | `Chrome Apps\Google Meet.lnk` |
| 21 | Teams | Microsoft Teams | `MSTeams_8wekyb3d8bbwe!MSTeams` |
| 22 | Plex | Plex | `Plex\Plex.lnk` |
| - | YouTube | *(no YouTube web app installed on Windows)* | — |
| - | YTMusic | *(no YouTube Music web app installed on Windows)* | — |
| 23 | Screen Sharing | TigerVNC Viewer | `TigerVNC\TigerVNC Viewer 64-bit.lnk` |
| 24 | GLKVM | GLKVM | `GLKVM.lnk` |
| 25 | Moonlight | Moonlight | `Moonlight Game Streaming\Moonlight.lnk` |
| 26 | Parsec | Parsec | `Parsec\Parsec.lnk` |
| 27 | Tailscale | Tailscale | `Tailscale.lnk` |
| 28 | OpenVPN | OpenVPN GUI | `OpenVPN\OpenVPN GUI.lnk` |
| 29 | Wireguard | WireGuard | `WireGuard.lnk` |
| 30 | Steam | Steam | `Steam\Steam.lnk` |
| 31 | Epic Games | Epic Games Launcher | `Epic Games Launcher.lnk` |
| 32 | Activity Monitor | Task Manager | `System Tools\Task Manager.lnk` |
| - | Xcode Beta | *(no Windows equivalent)* | — |
| - | Device Hub | *(no Windows equivalent — Xcode component)* | — |
| 33 | Stream Deck | Elgato Stream Deck | `Elgato\Stream Deck\Stream Deck.lnk` |

`.lnk` identities are Start menu shortcut paths, under
`%ProgramData%\Microsoft\Windows\Start Menu\Programs\` for machine-wide apps and
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\` for per-user apps (Chrome web
apps, Claude). Pins whose identity is an AUMID are packaged apps and have no
.lnk shortcut.

## Git Setup

- Follow instructions in [setup_git.md](./setup_git.md)

## GitHub CLI Setup

- Follow instructions in [setup_github_cli.md](./github-cli.md)

## Install Apps

### Install Package Managers

#### Install Chocolatey

##### Install Chocolatey Manually

- Follow instructions in [setup_windows_chocolatey.md](setup_windows_chocolatey.md)

##### Or Use Bootstrap Script to Automatically Install Chocolatey and Install Apps From: [windows_apps_personal_choco.txt](../app_lists/windows_apps_personal_choco.txt)

- Open powershell as admin in the directory where you have the script saved and run command to use bootstrap script to install apps:

  ```bash
  .\install_windows_apps_with_chocolatey.ps1
  ```

#### Install WinGet

- Enter command in powershell to check if winget is installed:

```bash
winget
```

- If instructions for winget do not pop up:
  - update windows
  - open windows app store and update "app installer"

- You should see "winget.exe" in following location:

  ```bash
  %LOCALAPPDATA%\Microsoft\WindowsApps
  ```

- If the command does not work after restarting powershell and the file is where epxected, check PATH variable and add the above location to it expanded

#### Install MSYS2

- Follow instructions in [setup_msys2.md](./msys2.md) to install MSYS2 with winget and install the POSIX tools (tmux, rsync, etc.) from the package list

## Google Chrome

- If not using bootstrap script, install google chrome with winget:

  ```bash
  winget install -e --id Google.Chrome
  ```
  
- Open chrome and sign in and sync
- Allow chrome to set itself as default browser
- If want to add another chrome account:
  - Click on profile and add another account to chrome and sign in
  - Pin the second instance of chrome with the small symbol on it to the task bar, and pin chrome to the taskbar
  - Then change the target of the default shortcut to:

    ```bash
    "C:\Program Files\Google\Chrome\Application\chrome.exe" --profile-directory="Default"
    ```

  - The second account shortcut should automatically be something like this:

    ```bash
    "C:\Program Files\Google\Chrome\Application\chrome.exe" --profile-directory="Profile 1"
    ```

## Syncthing Setup

- Follow instructions in [setup_syncthing.md](./setup_syncthing.md)

## Setting Up SSH Server

- Follow instructions in [setup_windows_ssh_server.md](./setup_windows_ssh_server.md)

## Terminal Configuration and Settings

### Use gsudo to elevate commands in a normal powershell session

- Install gsudo with Chocolatey

```bash
# elevated powershell
choco install gsudo
```

- Restart VSCode to bring in new system path

- To elevate a command:

```bash
gsudo <command>
```

- To check if you are elevated

```bash
[bool]([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator") # returns true if elevated
```

## Install and Set Up Programming Tools

### VSCode Setup

- Follow instructions in [setup_vscode.md](./setup_vscode.md)

### Docker Setup

- Follow instructions in [setup_docker.md](./setup_docker.md)

### Python Setup

- Follow instructions in [setup_python.md](./setup_python.md)

### Rust Setup

- Follow instructions in [setup_rust.md](./setup_rust.md)

### Go Setup

- Follow instructions in [setup_go.md](./setup_go.md)

## Install Node and Clasp

- If not using bootstrap script, install nodejs with chocolatey:

  ```bash
  choco install nodejs-lts
  ```
  
- restart powershell to be able to access npm
  
- Install clasp with npm:

  ```bash
  npm install -g @google/clasp
  ```

## WSL

- Open Microsoft App Store and install Ubuntu
- Turn on feature by running this in an admin powershell window:

  ```bash
  Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux
  ```
  
  - Hit Y or manually restart

- Check version of WSL
  
    ```bash
    wsl --list --verbose
    ```

  - Open Ubuntu and set up user and password

- If issues, may need to enable Windows features for "Virtual Machine Platform" and "Windows Hypervisor Platform"

  - To do this with powershell might be possible (untested):

  ```bash
  Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform
  Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux
  Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All
  ```

- If need to mount windows network drives in WSL

  - Open WSL and run the following command to mount the drives:

  ```bash
  sudo mkdir -p /mnt/d
  sudo mount -t drvfs D: /mnt/d
  ```

  - You can add this to your `.bashrc` or `.zshrc` file to automatically mount on startup.

## Remote screens

### Moonlight (client)

`moonlight-qt` in the choco list. Pairs with Sunshine on the host and streams a
hardware-encoded desktop, so this is the one to use for a machine with a GPU.
RyzenWhite already runs Sunshine on 47984/47989.

### TigerVNC Viewer (client)

`tigervnc` in the personal app list. The fallback for everything Sunshine cannot serve:
the Pis, headless boxes, and the login screen before any session exists.

### TightVNC (server)

- Follow instructions in [setup_vnc_server.md](./setup_vnc_server.md)

RealVNC is deliberately absent. It moved direct IP connections to its Enterprise
tier, leaving Home and Professional cloud-only, which makes it useless for
reaching a machine on the LAN by address.

## Sleep Fixes

- Check what devices can wake from sleep with command:

```bash
powercfg /devicequery wake_armed
```

- Response should be something like:

```plaintext
Intel(R) Wi-Fi 6E AX211 160MHz
USB4 Root Router (1.0)
USB4 Root Router (1.0) (001)
```

- Disable devices from waking the computer with commands like:

```bash
powercfg /devicedisablewake "Intel(R) Wi-Fi 6E AX211 160MHz"
powercfg /devicedisablewake "USB4 Root Router (1.0)"
powercfg /devicedisablewake "USB4 Root Router (1.0) (001)"
```
