# Setup macOS Workstation

## Start here: run bootstrap

One command takes a bare Mac to cloned, synced, deployed and packaged. It is
idempotent, so it doubles as a repair tool on a machine that already works:

```bash
curl -fsSL https://raw.githubusercontent.com/ReadableCode/dotfiles/master/scripts/bootstrap.sh | bash
```

Add `--dry-run` first to see what it would do without changing anything, and
`--credentials <ssh-url>` (repeatable) to clone the credentials repos — their URLs are
not in this public repo, see `cloning_credentials_repos.md` in the personal credentials
repo.

Bootstrap installs Homebrew, git and uv if missing, clones dotfiles to `~/GitHub`, runs
`uv sync`, `clone_repos.py` and `deploy_configs.py`, then installs everything in
`app_lists/Brewfile` via `scripts/install_mac_apps.sh` (which reports what is already
installed and prompts once for the rest). `brew bundle --file=app_lists/Brewfile` still
works if you just want a straight install of everything.

**What bootstrap does not do**, and you still need from the rest of this document:

- macOS system settings: hostname, scaling, Finder behaviour, keyboard, Dock, power
- signing in to iCloud / App Store, and anything installed from the App Store
- licensed apps and their keys
- Xcode and the beta toolchain (see `xcode-beta-setup-guide.md`)

The rest of this page is the reference detail behind those steps.

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
- Reminders
- Notes
- Bitwarden
- Chrome
- Edge
- Messages
- Phone
- FaceTime
- Contacts
- Mail
- Gmail
- Calendar
- Personal Calendar
- Outlook (PWA)
- Claude
- T3 Code
- VSCode
- Messenger
- Discord
- Slack
- Meet
- Teams
- Plex
- YouTube
- YTMusic
- Phone Mirroring
- VNCViewer
- GLKVM
- Moonlight
- Parsec
- Tailscale
- OpenVPN
- Wireguard
- Steam
- Epic Games
- Activity Monitor
- Xcode Beta
- Device Hub
- Stream Deck

The Downloads stack and Trash sit past the divider at the end of the Dock.

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

## Deploy configs (zshrc and friends)

All config links (zshrc, shared aliases, tmux, nvim, zed, VS Code, Hammerspoon,
Claude settings, ...) are driven by `deploy_manifest.yaml` — see
[deploy_configs.md](./deploy_configs.md):

```bash
cd ~/GitHub/dotfiles
uv run python src/deploy_configs.py status      # preview / drift report
uv run python src/deploy_configs.py             # deploy
```

Any pre-existing `~/.zshrc` is backed up to `data/config_backups/` and
replaced by a link to the repo version.

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

Either install everything straight from the Brewfile:

```bash
brew bundle --file=~/GitHub/dotfiles/app_lists/Brewfile
```

or use the installer, which lists what is already present and prompts once for the
rest (this is what bootstrap runs):

```bash
bash ~/GitHub/dotfiles/scripts/install_mac_apps.sh
```

### SQL Server ODBC driver (msodbcsql17)

Needed only on machines that run pyodbc code against SQL Server (connection
strings name "ODBC Driver 17 for SQL Server", so install 17, not 18). Not in
the Brewfile on purpose: the tap needs an explicit `brew trust` first, which
would fail a fresh machine's unattended `brew bundle` run.

```bash
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew trust microsoft/mssql-release
HOMEBREW_ACCEPT_EULA=Y brew install msodbcsql17
```

If pyodbc still reports the driver missing, the pip wheel is ignoring
Homebrew's config; point it there explicitly:

```bash
export ODBCSYSINI=/opt/homebrew/etc
```

### Cleaning up brew to get disk space back

```bash
brew cleanup --prune=all
rm -rf ~/Library/Caches/Homebrew
```

### Moving Homebrew Cache

Only Envy does this — its internal disk is small. Other Macs keep the defaults.

```bash
# create new cache directory
mkdir -p /Volumes/EnvyExtSSD/HomebrewCache
# set permissions for current user
sudo chown -R $(whoami) /Volumes/EnvyExtSSD/HomebrewCache
```

