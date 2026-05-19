# Neovim Setup Guide

A beginner-friendly guide to installing and configuring Neovim with this
repository's `init.vim`, on macOS, Linux, Windows, Android (Termux), and as a
portable install.

---

## Table of Contents

1. [What You're Installing](#what-youre-installing)
2. [Quick Start](#quick-start)
3. [Install Neovim](#install-neovim)
   - [macOS](#macos)
   - [Linux](#linux)
   - [Windows](#windows)
   - [Android (Termux)](#android-termux)
   - [Portable Install (no admin rights)](#portable-install-no-admin-rights)
4. [Deploy the Config (`init.vim`)](#deploy-the-config-initvim)
5. [Install Plugins and LSPs](#install-plugins-and-lsps)
6. [Verify Everything Works](#verify-everything-works)
7. [Troubleshooting](#troubleshooting)
8. [Reference: Neovim Key Symbols Explained](#reference-neovim-key-symbols-explained)

---

## What You're Installing

- **Neovim** — the editor itself.
- **vim-plug** — a plugin manager. Reads the `Plug '...'` lines in `init.vim`
  and downloads those plugins.
- **Node.js** — required by `Mason` so it can install language servers.
- **Mason** — installs and manages Language Server Protocol (LSP) servers
  (for example, `pyright` for Python autocomplete and error checking).

---

## Quick Start

1. Install Neovim (see your OS section below).
2. Install Node.js (needed for Mason / LSPs).
3. Install vim-plug.
4. Symlink this repo's `init.vim` to Neovim's config location.
5. Open `nvim` and run `:PlugInstall`, then `:Mason` (press `i` on `pyright`).
6. Restart your shell.

---

## Install Neovim

### macOS

Using [Homebrew](https://brew.sh):

```bash
brew install neovim node
```

Upgrade later with:

```bash
brew upgrade neovim
```

Install vim-plug:

```bash
curl -fLo ~/.local/share/nvim/site/autoload/plug.vim --create-dirs https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim
```

### Linux

```bash
sudo apt install neovim nodejs
# Upgrade later with:
sudo apt upgrade neovim
```

If you get errors like `Error executing Lua...field 'uv' a nil value`, your
distro's Neovim is too old. Install the unstable PPA:

```bash
sudo apt remove neovim
sudo add-apt-repository ppa:neovim-ppa/unstable -y
sudo apt update
sudo apt install neovim
```

Install vim-plug:

```bash
curl -fLo ~/.local/share/nvim/site/autoload/plug.vim --create-dirs \
  https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim
```

### Windows

Using [Chocolatey](https://chocolatey.org) (run PowerShell as Administrator):

```powershell
choco install neovim
choco install nodejs
# Upgrade later with:
choco upgrade neovim
```

Or using winget:

```powershell
winget install Neovim.Neovim
winget install OpenJS.NodeJS
```

Install vim-plug:

```powershell
iwr -useb https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim |
  ni -Path "$env:LOCALAPPDATA\nvim-data\site\autoload\plug.vim" -Force
```

### Android (Termux)

```bash
pkg install neovim nodejs
```

### Portable Install (no admin rights)

Use this if you can't install software system-wide (locked-down work
laptop, USB stick, etc.).

1. Download a release archive for your OS from
   [Neovim Releases](https://github.com/neovim/neovim/releases).
2. Extract it anywhere you have write access (e.g. `C:\Tools\nvim` or
   `~/tools/nvim`).
3. Add the extracted `bin/` directory to your `PATH`.
4. Verify with `nvim --version`.
5. Follow the [Deploy the Config](#deploy-the-config-initvim) section below —
   the same `init.vim` works for portable installs.

---

## Deploy the Config (`init.vim`)

Neovim looks for `init.vim` at an OS-specific path. Symlink this repo's copy
so edits flow both ways.

### macOS / Linux

```bash
mkdir -p ~/.config/nvim
ln -s ~/GitHub/dotfiles/application_configs/nvim/init.vim ~/.config/nvim/init.vim
```

### Windows (PowerShell as Administrator)

```powershell
cd $env:USERPROFILE\AppData\Local
mkdir nvim
cd nvim
cmd /c mklink init.vim C:\Users\jason\GitHub\dotfiles\application_configs\nvim\init.vim
```

Adjust the source path if your username or repo location differs, for example:

```powershell
cmd /c mklink init.vim C:\Users\16937827583938060798\HelloFreshProjects\dotfiles\application_configs\nvim\init.vim
```

---

## Install Plugins and LSPs

1. Open Neovim (there will be some errors first time, just hit enter)

   ```bash
   nvim
   ```

2. Install all plugins listed in `init.vim`:

   ```vim
   :PlugInstall
   ```

   - Once it is done hit `q` to close the dialog

3. Close Neovim with `:q`

4. Reopen Neovim with `nvim`

5. Open Mason to install LSPs:

   ```vim
   :Mason
   ```

   Move the cursor to `pyright` (or any other LSP you want) and press `i` to
   install it. Press `q` to close Mason when done.

6. Restart your shell so everything picks up cleanly.

### Re-sourcing the config without restarting

If you edit `init.vim`, you can reload it inside Neovim with:

```vim
:source ~/.config/nvim/init.vim
```

---

## Verify Everything Works

Inside Neovim:

- `:checkhealth` — runs Neovim's built-in diagnostics. Look for green ✓s.
- `:PlugStatus` — shows installed plugins.
- `:Mason` — shows installed LSPs.
- Open a `.py` file; you should see `pyright` start (status line / no errors
  about missing LSPs).

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Error executing Lua...field 'uv' a nil value` | Neovim is too old. Upgrade (see Linux section for the PPA). |
| `:PlugInstall` says command not found | vim-plug isn't installed. Re-run the vim-plug curl/iwr command for your OS. |
| Mason shows nothing | Node.js isn't installed or not on `PATH`. Run `node --version` to check. |
| Symlink "access denied" on Windows | Open PowerShell **as Administrator** before running `mklink`. |
| Edits to repo `init.vim` don't show up | Symlink wasn't created. Confirm with `ls -la ~/.config/nvim/` (mac/Linux) or `dir %LOCALAPPDATA%\nvim` (Windows). |

---

## Reference: Neovim Key Symbols Explained

Vim/Neovim documentation uses shorthand for special keys. This trips up new
users because the same symbol can mean different physical keys depending on
your OS and keyboard.

### Common notation

| Notation | Meaning |
| --- | --- |
| `<Leader>` | A user-defined "prefix" key. Default is `\` (backslash). You set it with `let mapleader = " "` etc. Used like: `<Leader>w` means "press Leader, then w". |
| `<LocalLeader>` | Like `<Leader>` but scoped to a specific filetype. Default is also `\`. |
| `<CR>` | Carriage Return — i.e. the **Enter / Return** key. |
| `<Esc>` | The **Escape** key. |
| `<Tab>` / `<S-Tab>` | Tab key / Shift+Tab. |
| `<BS>` | Backspace. |
| `<Space>` | The spacebar. |
| `<Up>` `<Down>` `<Left>` `<Right>` | Arrow keys. |
| `<C-x>` | **Ctrl** + `x`. Example: `<C-w>` = Ctrl+W. |
| `<S-x>` | **Shift** + `x`. |
| `<M-x>` or `<A-x>` | **Meta / Alt** + `x`. See OS mapping below. |
| `<D-x>` | **Super / Command** key + `x`. See OS mapping below. Rarely usable in a terminal. |
| `<F1>`–`<F12>` | Function keys. |

### What "Meta", "Alt", and "Super" actually press

These names come from old Unix keyboards. On modern hardware they map like
this:

| Vim name | macOS keyboard | Windows keyboard | Linux keyboard |
| --- | --- | --- | --- |
| **Alt / Meta** (`<M-…>`, `<A-…>`) | `Option` (⌥) | `Alt` | `Alt` |
| **Super** (`<D-…>`) | `Command` (⌘) | `Windows` key (⊞) | `Super` (often the Windows-logo key) |
| **Ctrl** (`<C-…>`) | `Control` (⌃) | `Ctrl` | `Ctrl` |
| **Shift** (`<S-…>`) | `Shift` (⇧) | `Shift` | `Shift` |

Cross-OS quirks worth knowing:

- **macOS Terminal / iTerm2**: `Option` does not send Alt by default. In
  iTerm2 enable: *Preferences → Profiles → Keys → Left Option key = Esc+*.
  In Apple Terminal: *Preferences → Profiles → Keyboard → Use Option as
  Meta key*.
- **`<D-…>` (Command / Super) generally does not work in terminal Neovim**
  on any OS — terminals intercept it. It only works in GUI front-ends like
  Neovide, VimR, or `nvim-qt`.
- **Windows**: the `Windows` key (`<D-…>`) is almost always swallowed by the
  OS — don't map to it.

### Example: reading a mapping

```vim
nnoremap <Leader>w :w<CR>
```

Means: in **n**ormal mode, press `Leader` then `w` to run `:w` (save) and
press Enter. With the default leader (`\`), that's `\` then `w`.

```vim
nnoremap <C-p> :Files<CR>
```

Means: press `Ctrl+p` to open the file picker.

---

That's it. If you ever forget where the config lives, it's
`~/.config/nvim/init.vim` (mac/Linux) or `%LOCALAPPDATA%\nvim\init.vim`
(Windows), symlinked to this repo.
