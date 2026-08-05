# Setup T3 Code

[T3 Code](https://t3.codes/) is an open-source (MIT) control plane for coding
agents — it orchestrates Claude Code, Codex, OpenCode, Cursor, and Grok from a
single interface, using your existing subscriptions/credentials (no token
reselling). Desktop apps for macOS/Windows/Linux plus iOS/Android companion
apps. Source: [github.com/pingdotgg/t3code](https://github.com/pingdotgg/t3code)

## Requirements

- Node.js `^22.16 || ^23.11 || >=24.10` (the Brewfile's `brew "node"` covers
  this)
- At least one coding agent CLI installed and authenticated (see below)

## Install (macOS)

Included in `app_lists/Brewfile`, so `brew bundle` installs it. To install
standalone:

```bash
brew install --cask t3-code
```

Alternative — run it without installing the desktop app (starts a local server
plus a web UI):

```bash
npx t3@latest
```

Other platforms: grab installers from the
[GitHub releases page](https://github.com/pingdotgg/t3code/releases), or the
[iOS](https://apps.apple.com/us/app/t3-code-remote-claude-more/id6787819824) /
[Android](https://play.google.com/store/apps/details?id=com.t3tools.t3code)
apps for remote control.

## New-Mac setup checklist

Ordered steps to bring a fresh Mac (e.g. the MacBook) to the same state as
Envy. Works for a human or for an agent driving the GUI with computer use —
agent-specific notes are marked **[agent]**. Details for each step live in
the sections below; this is the order that matters.

1. **Prereqs**: dotfiles + sibling credentials repos cloned, `claude`
   installed and authed (`claude auth login`), `gh` signed in to the
   personal account if this machine should have GitHub integration
   (`gh auth status` to check). **On a Mac, install T3 Code with brew** —
   `brew bundle` from `app_lists/Brewfile` (it's in there as
   `cask "t3-code"`), or standalone `brew install --cask t3-code`. Don't use
   the downloaded installer or `npx t3` on a Mac; brew keeps it tracked and
   updatable with everything else.
2. **Launch T3 Code once** ("T3 Code (Alpha)" in /Applications) so it creates
   `~/.t3/userdata/`. Expect the first-launch quirks below — **[agent]** if
   `ps aux` shows the process at 0.0% CPU with no helper processes and no
   window after ~10s, it is hung: kill it, clear the quarantine attr and the
   `Singleton*` files, and if `open -a` still hangs, exec the binary in
   `Contents/MacOS/` directly (all commands in the quirks section).
3. **Quit the app, then deploy the managed settings**:
   `uv run python src/deploy_configs.py` from the dotfiles repo. The
   `t3code_*` entries are gated on `~/.t3/userdata` existing, which is why
   the first launch comes first. Relaunch afterwards and the repo settings
   (providers, keybindings, UI prefs) are live — skip any in-app
   provider/keybinding configuration, it's already done.
4. **Verify providers and GitHub**: Settings (bottom-left) → **Providers**
   should list Claude; **Source Control** should show GitHub "Authenticated
   as" the personal account (click rescan if it doesn't). If the Claude row
   complains, the fix is CLI-side (`claude auth login`), not in the GUI.
5. **Add the remote environments** from the fleet table in the Environments
   section: Settings → **Connections** → Remote environments →
   **Add environment**. Pairings are per-machine — Envy's connections do not
   sync here, re-create them. **[agent]** dialog quirks: the dialog remembers
   the last-used card (Remote link vs SSH), so select the right card before
   typing; the suggested-hosts list under the SSH form shows tailnet
   `100.x` IPs from known_hosts — ignore them and type the LAN IP; Remote
   link hosts need an explicit `http://` prefix or the probe fails with
   "Transport error".
6. **(Optional) pair with Envy's own environment**: on Envy,
   Settings → Connections → **Create link**; on this Mac, Add environment →
   Remote link → paste the full pairing URL (it fills host + code). Codes
   are single-use — mint a fresh link per device. Envy must have the app
   open for its environment to be reachable.
7. **Verify**: each remote environment shows a green dot under
   Settings → Connections → Remote environments, and its projects/threads
   appear in the sidebar. **[agent]** a "Transport error" on a correct
   `http://` host usually means macOS blocked the app's LAN access — check
   System Settings → Privacy & Security → Local Network for "T3 Code
   (Alpha)" and have Jason approve it; the prompt only appears once. Better:
   pre-authorize the LAN subnet system-wide so the per-app prompt never
   gates connectivity (also documented in
   [setup_mac_workstation.md](./setup_mac_workstation.md)):

   ```bash
   sudo defaults write com.apple.network.local-network AllowedWiFiLocalNetworkAddresses -array "192.168.86.0/24"
   sudo defaults write com.apple.network.local-network AllowedEthernetLocalNetworkAddresses -array "192.168.86.0/24"
   ```

## Connect providers

Each agent needs its own CLI installed and authenticated **on the machine
running T3 Code** (not the browser/phone you control it from). Provider auth is
required before starting a session with that provider, not before starting T3
Code itself.

For Claude Code (already in the Brewfile as `cask "claude-code"`):

```bash
claude auth login
```

Then in T3 Code: **Settings → add/authenticate provider instances**. The
`claude` binary must be on `PATH`, or set an explicit binary path in Settings.
If auth fails at session start, the UI shows the login command to run.

Other providers (Codex, Cursor, Grok Build, OpenCode) follow the same pattern
with their own CLIs.

## First launch (macOS quirks seen on Envy, 2026-08-05)

Two things blocked the very first launch:

- The brew cask ships quarantined; if the Gatekeeper first-run dialog gets
  lost, the process hangs. `xattr -dr com.apple.quarantine "/Applications/T3
  Code (Alpha).app"` is equivalent to clicking Open once (the cask is
  notarized and checksum-verified by Homebrew).
- Killed launch attempts leave stale Electron singleton locks; remove
  `~/Library/Application Support/t3code/Singleton{Lock,Socket,Cookie}` before
  retrying.
- On the macOS 27 beta, launches via LaunchServices (`open -a`, Finder,
  Spotlight) sat frozen at `_dyld_start` with zero CPU, while executing
  `"/Applications/T3 Code (Alpha).app/Contents/MacOS/T3 Code (Alpha)"`
  directly started fine. Retest after OS/app updates.

## GitHub integration

There is no in-app OAuth or PAT field: T3 shells out to the **`gh` CLI on the
machine running the t3 server** and detects state with `gh auth status`. One
active account per environment — no multi-account UI. Setup here: Envy's `gh`
is signed in with the personal account, and T3 picked it up under
**Settings → Source Control** (rescan there if needed). Remote environments
each use their own machine's auth, so agents on work machines keep doing
GitHub through that context's normal token conventions — don't try to force a
second account through the GUI.

## Environments (multi-machine, LAN, no Tailscale)

One desktop UI drives several backends ("environments"); threads live on
whichever backend created them. Environments are added under
**Settings → Connections → Remote environments → Add environment**, using
plain LAN IPs — Tailscale is not required (T3 will suggest tailnet IPs it
finds in `~/.ssh/known_hosts`; ignore them).

Current fleet (2026-08-05):

| Environment | How | Notes |
|-------------|-----|-------|
| Envy (local) | implicit | The desktop app's own server. |
| Linux dev box | SSH card: LAN IP, user, port 22 | T3 starts/reuses a headless server on the remote over an SSH tunnel. |
| RyzenWhite | deferred | Windows: see below. |

Concrete LAN IPs and usernames are deliberately not listed here: look the
machine up in the `*_hosts.json` inventory of the sibling `*_credentials`
repo it belongs to (`hostname` + `user` fields).

**SSH environments (Linux/macOS remotes only).** Requirements on the remote:
Node `^22.16 || ^23.11 || >=24.10` resolvable from a *non-interactive* shell,
plus the agent CLIs (`claude`, ...) installed and authed there. The launcher
probes PATH then nvm/asdf/mise/fnm; on the Linux dev box the apt node was v18,
so Node 24 LTS was installed via the existing nvm and
`node`/`npm`/`npx` symlinked into `~/.local/bin` (already on the
non-interactive PATH). That prep is now scripted —
[`scripts/setup_t3_server_prereqs_linux.sh`](../scripts/setup_t3_server_prereqs_linux.sh)
(idempotent: checks the bare-PATH node version, installs Node 24 via nvm if
needed, links into `~/.local/bin`); run it on the remote from its dotfiles
clone. The remote server listens on loopback only; the desktop reaches it
through the SSH tunnel.

**Windows remotes: the SSH card does not work** — T3's remote launch scripts
are POSIX `sh` only. The intended workaround is a native server on the Windows
box paired as a **Remote link** — **but as of 2026-08-05 this is not working
yet on RyzenWhite** (see Known issues above); the steps below are the recipe
being attempted, not a verified setup. The whole recipe is scripted as
[`scripts/setup_t3_server_windows.ps1`](../scripts/setup_t3_server_windows.ps1)
— run it on the Windows box (fine over SSH: the serve runs as a logon
scheduled task, so it survives the session), and it finishes by minting a
single-use pairing code and printing it to the console it ran in; paste that
into the desktop's Remote-link dialog. Manual equivalent:

```powershell
npm install -g t3@<desktop version>   # done on RyzenWhite (matches 0.0.31)
t3 serve --host 0.0.0.0 --port 3773   # prints connection string + pairing token
```

Then on the desktop: Add environment → Remote link → Host
`http://<lan-ip>:3773` (the `http://` prefix matters — the dialog defaults to
https and fails with a transport error), pairing code from the serve output.
Caveat: a server started over SSH dies with the SSH session (Windows OpenSSH
kills the process tree), so for a persistent server register a logon task
once, from the Windows box itself:

```powershell
schtasks /Create /TN t3code-server /TR "C:\Users\jason\AppData\Roaming\npm\t3.cmd serve --host 0.0.0.0 --port 3773" /SC ONLOGON /F
schtasks /Run /TN t3code-server
```

Pairing codes are single-use; mint another with `t3 pair` for each new client
device.

## Settings (manifest-managed as of 2026-08-05)

`settings.json`, `client-settings.json`, and `keybindings.json` in
`~/.t3/userdata/` are deployed as symlinks from
`application_configs/t3code/` via the `t3code_*` entries in
`deploy_manifest.yaml` (gated on `~/.t3/userdata` existing, so machines
without T3 are skipped). The split:

| File | Manifest-worthy? | Why |
|------|------------------|-----|
| `settings.json` | yes | Provider instances, default model/effort. Has an `opencode.serverPassword` field — must stay empty in a public repo. |
| `client-settings.json` | yes | UI preferences (sidebar, diff, word wrap, ...). |
| `keybindings.json` | yes | Custom keybindings. |
| `desktop-settings.json` | no | Per-machine window bounds churn on every resize; also holds `serverExposureMode`. |
| `connection-catalog.json` | never | Per-machine registry of paired environments (an encrypted blob holding bearer tokens; named `saved-environments.json` in newer source). |
| `clerk-tokens.json`, `secrets/`, `state.sqlite`, `logs/`, `environment-id`, `server-runtime.json`, `~/.t3/caches/` | never | Auth tokens, signing keys, thread state — machine-private. |

Caveat (still true): Electron saves settings via atomic rename, which
replaces a deployed symlink with a plain file — expect `NOT_A_LINK` drift
after in-app settings changes. `deploy_configs.py status` catches it; merge
the in-app edit into the repo copy, then re-deploy to re-link (deploy backs
the machine file up to `data/config_backups/` first).

## Remote access from other devices

**Network access** is toggled on under Settings → Connections (stored as
`serverExposureMode` in the unmanaged `desktop-settings.json`), so other
devices on the LAN can pair with **Create link**. Environment pairings do NOT
sync between desktops — each client (laptop, phone) pairs itself:
SSH environments are re-added per machine, Remote-link environments need a
fresh single-use pairing code, and Envy's own environment is reachable only
while the desktop app is running (the backend is a child process; the
`t3 service install` background service is Linux-only). Once two clients are
connected to the same backend, threads and steering sync live in both
directions — the backend is event-sourced and clients are just subscribers.
Avoid composing into the *same running thread* from two machines at once
(composer drafts don't sync and pending turn-starts can stomp each other).
Tailscale HTTPS remains available for off-LAN use — see
[setup_tailscale.md](./setup_tailscale.md) — but is not part of this setup.

## Evaluation: what it replaces, and gaps before switching (as of 2026-07)

T3 is a candidate replacement for the **Claude desktop app** (agent session
management), NOT for VS Code — its editor pane is a viewer with a diff tab
(open via `Cmd+D` or the `+` tab button → Diff), not an editing environment.
So "no code cells" and "no inline completions" only disqualify it as an
editor, which it isn't trying to be. Keep VS Code for hand-editing (`# %%`
cells, Copilot-style completion).

Gaps that matter for replacing the Claude desktop app:

| Gap | Detail |
|-----|--------|
| Sessions are headless | T3 drives `claude` via the Agent SDK. Threads never appear in the Claude desktop/mobile apps, can't use Remote Control, and there is no TUI to `tmux attach` / jump back into from a terminal — T3's own desktop/phone apps are the *only* surface for its threads. |
| Desktop-app harness surfaces missing | Computer use (screenshots/GUI control), the in-app browser pane, claude.ai connectors (Gmail/Calendar MCP), artifacts, and the iOS simulator panel are Claude-desktop-app features and don't exist in T3 threads. CLAUDE.md, skills, auto-memory, and MCP servers configured in `~/.claude` DO apply, since it's the same `claude` binary. |
| No Anthropic cloud sessions | T3 can't spawn or steer sessions running in Anthropic's GitHub-repo sandbox; those are reachable only from Anthropic's own apps. |
| One serving machine | Everything a session touches (repo, agent CLI, auth) must exist on the machine whose t3 server owns the thread. |

## Multi-machine control surface (target setup)

Requirements: scale desktop → laptop → phone; three concurrent Claude Code
sessions — (1) local, (2) on a Linux SSH host natively, (3) local but in a
separate context targeting a locked-down Windows SSH host that must NOT have
Claude installed.

How T3 maps onto that:

- **Device scaling**: covered — network-accessible server + T3's phone/tablet
  apps over Tailscale (working today).
- **Local + Linux host**: covered by **environments** — one desktop UI, and an
  SSH-managed launch starts/reuses a headless t3 server on the remote (needs
  Node ≥22.16 plus `claude` installed and authed there; repos cloned there).
  Threads from both machines coexist as tabs in one window.
- **Windows-targeting session**: works the same as the general Claude Code
  pattern — the session runs on the *local* t3 server in its own project dir,
  edits locally, and executes remotely via a sync-and-run script over SSH
  (`rsync`/`scp` + `ssh ... powershell`), with the project CLAUDE.md pinning
  "never run locally". Nothing installs on Windows.
- **Unmet requirement**: "jump back into the session from a raw terminal."
  T3 threads are SDK-driven — there is no terminal attach. If that stays a
  hard requirement, the alternative surface is tmux-hosted `claude` sessions
  with Remote Control (phone/web via claude.ai; one connected session at a
  time) or a self-hosted web UI, at the cost of T3's side-by-side thread UI.

## Known issues & recommended fixes (as of 2026-08-05)

Running notes from daily use — each is either an upstream candidate
([github.com/pingdotgg/t3code](https://github.com/pingdotgg/t3code/issues)) or
a doc/automation task in this repo.

- **Settle button hit area (upstream)**: only part of the Settle button
  registers clicks, not the whole visible button. Fix: extend the click target
  to the full button bounds.
- **Finished threads can refuse to settle (upstream)**: some threads that are
  actually done won't settle because T3 still reports them as working, and the
  settle-error popup offers no way out. Fix: add a **Kill and settle** option
  to that error dialog so a stuck "working" state can be forced closed.
- **Projects don't show their machine (upstream)**: neither the sidebar nor
  the add-project wizard indicates which environment/machine a project runs
  on, so with several environments connected, same-named projects are
  indistinguishable. Fix: badge each project with its environment name in both
  places.
- **Same repo on two environments can't both be added (upstream)**: adding a
  project on a second environment silently does nothing when it matches an
  existing project on another machine — the project is never added. The
  dedup appears to be by repository identity, not (environment, path), so
  there is no workaround via distinct clone paths: the same repo with agents
  on two machines is simply not possible right now. This blocks the core
  multi-machine use case. Fix: key projects per-environment. Possibly related:
  `client-settings.json` has `sidebarProjectGroupingMode: "repository"` —
  worth testing whether a different grouping mode changes the behavior, but
  the add-wizard refusal suggests it's storage-level, not display-level.
- **New messages yank the scroll position (upstream)**: while scrolled up
  reading a thread's history, an incoming message auto-scrolls the view to
  the bottom. Fix: only auto-scroll when already at (or near) the bottom;
  otherwise keep the reading position and show a "new messages" jump pill.
- **Local Network permission is never requested (upstream)**: the app doesn't
  trigger macOS's Local Network prompt, so LAN connections just fail with
  "Transport error" and no hint that the OS permission is the cause. Fix:
  probe/request Local Network access on first LAN connection attempt and
  surface a pointed error. Workaround until then: the subnet pre-authorization
  in the new-Mac checklist above.
- **New SSH connections should offer a T3 connect method (upstream)**: when
  adding a new SSH connection, the wizard should prompt for a T3 connect
  method instead of silently assuming the SSH-tunnel launcher — e.g. offer
  SSH-managed launch vs Remote link pairing at that point.
- **Remote server install is undocumented / manual (upstream + this repo)**:
  what the SSH launcher actually installs and runs on the remote (the
  headless t3 server) isn't documented anywhere, and the prerequisites were
  hand-built here (Node 24 via nvm + `~/.local/bin` symlinks on the Linux dev
  box). Upstream fix: document the server install, or better, have the
  launcher verify/install Node and the server itself. This repo's side is now
  handled: `scripts/setup_t3_server_prereqs_linux.sh` automates the Linux
  prereqs and `scripts/setup_t3_server_windows.ps1` automates the (still
  unverified) Windows server recipe.
- **Windows remote host setup not working yet**: the Remote-link approach in
  the Windows section below has not succeeded on RyzenWhite yet — more
  attempts planned. Treat that section as the intended recipe, not a verified
  one, and keep the fleet table entry at "deferred" until it works.

## More docs

Full install/config docs live in the project repo:
[docs/user/install.md](https://github.com/pingdotgg/t3code/blob/main/docs/user/install.md)