Persist it in the machine-local zsh config. `~/.zshrc.local` is a symlink
deployed by `deploy_configs.py`, so edit the repo file, not the link:

```bash
$EDITOR ~/GitHub/dotfiles/application_configs/bash/zshrc_local.envy
```

The exports there are unconditional on purpose. If the SSD is not mounted,
brew/uv/go fail instead of rebuilding the caches on the internal disk the
redirect exists to protect — the shell prints a warning at startup saying the
volume is missing, so a failing `brew install` is easy to explain.

A machine with no `zshrc_local.<host>` variant has no `~/.zshrc.local` at all
(there is no bare default); `.zshrc` skips it and the manifest entry reports
`SKIP_VARIANT`.

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

The dotfiles config is deployed by the manifest (entry `hammerspoon_init` in
`deploy_manifest.yaml` — see [deploy_configs.md](./deploy_configs.md)):

```bash
cd ~/GitHub/dotfiles && uv run python src/deploy_configs.py
```

- Launch Hammerspoon from `/Applications` — it lives in the menu bar
- Click the menu bar icon → **Reload Config**
- Grant Accessibility permissions when prompted: System Settings → Privacy & Security → Accessibility

Current hotkeys defined in `application_configs/hammerspoon/init.lua`:

| Hotkey | Action |
| -------- | -------- |
| `Ctrl+Shift+C` | Copy selection, open as Google Sheets URL |
| `Ctrl+Shift+F` | Copy selection, open as Google Drive folder URL |
| `Cmd+Shift+V` | Paste as plain text (strips formatting) |
| `Ctrl+Shift+T` | Open front Finder window in Terminal |
| `Ctrl+Shift+L` | Apply saved layouts to every desktop in sequence |
| `Ctrl+Shift+A` | Apply the saved layout to this desktop only |
| `Ctrl+Shift+S` | Recapture **all** windows on this desktop |
| `Ctrl+Shift+W` | Recapture **only the focused app's** window(s) |
| `Ctrl+Shift+E` | Open the visual layout editor in a browser |
| `Ctrl+Shift+P` | Enforce every app's desktop assignment |
| `Ctrl+Shift+G` | Send visible windows to the desktop they belong on |
| `Ctrl+Shift+H` | Show the hotkey cheatsheet |

### Window layouts (per desktop)

Saved layouts live in `application_configs/hammerspoon/window_layouts.json`.
Because `init.lua` is symlinked from the repo, Hammerspoon follows the link and
writes that JSON back into the repo, so it can be committed. The desktop number
is detected automatically — you are only prompted if detection fails.

Layouts anchor on screen *orientation* (portrait vs landscape) rather than
display IDs, so they survive the KVM re-enumerating the monitors.

#### Assignment and position are separate

*Which desktop* an app lives on and *where on the screen* it sits are different
questions, so they are different config, and either can exist without the other:

| | Where it lives in the JSON | What it means |
| --- | --------------------------- | --------------- |
| assignment | `"assign": {"Mail": "all", "Microsoft Edge": 3}` | Which desktop the app's windows belong on. This is the Dock's Options → Assign To setting, which the config enforces. |
| rectangle | `"all"` for all-desktops apps, `"1"`/`"2"`/`"3"` otherwise | Where the window sits. |
| title match | `"match"` on a rectangle | *Which window* of that app the rectangle is for. |

So `"Microsoft Edge": 3` with no rectangle is "keep Edge on desktop 3, I don't
care where it sits". VS Code is the mirror image: three rectangles, no
assignment, because it is three separate windows.

An All Desktops app has **one** window that shows up everywhere, so it cannot be
in two places at once — a per-desktop rectangle for it is a lie waiting to drift.
Those windows live in `"all"` and are drawn on every tab of the editor, and the
assignment is what decides which side a captured window lands on.

An app with neither is simply not managed: apply never touches it. Un-configuring
an app means dropping both, which the editor's **Remove app…** does in one go.

#### Telling one window of an app from another

The Dock can only assign a whole app to a desktop, which is no help for VS Code:
it wants a different window on each. So a rectangle may carry `"match"`, a
substring of the window title:

```json
{ "app": "Code", "match": "envy (Workspace)", "screen": "landscape", ... }
```

Titles change as you switch files, so match the stable tail — VS Code puts the
workspace there (`envy (Workspace)`, or a remote machine's hostname) and
Chrome puts the profile there (`Jason (Personal)` on desktop 1, a work
profile on desktop 2). Because those matches name real hostnames and client
Chrome profiles, `window_layouts.json` is private: dotfiles carries only a
gitignored symlink and the data deploys from personal_credentials
(entry `hammerspoon_window_layouts`).

An entry may also **omit `unit` entirely**:

```json
{ "app": "Google Chrome", "match": "Jason (Personal)", "screen": "landscape" }
```

That says "this window belongs on this desktop, don't manage where it sits" — the
per-window version of an assignment, and the only way to say it for an app whose
windows want different desktops. Gather uses those entries; apply ignores them.
In the editor they appear under "Desktop N, not positioned", and the
**Stop positioning** / **Give it a rectangle** button moves an entry between the
two states.

A match beats the screen when apply hands windows out, and recapture refills a
matched slot from the window it names rather than whichever one came up first —
otherwise a recapture would swap two VS Code windows' rectangles. The editor
warns when an app has rectangles on more than one desktop and no match, since
that is the case nothing can resolve.

**Capture is split in two**, because recapturing everything after nudging one
window is how a half-arranged desktop overwrites good entries:

- `Ctrl+Shift+S` — recapture every window on this desktop.
- `Ctrl+Shift+W` — recapture only the focused app, leaving the rest of that
  desktop's saved entries untouched. This is the one to use after moving a
  single window. An app with two saved windows (GLKVM) keeps both slots, matched
  in order.

Both **merge** rather than replace. A saved entry carries things no capture can
reconstruct — its title match, and whether it is positioned at all — so
rebuilding the list from the screen would silently delete them. Merging also
means closing an app does not delete its layout. Windows on screen with no entry
are still added.

**Apply** with `Ctrl+Shift+L` (walks every desktop in turn) or `Ctrl+Shift+A`
(this desktop only). Both gather first — see below.

#### Getting windows onto the right desktop after a restart

VS Code reopens every window on one desktop at login. `Ctrl+Shift+G` (**gather**)
sends each window visible from here to the desktop the config names, working it
out from the app's assignment, then from a rectangle whose title match fits the
window, then — if the app has rectangles on exactly one desktop — that one.
Anything ambiguous is left alone. `Ctrl+Shift+L` gathers on every desktop first
and lays everything out second, so a window that arrives somewhere already
processed still gets positioned.

The move itself is a hand gesture, not an API call. `hs.spaces.moveWindowToSpace`
is the obvious route and it is a lie on this macOS: it returns `true` and the
window does not move (verified — `windowSpaces` reports the same space before and
after). What does work is what a person does: macOS carries a window that is
mid-drag when you press its "switch to desktop N" shortcut, so `wl.dragToDesktop`
grabs the title bar, holds, switches, and lets go. It grabs 30% across to stay
clear of the traffic lights and of whatever an app puts in the middle of its
title bar.

#### Visual editor

`Ctrl+Shift+E` opens `window_layout_editor.html` at
<http://localhost:21212/editor>, served by Hammerspoon's own local HTTP server.
It draws both monitors at their true proportions and lets you drag and resize
the saved rectangles instead of editing fractions by hand:

- Solid blue outlines are this desktop's windows; dashed purple ones marked `∀`
  are the all-desktops windows, drawn on every tab — drag one and it moves on all
  of them, because it is one window.
- Drag to move, corner/edge handles to resize; shift-click for multi-select.
- Windows snap to screen edges, a chosen grid (halves … twelfths), and the edges
  and centres of the other windows, with guides showing what caught. Hold
  <kbd>alt</kbd> while dragging to ignore snapping.
- **Scope** buttons move the selected app between all-desktops and this-desktop.
  They only ever re-file a rectangle the app already has; the **Add** buttons are
  what create one.
- **Match…** copies the selected rectangle onto any other entries you tick,
  including ones on other desktops. The entry list only shows one desktop at a
  time, so this is the way to give Slack on desktop 2 and Teams on desktop 3 the
  same slot as Messages on desktop 1.
- The **Desktop assignment** panel is a row per app with a dropdown, listing apps
  whether or not they have a rectangle. Apps assigned with no rectangle also show
  up in the entry list under "Assigned, no rectangle", so they cannot get lost.
- Removing config: hover any row in the entry list for an `×` that deletes that
  one rectangle, or use **Remove app…** to drop every rectangle the app has on
  every desktop. That one confirms first, spelling out exactly what it deletes.
  It leaves the All Desktops pin alone — drop that with the app's chip.
- Every button carries a hover tooltip spelling out exactly what it rewrites —
  the two recapture buttons name the desktop and say what gets lost.
- Alignment tools for the selection: align, distribute, equal size, close gaps,
  and **stack &amp; fill**, which divides the screen among the selected windows in
  their current order — the fast way to tidy the vertical monitor.
- Arrow keys nudge, alt+arrows resize, `⌘S` saves.
- "Ghost live windows" overlays where the windows actually are right now, so you
  can see saved-versus-actual before applying.
- Recapture-all and recapture-this-app are buttons too, and they only light up
  on the desktop you are standing on.

Saves are written by a fixed-key-order encoder, so editing one window produces
one window's worth of git diff rather than reshuffling the whole file.

The same server backs the Stream Deck keys (Website action, "GET request in
background"): `/applyLayouts`, `/apply?space=N`, `/snapshot`, `/snapshotApp`,
`/fixSticky`, `/learnSticky`, `/reload`. It binds to localhost only.

#### Enforcing assignments

Two things go wrong. An app pinned to All Desktops still *shows* the checkmark in
its Dock menu but stops following you between desktops (typically after a KVM
flip); and an app that belongs on one desktop drifts onto another. Both are
repaired from `"assign"`.

Detection needs no menus: `hs.spaces.windowSpaces()` reports every space a window
is on, and `wl.spaceIndex()` maps space IDs to desktop numbers, so "on every
desktop" and "on exactly desktop N" are directly observable. A mismatch with
`"assign"` is the bug.

The repairs drive the Dock's own right-click menu (Options → All Desktops / This
Desktop / None), readable and pressable without ever being rendered:

- **Fix drift** shoves misplaced windows onto their desktop and runs the
  un-assign / re-assign cycle on any stale All Desktops app. No desktop
  switching, so this is what runs automatically five seconds after a display
  change and again before `Ctrl+Shift+L`.
- **Enforce all** (`Ctrl+Shift+P`) also writes the numbered assignments. macOS
  resolves "This Desktop" against wherever you are standing, so this visits each
  desktop in turn and comes back. Every step is traced to the Hammerspoon console
  with a `[wl]` prefix.
- **Learn** records where each open app currently lives as its intended
  assignment. It merges rather than replaces, so apps that happen to be closed
  keep whatever they had.

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

## Pre-authorize Local Network access for the LAN

macOS's Local Network privacy check (System Settings → Privacy & Security →
Local Network) blocks each app's LAN traffic until its one-time prompt is
approved. Symptoms of a missed/denied prompt: "No route to host" from CLI
tools (e.g. Claude Code) or "Transport error" from T3 Code remote
environments, against LAN hosts that ping fine from Terminal. The prompt is
easy to lose and can't be clicked in headless/agent-driven setups, so
allowlist the home subnet system-wide instead of relying on per-app toggles:

```bash
sudo defaults write com.apple.network.local-network AllowedWiFiLocalNetworkAddresses -array "192.168.86.0/24"
sudo defaults write com.apple.network.local-network AllowedEthernetLocalNetworkAddresses -array "192.168.86.0/24"
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

## T3 Code Setup

- Installed by the Brewfile (`cask "t3-code"`); to connect agents and set up
  providers, follow instructions in [setup_t3_code.md](./setup_t3_code.md)
