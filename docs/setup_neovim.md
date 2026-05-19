# Neovim Setup Guide

A beginner-friendly guide to installing and configuring Neovim with this
repository's `init.lua`, on macOS, Linux, Windows, Android (Termux), and as a
portable install.

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
   - [Portable Install (no admin rights)](#portable-install-no-admin-rights)
4. [Deploy the Config (`init.lua`)](#deploy-the-config-initlua)
5. [Install Plugins and LSPs](#install-plugins-and-lsps)
6. [Set Up GitHub Copilot](#set-up-github-copilot)
7. [Verify Everything Works](#verify-everything-works)
8. [Troubleshooting](#troubleshooting)
9. [Reference: Neovim Key Symbols Explained](#reference-neovim-key-symbols-explained)

---

## What You're Installing

- **Neovim** — the editor itself.
- **vim-plug** — a plugin manager. Reads the `Plug(...)` lines in `init.lua`
  and downloads those plugins.
- **Node.js** — required by `Mason` so it can install language servers.
- **Mason** — installs and manages Language Server Protocol (LSP) servers
  (for example, `pyright` for Python autocomplete and error checking).

---

## Quick Start

1. Install Neovim (see your OS section below).
2. Install Node.js (needed for Mason / LSPs).
3. Install vim-plug.
4. Symlink this repo's `init.lua` to Neovim's config location.
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
5. Follow the [Deploy the Config](#deploy-the-config-initlua) section below —
   the same `init.lua` works for portable installs.

---

## Deploy the Config (`init.lua`)

Neovim looks for `init.lua` (preferred) or `init.vim` at an OS-specific path.
Symlink this repo's `init.lua` so edits flow both ways.

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

> Note: this only applies to the active config dir. `$XDG_CONFIG_HOME` and
> `NVIM_APPNAME` can point Neovim at a different folder; the same rules
> apply there. Two init files coexisting **inside this repo** are fine —
> they're just files in a folder, not in Neovim's config dir.

### macOS / Linux

```bash
mkdir -p ~/.config/nvim
ln -s ~/GitHub/dotfiles/application_configs/nvim/init.lua ~/.config/nvim/init.lua
```

Verify the link:

```bash
ls -la ~/.config/nvim/init.lua
```

### Windows (PowerShell as Administrator)

```powershell
cd $env:USERPROFILE\AppData\Local
mkdir nvim -ErrorAction SilentlyContinue
cd nvim
cmd /c mklink init.lua C:\Users\jason\GitHub\dotfiles\application_configs\nvim\init.lua
```

Adjust the source path if your username or repo location differs, for example:

```powershell
cmd /c mklink init.lua C:\Users\16937827583938060798\HelloFreshProjects\dotfiles\application_configs\nvim\init.lua
```

---

## Install Plugins and LSPs

1. Open Neovim (there will be some errors first time, just hit enter)

   ```bash
   nvim
   ```

2. Install all plugins listed in `init.lua`:

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

## Verify Everything Works

Inside Neovim:

- `:checkhealth` — runs Neovim's built-in diagnostics. Look for green ✓s.
- `:PlugStatus` — shows installed plugins.
- `:Mason` — shows installed LSPs.
- Open a `.py` file; you should see `pyright` start (status line / no errors
  about missing LSPs).
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
| Symlink "access denied" on Windows | Open PowerShell **as Administrator** before running `mklink`. |
| Edits to repo `init.lua` don't show up | Symlink wasn't created, or an old `init.vim` is shadowing it. Confirm with `ls -la ~/.config/nvim/` (mac/Linux) or `dir %LOCALAPPDATA%\nvim` (Windows). Remove any stray `init.vim`. |
| Copilot ghost text doesn't appear | Run `:Copilot status`. If *Not Authorized*, run `:Copilot setup`. If *Node.js too old*, upgrade to Node ≥ 20. |
| `:CopilotChat` says module not found | Run `:PlugInstall` to fetch `plenary.nvim` and `CopilotChat.nvim`, then restart Neovim. |
| `<Tab>` doesn't accept Copilot suggestion | Another plugin claimed `<Tab>`. Uncomment the `g:copilot_no_tab_map` block in `init.lua` to use `<C-J>` instead. |

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
