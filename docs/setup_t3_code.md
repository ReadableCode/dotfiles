# Setup T3 Code

[T3 Code](https://t3.codes/) is an open-source (MIT) control plane for coding
agents — it orchestrates Claude Code, Codex, OpenCode, Cursor, and Grok from a
single interface, using your existing subscriptions/credentials (no token
reselling). Desktop apps for macOS/Windows/Linux plus iOS/Android companion
apps. Source: [github.com/pingdotgg/t3code](https://github.com/pingdotgg/t3code)

## Requirements

- Node.js `^22.16 || ^23.11 || >=24.10` (the Brewfile's `brew "node"` covers
  this) — only for the headless `npx t3` / `t3 serve` paths; the desktop
  app is self-contained
- At least one coding agent CLI installed and authenticated (see below) —
  only on machines that *run* agents; a client-only viewer needs neither

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

## Install (Windows)

Desktop app via winget — never the website installer, so the package manager
tracks it like everything else (it's in
`app_lists/windows_apps_personal_winget.txt`):

```powershell
winget install T3Tools.T3Code
```

Headless server instead (the RyzenWhite pattern): don't install the desktop
app at all — run `scripts/setup_t3_server_windows.ps1`, which installs the
npm `t3` package pinned to the desktop version and registers the scheduled
task. See the Windows remotes section.

Phones: the
[iOS](https://apps.apple.com/us/app/t3-code-remote-claude-more/id6787819824) /
[Android](https://play.google.com/store/apps/details?id=com.t3tools.t3code)
apps for remote control. Linux desktop: installers on the
[GitHub releases page](https://github.com/pingdotgg/t3code/releases) (no
machine uses this yet).

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
5. **Sign into T3 Connect**: environments linked to the account (see the
   fleet table — e.g. RyzenWhite) appear on their own once the app is signed
   in; nothing to re-create per machine.
6. **Add any SSH-card environments** from the fleet table (e.g. the Linux
   dev box): Settings → **Connections** → Remote environments →
   **Add environment**. These pairings ARE per-machine — Envy's do not sync,
   re-create them. **[agent]** dialog quirks: the dialog remembers the
   last-used card, so select the SSH card before typing; the suggested-hosts
   list shows tailnet `100.x` IPs from known_hosts — ignore them and type
   the LAN IP.
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

## New Windows client-only machine checklist

For a Windows box that just runs the desktop app as a viewer/steering client
(no local agents, not reachable from other machines, sees only T3
Connect-linked environments). Much shorter than the Mac list:

1. **Install**: `winget install T3Tools.T3Code` (see Install (Windows) —
   never the website installer). Verify it grabbed the fleet's stable
   version, not a nightly — a 0.0.32 nightly is what left RyzenWhite's
   configs full of entries the 0.0.31 schema rejects. Expect a SmartScreen
   warning on first run of an unsigned alpha: More info → Run anyway.
2. **Launch once and sign into the T3 account** (Settings, bottom-left).
   T3 Connect-linked environments (see the fleet table) appear on their own
   with their projects and threads — no per-device pairing. Environments
   whose desktop-app backend is a child process (e.g. Envy) only show while
   that app is running. Tailscale-Serve machines (RyzenWhite) and SSH-card
   environments do NOT appear — those are per-client pairings; add them only
   if this machine actually needs them.
3. **Deliberately skip the rest**: no Node (desktop app is self-contained),
   no `claude` CLI (providers auth on the machine *running* the agent — just
   don't start local threads here), no T3 Connect publishing or
   `setup_t3_server_windows.ps1` (keeps the machine unreachable and burns no
   tunnel slot), no Network access toggle.
4. **Optional managed settings**: if the machine has a dotfiles clone, quit
   the app, `uv run python src/deploy_configs.py`, relaunch. Windows
   correctly resolves the bare server-safe config files, not the `.mac.json`
   variants. With no clone, in-app defaults are fine for a client-only box.
5. **Verify**: open a thread running on another environment and watch it
   stream; steering from here works (the backend is event-sourced, clients
   are subscribers). Don't compose into the same running thread from two
   machines at once.

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

## Environments (multi-machine)

One desktop UI drives several backends ("environments"); threads live on
whichever backend created them. Environments are added under
**Settings → Connections → Remote environments → Add environment**, using
plain LAN IPs — Tailscale is not required (T3 will suggest tailnet IPs it
finds in `~/.ssh/known_hosts`; ignore them).

**T3 Connect is the recommended way to attach a remote**: sign the remote's
server into the T3 account (`t3 connect link --headless` on the remote) and
it reaches the desktop through T3's relay — no pairing codes, no open ports
or firewall rules, and it works off-LAN. **Caveat: accounts get 3 managed
tunnels** (see Known issues); beyond that, expose the server with
`t3 serve --tailscale-serve` and pair it as a Remote link over the tailnet
(per-client pairing codes, no push notifications from that environment, but
no slot used). The SSH card remains as a LAN alternative for Linux/macOS
remotes.

Current fleet (2026-08-05):

| Environment | How | Notes |
|-------------|-----|-------|
| Envy (local) | implicit | The desktop app's own server. |
| Linux dev box | SSH card: LAN IP, user, port 22 | T3 starts/reuses a headless server on the remote over an SSH tunnel. |
| RyzenWhite | Remote link over Tailscale Serve | Windows: native server; T3 Connect blocked by the 3-tunnel cap. See below. |

Concrete LAN IPs and usernames are deliberately not listed here: look the
machine up in the `*_hosts.json` inventory of the sibling `*_credentials`
repo it belongs to (`hostname` + `user` fields).

**Slot policy**: the 3 T3 Connect tunnel slots go to the most-used machines,
because only relay-linked environments send push notifications and Live
Activities to the phone. Least-used machines (RyzenWhite) ride Tailscale
Serve instead. Mixing transports is fine — the connection method is
per-environment plumbing and threads behave identically once connected.

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
are POSIX `sh` only. Set the machine up as a native server instead, scripted
end-to-end as
[`scripts/setup_t3_server_windows.ps1`](../scripts/setup_t3_server_windows.ps1)
(run on the Windows box, fine over SSH). What it does:

1. Verifies Node, installs `t3@<desktop version>` globally.
2. Registers and starts a `t3code-server` **scheduled task** (boot + logon
   triggers) running `t3 serve` — a serve started in an SSH session dies
   with it, Windows OpenSSH kills the process tree. Loopback only: both
   reachability paths dial loopback, so no `0.0.0.0` bind and no firewall
   rule.
3. Reachability, default **Tailscale Serve**: the serve runs with
   `--tailscale-serve` (HTTPS on the tailnet, needs tailscale logged in on
   the box) and the script prints the tailnet URL plus a single-use pairing
   token. On each client: Add environment → Remote link →
   `https://<machine>.<tailnet>.ts.net` + token. Mint a token per client —
   over SSH is fine, no desktop session needed:
   `t3 auth pairing create` (single-use, short-lived;
   `t3 auth pairing list`/`revoke` to manage). Note there is no `t3 pair`
   command despite older docs: bare `t3 <word>` treats the word as a cwd and
   silently starts a stray server. Alternative, `-T3ConnectLink`: interactive OAuth
   (`t3 connect link --headless` — open the printed URL, paste the code
   back exactly as displayed, then the task restarts to activate it). Uses
   a managed-tunnel slot; see the 3-tunnel cap in Known issues.

RyzenWhite runs the Tailscale path (2026-08-05, working: desktop pairs over
the tailnet URL). Windows task specifics baked into the script: the
principal is **S4U** (a default-principal task silently never starts when no
one is logged on, `LastTaskResult` 267011), and the serve line lives in
`~\.t3\t3serve.cmd` because a redirect inside the task's argument string
gets eaten by quoting. A T3 Connect credential is also stored there
("Authorized as" the account), so if a tunnel slot ever frees up,
`t3 connect link` + a task restart flips it to the relay with no new OAuth.

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

**Platform variants (2026-08-05)**: all three files exist as a `*.mac.json`
variant plus a bare default. Macs auto-resolve the mac variant; Windows and
Linux (both running the npm `t3` server) fall through to the bare file,
which must stay within what that pinned server version's schema accepts —
the server hard-warns on unknown keys/commands ("ignoring invalid keybinding
entry" in `~/.t3/server.log`, surfaced as config-issue warnings in connected
clients). Merge Envy's in-app edits into the `*.mac.json` files only, and
promote settings to the bare files only after confirming the npm build
accepts them.

## Remote access from other devices

Preferred path: sign every client (laptop, phone) into the same **T3
account** — T3 Connect-linked environments appear on each of them with no
per-device pairing. Only SSH-card environments are re-added per machine.
LAN **Create link** pairing still exists for account-less one-offs (requires
Network access toggled on under Settings → Connections, stored as
`serverExposureMode` in the unmanaged `desktop-settings.json`). Envy's own
environment is reachable only while the desktop app is running (the backend
is a child process; the `t3 service install` background service is
Linux-only). Once two clients are connected to the same backend, threads and
steering sync live in both directions — the backend is event-sourced and
clients are just subscribers.
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
| T3 Connect tunnel cap | Accounts get **3 managed tunnels**, counted against *published environments* — the local desktop's own published environment occupies a slot, so the dashboard's remote-environments list understates usage (it looks like 2 when all 3 are taken). The headless CLI surfaces a refusal only as a bare `403` with no message; the desktop dialog shows the real reason. Machines beyond the cap pair over Tailscale Serve instead — full thread functionality, but no push notifications or Live Activities from those environments. |

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

- **No verbose transcript view (upstream)**: T3 has no equivalent of Claude
  Code's verbose mode — tool calls render as truncated summaries with no
  setting, keybinding command, or provider option to expand them (confirmed
  against the 0.0.31 schemas: client-settings, server settings, claudeAgent
  provider config, and the keybinding command enum have nothing). The
  `verbose`/`viewMode` keys in `~/.claude/settings.json` only affect the
  Claude Code CLI/desktop TUI; T3 already launches `claude` with
  `--verbose --output-format stream-json` and does its own rendering, so
  the data is there — the UI just never shows it. Also verified absent in
  the latest nightly (`t3@0.0.32-nightly.20260805.1008`: client settings
  gained font options, nothing transcript-related), so upgrading doesn't
  help. Fix: an upstream transcript view-mode toggle (default/verbose) like
  Claude Code's — since threads store the full stream-json, it should apply
  retroactively to existing threads. Interim: click individual tool cards
  to expand them, or run `claude` in T3's terminal panel (`mod+j`) where
  `~/.claude/settings.json` `verbose: true` applies.
- **Links in responses aren't clickable (upstream)**: URLs in assistant
  responses render as plain text — no way to open one without selecting and
  copying it by hand (extra painful on the phone apps). Fix: linkify URLs
  (and markdown links) in the transcript renderer and open them in the
  system browser.
- **npm server rejects newer config than its pinned version (this repo,
  handled)**: the headless `t3` server schema-validates managed configs and
  warns on anything a newer build wrote — RyzenWhite's `server.log` spammed
  "ignoring invalid keybinding entry" for `filePicker.toggle` /
  `projectSearch.toggle`, leftovers from the 0.0.32 nightly's default
  keybindings after the downgrade to 0.0.31. Handled by the platform
  variant split in the Settings section (bare files stay server-safe);
  deploying to RyzenWhite replaces the stale file and clears the warnings.
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
  **Working workaround (2026-08-05)**: add the *parent* workspace folder
  (e.g. `~/GitHub`) as the project instead of the repo — a non-repo
  directory has no repository identity, so the dedup never fires and each
  machine gets its own project over the same repos. Combine with the naming
  convention below.
- **Workaround for the missing environment badges**: prefix project names
  with the machine (`RW-GitHub`, `Envy-GitHub`) when adding/renaming, so
  same-named projects on different environments stay distinguishable in the
  sidebar and in the new-chat picker.
- **iOS app misses new threads until relaunch (upstream)**: a thread created
  from another client on a connected environment didn't appear on the
  iPhone until the app was killed and reopened; after relaunch it showed and
  synced normally (seen 2026-08-05 on a Tailscale-paired environment). Fix:
  resubscribe/refresh thread lists when the app foregrounds instead of only
  at launch.
- **Slash commands don't auto-suggest on mobile (upstream)**: typing `/` in
  the composer on the phone apps shows no suggestion popup and no
  autocompletion — the full command name must be typed from memory, unlike
  the desktop app. Fix: bring the desktop slash-command picker to the mobile
  composer.
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
  method instead of silently assuming the SSH-tunnel launcher — i.e. offer
  T3 Connect linking at that point.
- **Remote server install is undocumented / manual (upstream + this repo)**:
  what the SSH launcher actually installs and runs on the remote (the
  headless t3 server) isn't documented anywhere, and the prerequisites were
  hand-built here (Node 24 via nvm + `~/.local/bin` symlinks on the Linux dev
  box). Upstream fix: document the server install, or better, have the
  launcher verify/install Node and the server itself. This repo's side is now
  handled: `scripts/setup_t3_server_prereqs_linux.sh` automates the Linux
  prereqs and `scripts/setup_t3_server_windows.ps1` automates the Windows
  server + T3 Connect link setup.
- **T3 Connect: 3 managed tunnels per account, and the CLI hides the error
  (root cause found 2026-08-05)**: the mystery relay `403 POST
  /v1/client/environment-links` on RyzenWhite was the account's tunnel cap —
  the desktop's Set up T3 Connect dialog shows the real message ("this
  account already has its maximum of 3 managed tunnels. Unlink an
  environment to free one up"), while the headless CLI logs only a bare 403
  (upstream ask: surface the relay's error body). The three slots here:
  Envy's published environment plus the two laptop environments. The cap
  counts *published environments*, not the remote-environments list in the
  dashboard — which is why it looks like only two. Workaround in use for
  RyzenWhite: `t3 serve --tailscale-serve` + Remote link over the tailnet
  (no slot consumed; see Windows remotes section). Debugging breadcrumbs
  kept: auth codes are genuinely issued uppercase (a re-cased code 400s at
  token exchange — enter exactly as displayed); the 0.0.32 nightly never
  attempts the reconcile at all; upstream issue creation is restricted, so
  report via their Discord.

## More docs

Full install/config docs live in the project repo:
[docs/user/install.md](https://github.com/pingdotgg/t3code/blob/main/docs/user/install.md)
