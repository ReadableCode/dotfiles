# Setup Windows Workstation

## Update and Rename System

* Update Windows (don't restart)
* Change name of system to something useful and update and restart

## Enable Powershell Scripts

* Open powershell as admin and run command:

```bash
Set-ExecutionPolicy RemoteSigned
```

* Or if don't have admin rights, open powershell and run command:

```bash
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## Source Powershell Profile

* Find the location of your powershell profile by running (do not run in vscode terminal, run in powershell directly):

```bash
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

* If error that it cannot be opened:

```powershell
New-Item -ItemType Directory -Path (Split-Path -Parent $PROFILE) -Force
Add-Content -Path $PROFILE -Value 'path you found earlier'
```

* Add the following line to the end of the file or change the existing line to this:

```bash
. <resolved-path>
```

## Deploy Configs

Config deployment (VS Code settings, AutoHotkey startup scripts, ...) is
manifest-driven — see [deploy_configs.md](./deploy_configs.md):

```powershell
cd ~\GitHub\dotfiles
uv run python src/deploy_configs.py status      # preview / drift report
uv run python src/deploy_configs.py             # deploy
```

Notes:

* Enable Developer Mode first (see "Set some windows settings" below) so real
  symlinks are created without admin. Without it the deploy falls back to
  **hard links** (never a copy). Hard links get orphaned when `git pull`
  rewrites a file — run `deploy_configs.py status` (or re-deploy) after
  pulling; it inode-checks them and re-links anything orphaned.
* The AutoHotkey startup entries (`app_jumping.ahk`, `sheets.ahk` → the
  Startup folder) are manifest entries now; `scripts/create_sym_links_startup.ps1`
  is the legacy way to create them.
* Neovim and the PowerShell profile intentionally use no links (config-path
  indirection) — see their `method: none` entries in `deploy_manifest.yaml`.

## Activate Windows with Script if unliscensed

* Open powershell and run command:

  ```bash
  irm https://get.activated.win | iex
  ```

## Set some windows settings

* Uninstall unneeded apps
* Make sure windows defender is on
* Enable Developer Mode (required for creating symlinks without admin)
  * Settings → System → For developers → Developer Mode ON
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

## Set app order on Taskbar

The Windows translation of the macOS dock order in
[setup_mac_workstation.md](./setup_mac_workstation.md) ("Set app order on
Dock"). Same sequence, left to right; the Start button, Search and Task View
are fixed taskbar elements on Windows and are not pins, so they are not in the
list.

| # | macOS dock | Windows pin | Pin identity |
|---|------------|-------------|--------------|
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
| 9 | Atlas | ChatGPT web app | `Chrome Apps\ChatGPT.lnk` |
| 10 | Messages / Phone / Phone Mirroring | Phone Link (all three in one app) | `Microsoft.YourPhone_8wekyb3d8bbwe!App` |
| - | FaceTime | *(no Windows equivalent)* | — |
| 11 | Contacts | People | `Microsoft.M365Companions_8wekyb3d8bbwe!People` |
| 12 | Mail | Gmail web app | `Chrome Apps\Gmail (1).lnk` |
| 13 | Calendar | Google Calendar web app | `Chrome Apps\Google Calendar (1).lnk` |
| 14 | Claude | Claude | `Anthropic\Claude.lnk` |
| 15 | VSCode | Visual Studio Code | `Microsoft.VisualStudioCode` |
| 16 | Messenger | Messenger web app | `Chrome Apps\Messenger.lnk` |
| 17 | Discord | Discord | `com.squirrel.Discord.Discord` |
| 18 | Slack | Slack | `com.squirrel.slack.slack` |
| 19 | Meet | Google Meet web app | `Chrome Apps\Google Meet.lnk` |
| 20 | Teams | Microsoft Teams | `MSTeams_8wekyb3d8bbwe!MSTeams` |
| 21 | Plex | Plex | `Plex\Plex.lnk` |
| - | YouTube | *(no YouTube web app installed — only YouTube Music)* | — |
| 22 | YTMusic | YouTube Music web app | `Chrome Apps\YouTube Music.lnk` |
| 23 | Parsec | Parsec | `Parsec\Parsec.lnk` |
| 24 | VNCViewer | VNC Viewer | `RealVNC\VNC Viewer.lnk` |
| 25 | GLKVM | GLKVM | `GLKVM.lnk` |
| - | Moonlight | *(not installed — Sunshine is the host half, not the client)* | — |
| 26 | Tailscale | Tailscale | `Tailscale.lnk` |
| 27 | OpenVPN | OpenVPN GUI | `OpenVPN\OpenVPN GUI.lnk` |
| 28 | Wireguard | WireGuard | `WireGuard.lnk` |
| 29 | Steam | Steam | `Steam\Steam.lnk` |
| 30 | Epic Games | Epic Games Launcher | `Epic Games Launcher.lnk` |
| 31 | Activity Monitor | Task Manager | `System Tools\Task Manager.lnk` |
| - | Shortcuts | *(no Windows equivalent — closest is Power Automate)* | — |

`.lnk` identities are Start menu shortcut paths, under
`%ProgramData%\Microsoft\Windows\Start Menu\Programs\` for machine-wide apps and
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\` for per-user apps (Chrome web
apps, Claude). The full paths live in the layout XML below.

### Applying the order

Windows 11 has no supported "pin these apps in this order" command — the
`taskbarpin` shell verb is gone and `Import-StartLayout` is unsupported on
Windows 11. The only mechanism that takes an ordered list is the taskbar layout
XML (`<CustomTaskbarLayoutCollection>`), where document order *is* left-to-right
pin order and **apps that are not installed are silently skipped**, which is why
one file works on every machine without installing anything to fill the gaps.

The layout lives at
[application_configs/windows_taskbar/LayoutModification.xml](../application_configs/windows_taskbar/LayoutModification.xml)
and [scripts/apply_taskbar_layout.ps1](../scripts/apply_taskbar_layout.ps1)
stages it:

```powershell
# normal (non-elevated) powershell - pins are per-user HKCU state
cd ~\GitHub\dotfiles\scripts
.\apply_taskbar_layout.ps1 -DryRun   # show what resolves and what gets skipped
.\apply_taskbar_layout.ps1           # back up, stage, clear old pins
# sign out and back in - the pins only appear at sign-in
.\apply_taskbar_layout.ps1 -RemovePolicy   # then unlock Start, keep the pins
```

**A sign-out/in is mandatory.** Tested on 26200: dropping the XML at
`%LOCALAPPDATA%\Microsoft\Windows\Shell\LayoutModification.xml` and restarting
Explorer makes Explorer *read* the file (it stamps `LayoutXMLLastModified` under
`Taskband`) but pin nothing — with or without the Start Layout policy set, and
with `Taskband` deleted first. Explorer only materializes a taskbar layout at
sign-in. Between running the script and signing back in the taskbar has **no
pins at all**, so run it when you're about to log out or reboot. (Instant apply
exists only on Insider builds ≥ 26200.5722.)

What the script does, and why each step is needed:

1. Backs up the current pins (`User Pinned\TaskBar\*.lnk` plus the `Taskband`
   registry key) to `%LOCALAPPDATA%\dotfiles\taskbar_backups\<timestamp>`;
   `-RestoreFrom <folder>` puts them back.
2. Rescues shortcuts the layout points at that only exist as a pin — Chrome web
   apps pinned straight from Chrome (ChatGPT) have no Start menu `.lnk`, so it
   copies the pin into `Chrome Apps\` first. Skipping this step loses the pin
   when the pins are cleared.
3. Copies the XML to `%LOCALAPPDATA%\Microsoft\Windows\Shell\LayoutModification.xml`.
4. Sets the Start Layout policy (`HKCU\SOFTWARE\Policies\Microsoft\Windows\Explorer`
   → `StartLayoutFile` + `LockedStartLayout=1`) pointing at the repo XML. That
   key is admin-writable only, so this step goes through `gsudo` and prompts for
   UAC. This is what actually applies the layout at sign-in.
5. Clears existing pins and the `Taskband` key. Required: layout pins are
   appended *after* whatever the user already pinned, so leftover pins would
   corrupt the order.
6. Restarts Explorer and tells you to sign out.

After signing back in, `-RemovePolicy` deletes those two policy values: the
pins persist, the Start menu unlocks, and the pins go back to being freely
draggable/unpinnable. Leave the policy in place and the layout is re-enforced on
every policy refresh, which undoes manual pin changes. Re-run the whole script
after editing the XML.

Verify after sign-in — `User Pinned\TaskBar` should hold a `.lnk` per pin:

```powershell
Get-ChildItem "$env:APPDATA\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar" -Filter *.lnk | Select-Object -ExpandProperty Name
```

To read the live taskbar (running apps and pins) without a screenshot, enumerate
`Shell_TrayWnd` buttons through UI Automation — handy for confirming what
actually got pinned:

```powershell
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ClassNameProperty, "Shell_TrayWnd")
$tray = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
$btn = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)
$tray.FindAll([System.Windows.Automation.TreeScope]::Descendants, $btn) | ForEach-Object { $_.Current.Name }
```

Alternatives that were considered and rejected:

* **The per-user layout file on its own** (no policy). Cleanest on paper, but on
  build 26200 Explorer reads it and pins nothing — see the note above.
* **Exporting the `Taskband` registry blob from a hand-arranged machine.** Works
  as a backup/restore (which is what step 1 uses it for), but the blob is opaque
  binary containing per-machine paths, so it is neither reviewable in git nor
  portable between hosts.
* **`Shell.Application` `InvokeVerb("taskbarpin")`.** The Windows 10 method;
  Microsoft removed the verb on Windows 11.

Note: this is ~31 pins. On a narrow display the centered taskbar will run out of
room — Settings → Personalization → Taskbar → Taskbar behaviors → "Combine
taskbar buttons" and left-aligning the taskbar buy back space.

## Git Setup

* Follow instructions in [setup_git.md](./setup_git.md)

## GitHub CLI Setup

* Follow instructions in [github-cli.md](./github-cli.md)

## Install Apps

### Install Package Managers

#### Install Chocolatey

##### Install Chocolatey Manually

* Follow instructions in [setup_windows_chocolatey.md](setup_windows_chocolatey.md)

##### Or Use Bootstrap Script to Automatically Install Chocolatey and Install Apps From: [windows_apps_personal_choco.txt](../app_lists/windows_apps_personal_choco.txt)

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

* If need to mount windows network drives in WSL

  * Open WSL and run the following command to mount the drives:

  ```bash
  sudo mkdir -p /mnt/d
  sudo mount -t drvfs D: /mnt/d
  ```

  * You can add this to your `.bashrc` or `.zshrc` file to automatically mount on startup.

## VNC

### VNC Connect (Viewer)

* If not using bootstrap script, install vnc-connect with winget:
  * winget install -e --id RealVNC.VNC-Connect
* Open vnc-connect and sign in if need to connect through their service, local may not need sign in (using tiger vnc or tight vnc servers)

### VNC Server (Server)

* Follow instructions in [setup_vnc_server.md](./setup_vnc_server.md)

## Sleep Fixes

* Check what devices can wake from sleep with command:

```bash
powercfg /devicequery wake_armed
```

* Response should be something like:

```plaintext
Intel(R) Wi-Fi 6E AX211 160MHz
USB4 Root Router (1.0)
USB4 Root Router (1.0) (001)
```

* Disable devices from waking the computer with commands like:

```bash
powercfg /devicedisablewake "Intel(R) Wi-Fi 6E AX211 160MHz"
powercfg /devicedisablewake "USB4 Root Router (1.0)"
powercfg /devicedisablewake "USB4 Root Router (1.0) (001)"
```
