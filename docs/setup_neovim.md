# Neovim

## Installation

### Installation on Linux

```bash
sudo apt install neovim
# will need to upgrade if older version
sudo apt upgrade neovim
# install VimPlug
curl -fLo ~/.local/share/nvim/site/autoload/plug.vim --create-dirs <https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim>
# install node for Mason / LSP support
sudo apt install nodejs
# Run NeoVim and install the plugins
nvim
# inside NeoVim run
:PlugInstall
:Mason
# press i to install pyright if it’s not already installed.
# restart your shell to take effect
```

### Installation on Windows

```bash
choco install neovim
# will need to upgrade if older version
choco upgrade neovim
# install VimPlug
iwr -useb <https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim> | ni -Path "$env:LOCALAPPDATA\nvim-data\site\autoload\plug.vim" -Force
# install node for Mason / LSP support
winget install OpenJS.NodeJS
# Run NeoVim and install the plugins
nvim
# inside NeoVim run
:PlugInstall
:Mason
# press i to install pyright if it’s not already installed.
# restart your shell to take effect
```

### Installation on Android with Termux

```bash
pkg install neovim
```

## Deploying Configuration

### Deploying Configuration on Windows

- For windows powershell your config needs to be symlinked to `%USERPROFILE%\AppData\Local\nvim\init.vim`
  - Open a powershell terminal as an administrator
  - `cd $env:USERPROFILE\AppData\Local`
  - `mkdir nvim`
  - `cd nvim`
  - `cmd /c mklink C:\Users\jason\AppData\Local\nvim\init.vim C:\Users\jason\GitHub\dotfiles\application_configs\nvim\init.vim`
  - OR
  - `cmd /c mklink init.vim C:\Users\16937827583938060798\HelloFreshProjects\dotfiles\application_configs\nvim\init.vim`

### Deploying Configuration on Linux

- For linux this file needs to be symlinked to ~/.config/nvim/
  - `ln -s ~/dotfiles/application_configs/nvim/init.vim ~/.config/nvim/init.vim`

## Install vim-plug for managing Neovim plugins

### Install vim-plug for managing Neovim plugins on Linux or Mac

```bash
curl -fLo ~/.local/share/nvim/site/autoload/plug.vim --create-dirs https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim
```

### Install vim-plug for managing Neovim plugins on Windows

```bash
iwr -useb https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim | ni -Path "$env:LOCALAPPDATA\nvim-data\site\autoload\plug.vim" -Force
```

### Load the vim-plug plugin manager

- Open Neovim and run `:PlugInstall` to install the plugins

## Manual Configuration

### Sourcing a file

Open Neovim.
Enter command mode by pressing Esc and then :
Type the following command and press Enter:

```vim
:source ~/.config/nvim/init.vim
```
