# Setup macOS Workstation

## Set hostname

System Settings → General → About

## Always show all files

```bash
defaults write com.apple.finder AppleShowAllFiles -bool true && killall Finder
```

## Change scaling

System Settings → Displays → More Space

## Set key repeat delay and rate

System Settings → Keyboard
Set "Key Repeat" to Fast and "Delay Until Repeat" to one click below short

## Enable apps collapsing into dock icons

1. Open System Settings → Desktop & Dock.
2. Scroll to Windows & Apps.
3. Enable “Prefer tabs when opening documents” → Always (optional).
4. Then turn ON:
  ✅ “Minimize windows into application’s icon”.
4a. Mission control:
  Enable Group applications by application
5. Close Settings.

## Auto hide the dock

1. Open System Settings → Desktop & Dock.
2. Enable "Automaticcally Hide and Show the Dock"

## Disable Displays have separate spaces and other desktop settings

1. Open System Settings → Desktop & Dock.
2. Scroll to Mission Control.
3. Disable "Displays have separate spaces"
4. Disable "Show suggested and recent applications in Dock"
5. Disable "Automatically rearrange Spaces based on most recent use"

## Set app order on Dock

- Finder
- Apps
- App Store
- Settings
- Terminal
- Redminders
- Notes
- Bitwarden
- Chrome
- Edge
- Atlas
- Messages
- Phone
- FaceTime
- Contacts
- Mail
- Calendar
- Claude
- VSCode
- Messenger
- Discord
- Slack/Meet/Teams
- Plex
- YouTube
- YTMusic
- Phone Mirroring
- Parsec
- VNCViewer
- GLKVM
- Moonlight
- Tailscale
- OpenVPN
- Wireguard
- Steam
- Epic Games
- Activity Monitor
- Shortcuts

## Disable clicking desktop moves windows

1. Open System Settings → Desktop & Dock.
2. Scroll to Desktop and Stage Manager.
3. Change the "Show Desktop" setting to Only in Stage Manager

## Trim control center and menu bar

System Settings → Menu Bar

1. Disable items in Menu Bar that you do not need.

## Show battery percentage and weather

System Settings → Menu Bar → Battery

1. Turn ON “Show Percentage”.

System Settings → Menu Bar → Weather

1. Turn ON “Weather”.
2. Click on the Weather item in Menu Bar
3. Click open weather to select your preferred city and settings

## HID Configuration

1. **System Settings → Trackpad → Point & Click**  
2. Turn on tap to click

### Enable tap dragging

Open System Settings → Accessibility → Pointer Control.  ￼
 2. Click on Trackpad Options…
 3. Check “Use trackpad for dragging”. Then choose your preferred dragging style:
 • “without Drag Lock” — you double-tap and hold the second tap, and then drag, releasing ends drag.  ￼
 • “with Drag Lock” — you double-tap and drag, and you can lift your finger and continue dragging; end by tapping again

## Finder Configuration

Finder → Settings → Disable "Open folders in tabs instead of new windows"

Finder → Settings → New Finder windows show: → Select home folder

Finder → Settings → Tags → Uncheck all tags

Finder → Settings → Advanced → Enable “Show all filename extensions”

Finder → Settings → Advanced → Enable “Keep Folders on Top In Windows when sorting by name”

Finder → Settings → Advanced → “When performing a search" → Change to "search the current folder"

Finder → View → Show Path Bar

Finder → View → Show Status Bar

- To show hidden files and folders, open a finder window and press `Command + Shift + .`

## Git Setup

- Follow instructions in [setup_git.md](./setup_git.md)

## GitHub CLI Setup

- Follow instructions in [github-cli.md](./github-cli.md)

## Clone dotfiles

```bash
cd ~
mkdir GitHub
cd GitHub
git clone git@github.com:ReadableCode/dotfiles.git
```

## Symlink zsh config

```bash
mv ~/.zshrc ~/.zshrc.bak
ln -s ~/GitHub/dotfiles/application_configs/bash/.zshrc ~/.zshrc
```

## Brew Setup

