# Neovim Setup Guide

A beginner-friendly guide to installing and configuring Neovim with this
repository's `init.lua`, on macOS, Linux, Windows, and Android (Termux).
Includes a Windows portable (no admin rights) install path.

> The canonical config is
> [application_configs/nvim/init.lua](../application_configs/nvim/init.lua).
> The legacy `init.vim` is kept in the repo for reference only — Neovim loads
> `init.lua` first when both exist.

---

## Table of Contents

1. [What You're Installing](#what-youre-installing)
2. [Quick Start](#quick-start)
3. [Install Neovim](#install-neovim)
   - [macOS](#macos)
   - [Linux](#linux)
   - [Windows](#windows)
   - [Android (Termux)](#android-termux)
   - [Portable Install (Windows, no admin rights)](#portable-install-windows-no-admin-rights)
4. [Deploy the Config (`init.lua`)](#deploy-the-config-initlua)
5. [Install Plugins and LSPs](#install-plugins-and-lsps)
6. [Set Up GitHub Copilot](#set-up-github-copilot)
7. [Telescope Keymaps](#telescope-keymaps)
8. [Verify Everything Works](#verify-everything-works)
9. [Troubleshooting](#troubleshooting)
10. [Reference: Neovim Key Symbols Explained](#reference-neovim-key-symbols-explained)

---

## What You're Installing

- **Neovim** — the editor itself.
- **vim-plug** — a plugin manager. Reads the `Plug(...)` lines in `init.lua`
  and downloads those plugins.
- **Node.js** — required by `Mason` (LSP installs) and GitHub Copilot.
- **Mason** — installs and manages Language Server Protocol (LSP) servers
  (for example, `pyright` for Python autocomplete and error checking).
- **Telescope** — fuzzy finder for files, live grep, buffers, and more.
  Requires `ripgrep` for `:Telescope live_grep` and `fd` for `:Telescope find_files`
  (see install step below).

---

## Quick Start

1. Install Neovim (see your OS section below).
2. Install Node.js (needed for Mason / LSPs and Copilot).
3. Install `ripgrep` and `fd` (needed for Telescope live grep and file finder).
4. Install vim-plug.
5. Symlink this repo's `init.lua` to Neovim's config location.
6. Open `nvim` — plugins install automatically on first launch.
7. Run `:Copilot setup` to authenticate GitHub Copilot (one-time).

---

## Install Neovim

### macOS

Using [Homebrew](https://brew.sh):

```bash
brew install neovim node ripgrep fd
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
sudo apt install neovim nodejs ripgrep fd-find
# Upgrade later with:
sudo apt upgrade neovim
```

> On Linux, `fd` is installed as `fdfind`. Create a symlink so Telescope finds it:
>
> ```bash
> mkdir -p ~/.local/bin && ln -s $(which fdfind) ~/.local/bin/fd
> ```

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
choco install neovim nodejs ripgrep fd
# Upgrade later with:
choco upgrade neovim
```

Or using winget:

```powershell
winget install Neovim.Neovim
winget install OpenJS.NodeJS
winget install BurntSushi.ripgrep.MSVC
winget install sharkdp.fd
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

### Portable Install (Windows, no admin rights)

Use this when you can't install software system-wide on a Windows machine
(locked-down work laptop, shared PC, etc.).

#### 1. Download and extract Neovim

1. Go to [Neovim Releases](https://github.com/neovim/neovim/releases).
2. Download `nvim-win64.zip` from the latest stable release.
3. Extract to `C:\Users\jason.christiansen\userapps\nvim-win64\`

#### 2. Download Node.js (portable, no installer)

Mason and Copilot need Node.js. Use the zip build, not the installer:

1. Go to [Node.js Downloads](https://nodejs.org/en/download) and download
   the **Windows Binary (.zip)** for the LTS release.
2. Extract to `C:\Users\jason.christiansen\userapps\node\`

#### 3. Download ripgrep and fd (portable)

Both ship as standalone zip downloads — no installer required.

**ripgrep:**

1. Go to [ripgrep Releases](https://github.com/BurntSushi/ripgrep/releases).
2. Download `ripgrep-*-x86_64-pc-windows-msvc.zip`.
3. Extract to `C:\Users\jason.christiansen\userapps\ripgrep\`

**fd:**

1. Go to [fd Releases](https://github.com/sharkdp/fd/releases).
2. Download `fd-*-x86_64-pc-windows-msvc.zip`.
3. Extract to `C:\Users\jason.christiansen\userapps\fd\`

#### 4. Install vim-plug

```powershell
iwr -useb https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim |
  ni -Path "$env:LOCALAPPDATA\nvim-data\site\autoload\plug.vim" -Force
```

#### 5. Point Neovim at the config (automatic via profile)

`powershell_aliases.ps1` sets `XDG_CONFIG_HOME` to point directly at the
repo's `application_configs` folder whenever PowerShell starts on Windows.
Neovim respects this variable and looks for its config at
`$XDG_CONFIG_HOME\nvim\init.lua` — which is exactly where the file already
lives in the repo. No symlink, hard link, or `%LOCALAPPDATA%\nvim\` directory
needed.

To verify once Neovim is open:

```vim
:echo stdpath('config')
```

The path returned should end in `application_configs\nvim`.

#### 6. Configure the git credential helper

PortableGit has no credential helper set on first use. Without this,
`:PlugInstall` will pop up a **`CredentialHelperSelector` dialog on the
host machine's desktop for every plugin being cloned in parallel** — even
if you're connected over SSH, the dialogs appear on the physical screen of
the machine, not in your terminal. Run this once to pre-configure it:

```powershell
git config --global credential.helper manager
```

If the dialogs do appear (e.g. you forgot this step), check
**"Always use this from now on"**, leave `manager` selected, and click
**Select** on the front dialog — the rest will auto-dismiss.

#### 7. Open Neovim

```powershell
nvim
```

Plugins will auto-install on first launch. Once done, run `:Copilot setup`
to authenticate GitHub Copilot.

---

## Deploy the Config (`init.lua`)

Neovim looks for `init.lua` (preferred) or `init.vim` at an OS-specific path.
On macOS/Linux, symlink this repo's `init.lua` so edits flow both ways.
On Windows, `XDG_CONFIG_HOME` is set by `powershell_aliases.ps1` to point
directly at the repo — no symlink or hard link needed.

### Which file does Neovim load if both exist?

Neovim only ever loads **one** init file. On startup it searches the config
dir (`~/.config/nvim/` on mac/Linux, `%LOCALAPPDATA%\nvim\` on Windows) and
picks the first of these it finds, in this order:

1. `init.lua`
2. `init.vim`
3. `init.fnl`

So if `init.lua` exists, `init.vim` is silently ignored — they will **not**
both run. Since Neovim 0.9, having both files in the same config dir also
prints a warning (`E5422: Conflicting configs`) on startup, and `init.lua`
still wins.

A symlinked `init.lua` counts as existing. If you previously symlinked
`init.vim`, remove that symlink first to clear the warning:

```bash
rm ~/.config/nvim/init.vim          # mac/Linux
```

```powershell
del $env:LOCALAPPDATA\nvim\init.vim   # Windows
```

> Note: this only applies to the active config dir. On Windows, we use
> `XDG_CONFIG_HOME` (set in `powershell_aliases.ps1`) to point Neovim straight
> at the repo — no copy or link required. `NVIM_APPNAME` can also redirect the
> config dir if needed; the same init file priority rules apply. Two init
> files coexisting **inside this repo** are fine — they're just files in a
> folder, not in Neovim's config dir.

### macOS / Linux

The `~/.config/nvim/init.lua` link is manifest-driven (entry `nvim_init` in
`deploy_manifest.yaml` — see [deploy_configs.md](./deploy_configs.md)):

```bash
cd ~/GitHub/dotfiles
uv run python src/deploy_configs.py --dry-run   # preview
uv run python src/deploy_configs.py             # deploy
```

Verify the link:

```bash
ls -la ~/.config/nvim/init.lua
```

### Windows

`powershell_aliases.ps1` sets `XDG_CONFIG_HOME` to point directly at the
repo's `application_configs` folder on any Windows machine. Neovim finds the
config at `application_configs\nvim\init.lua` automatically — no symlink or
hard link needed, and nothing breaks when `git pull` runs.

Confirm it's working from inside Neovim:

```vim
:echo stdpath('config')
```

The path should end in `application_configs\nvim`.

---

## Install Plugins and LSPs

> **Plugins install automatically.** When you open `nvim` for the first time
> after symlinking `init.lua`, the config detects any missing plugins and runs
> `:PlugInstall` for you. You don't need to do it manually.

If you ever need to force a reinstall or update:

```vim
:PlugInstall     " install any missing plugins
:PlugUpdate      " update all plugins to their latest version
```

After `:PlugInstall` completes, press `q` to close the dialog, then quit and
reopen `nvim` so all plugins initialise cleanly.

### LSPs (Mason)

`pyright` (Python) auto-installs on startup via `ensure_installed` in the
config. For other LSPs:

```vim
:Mason
```

Navigate to the LSP you want and press `i`. Press `q` to close.

To add a language to the auto-install list, add it to `ensure_installed`
in [application_configs/nvim/init.lua](../application_configs/nvim/init.lua):

```lua
ensure_installed = { 'pyright', 'lua_ls', 'gopls' },
```

### Re-sourcing the config without restarting

If you edit `init.lua`, reload it inside Neovim with:

```vim
:source ~/.config/nvim/init.lua
```

(Some Lua state — like already-registered autocmd groups or `setup()` calls —
may need a full `nvim` restart to fully re-apply.)

---

## Set Up GitHub Copilot

The config ships with two Copilot plugins:

- **`github/copilot.vim`** — inline ghost-text suggestions while you type.
- **`CopilotC-Nvim/CopilotChat.nvim`** — chat window (`:CopilotChat`) plus
  helpers like `:CopilotChatExplain`, `:CopilotChatFix`, `:CopilotChatTests`,
  `:CopilotChatReview`. Requires `nvim-lua/plenary.nvim` (also bundled).

### Prerequisites

- An active GitHub Copilot subscription on your GitHub account.
- **Node.js ≥ 20** on `PATH` (`node --version`). You already installed Node
  for Mason — just confirm the version is current. Upgrade via Homebrew
  (`brew upgrade node`), apt, choco, or winget if needed.

### 1. Install the plugins

Inside Neovim:

```vim
:PlugInstall
```

### 2. Authenticate

```vim
:Copilot setup
```

Neovim prints a device code and a URL. Open the URL in a browser, paste the
code, approve the device. One-time per machine. Verify:

```vim
:Copilot status
```

Should report *Online* and *Enabled*.

### 3. Use inline completions (Tab completion)

Just start typing. Gray "ghost text" appears as Copilot suggests code.

| Keys (insert mode) | Action |
| --- | --- |
| `<Tab>` | Accept the full suggestion |
| `<M-]>` | Next suggestion |
| `<M-[>` | Previous suggestion |
| `<C-]>` | Dismiss suggestion |
| `<M-\>` | Request a suggestion manually |

> On macOS terminals, `<M-…>` = `Option`. Enable "Use Option as Meta key"
> in iTerm2 / Terminal preferences (see the [Reference](#reference-neovim-key-symbols-explained)
> section).

If `<Tab>` conflicts with a snippet plugin, uncomment the remap block in
[application_configs/nvim/init.lua](../application_configs/nvim/init.lua) to use
`<C-J>` instead:

```lua
vim.g.copilot_no_tab_map = true
vim.keymap.set('i', '<C-J>', 'copilot#Accept("\\<CR>")', {
  silent = true, script = true, expr = true, replace_keycodes = false,
})
```

Toggle Copilot per buffer with `:Copilot disable` / `:Copilot enable`.

### 4. Use Copilot Chat

The config defines these leader mappings (default `<Leader>` is `\`):

| Mapping | Command | What it does |
| --- | --- | --- |
| `<Leader>cc` | `:CopilotChat` | Open chat window (works in normal & visual mode) |
| `<Leader>ce` | `:CopilotChatExplain` | Explain the selected code |
| `<Leader>cf` | `:CopilotChatFix` | Suggest a fix for the selected code |
| `<Leader>ct` | `:CopilotChatTests` | Generate tests for the selection |
| `<Leader>cr` | `:CopilotChatReview` | Review the selection |

Free-form prompt:

```vim
:CopilotChat how do I read a JSON file in Python?
```

Other useful commands: `:CopilotChatModels` (switch model),
`:CopilotChatPrompts` (browse built-in prompts), `:CopilotChatReset`.

### 5. Using the chat window

When `:CopilotChat` (or `<Leader>cc`) opens the side panel, it behaves like
any Neovim buffer — typing your question is **not** the same as sending it.
You have to submit explicitly.

Default keymaps inside the chat buffer:

| Mode | Keys | Action |
| --- | --- | --- |
| Normal | `<CR>` (Enter) | **Submit** the prompt you typed |
| Insert | `<C-s>` | Submit the prompt without leaving insert mode |
| Normal | `q` | Close the chat window |
| Normal | `<C-l>` | Reset / clear the conversation |
| Normal | `gy` | Yank the last code block from the response |
| Normal | `gd` | Show diff of the suggested change |
| Normal | `ga` | Accept the diff into your source buffer |

Typical flow:

1. `<Leader>cc` to open the chat panel.
2. Press `i` (or `o`) to enter insert mode at the prompt line at the bottom.
3. Type your question.
4. Press `<Esc>` then `<CR>` — **or** stay in insert mode and press `<C-s>`.
5. The answer streams in above your prompt.

> **About the gray ghost text in the chat window:** that's `copilot.vim`'s
> inline completion suggesting your next line — it has nothing to do with
> submitting the chat. Ignore it, or disable Copilot completions in the chat
> buffer by adding this to [application_configs/nvim/init.lua](../application_configs/nvim/init.lua):
>
> ```lua
> vim.api.nvim_create_autocmd('FileType', {
>   pattern = 'copilot-chat',
>   callback = function() vim.b.copilot_enabled = false end,
> })
> ```

If `<CR>` doesn't submit, check `:verbose nmap <CR>` inside the chat buffer
to see what plugin grabbed it, or call `:CopilotChatSubmitPrompt` directly.

### 6. Referencing files and buffers in your prompt

CopilotChat.nvim uses `#`-prefixed **context references** to pull extra files
or buffers into the conversation. Type them inline anywhere in your prompt.

| Reference | What it sends to Copilot |
| --- | --- |
| `#buffer` | The buffer that was active **when you opened the chat** |
| `#buffers` | **All** currently loaded buffers (every file open in any split/tab) |
| `#file:path/to/file.py` | A specific file by path (relative to cwd or absolute) |
| `#selection` | The visual selection you made before opening chat |
| `#git:staged` / `#git:unstaged` | Current git diff |
| `#system:'cmd'` | Output of a shell command |
| `#url:https://…` | Contents of a URL |

**Referencing a file open in another split:**

The easiest way is `#buffers`, which includes every open file:

```plaintext
#buffers how does the LSP config interact with mason?
```

Or target one file explicitly with `#file:`:

```plaintext
#file:application_configs/nvim/init.vim explain the autocmd on the last line
```

Tab-completion works on these references inside the chat prompt — start
typing `#` then `<Tab>` to cycle through available context providers and
file paths.

Workflow tip: open the file you want to discuss in a vertical split
(`:vsplit path/to/file`), then `<Leader>cc` to open chat. The originating
buffer is captured as `#buffer`, and any other open file is reachable via
`#buffers` or `#file:…`.

---

## Telescope Keymaps

Telescope is a fuzzy finder. All mappings use `<Leader>f*` (default `\f*`).

| Mapping | What it does |
| --- | --- |
| `<Leader>ff` | Find files in the project (respects `.gitignore`) |
| `<Leader>fg` | Live grep (search text across all files — needs `ripgrep`) |
| `<Leader>fb` | Browse open buffers |
| `<Leader>fh` | Search Neovim help tags |
| `<Leader>fr` | Resume the last Telescope picker |

You can also call any picker directly:

```vim
:Telescope find_files
:Telescope live_grep
:Telescope lsp_references
:Telescope git_commits
```

Inside a Telescope window:

| Keys | Action |
| --- | --- |
| Type anything | Filter results |
| `<CR>` | Open selected item |
| `<C-v>` | Open in vertical split |
| `<C-x>` | Open in horizontal split |
| `<C-t>` | Open in new tab |
| `<Esc>` | Close picker |

---

## Verify Everything Works

Inside Neovim:

- `:checkhealth` — runs Neovim's built-in diagnostics. Look for green ✓s.
- `:PlugStatus` — shows installed plugins.
- `:Mason` — shows installed LSPs.
- Open a `.py` file; you should see `pyright` start (status line / no errors
  about missing LSPs).
- `<Leader>ff` should open a Telescope file picker.
- Start typing in a code file — gray ghost text should appear from Copilot.
  Press `<Tab>` to accept. Run `:Copilot status` to confirm it's *Online*.
- Run `:CopilotChat` — a chat window should open.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Error executing Lua...field 'uv' a nil value` | Neovim is too old. Upgrade (see Linux section for the PPA). |
| `:PlugInstall` says command not found | vim-plug isn't installed. Re-run the vim-plug curl/iwr command for your OS. |
| Mason shows nothing | Node.js isn't installed or not on `PATH`. Run `node --version` to check. |
| Symlink "access denied" on Windows | Not needed — `powershell_aliases.ps1` sets `XDG_CONFIG_HOME` pointing directly at the repo. No symlink or hard link is used on Windows. |
| Edits to repo `init.lua` don't show up | Symlink wasn't created, or an old `init.vim` is shadowing it. Confirm with `ls -la ~/.config/nvim/` (mac/Linux) or `dir %LOCALAPPDATA%\nvim` (Windows). Remove any stray `init.vim`. |
| Copilot ghost text doesn't appear | Run `:Copilot status`. If *Not Authorized*, run `:Copilot setup`. If *Node.js too old*, upgrade to Node ≥ 20. |
| `:CopilotChat` says module not found | Run `:PlugInstall` to fetch `plenary.nvim` and `CopilotChat.nvim`, then restart Neovim. |
| `<Tab>` doesn't accept Copilot suggestion | Another plugin claimed `<Tab>`. Uncomment the `g:copilot_no_tab_map` block in `init.lua` to use `<C-J>` instead. |
| Telescope `live_grep` says no results / binary not found | Install `ripgrep`: `brew install ripgrep` / `sudo apt install ripgrep` / `choco install ripgrep`. |
| Telescope `find_files` shows nothing / `fd not found` | Install `fd`: `brew install fd` / `sudo apt install fd-find` (then symlink: `ln -s $(which fdfind) ~/.local/bin/fd`) / `choco install fd`. |
| Plugins didn't auto-install on first launch | vim-plug itself isn't installed. Run the `curl`/`iwr` command for your OS, then reopen `nvim`. |

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
`~/.config/nvim/init.lua` (mac/Linux) or `%LOCALAPPDATA%\nvim\init.lua`
(Windows), symlinked to this repo.
