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
5. Close Settings.

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

Finder → Settings → Advanced → “Show all filename extensions”

Finder → Settings → Advanced → “When performing a search" → Change to search the current folder

Finder → Settings → Sidebar > Configure sidebar including change to new windows opening in user folder

Finder → Settings → Tags → Uncheck all tags

## Git Setup

* Follow instructions in [setup_git.md](./setup_git.md)

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

* Install brew, run one line at a time in terminal:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
# follow prompts to add pathing to shell profile
brew update
brew upgrade
brew upgrade --cask
brew cleanup
```

* Use Brewfile in ../app_lists/Brewfile to install apps:

```bash
cd ../app_lists
brew bundle
```

## Install Wireguard

* install from the App Store

## Python Setup

* Follow instructions in [setup_python.md](./setup_python.md)

## VSCode Setup

* Follow instructions in [setup_vscode.md](./setup_vscode.md)

## Docker Setup

* Follow instructions in [setup_docker.md](./setup_docker.md)
