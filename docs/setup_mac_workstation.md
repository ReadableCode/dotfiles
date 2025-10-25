# Setup macOS Workstation

## Set settings

## Finder Configuration

Finder → Settings → Advanced → “Show all filename extensions”

Finder → Settings → Tags → Uncheck all tags

## HID Configuration

1. **System Settings → Trackpad → Point & Click**  
2. Toggle on **“Secondary click”**  
3. Choose **“Click or tap with two fingers.”**

## Git Setup

* Follow instructions in [setup_git.md](./setup_git.md)

## Symlink zsh config

```bash
mv ~/.zshrc ~/.zshrc.bak
ln -s /home/jason/GitHub/dotfiles/application_configs/bash/.zshrc ~/.zshrc
```

## Brew Setup

* Install brew, run one line at a time in terminal:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
export PATH="/opt/homebrew/bin:$PATH"
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

## Python Setup

* Follow instructions in [setup_python.md](./setup_python.md)

## VSCode Setup

* Follow instructions in [setup_vscode.md](./setup_vscode.md)

## Docker Setup

* Follow instructions in [setup_docker.md](./setup_docker.md)