- Install brew, run one line at a time in terminal:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
# follow prompts to add pathing to shell profile
brew update
brew upgrade
brew upgrade --cask
brew cleanup
```

- Use Brewfile in ../app_lists/Brewfile to install apps:

```bash
cd ../app_lists
brew bundle
```

### Cleaning up brew to get disk space back

```bash
brew cleanup --prune=all
rm -rf ~/Library/Caches/Homebrew
```

### Moving Homebrew Cache

```bash
# create new cache directory
mkdir -p /Volumes/EnvyExtSSD/HomebrewCache
# set permissions for current user
sudo chown -R $(whoami) /Volumes/EnvyExtSSD/HomebrewCache
# persist in machine-local zsh config (not synced to other machines)
echo 'export HOMEBREW_CACHE=/Volumes/EnvyExtSSD/HomebrewCache' >> ~/.zshrc.local
```

## Claude Setup

### Moving Claude data directory to external drive

quit Claude fully first, then:

```bash
mv ~/Library/Application\ Support/Claude /Volumes/EnvyExtSSD/Claude
ln -s /Volumes/EnvyExtSSD/Claude ~/Library/Application\ Support/Claude
```

## Install Binary Installler Apps

- Install Logi Options
- Install Logitech G Hub

## Clipboard History (Maccy)

macOS has no built-in clipboard history. Install Maccy for a free, minimal visual clipboard manager:

```bash
brew install --cask maccy
```

- Open Maccy → Preferences → set hotkey (default: `Cmd+Shift+C`)
- Shows a searchable visual list of recent clipboard items

## Hammerspoon (AutoHotkey equivalent)

Hammerspoon is a free Mac automation tool scriptable in Lua — use it for hotkeys, window management, and macros.

```bash
brew install --cask hammerspoon
```

Symlink the dotfiles config:

```bash
mkdir -p ~/.hammerspoon
ln -sf ~/GitHub/dotfiles/application_configs/hammerspoon/init.lua ~/.hammerspoon/init.lua
```

- Launch Hammerspoon from `/Applications` — it lives in the menu bar
- Click the menu bar icon → **Reload Config**
- Grant Accessibility permissions when prompted: System Settings → Privacy & Security → Accessibility

Current hotkeys defined in `application_configs/hammerspoon/init.lua`:

| Hotkey | Action |
|--------|--------|
| `Ctrl+Shift+C` | Copy selection, open as Google Sheets URL |
| `Ctrl+Shift+F` | Copy selection, open as Google Drive folder URL |
| `Cmd+Shift+V` | Paste as plain text (strips formatting) |
| `Ctrl+Shift+T` | Open front Finder window in Terminal |
| `Ctrl+Shift+S` | Save current space's window layout (asks for a space number) |
| `Ctrl+Shift+L` | Load a saved window layout (asks for a space number) |
| `Ctrl+Shift+H` | Show the hotkey cheatsheet |

### Window layouts (per space)

Saved layouts live in `application_configs/hammerspoon/window_layouts.json`,
keyed by a space number you type. Because `init.lua` is symlinked from the repo,
Hammerspoon follows the link and writes that JSON back into the repo, so it can
be committed.

- **Save:** switch to a space, arrange its windows, press `Ctrl+Shift+S`, and
  type that space's number. Repeat on each space, then commit
  `window_layouts.json`.
- **Load:** switch to a space, press `Ctrl+Shift+L`, type the same number.
  Repeat per space (e.g. after a KVM switch) to snap windows back into place.

Layouts anchor on screen *orientation* (portrait vs landscape) rather than
display IDs, so they survive the KVM re-enumerating the monitors.

## Enable SSH Server

- System Settings -> General -> Sharing -> Remote Management
- System Settings -> General -> Sharing -> Remote Login

### Generate ssh keys if needed

- open terminal and run commands:

  ```bash
  cd ~
  ls -a
  ```
  
- if .ssh directory doesn't exist:

  ```bash
  mkdir .ssh
  ```
  
- enter .ssh directory

  ```bash
  cd .ssh
  ```
  
- if .pub key doesn't exist:

  ```bash
  ssh-keygen -t rsa -b 4096
  # press enter to accept defaults
  ```

- To create an additional key or with a different name:

  ```bash
  ssh-keygen -t rsa -b 4096 -f ~/.ssh/key_name
  ```
  
- Run the following command and copy just the key if needed to deploy:

  ```bash
  cat ~/.ssh/id_rsa.pub
  ```

## Disable auto punctuation

System Settings → Keyboard → Text Input → U.S. -> Edit -> Turn off dobule space to period and other auto punctuation features

## Install Wireguard

- install from the App Store

## Install GLKVM app

- install from the App Store

## Python Setup

- Follow instructions in [setup_python.md](./setup_python.md)

## VSCode Setup

- Follow instructions in [setup_vscode.md](./setup_vscode.md)

## Docker Setup

- Follow instructions in [setup_docker.md](./setup_docker.md)
