# Setup RustDesk

How an iPhone or iPad reaches a machine's screen. Everything else in the fleet
uses VNC or RDP (`setup_vnc_server.md`); this doc exists because iOS is the one
client platform that has no free software VNC viewer, so the phone needs a
different protocol to get in at all.

RustDesk is used **only** for that. It does not replace VNC anywhere, and a
machine that already answers a VNC viewer keeps doing so.

## Why this one

The only GPL-lineage VNC app on the App Store is paid and ships no iOS source.
Moonlight to Sunshine was the first way round that and is still the backup
(`setup_vnc_server.md`), but it streams one display per session and its input
model is built for games. RustDesk controls a desktop, switches between a
host's monitors, and has a real modifier key row.

On the rug-pull question, which is the reason this was not decided quickly:

- The client is plain AGPL-3.0. Its `LICENCE` is unmodified FSF text with no
  copyright line, no non-commercial clause and no trademark clause.
- RustDesk's own terms exclude it: "'Software' does not include the RustDesk
  client or RustDesk Server OSS, which Company releases under their own open
  source license." The agreement they can amend unilaterally covers the
  services they host, not the binary on these machines.
- Contributions carry a DCO sign-off, not a CLA. Nobody assigned copyright, so
  the company cannot relicense other people's work in a future version.
- The paid tier at rustdesk.com/pricing is **RustDesk Server Pro**, a
  self-hosted management server (web console, API, SSO, LDAP, audit log, device
  quotas). The page states "This pricing is for self-hosting solution, it is
  NOT a SaaS subscription." Direct IP uses no server at all, free or paid.

The one real exposure: the iOS client is distributed by that company through
the App Store, and the project documents no way to build it for iOS yourself
(the build docs cover Linux, Windows and macOS only). If the app were withdrawn
or made paid, an installed copy keeps working until an iOS release breaks it,
and there is no quick self-build. That is why every VNC and RDP server in the
fleet stays exactly as it is: they are the vendor-proof floor, and losing the
app would cost convenience from the phone, not access to any machine.

## Direct IP, so no RustDesk server is in the path

By default the client registers with RustDesk's public ID server
(`rendezvous_server = 'rs-ny.rustdesk.com:21116'` in `RustDesk2.toml`) and
connects by a numeric ID. Direct IP access skips that: the phone connects
straight to the host's LAN address, reachable from anywhere through the
Tailscale subnet route, and nothing that company runs is involved.

That is two options under `[options]` in `RustDesk2.toml`:

```toml
[options]
direct-server = 'Y'
direct-access-port = '21118'
```

Their docs list 21118 in a ports table as WebSocket communication and in
advanced settings as the direct access port. The second is right: with
`direct-server = 'Y'` the host listens on 21118.

### Declaring it

RustDesk rewrites `RustDesk2.toml` itself, next to its own runtime state
(`nat_type`, `serial`, `local-ip-addr`), so a deployed symlink would hand the
app a repo file to write into. The options are declared on the host record
instead, the same way Tailscale routes and the gnome-remote-desktop login are:

```json
"rustdesk": {"direct_access_port": 21118}
```

in `<context>_hosts.json`. `src/rustdesk_server.py` ensures those two keys and
leaves every other key alone, as step 5d of `refresh_machine.py`, so a
`gitpullall` restores them if anything resets the file. `--check` reports and
writes nothing. A host with no `rustdesk` block is a client only and the step
changes nothing there.

**Among the Macs only Envy serves RustDesk.** MacBookProM5 is a portable, runs
no screen server of any kind, and is a client only, the same rule
`setup_vnc_server.md` applies to VNC.

## Host setup

1. The app comes from the personal app list (`cask: rustdesk`), so
   `installmissing` places it. Start it once so it writes its config.
2. Run `gitpullall` (or `uv run python src/rustdesk_server.py`) to set the
   direct IP options, then restart RustDesk so it re-reads the file.
3. Grant macOS permissions. RustDesk needs **Screen Recording** to capture,
   **Accessibility** to inject keyboard and mouse, and **Input Monitoring** on
   newer releases. They are prompted on the first connection and have to be
   approved at the machine.
4. Set the security options below.

### Where the settings are

Settings is **not** a gear. It is the vertical three-dot button `⋮`
immediately right of the "ID" label at the top left of the main window
(tooltip "Settings"), or the menu icon at the far right of the tab strip.
Either opens Settings as a tab in the same window. On an installed client the
Security tab is behind an "Unlock Security Settings" header, which asks for the
account password.

### Security settings, for a machine only its owner connects to

| Setting | Value | Why |
| --- | --- | --- |
| Accept sessions via | **password** | "Both" also allows click-to-accept, which needs someone at the machine to approve. Useless when the point is reaching it while away. |
| Password type | **permanent password** only | A one-time password is displayed on the host's screen, so it is for granting someone else access and is worthless remotely. |
| Enable remote restart | **off** | FileVault. A remote reboot parks the Mac at the pre-boot unlock screen with no network stack, and locks you out until you walk to it. |
| Enable terminal | off | ssh already reaches these machines. One method per job, and less that a leaked password grants. |
| Enable TCP tunneling | off | Nothing here needs port forwarding through the session. |
| Enable recording session | off | Not needed. |
| Enable remote configuration modification | off | It would let a connected client rewrite these rules, including the password. |
| Clipboard (Permissions card) | **on** | Clipboard sync in both directions is the reason this beat a browser gateway. |

The permanent password is **machine-local and in no repo**, like `~/.vnc/passwd`.
RustDesk stores it in `RustDesk.toml` as a derived value plus a salt, beside the
machine's key pair, so it cannot be hand-written into that file either. Set it
in the Security tab, or with `sudo rustdesk --password <pw>` (installed client
only, and it lands in shell history and `ps`).

## From the phone

Type the host's **IP address** into the Remote ID field rather than an ID. That
is what keeps the public ID server out of the path.

- **Monitors**: the TV icon in the bottom bar gives numbered buttons, one
  display at a time. There is no all-monitors-at-once view on mobile.
- **Keyboard**: the on-screen row carries Ctrl, Alt, Shift and a Meta key
  rendered as `Cmd` when the host is a Mac (it reads the host's platform, not
  the phone's), an Fn toggle for F1 to F12, and a row with Esc, Tab, Home, End,
  Ins, Del, PgUp, PgDn and arrows, plus Cmd+C, Cmd+V and Cmd+S buttons.
- **Clipboard**: sync fires when the app returns to the foreground, so
  background and reopen it if a copy made elsewhere has not arrived.

## What it does not cover

- **A FileVault pre-boot unlock.** Envy has FileVault on with no auto-login, so
  after a reboot or power cut it sits at a screen with no network stack at all.
  Nothing reaches it there: not RustDesk, not Screen Sharing, not ssh. That case
  is the physical keyboard whatever the protocol.
- **A login window.** RustDesk runs in the signed-in session.
- **The Pis.** No armv6 build for pi0 and Wayland support is experimental, so
  they stay on wayvnc.
- **Unraid and anything else that only speaks VNC.** Reached from a real
  computer with a VNC viewer as before.
