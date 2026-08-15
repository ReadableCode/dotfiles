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

## Server version

**Headless servers install unpinned**, same as the desktop app: `t3@latest`
on both paths (`setup_t3_server_windows.ps1` defaults `-Version` to it, the
Linux prereq script prints `npx -y t3@latest service install`). No file in
this repo names a server version, so nothing here can go stale — the Windows
installer's old hardcoded `0.0.31` (2026-07-29) was two releases behind the
0.0.33 the fleet moved to on 2026-08-14 and would have *downgraded*
RyzenWhite on the next run, back into the keybinding rejections below.

`latest` is npm's **stable** tag. Nightlies ship under a separate `nightly`
tag and are never resolved by `@latest` — the 0.0.32 nightly that filled
RyzenWhite's configs with entries the server then rejected (see Known issues)
came from a desktop install that grabbed a nightly build, not from a floating
npm server install.

**The one coupling to watch.** The deployed bare `keybindings.json` in
`application_configs/t3code/` carries some server version's default bindings.
A server **older** than that logs `ignoring invalid keybinding entry`; a
**newer** one merges its own defaults in and replaces the deployed symlink
with a plain file (`NOT_A_LINK` in `deploy_configs.py status`). So the bare
file tracks the **oldest server running anywhere**:

1. roll every server up (Windows: re-run the installer; Linux:
   `npx -y t3@latest service update`),
2. only then promote new default bindings into the bare file,
3. after any server install, check that box's boot log for
   `ignoring invalid keybinding entry`.

