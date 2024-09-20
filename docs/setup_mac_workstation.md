# Setup macOS Workstation

## Git Setup

* Follow instructions in [setup_git.md](./setup_git.md)

## Brew Setup

* Option 1: Just Install brew, run one line at a time

  ```bash
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  export PATH="/opt/homebrew/bin:$PATH"
  brew update
  brew upgrade
  brew upgrade --cask
  brew cleanup
  ```

* Option 2: Use Included Script to install recommended packages and brew, also applies some path fixes and other macOS specefic settings

  * Clone this repository into a directory
  
  * Make sure the app_lists folder has the apps you want to install in the list you use
  
  * Run the following commands from the directory you just cloned

  ```bash
  cd scripts
  chmod +x setup_macos.sh
  ./install_mac_apps_<name of the app list you chose>.sh # fill inthe <> with the name of the apps list you chose
  ```

  * This script will install brew and some recommended packages
  * It will also apply some path fixes and other macOS specefic settings

## Python Setup

* If not using an app list with brew: Follow instructions in [setup_python.md](./setup_python.md)

## VSCode Setup

* If not using an app list with brew: Follow instructions in [setup_vscode.md](./setup_vscode.md)

## Docker Setup

* If not using an app list with brew: Follow instructions in [setup_docker.md](./setup_docker.md)
