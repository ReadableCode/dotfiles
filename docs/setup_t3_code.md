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

## GitHub integration

T3 Code has one-button GitHub integration for commits, pushes, and PR
creation — connect it from Settings after first launch.

## Settings (NOT manifest-managed for now)

T3 Code's server/UI settings live in `~/.t3/userdata/`. They were briefly
ingested into `application_configs/t3code/` and symlinked via the manifest
(2026-07-31), then backed out the same day pending a decision on adopting T3 —
revisit if it becomes a daily driver. For reference, the split that was used:

| File | Manifest-worthy? | Why |
|------|------------------|-----|
| `settings.json` | yes | Provider instances, default model/effort. Has an `opencode.serverPassword` field — must stay empty in a public repo. |
| `client-settings.json` | yes | UI preferences (sidebar, diff, word wrap, ...). |
| `keybindings.json` | yes | Custom keybindings. |
| `desktop-settings.json` | no | Per-machine window bounds churn on every resize. |
| `clerk-tokens.json`, `secrets/`, `state.sqlite`, `logs/`, `environment-id`, `server-runtime.json`, `~/.t3/caches/` | never | Auth tokens, signing keys, thread state — machine-private. |

Caveat found while testing: Electron apps often save settings via atomic
rename, which replaces a deployed symlink with a plain file — if these are
ever re-managed, expect `NOT_A_LINK` drift after in-app settings changes.

## Remote access from other devices

Set **serverExposureMode: network-accessible** in the desktop app's settings
(stored in the unmanaged `desktop-settings.json`), then reach the session from
the phone/tablet apps over Tailscale — see
[setup_tailscale.md](./setup_tailscale.md).

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

## More docs

Full install/config docs live in the project repo:
[docs/user/install.md](https://github.com/pingdotgg/t3code/blob/main/docs/user/install.md)