Because installs float, a machine that hasn't been touched in months is the
one that falls behind — re-run the installer on the quiet boxes before step 2,
or hold a machine deliberately with an explicit `-Version` / `t3@<version>`.
`keybindings.mac.json` is a separate track (the desktop app's version).

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
npm `t3` package (unpinned — see [Server version](#server-version)) and
registers the scheduled task. See the Windows remotes section.

Phones: the
[iOS](https://apps.apple.com/us/app/t3-code-remote-claude-more/id6787819824) /
[Android](https://play.google.com/store/apps/details?id=com.t3tools.t3code)
apps for remote control. Linux desktop: installers on the
[GitHub releases page](https://github.com/pingdotgg/t3code/releases) (no
machine uses this yet — the Linux boxes run the headless server below).

## Install (Linux) — always-on server via systemd

Linux is the **only** platform with a real background service: `t3 service
install` writes a systemd **user** unit and turns lingering on, so the server
starts at boot and keeps running with nobody logged in. No desktop app, no
scheduled-task workaround like Windows needs, and unlike a `serve` started
over SSH it doesn't die with the session.

Done on JasonZephyrus (Fedora 43) 2026-08-14.

```bash
# 1. prereqs (node in range + a C++ toolchain — see the node-pty trap below)
./scripts/setup_t3_server_prereqs_linux.sh

# 2. install the service (the prereq script prints this line too)
npx -y t3@latest service install

# 3. verify all three properties that make it "always on"
systemctl --user is-active t3code.service     # active
systemctl --user is-enabled t3code.service    # enabled  -> starts at boot
loginctl show-user "$USER" -p Linger          # Linger=yes -> without a login
```

`service install` sets up all three itself (including `loginctl
enable-linger`); there is nothing to enable by hand. Management is
`systemctl --user {status,restart} t3code.service` — **never** `sudo
systemctl`, it's a user unit. Logs go to
`~/.t3/userdata/logs/boot-service.log`, and updates use
`npx -y t3@<version> service update` (**not** the panel's copy-update
command — see [Updating a service-managed Linux
server](#updating-a-service-managed-linux-server-2026-08-11)).

What it writes, as of 0.0.33 — worth knowing before hand-editing anything:

```ini
# ~/.config/systemd/user/t3code.service
Environment=T3CODE_HOME=/home/<user>/.t3
ExecStart=/usr/bin/node-22 /home/<user>/.t3/runtime/service-launcher.mjs
Restart=always
RestartSec=5
StandardOutput=append:/home/<user>/.t3/userdata/logs/boot-service.log
WantedBy=default.target
```

`ExecStart` points at the version-agnostic `service-launcher.mjs` (the runtime
itself lives in `~/.t3/runtime/versions/<version>/`), so `service update`
swaps versions without rewriting the unit. The server binds **loopback only**
(`127.0.0.1:3773`) — no `0.0.0.0` bind, no firewall rule; every reachability
path below dials loopback. The connection string and a pairing token are
printed into the boot log once it's ready.

### Trap 1: `~/.local/bin` is not on a systemd user service's PATH

The user manager's PATH is just `/usr/local/bin:/usr/bin`. Services source no
shell rc, so **`claude` installed at `~/.local/bin/claude` is invisible to the
service** even though it works fine in your terminal — threads then fail at
session start, having looked healthy up to that point. Fix with a drop-in
(not an edit to the unit, so `t3 service update` can't clobber it):

```bash
mkdir -p ~/.config/systemd/user/t3code.service.d
cat > ~/.config/systemd/user/t3code.service.d/10-path.conf <<'EOF'
[Service]
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin
EOF
systemctl --user daemon-reload && systemctl --user restart t3code.service
```

Verify it took — check the *process*, not your shell:

```bash
tr '\0' '\n' < /proc/$(systemctl --user show t3code.service -p MainPID --value)/environ | grep ^PATH=
```

`~/.config/environment.d/*.conf` is the machine-wide alternative, but note it
is read only when the user manager *starts*: neither `daemon-reload` nor
`daemon-reexec` re-imports it (re-exec deliberately preserves the existing
environment), so it appears to do nothing until the next login. The drop-in
applies immediately, which is why it's the documented fix here.

### Trap 2: node-pty has no linux-x64 prebuild

The npm `t3` package depends on node-pty, which npm compiles from source. On
Fedora that fails — `gcc` ships, the C++ compiler does not — and the failure
mode is nasty: `make ... Error 127`, after which **`npx t3 ...` exits 1
printing absolutely nothing**, which reads like a broken network rather than a
missing package. `sudo dnf install -y gcc-c++ make` (Debian:
`build-essential`). `setup_t3_server_prereqs_linux.sh` now checks for this;
it's also in the Fedora package line in
[setup_linux_workstation.md](./setup_linux_workstation.md).

### Managed settings

`~/.t3/userdata/` only exists after the service has started once, and the
`t3code_*` manifest entries are gated on it — so deploy **after** the install,
then restart to pick the files up:

```bash
uv run python src/deploy_configs.py
systemctl --user restart t3code.service
```

The host must be in the `user_t3code_settings` hosts list in
`personal_manifest.yaml` or `settings.json` is skipped (the other two files
deploy for everyone). Confirm all three landed as symlinks with
`ls -l ~/.t3/userdata/*.json`, and check the boot log for "ignoring invalid
keybinding entry" — the bare (non-`.mac`) files must stay within the pinned
server's schema.

**The headless server breaks the keybindings symlink too** (JasonZephyrus,
2026-08-14). The `NOT_A_LINK` drift documented under Settings is not
desktop-only: on first start the **0.0.33 headless server** merged its own
defaults into `keybindings.json` and saved, replacing the deployed symlink
with a regular file. It writes once — a file that already contains the
defaults survives later restarts — so this is a one-shot on a fresh install,
not a loop, but `deploy_configs.py status` reports `NOT_A_LINK` until it's
resolved.

The three commands it added were the catch:
`filePicker.toggle`, `projectSearch.toggle`, `themeEditor.toggle` — the first
two are exactly what **0.0.31 rejected** with "ignoring invalid keybinding
entry" (see Known issues; that's why they were stripped from the bare file in
the first place). Simply re-deploying would have handed 0.0.33 a file it
rewrites again, so the bare file had to move up with the servers.

**Resolved 2026-08-14**: the three bindings are now in the bare
`keybindings.json` and the fleet's servers moved to 0.0.33 together. Restart
after re-deploying and the server leaves the file alone — verified here: the
symlink survives restarts and the boot log is free of keybinding warnings.
The lesson generalizes — **the bare file tracks the lowest server version
deployed anywhere**, so bump the servers first and promote new default
bindings second. `keybindings.mac.json` is a separate track (the desktop
app's version) and was deliberately left alone.

### Reachability: Tailscale Serve on the boot service

A service-managed box is loopback-only and linked to nothing by default. Only
**T3 Connect** (`t3 connect link`) consumes one of the account's 3 managed
tunnels — **Remote link pairing is token-based, unlimited, and never touches
the T3 account**, so a full tunnel cap does not block anything here. Same
choice RyzenWhite made, for the same reason.

**Serve flags reach the service only through the environment.** The Linux
service launcher spawns `serve` with **no arguments** and there is no wrapper
script to edit (the Windows setup's `~\.t3\t3serve.cmd` trick has no
equivalent). It does pass its own environment through, and every `serve` flag
has a `T3CODE_*` twin — `T3CODE_TAILSCALE_SERVE`,
`T3CODE_TAILSCALE_SERVE_PORT`, `T3CODE_HOST`, `T3CODE_PORT`,
`T3CODE_MODE`. So configuration is a drop-in:

```bash
cat > ~/.config/systemd/user/t3code.service.d/20-tailscale-serve.conf <<'EOF'
[Service]
Environment=T3CODE_TAILSCALE_SERVE=true
EOF
systemctl --user daemon-reload && systemctl --user restart t3code.service
```

Parsed by Effect's `Config.boolean`, so `true`/`1`/`on` all work. Use
`T3CODE_HOST=0.0.0.0` instead for a plain LAN bind (then open the port in
firewalld — Tailscale Serve needs no firewall rule, since it proxies from
loopback).

**`tailscale serve` needs an operator grant.** It is a state-changing command,
so as a normal user it fails and the server logs a `WARN ... Failed to
configure Tailscale Serve` with `stderrDiagnostic: 'permission-denied'` —
while otherwise starting up fine, so it's easy to miss. Run once:

```bash
sudo tailscale set --operator=$USER
```

Don't "fix" it by running the service as root: `~/.local/bin/claude`, `~/.t3`,
and the deployed dotfiles symlinks are all user-owned. Windows never hits this
because its scheduled task runs with different privileges. On success the log
line becomes `INFO ... Tailscale Serve configured`, and
`tailscale serve status` shows the proxy:

```
https://<machine>.<tailnet>.ts.net (tailnet only)
|-- / proxy http://127.0.0.1:3773
```

**The first HTTPS request fails**, because Tailscale provisions the
Let's Encrypt cert on demand — curl reports exit 35 / `HTTP 000`. Retry a few
seconds later and it's a normal `HTTP 200`; nothing is wrong.

**`serve` is tailnet-only; `funnel` is the public one.** They are sibling
commands with near-identical syntax, and only `tailscale funnel` puts a
machine on the public internet. Nothing here uses Funnel. Confirm exposure by
looking at what is actually bound rather than trusting the config — the `443`
listener should carry the **tailnet IP**, never `0.0.0.0`, and the t3 server
itself should stay on loopback:

```console
$ ss -tlnp | grep -E '3773|443'
LISTEN 0 4096   <tailnet-ip>:443     0.0.0.0:*      # tailnet IP only, not 0.0.0.0
LISTEN 0  511      127.0.0.1:3773    0.0.0.0:*      # t3, loopback only
$ tailscale serve status                                 # says "(tailnet only)"
```

Note that "tailnet only" means *the whole tailnet*, which includes any nodes
**shared in from another account** — this tailnet has several. If a machine
shouldn't reach these servers, that's an ACL question in the Tailscale admin
console, not something the serve config controls. The Let's Encrypt cert also
means the machine name appears in public Certificate Transparency logs; the
service behind it stays unreachable.

Then pair each client — **mint one token per client**, and note the TTL is
about **five minutes**, so mint it when you're actually sitting at the client:

```bash
t3 auth pairing create      # single-use; also `pairing list` / `pairing revoke`
```

Desktop: Add environment → **Remote link** → the `https://` tailnet URL + the
token. There is no `t3 pair` command despite older docs — bare `t3 <word>`
treats the word as a cwd and silently starts a stray server.

Reboot persistence is three independent things; check all three, since any one
of them silently breaks "always on":

```bash
systemctl is-enabled tailscaled                # tailnet comes back
systemctl --user is-enabled t3code.service     # unit comes back
loginctl show-user "$USER" -p Linger           # ...without a login
```

**Don't also use the SSH card on a service-managed box.** They are two
different servers: the launcher in `~/.t3/ssh-launch/*/run-t3.sh` prefers a
`t3` on PATH and otherwise runs `npx t3@<version>`, starting a server of its
own — the same "second server" hazard as the copy-update-command bug above.

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
   never the website installer). Verify it grabbed the stable release,
   not a nightly — a 0.0.32 nightly is what left RyzenWhite's
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

### Claude Code on Bedrock (2026-08-06)

On a machine where Claude Code authenticates through Bedrock rather than a
Claude subscription — `CLAUDE_CODE_USE_BEDROCK=1` plus `AWS_PROFILE` /
`AWS_REGION` / `ANTHROPIC_MODEL` in the `env` block of
`~/.claude/settings.json` — the interactive CLI works but **every T3 turn
fails**. Nothing is wrong with the auth: T3 spawns that same CLI and the CLI
reads that same settings file. The breakage is the two per-thread values T3
asserts *on top of* the config, both first-party-only concepts that
`settings.json` cannot override. See Known issues for the upstream detail;
this is the procedure.

**Symptoms, in the order you hit them**

| Symptom | Cause |
|---------|-------|
| `Provider turn start failed · turn/setPermissionMode failed`, turn dies before any model call | thread permission mode is **Auto** |
| `API Error (claude-opus-5): 400 The provided model identifier is invalid` | picker sent a first-party slug as `--model` |
| the Bedrock model isn't in the picker to select | `customModels` has no UI — see below |

**1. Permission mode — per thread, no config.** Set the thread's permission
dropdown to anything except Auto. T3 maps Auto to SDK
`permissionMode: "auto"`, which Claude Code refuses for non-first-party
providers, so the control request T3 sends at every turn start is rejected.
`"CLAUDE_CODE_ENABLE_AUTO_MODE": "1"` in the settings `env` block is the
durable version, but a second per-model gate may still block it for
inference-profile IDs — the dropdown is the reliable fix.

**2. Model — needs a `settings.json` edit.** The picker sends slugs like
`claude-opus-5` as `--model`, which beats `ANTHROPIC_MODEL`. Register the
inference profile as a custom model in the *T3 server* settings
(`~/.t3/userdata/settings.json`, not `~/.claude/settings.json`):

```json
{
  "textGenerationModelSelection": {
    "instanceId": "claudeAgent",
    "model": "<region>.anthropic.<model>-v1:0",
    "options": []
  },
  "providerInstances": {
    "claudeAgent": {
      "driver": "claudeAgent",
      "enabled": true,
      "config": {
        "enabled": true,
        "binaryPath": "claude",
        "homePath": "",
        "launchArgs": "",
        "customModels": ["<region>.anthropic.<model>-v1:0"]
      }
    }
  }
}
```

`customModels` is real and the server reads it, but its schema marks it
`providerSettingsForm: { hidden: true }` and leaves it out of the form
`order` — **no UI can set it**, which is what makes this look unfixable from
inside the app. Notes on that block:

- `textGenerationModelSelection` is separate and easy to miss: it drives the
  `claude -p --model ...` calls behind commit messages and thread titles, so
  it needs the profile ID too or those keep 400ing after threads work.
- `options: []` is right for a custom model. Custom models resolve to empty
  capabilities, so T3 stops appending the `[1m]` suffix and `--effort` for
  them — and their effort / context-window dropdowns disappear in the UI.
  That's the trade for using Bedrock here.
- This writes an explicit `claudeAgent` providerInstance where the instance
  was previously implicit. Watch the provider list on first deploy.
- Model IDs pass through `normalizeCustomModelSlug`, which only trims, so
  the dots and colons survive intact. It's an array — list several profiles
  if more than one is enabled.

**Where the file comes from.** Bedrock config must not reach the personal
machines, so such a host gets its own `settings.json` from its context
manifest instead of the shared one (Settings section below). A host variant
`t3code/settings.<host>.json` in that context's credentials repo auto-resolves
for that machine; other hosts on the same entry fall through to the bare
`t3code/settings.json` beside it.

**Applying it**, on the machine running the server:

```bash
git -C <dotfiles> pull && git -C <context credentials repo> pull
uv run python src/deploy_configs.py            # from the dotfiles checkout
ls -l ~/.t3/userdata/settings.json             # confirm it points at the variant
systemctl --user restart t3code.service        # if installed as a boot service
```

Then per thread: permission dropdown off Auto, model picker → the inference
profile. If the model isn't listed after the restart, that pinned server
build predates `customModels` on the Claude driver (check `~/.t3/server.log`
for a config-issue warning); fall back to putting
`--model <region>.anthropic.<model>-v1:0` in the provider's **Launch
arguments** field, which *is* in the UI. Those parse into the SDK's
`extraArgs` and are appended after T3's own `--model`, so the last one wins.
Only safe once that host owns its own settings file — otherwise the write
lands in the shared one.

**Also check `~/.claude/settings.json`** on that machine: a top-level
`"model"` key (e.g. `"opus[1m]"`) beats `env.ANTHROPIC_MODEL`, so any CLI
invocation without an explicit `--model` still resolves to a first-party
alias Bedrock rejects. Drop it or set it to the inference profile.

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

Current fleet (2026-08-14):

| Environment | How | Notes |
|-------------|-----|-------|
| Envy (local) | implicit | The desktop app's own server. |
| Linux dev box | SSH card: LAN IP, user, port 22 | T3 starts/reuses a headless server on the remote over an SSH tunnel. |
| RyzenWhite | Remote link over Tailscale Serve | Windows: native server; T3 Connect blocked by the 3-tunnel cap. See below. |
| JasonZephyrus | Remote link over Tailscale Serve | Fedora 43: systemd boot service (`t3 service install`), not the SSH card. See [Install (Linux)](#install-linux--always-on-server-via-systemd). |

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
needed, links into `~/.local/bin`, and installs a C++ toolchain if none is
present — node-pty builds from source); run it on the remote from its dotfiles
clone. The remote server listens on loopback only; the desktop reaches it
through the SSH tunnel.

**Windows remotes: the SSH card does not work** — T3's remote launch scripts
are POSIX `sh` only. Set the machine up as a native server instead, scripted
end-to-end as
[`scripts/setup_t3_server_windows.ps1`](../scripts/setup_t3_server_windows.ps1)
(run on the Windows box, fine over SSH). What it does:

1. Verifies Node, installs `t3@latest` globally and prints the version it
   resolved (see [Server version](#server-version)).
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

## Updating a service-managed Linux server (2026-08-11)

When a T3 Connect Linux environment runs as the background service
(`t3 service install` → systemd user unit `t3code.service`), the desktop
panel eventually shows **"Server update available"** with a
**Copy update command** button. The command it gives is just
`npx t3@<version>` — **do not run it as-is**. That is the *run* command for
the new version, not an updater:

- It starts a second t3 server in the foreground of whatever shell runs it,
  which re-points the managed relay tunnel's ingress at its own ephemeral
  port (the tunnel follows the newest server).
- Ctrl+C'ing it then strands the relay proxying into a dead port: the panel
  shows "Failed to connect … Relay environment endpoint is unavailable"
  while `systemctl --user status t3code` still says active/running. The
  smoking gun in `~/.t3/userdata/logs/boot-service.log` is cloudflared
  spamming `ERR … dial tcp 127.0.0.1:<port>: connect: connection refused` —
  the same dead-origin class as Envy's exposure-port mismatch, but with no
  exposure toggle here to re-kick it.

**Recovery** from that state: `systemctl --user restart t3code.service`.
The restart re-spawns cloudflared against the service's own port. Expect
1–2 minutes of `CRYPTO_ERROR 0x178 … tls: no application protocol` QUIC
retries in the log before it falls back to http2 and registers **4 tunnel
connections** — that's the ready signal (same readiness behavior as Envy).

**The correct update command** (the CLI has a real updater, the panel just
doesn't surface it):

```bash
npx -y t3@latest service update
```

The version the panel names works here too; what matters is the
`service update` verb, not the tag. It installs the
runtime under `~/.t3/runtime/versions/<version>`, rewrites
the unit, and restarts the service — sessions on the box restart with it.
As of 0.0.33 the rewrite also switches `ExecStart` from a version-pinned
runtime path to the version-agnostic `~/.t3/runtime/service-launcher.mjs`,
so future updates shouldn't need to touch the unit at all. Verify with
`systemctl --user status t3code` (the serve process's path shows the
running version) and wait for the 4 registered connections in
`boot-service.log`; the panel then goes green and the update banner clears.

## Settings (manifest-managed as of 2026-08-05)

`settings.json`, `client-settings.json`, and `keybindings.json` in
`~/.t3/userdata/` are deployed as symlinks from
`application_configs/t3code/` (gated on `~/.t3/userdata` existing, so machines
without T3 are skipped). `client-settings.json` and `keybindings.json` deploy
from the `t3code_*` entries in `deploy_manifest.yaml`; **`settings.json`
deploys from `user_t3code_settings` in `personal_manifest.yaml`** as of
2026-08-06 — the file is still the public one in this repo, but the entry
needs a hosts whitelist so a client context can point the same dest at its own
copy (hosts filters are overlay-manifest-only). Work machines get their
`settings.json` from their own context manifest instead — see
[Claude Code on Bedrock](#claude-code-on-bedrock-2026-08-06) for the case that
forced the split. Adding a personal T3 machine means adding it to that entry's
hosts list. The split:

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
Linux-only — it installs a systemd **user** unit `t3code.service` plus
`loginctl enable-linger`, so managing it is `systemctl --user
{status,restart} t3code.service`, never `sudo systemctl`). Once two clients
are connected to the same backend, threads and
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

## Known issues & recommended fixes (as of 2026-08-06)

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
- **Background commands can't be watched live, from inside or outside T3
  (upstream, 2026-08-06)**: when a thread launches a long-running command in
  the background, the thread shows only a collapsed Work Log card
  ("Background command ... ") — there is no live output pane, so the only way
  to see progress is to ask the thread to poll it and wait for the reply. It
  can't be watched from outside either: the background shell belongs to the
  `claude` process T3 spawned for that thread, and `BashOutput` / `/bashes`
  only work inside the owning session, so another Claude Code session (CLI,
  desktop, or a second T3 thread) can't attach. Resuming the session id in a
  new process does not restore background shells — the old process owns them
  until it exits. Fix: stream background-command output into an expandable
  live pane (the data is already in the stream-json). Workarounds, best
  first: (1) have the script write its own log (`./run.sh > /tmp/run.log
  2>&1 &`) so any session, terminal, or machine can `tail -f` it;
  (2) ask the owning thread to check; (3) read the raw transcript — map
  thread → Claude session with
  `sqlite3 -readonly ~/.t3/userdata/state.sqlite "select thread_id, status,
  json_extract(resume_cursor_json,'$.resume') as session_id,
  json_extract(runtime_payload_json,'$.cwd') as cwd from
  provider_session_runtime order by last_seen_at desc limit 5;"`, then
  `tail -f ~/.claude/projects/<cwd-slug>/<session_id>.jsonl` to see the tool
  calls and every polled output the thread has captured.
- **File preview stops at the first 1 MB, with no tail (upstream,
  2026-08-06)**: opening a large file in the side pane shows
  "Preview limited to the first 1 MB of a *N* byte file" (seen on a ~120 MB
  run log) and there is no way to seek to the end, follow the tail, or load
  the next chunk — so for a growing log, the one part that matters (the last
  lines) is the one part the viewer can't reach. This makes the file pane
  useless as a substitute for the missing live output above. Fix: a tail/
  follow mode, or at minimum a "jump to end" that loads the final 1 MB.
  Workaround: `tail -f` the file in the terminal panel (`mod+j`) or from any
  shell on that machine.
- **Links in responses aren't clickable (upstream)**: URLs in assistant
  responses render as plain text — no way to open one without selecting and
  copying it by hand (extra painful on the phone apps). Fix: linkify URLs
  (and markdown links) in the transcript renderer and open them in the
  system browser.
- **Bedrock-authed machines: T3 overrides the two things `settings.json`
  can't win (upstream + this repo, handled 2026-08-06)**: on a machine where
  Claude Code authenticates through Bedrock
  (`CLAUDE_CODE_USE_BEDROCK=1` in `~/.claude/settings.json`), the interactive
  CLI works but every T3 turn fails. T3 does spawn that CLI and the CLI does
  read its own settings — the problem is the two per-thread values T3 layers
  on top, both of which are first-party-only concepts.
  1. **Permission mode.** T3 maps its Auto runtime mode to SDK
     `permissionMode: "auto"`; Claude Code disables auto mode for
     non-first-party providers ("auto mode disabled: provider bedrock
     requires the `CLAUDE_CODE_ENABLE_AUTO_MODE` opt-in"), so the CLI rejects
     the `setPermissionMode` control request T3 sends at *every turn start*
     and the thread dies with `Provider turn start failed ·
     turn/setPermissionMode failed` before any model call. Interactive use
     never hits it because the TUI doesn't offer Auto. Upstream:
     [#4495](https://github.com/pingdotgg/t3code/issues/4495) (open; PR #4510
     remapping auto→default was closed unmerged, still present in 0.0.31).
     Fix: set the thread's permission dropdown to anything but Auto. Adding
     `"CLAUDE_CODE_ENABLE_AUTO_MODE": "1"` to the settings `env` block is the
     durable version, but a second per-model gate ("auto mode unavailable for
     this model") may still block it for inference-profile model IDs.
  2. **Model.** T3's picker sends first-party slugs (`claude-opus-5`) as
     `--model`, overriding `ANTHROPIC_MODEL` from settings, and Bedrock
     answers `400 The provided model identifier is invalid`. The Claude
     provider config has a `customModels` array for exactly this, but its
     schema marks it `providerSettingsForm: { hidden: true }` and leaves it
     out of the form `order` — **there is no UI for it**, which is what makes
     this look unfixable from inside the app. Set it in `settings.json` and
     the inference profile shows up in the picker. `normalizeCustomModelSlug`
     only trims, so the dots and colons in
     `<region>.anthropic.<model>-v1:0` survive; custom models resolve to
     empty capabilities, so T3 also stops appending the `[1m]` suffix and
     `--effort` for them (and their effort/context-window dropdowns
     disappear — that's the trade).
  Handled here by giving Bedrock machines their own `settings.json` from
  their context manifest rather than the shared one — full procedure in
  [Claude Code on Bedrock](#claude-code-on-bedrock-2026-08-06) under Connect
  providers.
- **npm server rejects newer config than its pinned version (this repo,
  handled)**: the headless `t3` server schema-validates managed configs and
  warns on anything a newer build wrote — RyzenWhite's `server.log` spammed
  "ignoring invalid keybinding entry" for `filePicker.toggle` /
  `projectSearch.toggle`, leftovers from the 0.0.32 nightly's default
  keybindings after the downgrade to 0.0.31. Handled by the platform
  variant split in the Settings section (bare files stay server-safe);
  deploying to RyzenWhite replaces the stale file and clears the warnings.
- **"Copy update command" starts a second server instead of updating the
  service (upstream, 2026-08-11)**: for a service-managed Linux environment,
  the remote-environments panel's update command is bare `npx t3@<version>`
  — running it spawns a foreground server that steals the relay tunnel;
  killing it strands the environment on "Relay environment endpoint is
  unavailable" until `systemctl --user restart t3code.service`. The CLI has
  a real updater (`t3 service update`) that the panel should surface when
  the endpoint is service-managed. Full procedure and recovery in
  [Updating a service-managed Linux server](#updating-a-service-managed-linux-server-2026-08-11).
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
