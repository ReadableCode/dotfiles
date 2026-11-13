# Setup T3 Code

[T3 Code](https://t3.codes/) is an open-source (MIT) control plane for coding
agents — it orchestrates Claude Code, Codex, OpenCode, Cursor, and Grok from a
single interface, using your existing subscriptions/credentials (no token
reselling). Desktop apps for macOS/Windows/Linux plus iOS/Android companion
apps. Source: [github.com/pingdotgg/t3code](https://github.com/pingdotgg/t3code)

## Requirements

- Node.js `^22.16 || ^23.11 || >=24.10` (`node` in the brew list covers
  this) — only for the headless `npx t3` / `t3 serve` paths; the desktop
  app is self-contained
- At least one coding agent CLI installed and authenticated (see below) —
  only on machines that *run* agents; a client-only viewer needs neither

## Server version

**Headless servers install unpinned**, same as the desktop app: `t3@latest`
(the Linux prereq script prints `npx -y t3@latest service install`). No file in
this repo names a server version, so nothing here can go stale. Only Linux runs
a headless server; see [Windows: desktop app only](#windows-desktop-app-only).

`latest` is npm's **stable** tag. Nightlies ship under a separate `nightly`
tag and are never resolved by `@latest`. A desktop install can still grab a
nightly build, and a nightly writes config entries a stable server then
rejects (see [t3_issues.md](t3_issues.md)).

No file in this repo reaches a server's `~/.t3/userdata/`, so an update has
nothing here to keep in step: at start a server merges any default binding its
own `keybindings.json` lacks and saves the file, and that file is its own
(see [Settings](#settings)).

## Install (macOS)

Listed as the cask `t3-code` in the context app lists
(`<context>_app_lists.yaml`), so `scripts/install_mac_apps.sh` installs it on a
member Mac. To install standalone:

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
tracks it like everything else (`T3Tools.T3Code` in the `<context>_app_lists.yaml`
of each context that uses it, since not every context's machines may carry it):

```powershell
winget install T3Tools.T3Code
```

**That is the whole Windows install.** There is no headless-server option: the
desktop app is the only supported way to run T3 on Windows, and a Windows box
is therefore never an always-on environment. See
[Windows: desktop app only](#windows-desktop-app-only).

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
`npx -y t3@<version> update` (**not** the panel's copy-update
command — see [Updating a service-managed Linux
server](#updating-a-service-managed-linux-server)).

What it writes, as of 0.1.8 — worth knowing before hand-editing anything:

```ini
# ~/.config/systemd/user/t3code.service
Environment=T3CODE_HOME=/home/<user>/.t3
Environment=T3_BOOT_SERVICE_UNIT=t3code.service
ExecStart=/home/<user>/.t3/runtime/versions/<version>/t3 __service-launcher
Restart=always
RestartSec=5
StandardOutput=append:/home/<user>/.t3/userdata/logs/boot-service.log
WantedBy=default.target
```

`ExecStart` is the release's own standalone binary (node is only needed for
the `npx` that installs it), and `t3 update` rewrites the line to the new
version's directory. That binary is also the CLI on a box with no `t3` on
PATH: `T3CODE_HOME=~/.t3 ~/.t3/runtime/versions/<version>/t3 <subcommand>`.
The unit sets no `PATH`. A fresh install binds **loopback only**
(`127.0.0.1:3773`) — no `0.0.0.0` bind, no firewall rule; every reachability
path below dials loopback. The connection string and a pairing token are
printed into the boot log once it's ready. `t3 status` shows the bind as
`Local network off`, and `~/.t3/service.env` holds `T3CODE_LAN=false`. A
service first installed on an older release has no such line and keeps the
old default, LAN on: it listens on `0.0.0.0:3773`, answers the whole LAN with
only a pairing code as the lock, and `t3 status` reads `Local network on ·
kept from an older install`. `t3 up --no-lan` writes the line and restarts the
service; do it on any box whose status reads that (JasonZephyrus did until
2026-11-10).

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

### Settings

Nothing is deployed into `~/.t3/userdata/` ([Settings](#settings)). A new
server starts from T3's defaults and a signed-in client pushes the five shared
settings to it on its own. To start a personal machine from envy's provider
setup instead, stop the service, copy envy's `settings.json` from the record
in `personal_credentials`, and start it again:

```bash
systemctl --user stop t3code.service
cp ~/GitHub/personal_credentials/t3code/settings.json ~/.t3/userdata/settings.json
systemctl --user start t3code.service
```

The directory only exists after the service has started once. From then on the
file is that server's own.

### Reachability: Tailscale Serve on the boot service

No machine uses this now: every T3 host is linked to T3 Connect and reachable
no other way. It is the fallback for an account that has run out of managed
tunnels, and the last drop-in for it (JasonZephyrus) was retired 2026-11-10.

A service-managed box is loopback-only and linked to nothing by default. Only
**T3 Connect** (`t3 connect link`) consumes one of the account's 3 managed
tunnels — **Remote link pairing is token-based, unlimited, and never touches
the T3 account**, so a full tunnel cap does not block anything here.

**Serve flags reach the service only through the environment.** The Linux
service launcher spawns `serve` with **no arguments** and there is no wrapper
script to edit. It does pass its own environment through, and every `serve` flag
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

**Linking the boot service to T3 Connect.** With no `t3` on PATH, call the
service's own binary on the box:

```bash
T3=~/.t3/runtime/versions/<version>/t3
printf 'y\n' | T3CODE_HOME=~/.t3 $T3 connect link --headless   # prints a URL and a code, waits 10 minutes for the approval
systemctl --user restart t3code.service                         # the link applies at the next start
T3CODE_HOME=~/.t3 $T3 connect publish                           # phone push, off after a link
T3CODE_HOME=~/.t3 $T3 connect status
```

The `y` answers the one-time question about downloading the relay client
(`cloudflared`); over ssh with no terminal the unanswered question exits 130.
Open the URL on any device signed in to the T3 account. Ignore the "start the
server with `t3 serve`" hint it ends with: the service is the server.

**The T3 Connect tunnel is pinned to http2.** T3 Connect runs a `cloudflared`
child (`~/.t3/tools/cloudflared/`) that inherits the service environment, so
`30-tunnel-http2.conf` sets `TUNNEL_TRANSPORT_PROTOCOL=http2`; on Windows the
desktop app's backend passes its environment to the same child, so
`start_t3code_client.ahk` sets the variable before it launches the app (a T3
opened by hand from the Start Menu is not pinned). QUIC to the edge fails from
every machine on the home LAN that has tried it (JasonZephyrus, EliteDesk,
nukbuntu, and a Windows desktop app) every time (`tls: no application
protocol`), so the cause is the home network path, not one machine.
cloudflared falls back to http2 on a cold start (one to three minutes
unpinned), but after a suspend it retries QUIC only and never reconnects: the
service stays `active` while the machine is gone from T3 Connect. Check the
tunnel with `t3 connect status`, which should end `Other devices can reach
this machine · Tunnel connected · 4 connections · HTTP2`. 0.1.8 starts
cloudflared with `--metrics 127.0.0.1:0`, so its `/ready` endpoint is on a
random port (`ss -tlnp | grep cloudflared`), no longer 20241.

**`tailscale serve` needs an operator grant.** It is a state-changing command,
so as a normal user it fails and the server logs a `WARN ... Failed to
configure Tailscale Serve` with `stderrDiagnostic: 'permission-denied'` —
while otherwise starting up fine, so it's easy to miss. Run once:

```bash
sudo tailscale set --operator=$USER
```

Don't "fix" it by running the service as root: `~/.local/bin/claude`, `~/.t3`,
and the deployed dotfiles symlinks are all user-owned. On success the log
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
token. 0.0.33 also has a `t3 pair` ("Mint a pairing token for a running T3 Code
server and print it as a QR code"). Take care not to invent a subcommand,
though: bare `t3 <word>` treats an unrecognised word as a cwd and silently
starts a stray server, so check `t3 --help` first.

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
No machine uses the SSH card any more. To check a host, `ls ~/.t3/ssh-launch`
should find nothing and the only `t3 serve` process should be the boot
service's child; a launcher folder that comes back means some client still
has an SSH environment saved for that host.

## New-Mac setup checklist

Ordered steps to bring a fresh Mac (e.g. the MacBook) to the same state as
Envy. Works for a human or for an agent driving the GUI with computer use —
agent-specific notes are marked **[agent]**. Details for each step live in the
sections below; this is the order that matters.

1. **Prereqs**: dotfiles + sibling credentials repos cloned, `claude`
   installed and authed (`claude auth login`), `gh` signed in to the
   personal account if this machine should have GitHub integration
   (`gh auth status` to check). **On a Mac, install T3 Code with brew** —
   `scripts/install_mac_apps.sh` (the context app lists carry it as the cask
   `t3-code`), or standalone `brew install --cask t3-code`. Don't use
   the downloaded installer or `npx t3` on a Mac; brew keeps it tracked and
   updatable with everything else.
2. **Launch T3 Code once** ("T3 Code (Alpha)" in /Applications) so it creates
   `~/.t3/userdata/`. Expect the first-launch quirks below — **[agent]** if
   `ps aux` shows the process at 0.0% CPU with no helper processes and no
   window after ~10s, it is hung: kill it, clear the quarantine attr and the
   `Singleton*` files, and if `open -a` still hangs, exec the binary in
   `Contents/MacOS/` directly (all commands in the quirks section).
3. **Settings**: nothing is deployed ([Settings](#settings)). To start from
   Envy's setup, quit the app and copy `settings.json`,
   `client-settings.json` and `keybindings.json` from
   `personal_credentials/t3code/` into `~/.t3/userdata/`, then relaunch. The
   first launch comes first because it creates that directory. From then on
   this machine's T3 owns those files.
4. **Verify providers and GitHub**: Settings (bottom-left) → **Providers**
   should list Claude; **Source Control** should show GitHub "Authenticated
   as" the personal account (click rescan if it doesn't). If the Claude row
   complains, the fix is CLI-side (`claude auth login`), not in the GUI.
5. **Sign into T3 Connect**: environments linked to the account (see the fleet
   table) appear on their own once the app is signed in; nothing to re-create
   per machine.
6. **Add no SSH-card environment.** The fleet table has none: every remote is
   reached through T3 Connect, and T3 is not to reach another host over SSH.
   If one is ever wanted again it is added under Settings → **Connections** →
   Remote environments → **Add environment**, per machine (they do not sync).
   **[agent]** dialog quirks: the dialog remembers the last-used card, so
   select the SSH card before typing; the suggested-hosts list shows tailnet
   `100.x` IPs from known_hosts — ignore them and type the LAN IP.
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

1. **Install**: `winget install T3Tools.T3Code` (see Install (Windows) — never
   the website installer). Verify it grabbed the stable release, not a
   nightly: a nightly writes config entries a stable server rejects. Expect a
   SmartScreen warning on first run of an unsigned alpha: More info → Run
   anyway.
2. **Launch once and sign into the T3 account** (Settings, bottom-left). T3
   Connect-linked environments (see the fleet table) appear on their own with
   their projects and threads — no per-device pairing. Environments whose
   desktop-app backend is a child process (e.g. Envy) only show while that app
   is running. Tailscale-Serve machines and SSH-card environments do NOT
   appear — those are per-client pairings; add them only if this machine
   actually needs them.
3. **Deliberately skip the rest**: no Node (desktop app is self-contained),
   no `claude` CLI (providers auth on the machine *running* the agent — just
   don't start local threads here), no T3 Connect publishing (keeps the machine
   unreachable and burns no tunnel slot), no Network access toggle. There is no
   Windows headless-server option to skip; see
   [Windows: desktop app only](#windows-desktop-app-only).
4. **Settings**: nothing is deployed ([Settings](#settings)); in-app
   defaults are fine for a client-only box.
5. **Verify**: open a thread running on another environment and watch it
   stream; steering from here works (the backend is event-sourced, clients
   are subscribers). Don't compose into the same running thread from two
   machines at once.

## Connect providers

Each agent needs its own CLI installed and authenticated **on the machine
running T3 Code** (not the browser/phone you control it from). Provider auth is
required before starting a session with that provider, not before starting T3
Code itself.

For Claude Code (`cask "claude-code@latest"` in the app lists of each context that uses it):

```bash
claude auth login
```

Then in T3 Code: **Settings → add/authenticate provider instances**. The
`claude` binary must be on `PATH`, or set an explicit binary path in Settings.
If auth fails at session start, the UI shows the login command to run.

Other providers (Codex, Cursor, Grok Build, OpenCode) follow the same pattern
with their own CLIs.

### Claude Code on Bedrock

On a machine where Claude Code authenticates through Bedrock rather than a
Claude subscription — `CLAUDE_CODE_USE_BEDROCK=1` plus `AWS_PROFILE` /
`AWS_REGION` / `ANTHROPIC_MODEL` in the `env` block of
`~/.claude/settings.json` — the interactive CLI works but **every T3 turn
fails**. Nothing is wrong with the auth: T3 spawns that same CLI and the CLI
reads that same settings file. The breakage is the two per-thread values T3
asserts *on top of* the config, both first-party-only concepts that
`settings.json` cannot override. See [t3_issues.md](t3_issues.md)
for the upstream detail; this is the procedure.

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
- The block writes an explicit `claudeAgent` providerInstance; watch the
  provider list on first deploy.
- Model IDs pass through `normalizeCustomModelSlug`, which only trims, so
  the dots and colons survive intact. It's an array — list several profiles
  if more than one is enabled.

**Where the file comes from.** Nowhere: no manifest deploys a T3
`settings.json` (Settings section below), so the block is merged by hand into
that machine's own file. Keep the model IDs in that context's own docs, so a
rebuilt machine can be given them again.

**Applying it**, on the machine running the server:

```bash
systemctl --user stop t3code.service           # if installed as a boot service
$EDITOR ~/.t3/userdata/settings.json           # merge the block above
systemctl --user start t3code.service
```

Stop the server first: it rewrites the file on its own and would overwrite an
edit made under it.

Then per thread: permission dropdown off Auto, model picker → the inference
profile. If the model isn't listed after the restart, that pinned server
build predates `customModels` on the Claude driver (check `~/.t3/server.log`
for a config-issue warning); fall back to putting
`--model <region>.anthropic.<model>-v1:0` in the provider's **Launch
arguments** field, which *is* in the UI. Those parse into the SDK's
`extraArgs` and are appended after T3's own `--model`, so the last one wins.

**Also check `~/.claude/settings.json`** on that machine: a top-level
`"model"` key (e.g. `"opus[1m]"`) beats `env.ANTHROPIC_MODEL`, so any CLI
invocation without an explicit `--model` still resolves to a first-party
alias Bedrock rejects. Drop it or set it to the inference profile.

## First launch (macOS quirks)

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
active account per environment — no multi-account UI. Sign that machine's `gh`
in to the personal account and T3 picks it up under **Settings → Source
Control** (rescan there if needed). Remote environments each use their own
machine's auth, so agents on work machines keep doing GitHub through that
context's normal token conventions — don't try to force a second account
through the GUI. The flip side: on a personal machine, a client project's pull
request pane can never load (see [t3_issues.md](t3_issues.md), "Pull
request pane fails for client repos").

## Environments (multi-machine)

One desktop UI drives several backends ("environments"); threads live on
whichever backend created them. Environments are added under
**Settings → Connections → Remote environments → Add environment**, using
plain LAN IPs — Tailscale is not required (T3 will suggest tailnet IPs it
finds in `~/.ssh/known_hosts`; ignore them).

**T3 Connect is the recommended way to attach a remote**: sign the remote's
server into the T3 account (`t3 connect link --headless` on the remote) and it
reaches the desktop through T3's relay — no pairing codes, no open ports or
firewall rules, and it works off-LAN. **Caveat: accounts get 3 managed
tunnels** (see [t3_issues.md](t3_issues.md)); beyond that, expose
the server with `t3 serve --tailscale-serve` and pair it as a Remote link over
the tailnet (per-client pairing codes, no push notifications from that
environment, but no slot used). The SSH card remains as a LAN alternative for
Linux/macOS remotes.

Current fleet:

| Machine | How | Notes |
|-------------|-----|-------|
| Envy (local) | implicit | The desktop app's own server. |
| JasonZephyrus | T3 Connect | Fedora: systemd boot service (`t3 service install`), not the SSH card, with agent-activity publishing on. No `t3` on PATH: the CLI is the service's own copy, `T3CODE_HOME=~/.t3 ~/.t3/runtime/versions/<version>/t3` (a bare `npx t3` starts a second server). See [Install (Linux)](#install-linux--always-on-server-via-systemd). |
| EliteDesk | T3 Connect | Ubuntu: systemd boot service, agent-activity publishing on, node from nvm linked into `~/.local/bin` by the prereq script. Same CLI path as JasonZephyrus. |
| nukbuntu | T3 Connect | Ubuntu: same setup as EliteDesk. |
| RyzenWhite | T3 Connect | Windows: **desktop app only**, the app's own backend on `~/.t3`, no headless serve. The backend runs its own T3 Connect tunnel while the app is open, started at logon by `start_t3code_client.ahk`, which pins it to http2. See [Windows: desktop app only](#windows-desktop-app-only). |



Concrete LAN IPs and usernames are deliberately not listed here: look the
machine up in the `*_hosts.json` inventory of the sibling `*_credentials`
repo it belongs to (`hostname` + `user` fields).

**Slot policy**: a slot goes to a machine whose own threads other devices need
to reach, never to one that is only a client. A desktop or phone app signed
into the T3 account sees every slotted environment without a slot of its own,
and the desktop app raises its own notifications for every environment it is
connected to (`apps/web/src/components/ThreadNotificationCoordinator.tsx`
upstream); only phone push and Live Activities come from the relay. The
account holds more than the default three since 2026-11 (see the tunnel cap
row under the gaps); the slots go to Envy, the work laptops, JasonZephyrus (the
always-on agent server and dev target), EliteDesk, nukbuntu and RyzenWhite. The
MacBook is a client only: a thread
started on the MacBook is finished there. To move a slot: turn T3 Connect off
on the old host (Settings → Connections), then on any signed-in client open
the account avatar → **Manage account** → **T3 Connect** and **Deregister**
it; link the new host and restart its server. After `link`, also run `t3
connect publish`: a linked environment starts with agent-activity publishing
(phone push) disabled. Machines beyond the cap ride Tailscale Serve. A `t3
connect link --publish-only` link takes no slot, lists the environment on the
account and, per the source (`apps/server/src/cli/connect.ts`), still sends
phone push through the relay; not tried here yet, and other devices still pair
to it per device. Mixing transports is fine: the connection method is
per-environment plumbing, threads behave identically once connected, and a
machine can carry both at once.

**SSH environments (Linux/macOS remotes only).** Requirements on the remote:
Node `^22.16 || ^23.11 || >=24.10` resolvable from a *non-interactive* shell,
plus the agent CLIs (`claude`, ...) installed and authed there. The launcher
probes PATH then nvm/asdf/mise/fnm. That prep is scripted —
[`scripts/setup_t3_server_prereqs_linux.sh`](../scripts/setup_t3_server_prereqs_linux.sh)
(idempotent: checks the bare-PATH node version, installs Node 24 via nvm if
needed, links into `~/.local/bin`, and installs a C++ toolchain if none is
present — node-pty builds from source); run it on the remote from its dotfiles
clone. The remote server listens on loopback only; the desktop reaches it
through the SSH tunnel.

**Windows machines cannot be remote environments at all.** The SSH card does
not work (T3's remote launch scripts are POSIX `sh` only) and there is no
native headless server, see
[Windows: desktop app only](#windows-desktop-app-only). A Windows box is a
*client* that reaches other environments; it is only an environment itself
while its own desktop app is open, and only for that app.

If a Windows machine genuinely needs to host agents for other clients, the
honest answers are to run the work on a Linux box instead, or to accept the
desktop app being open.

### Windows: desktop app only

**On Windows, T3 is the desktop app and nothing else.** One backend, the app's
own, on `~/.t3`. No headless serve, no scheduled task, no second data
directory. Windows has no service manager for T3 — `t3 service status` answers
"unavailable on this machine · Supported on: Linux with systemd" — so there is
nothing to supervise an always-on server with, and a scheduled task plus a
`cmd` restart loop is not a working substitute for one.

**What it costs.** A Windows box is an environment only while its desktop app
is open, and it cannot be a remote environment for other clients at all (the
SSH card is POSIX-only). That is the accepted trade. Machines that must be
always-on are Linux, which has a real boot service.

**Never split the T3 home.** `clerk-tokens.json` (the account session) and
`connection-catalog.json` (the paired environments) live in `~/.t3`, so a
launch pointed at any other `T3CODE_HOME` comes up signed out with an empty
environment list while a manual launch on `~/.t3` looks fine. Environment
identity is per-home too (`userdata/environment-id` plus
`secrets/cloud-relay-environment-credential.bin`), so a second home is a second
environment id and every client has to re-pair.

**Port 3773 is load-bearing.** `start_t3code_client.ahk` sets
`T3CODE_PORT=3773`. `resolveDesktopBackendPort()` would scan upward from 3773
and land there anyway while it is free, but the tailnet path is a `tailscale
serve` proxy hardwired to `http://127.0.0.1:3773`, so a silent drift to 3774
takes that path down with no error anywhere. `T3CODE_PORT` is read by the
Electron parent, which passes the resolved port to the backend explicitly and
strips it from the child env (`DESKTOP_BACKEND_ENV_NAMES` — which also contains
`T3CODE_TAILSCALE_SERVE`, so that one cannot be handed to the desktop backend
the way the Linux service takes it). Nothing needs to: `tailscale serve` config
lives in tailscaled's own state and persists, so it keeps proxying to whatever
holds 3773.

**Autostart is the only thing keeping the box present.** `t3code_client_startup`
(`scripts/start_t3code_client.ahk` → the Startup folder) is what launches the
app at logon; without it the machine is not an environment until someone opens
it by hand. The app's own open-at-login toggle writes an
`HKCU\...\CurrentVersion\Run` value no repo file owns and
`deploy_configs.py status` cannot see, so an empty Startup folder is the thing
to check when a box stops showing up.

**Update restarts leave it signed out.** Windows Update restarts just after
the end of active hours, and without automatic sign-on the box then waits at
the sign-in screen, so nothing in the Startup folder runs until someone logs
in, which can be hours. The host's `updater.windows.restart_sign_on` in its
inventory entry turns it on, and `preview_updates: false` halves the restarts;
see "Windows settings from the inventory" in
`docs/setup_windows_workstation_personal.md`. Even signed in, the Startup
folder runs last, after every Run-key app, each allowed 30 seconds, which can
add up to several minutes. `parallel_logon_apps: true` in the same block stops
Explorer waiting on each one.

Note `desktop-settings.json` is per-home and unmanaged, so
`serverExposureMode` carries over independently: a home set to
`network-accessible` binds `0.0.0.0` rather than loopback (Settings →
Connections → Network access). RyzenWhite's `~/.t3` copy is
`network-accessible`, which is why its backend shows as `0.0.0.0:3773`.

## Updating a service-managed Linux server

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
  shows "Failed to connect … Relay environment endpoint is unavailable" while
  `systemctl --user status t3code` still says active/running. The smoking gun
  in `~/.t3/userdata/logs/boot-service.log` is cloudflared spamming `ERR …
  dial tcp 127.0.0.1:<port>: connect: connection refused` — the same
  dead-origin class as Envy's exposure-port mismatch, but with no exposure
  toggle here to re-kick it.

**Recovery** from that state: `systemctl --user restart t3code.service`. The
restart re-spawns cloudflared against the service's own port. Expect 1–2
minutes of `CRYPTO_ERROR 0x178 … tls: no application protocol` QUIC retries in
the log before it falls back to http2 and registers **4 tunnel connections**,
the ready signal (same readiness behavior as Envy).

**The correct update command** (the CLI has a real updater, the panel just
doesn't surface it):

```bash
npx -y t3@latest update
```

The version the panel names works here too; what matters is the
`update` verb, not the tag. It installs the
runtime under `~/.t3/runtime/versions/<version>`, rewrites
the unit, and restarts the service — sessions on the box restart with it.
`service update` was the verb through 0.0.42; the 0.0.44 CLI still accepts
it but prints "`t3 service update` is deprecated: run `t3 update` to move to
a newer release, or `t3 service install` to repair the service" and then
performs the update anyway.
As of 0.0.33 the rewrite also switches `ExecStart` from a version-pinned
runtime path to the version-agnostic `~/.t3/runtime/service-launcher.mjs`,
so future updates shouldn't need to touch the unit at all. Verify with
`systemctl --user status t3code` (the serve process's path shows the
running version) and wait for the 4 registered connections in
`boot-service.log`; the panel then goes green and the update banner clears.

## Settings

`settings.json`, `client-settings.json` and `keybindings.json` in
`~/.t3/userdata/` are **not deployed**, by this repo or by any context. Each
machine's T3 owns its own three files. T3 writes them itself, after an in-app
change, after an app update and when a client pushes its shared settings, and
while they were links into a checkout those writes went through the link: the
machine was left with a modified tracked file, and git refused its next pull
of that file.

A record of envy's files is kept in `personal_credentials/t3code/`. Three
`method: ingest` entries in `personal_manifest.yaml` (`t3code_settings`,
`t3code_client_settings`, `t3code_keybindings`) run on envy alone: every
deploy there writes envy's file over the record when the two differ, in
canonical JSON, and leaves that checkout dirty to be committed by hand like
the deployment map. Nothing reads the record back. It is in the private
credentials repo because `settings.json` has a field for a provider password.
`t3code/README.md` there says the same beside the files, and
[repo_deploy_configs.md](repo_deploy_configs.md) describes the method.

A machine that still has the old links loses them on its next `gitpullall`:
the `keep_copy` removals replace each link with a regular file, so T3 keeps
its settings. The files those links pointed at are deleted from their repos,
so the link is usually dangling by the time prune reaches it; prune then
writes the content git last held for the target, which is what the link
showed. A running T3 saves a nearly empty `settings.json` back through the
dangling link in the meantime; prune ignores that file and removes it from the
checkout. Check with `ls -l ~/.t3/userdata/*.json`; none of the three should
be a link.

One case needs a hand. A machine whose T3 had already written through a link
has a modified tracked file, and git refuses the pull that deletes it, so the
new code never arrives. `gitpullall` there reports the repo as not pulled. On
that machine, once:

```bash
git -C ~/GitHub/dotfiles checkout -- application_configs/t3code
gitpullall
```

That drops what T3 had written into the checkout since the last commit. The
pull then deletes the files, and prune gives T3 the last committed content as
its own file. To keep the uncommitted changes instead, copy the two files out
of `application_configs/t3code/` before the checkout and over
`~/.t3/userdata/` after the `gitpullall`.

The five keys the client holds identical on every environment
(`continueThreadsAfterServerUpdate`, `sidebarAutoSettleAfterDays`,
`sidebarAutoSettleOnMerge`, `newWorktreesStartFromOrigin`,
`sourceControlWritingStyle`) are defined in the app's own
`packages/client-runtime/src/state/sharedSettings.ts`. The client pushes them
to every environment it is connected to, so they converge without any file
from here; an environment that differs shows up in the client's "Settings
differ on <host>" banner. Reloads are visible in
`~/.t3/userdata/logs/server.trace.ndjson` as `"startup.phase":"settings.start"`.

| File | In the repo? | Why |
|------|--------------|-----|
| `settings.json` | envy's copy, in `personal_credentials` | Provider instances, default model/effort. Has an `opencode.serverPassword` field, which is why the record is not in a public repo. |
| `client-settings.json` | envy's copy, in `personal_credentials` | UI preferences (sidebar, diff, word wrap, ...). |
| `keybindings.json` | envy's copy, in `personal_credentials` | Custom keybindings. |
| `desktop-settings.json` | no | Per-machine window bounds churn on every resize; also holds `serverExposureMode`. |
| `connection-catalog.json` | never | Per-machine registry of paired environments (named `saved-environments.json` in newer source). **Not syncable even by hand**: the app writes `{version, encryptedCatalog}` where the payload is Electron `safeStorage` — DPAPI on Windows, Keychain on macOS — so it is keyed to one OS user on one machine. A copy from another box cannot decrypt, hand-written JSON is not the expected shape, and the only writer is the `desktop:set-connection-catalog` IPC channel, i.e. the GUI. Adding an environment is a GUI-only operation in 0.0.33; there is no CLI subcommand for it (every `t3` subcommand is server-side). |
| `clerk-tokens.json`, `secrets/`, `statev2.sqlite`, `logs/`, `environment-id`, `server-runtime.json`, `~/.t3/caches/` | never | Auth tokens, signing keys, thread state — machine-private. |

`clerk-tokens.json` and `connection-catalog.json` are **home-private** as well
as machine-private; see
[Windows: desktop app only](#windows-desktop-app-only).

One runtime entry lives one level up in `~/.t3/`: `t3code_client_startup`, the
desktop app's Startup-folder launcher.

## Remote access from other devices

Preferred path: sign every client (laptop, phone) into the same **T3 account**
— T3 Connect-linked environments appear on each of them with no per-device
pairing. Only SSH-card environments are re-added per machine. LAN **Create
link** pairing still exists for account-less one-offs (requires Network access
toggled on under Settings → Connections, stored as `serverExposureMode` in the
unmanaged `desktop-settings.json`). Envy's own environment is reachable only
while the desktop app is running (the backend is a child process; the `t3
service install` background service is Linux-only — it installs a systemd
**user** unit `t3code.service` plus `loginctl enable-linger`, so managing it
is `systemctl --user {status,restart} t3code.service`, never `sudo
systemctl`). Once two clients are connected to the same backend, threads and
steering sync live in both directions — the backend is event-sourced and
clients are just subscribers. Avoid composing into the *same running thread*
from two machines at once (composer drafts don't sync and pending turn-starts
can stomp each other). Tailscale HTTPS remains available for off-LAN use — see
[setup_tailscale.md](./setup_tailscale.md) — but is not part of this setup.

## What T3 replaces, and the gaps that remain

T3 replaces the **Claude desktop app** (agent session
management), NOT VS Code — its editor pane is a viewer with a diff tab
(open via `Cmd+D` or the `+` tab button → Diff), not an editing environment.
So "no code cells" and "no inline completions" only disqualify it as an
editor, which it isn't trying to be. Keep VS Code for hand-editing (`# %%`
cells, Copilot-style completion).

Gaps that matter next to the Claude desktop app:

| Gap | Detail |
|-----|--------|
| Sessions are headless | T3 drives `claude` via the Agent SDK. Threads never appear in the Claude desktop/mobile apps, can't use Remote Control, and there is no TUI to `tmux attach` / jump back into from a terminal — T3's own desktop/phone apps are the *only* surface for its threads. |
| No computer use | The CLI's built-in `computer-use` MCP server is added only to an interactive session (the `!isInteractive()` gate in `claude` 2.1.280, checked before the Pro/Max and feature-flag gates, which this account passes). T3 launches `claude` with `--input-format stream-json` through the Agent SDK, which the CLI treats as non-interactive, so the server is never wired and no `mcp__computer-use__*` tools or enable tool appear in a thread. Enabling `computer-use` under `/mcp` in a terminal session persists per project but changes nothing for T3: the gate runs before that setting is read. Registering `claude --computer-use-mcp` as a stdio server in `.mcp.json` does not work either: it lists all the tools and refuses every call with "not wired to a session" (verified 2026-09-25). Anthropic's docs say the same: computer use requires an interactive session and is not available with `-p`. To drive a GUI, run `claude` in a terminal on that machine (enable `computer-use` in `/mcp` once per project) or use the Claude desktop app. |
| Other desktop-app surfaces missing | The in-app browser pane, artifacts and the iOS simulator panel are Claude-desktop-app features and don't exist in T3 threads (T3 has its own device panel for simulators, `mcp__t3-code__device_*`). claude.ai connectors (Gmail, Calendar, Drive, Docs, Slack) DO reach T3 threads: they are remote MCP servers registered on the claude.ai account and `claude mcp list` shows them connected from inside a thread (verified 2026-09-25). CLAUDE.md, skills, auto-memory, and MCP servers configured in `~/.claude` also apply, since it's the same `claude` binary. |
| No Anthropic cloud sessions | T3 can't spawn or steer sessions running in Anthropic's GitHub-repo sandbox; those are reachable only from Anthropic's own apps. |
| One serving machine | Everything a session touches (repo, agent CLI, auth) must exist on the machine whose t3 server owns the thread. |
| T3 Connect tunnel cap | Accounts get **3 managed tunnels**, counted against *published environments* — the local desktop's own published environment occupies a slot, so the dashboard's remote-environments list understates usage (it looks like 2 when all 3 are taken). The headless CLI surfaces a refusal only as a bare `403` with no message; the desktop dialog shows the real reason. Machines beyond the cap pair over Tailscale Serve instead — full thread functionality, but no phone push or Live Activities unless also linked `--publish-only` (see Slot policy). Why 3: each managed tunnel is a real Cloudflare Tunnel plus DNS record in T3's own Cloudflare account, billed whether or not a connector is attached; `DEFAULT_MANAGED_TUNNEL_LIMIT = 3` in `infra/relay/src/environments/ManagedTunnelLimits.ts` (lowered from 10 in upstream #4530, no reason given) is a soft quota the T3 team can raise per user with a row in `relay_managed_tunnel_limits`. A linked paid T3 Chat plan raises it: 10 on Pro, 100 on Premier (`T3CHAT_PLAN_TUNNEL_LIMITS` in `packages/contracts/src/relay.ts`, upstream #25931). |

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

## Working on the T3 source

The upstream repo ([github.com/pingdotgg/t3code](https://github.com/pingdotgg/t3code),
MIT) is cloned as `~/GitHub/t3code` on the personal dev workstations only: it
is declared in the personal repo list (`personal_repos.yaml`, `org: pingdotgg`,
`hosts: *dev_hosts`), so `clone_repos.py` offers it there and nowhere else.
Nothing deploys from it; it exists to read the code behind the quirks in this
file (the desktop bundle is minified in `app.asar`, the checkout is not) and
to prepare fixes.

Reading the source needs nothing beyond the clone. Building or running it needs:

- `vp` (Vite+), installed with the vendor script `curl -fsSL https://vite.plus | bash`.
  Not in the brew list because it is not a formula; add it to
  `app_lists/mac_apps_non_brew.md` before installing it on any machine.
- Node `^24.13.1` (`package.json` engines) and `pnpm@11.10.0`, which `vp`
  provisions. The brew list's `node` is 26 here, so expect an engines warning.
- `vp i` in the checkout, then `vp run dev --home-dir /tmp/t3code-dev` (server
  plus web) or `vp run dev:desktop`. **Never run a dev server against
  `~/.t3/userdata`**; the main checkout defaults to `~/.t3/dev/userdata` and a
  worktree to its own gitignored `.t3`. Checks: `vp test run <files>`,
  `vp lint <files>`, `vp run --filter <package> typecheck`.
- The repo's `t3.json` runs `node scripts/setup-worktree.ts` on worktree
  creation, so opening the checkout as a T3 project works out of the box.

Contribution mechanics, from `CONTRIBUTING.md` and `.github/pull_request_template.md`:

1. Fork on GitHub and add the fork as a second remote (`origin` stays
   upstream); push branches to the fork.
2. Keep the PR small and single-purpose. Bug fixes are the only category they
   say they merge; features go to the Ideas discussion first.
3. Fill the template's *What Changed* and *Why*; UI changes need before/after
   images, interaction changes a short video.
4. Expect `vouch:unvouched` (`.github/VOUCHED.td`) and `size:*` labels from
   the bots, plus Macroscope and CodeRabbit reviews. Unvouched PRs are
   routinely closed.
5. As of 2026-09-19 the orchestration and provider layers under
   `apps/server/src/{orchestration,provider}` are frozen for a V2 rewrite and
   PRs there are closed on sight; comment on the existing issue instead and
   watch for the rewrite landing.

## Workarounds on our machines

What we do on a machine to work around a T3 issue. The issues themselves,
with causes and upstream state, are in [t3_issues.md](t3_issues.md).
Workarounds that are part of the setup above (Bedrock `settings.json`, the
platform variants, the update command, Local Network pre-authorization, the
Linux prereq script, Tailscale Serve past the tunnel cap, the http2 pin,
Windows restart sign-on) are not repeated here.

- **Same repo on two environments**: add the parent workspace folder (e.g.
  `~/GitHub`) as the project instead of the repo, and prefix project names
  with the machine (`RW-GitHub`, `Envy-GitHub`) so the sidebar tells them
  apart.
- **T3 account sign-in on Windows**: use *Email address → Continue* with the
  emailed code, or *Use passkey instead*. The provider buttons loop forever.
- **T3 Connect 502s after a reboot**: compare the cloudflared ingress port
  (`curl 127.0.0.1:20241/config`) with `~/.t3/userdata/server-runtime.json`.
  If they differ, toggle server exposure off and on in T3 settings and wait
  for `readyConnections: 4` in `/ready`.
- **Remote link dead after 30 days**: run `t3 auth pairing create` on the
  server and re-pair from the client within the token's 5-minute TTL.
- **"OAuth session expired" in T3 only**: run
  `env -i HOME="$HOME" PATH="$PATH" claude -p "ok"` as the user, then kill any
  T3-spawned `claude --output-format stream-json` started before it. A
  corrupt keychain item needs `/login`.
- **Duplicate servers on one state db**: switch the other machine's client to
  T3 Connect or delete its SSH-remote connection. Never kill the servers.
- **A hung FUSE mount wedges the server**: SIGKILL the fuse daemon, restart
  from outside the service's cgroup (`systemd-run --user --collect
  --unit=t3-restart-manual systemctl --user restart t3code.service`), then
  remount.
- **Claude Code update on a Mac that redirects `HOMEBREW_CACHE`**: update
  with myupdater or `brew upgrade --cask claude-code@latest` from a shell.
  T3's own update prompt reads a stale cache.

## More docs

Full install/config docs live in the project repo:
[docs/user/install.md](https://github.com/pingdotgg/t3code/blob/main/docs/user/install.md)
