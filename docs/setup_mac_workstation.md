# Setup macOS Workstation

## Set hostname

System Settings → General → About

## Change scaling

System Settings → Displays → More Space

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
- GLINet
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

Finder → Settings → Advanced → “When performing a search" → Change to "search the current folder"

Finder → View → Show Path Bar

Finder → View → Show Status Bar

## Git Setup

- Follow instructions in [setup_git.md](./setup_git.md)

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

## Install Binary Installler Apps

- Install Logi Options
- Install Logitech G Hub

## Enable SSH Server

- System Settings -> General -> Sharing -> Remote Management
- System Settings -> General -> Sharing -> Remote Login

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
