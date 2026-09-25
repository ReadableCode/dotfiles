# Setup Tiger VNC

Two different mechanisms live in this doc. Pick by whether the machine has a
usable console session:

| | Screen scraping (`x0vncserver`) | Virtual desktop (`Xtigervnc`) |
| --- | --- | --- |
| Shows you | whatever is on display `:0` | its own separate desktop |
| Needs | a logged-in X11 session on a real seat | nothing - runs headless |
| Started by | XDG autostart at graphical login | systemd user unit + linger |
| Port | 5900 | 5901 for `:1` |
| Deployed on | EliteDesk | NukBuntu |

Neither method supports Wayland. Both boxes keep `WaylandEnable=false` in
`/etc/gdm3/custom.conf` for that reason.

## Clients

The servers here speak plain RFB with VncAuth on 5900/5901, so any standards
compliant viewer works. One per platform, all free software, none of them
reachable only through a vendor's cloud:

The `vnc<host>` aliases offer to install the viewer when it is missing,
whatever the app lists say: the lists gate what a refresh offers on its own,
and a typed alias may fetch the one package it needs. The lists below are where
a refresh offers it.

| Platform | Client | Listed for refresh in |
| --- | --- | --- |
| macOS | Screen Sharing (built in); TigerVNC for the Pis | the personal `<context>_app_lists.yaml` (`cask: tigervnc`) |
| Windows | TigerVNC Viewer | the same file (`choco: tigervnc`) |
| Linux (apt) | TigerVNC Viewer | the same file (`apt: tigervnc-viewer`) |
| Linux (Fedora) | TigerVNC Viewer | the same file (`dnf: tigervnc`) |
| Android | AVNC | F-Droid |
| iOS | *(none - see below)* | |

### Which viewer an alias picks, and why it matters

The `vnc<host>` aliases pick the viewer from the **target's server**, not from
the machine you are sitting at and not from the target's OS. From a Mac, a
target whose server speaks VNC Auth or Apple ARD gets Screen Sharing
(`open vnc://`); everything else runs `src/vnc_connect.py`, which launches
TigerVNC.

Prefer Screen Sharing wherever it can negotiate at all, because TigerVNC 1.16
cannot do three things it does:

| | Screen Sharing | TigerVNC 1.16 |
| --- | --- | --- |
| Fit desktop to window | yes | **no - upstream removed local scaling** |
| Remote cursor | yes | only with `-AlwaysCursor=1` |
| Command key as Super | yes | full-screen only (`FullscreenSystemKeys`) |

The scaling one has no workaround. TigerVNC's only resize path is
`RemoteResize`, which asks the *server* to change its desktop size, and a server
that cannot do that (TightVNC) leaves you with scrollbars and no way to see the
whole desktop at once.

Which hosts can take Screen Sharing is declared per host with
`vnc_screen_sharing: true` in the inventory, because it is a property of the
server rather than the OS. macOS targets are implicitly true. Probed
2026-09-21:

| Server | Offers | Screen Sharing |
| --- | --- | --- |
| TightVNC 2.8 (RyzenWhite) | VNC Auth, Tight | yes |
| x0vncserver / Xtigervnc | VeNCrypt, VNC Auth | yes |
| wayvnc (the Pis) | VeNCrypt, RSA-AES, RA2 | **no** |

Read any host's list yourself - it arrives before authentication:

```bash
python3 - <<'EOF'
import socket
s = socket.create_connection(("192.168.86.94", 5900), 3)
s.recv(12); s.sendall(b"RFB 003.008\n")
print(list(s.recv(s.recv(1)[0])))   # 2 = VNC Auth, 30 = ARD, 19 = VeNCrypt
EOF
```

"TigerVNC everywhere" was briefly the rule here and it was wrong: it
generalised a wayvnc constraint to the whole fleet, which cost the Windows and
Linux boxes their scaling and their cursor for no reason.

`vnc_connect.py` passes `-RemoteResize=0`, `-AlwaysCursor=1` and
`-CursorType=System`. TigerVNC otherwise asks the server to match the desktop to
the local window on every resize, and wayvnc on a headless Pi cannot resize its
output, so it refuses and the viewer logs `SetDesktopSize failed: 4` for the
rest of the session. `AlwaysCursor` defaults to **off**, and the symptom is
simply no visible pointer.

### Screen Sharing says "Unable to communicate", then asks for a password

That dialog is not a transport failure, despite its wording ("make sure the
remote computer is available and the firewall is not blocking screen sharing").
Apple's client makes a first connection, reads the auth challenge, hangs up,
then reopens with a password box. The scary dialog is what you see in between.

The VNC password is **not** the machine's login password. VNC Auth carries no
username at all - only a password - so there is no username field to hint that
an account password is the wrong thing to type. TightVNC keeps its own password
in `HKLM\SOFTWARE\TightVNC\Server`, set from its tray icon, and it is
unrelated to the Windows account. This cost an afternoon on 2026-09-21.

Two more things worth knowing before blaming the client:

- **VNC Auth uses only the first 8 characters** of the password. The DES key is
  8 bytes; anything past that is discarded by every implementation.
- Apple's client negotiates **RFB 003.003**, the oldest version, in which the
  server picks the security type unilaterally instead of offering a list.

Tell auth apart from transport without ever handling the password - the
response is DES-encrypted on the wire, and the verdict is a separate 4-byte
result. Proxy the connection and read only that:

```python
# 127.0.0.1:5999 -> the real server; point Screen Sharing at the proxy.
# b"\x00\x00\x00\x02" + 16 bytes  = VNC Auth selected, challenge sent
# 16 bytes from the client           = the auth response
# next 4 bytes from the server       = 0 is OK, 1 is AUTH FAILED
```

`1` means the password is wrong and everything else is fine. If instead the
client never sends 16 bytes, the problem really is the negotiation.

Check the transport separately, and do not trust the dialog for it: `lsof -nP
-i TCP@<host>` while connecting shows whether the socket reaches ESTABLISHED.
It did here, which ruled out the firewall and macOS Local Network permission
(`docs/setup_mac_workstation.md`) before any of them were touched.

The first connection to each Pi warns that the certificate is untrusted and
that `CN=raspberrypi` does not match the hostname. That is wayvnc's self-signed
certificate, generated per Pi by `wayvnc-generate-keys.service`. Accepting it
pins that key for the host, so it only asks once.

**macOS Screen Sharing cannot reach the Pis.** wayvnc offers only VeNCrypt (19),
RSA-AES (129) and RA2 (5); Screen Sharing speaks only VNC Auth (2) and Apple ARD
(30), so it fails at negotiation before asking for a password. This was found
the hard way on 2026-09-20 - the built-in client had been assumed sufficient.
TigerVNC speaks all of them, which is why the Pis - and only the Pis - launch
`vncviewer` from a Mac rather than `open vnc://`.

iOS has no free software VNC client: the only GPL-lineage app on the App Store
is paid and ships no iOS source. Reach a GPU host from an iPad with Moonlight
instead, which is GPL-3.0 and free on every platform. That covers RyzenWhite,
which already runs Sunshine. It does not cover the Pis or a login screen, which
is what this doc is for.

RealVNC appears nowhere on the fleet. It moved direct IP connections to its
Enterprise tier, leaving the free and Home tiers able to connect only through
RealVNC's own cloud.

## Screen scraping (x0vncserver)

Mirrors display `:0`, so it only shows something when a user is actually logged
in on the console. On a box with no monitor attached and GDM parked at the
greeter, it gives you the login screen at best, and usually just
`Invalid MIT-MAGIC-COOKIE-1 key` - the greeter's X authority is not yours. Use
the virtual desktop path instead on those machines.

### Install

```bash
sudo apt update
sudo apt remove realvnc-vnc-server realvnc-vnc-viewer # if real vnc already installed
sudo apt install tigervnc-scraping-server
mkdir -p ~/.vnc
tigervncpasswd
```

### Configure

```bash
sudo nano /etc/tigervnc/vncserver-config-defaults
```

Add or change the folling line to this:

```bash
$localhost = "no";
```

### Start

```bash
x0vncserver -passwordfile ~/.vnc/passwd -display :0
```

### Check Status

- To check if the service is running:

  ```bash
  sudo netstat -tuln | grep 5900
  ```

### To close

```bash
sudo pkill X0tigervnc
```

### To Start Automatically

Nothing here is hand-written any more — all three pieces are in the repo and
the autostart entry is deployed by the manifest:

| Piece | Where it lives |
| --- | --- |
| Start script | [`scripts/start_x0vncserver.sh`](../scripts/start_x0vncserver.sh) — backgrounds `x0vncserver` on display `:0`, appends to `~/x0vncserver.log`, writes `~/x0vncserver.pid` |
| Stop script | [`scripts/stop_x0vncserver.sh`](../scripts/stop_x0vncserver.sh) |
| Autostart entry | `application_configs/autostart/start_x0vncserver.desktop`, linked to `~/.config/autostart/start_x0vncserver.desktop` by manifest entry `vnc_autostart_desktop` |

The script bodies are deliberately **not** reproduced in this doc: a copy
drifts from the real script invisibly (one here had lost the `&`, so following
the doc gave you a start script that never returned).

So on a rebuilt machine, after the install and `tigervncpasswd` steps above:

```bash
cd ~/GitHub/dotfiles
uv run python src/deploy_configs.py
```

then log out and back in — autostart entries only run at session start. The
entry is host-filtered (EliteDesk today) in the personal overlay manifest,
because not every Linux box should answer on 5900; JasonZephyrus deliberately
does not. To add a machine, add its name to that entry's `hosts:` list. If its
checkout path or username is not `/home/jason/GitHub`, add a
`start_x0vncserver.<host>.desktop` variant next to the payload — `.desktop`
files take no placeholders, so `Exec=` is a literal path.

When that checkout path is itself a context identifier, the variant cannot sit
next to the public payload: the leak check refuses it, correctly. Put the
payload **and** its own host-filtered entry in that context's credentials repo
instead, replacing this entry on that host rather than overriding it — the same
shape the per-context VS Code workspace entries already use. Nothing about the
mechanism changes; only the file holding the literal `Exec=` moves.

### The `-localhost` default changed, so the script sets it

`x0vncserver` binds `0.0.0.0:5900` under tigervnc 1.12 and `127.0.0.1:5900`
under 1.15. Nothing warns you: the log still says
`New X0tigervnc server ... on port 5900` either way, the process is running and
healthy, and the only symptom is that every remote viewer gets connection
refused. An OS upgrade crossing that version boundary therefore turns remote
VNC off silently.

`scripts/start_x0vncserver.sh` passes `-localhost=0` explicitly so both
versions behave the same. Note the `=0` form — `-localhost no` is not valid
syntax for `x0vncserver` and it exits on it.

Check which one you actually got, rather than trusting the log:

```bash
ss -tlnp | grep 5900
```

`0.0.0.0:5900` is reachable; `127.0.0.1:5900` is not.

- To check status:

```bash
sudo netstat -tuln | grep 5900
```

## Virtual desktop, headless (Xtigervnc)

For a machine with no monitor and no console login - NukBuntu. `vncserver`
starts its own X server on its own display, so there is no `:0` to attach to
and no Xauthority to borrow.

### Install

```bash
sudo apt update
sudo apt install tigervnc-standalone-server
mkdir -p ~/.vnc
tigervncpasswd
```

`tigervnc-standalone-server` is deliberately not in `app_lists/linux_apps.txt`:
that list installs on every Linux box, and not every Linux box should answer on
a VNC port.

### Deploy the unit and session

| Piece | Where it lives |
| --- | --- |
| systemd user unit | `application_configs/systemd/vncserver@.service`, linked to `~/.config/systemd/user/vncserver@.service` by manifest entry `vnc_virtual_desktop_unit` |
| Session startup | `application_configs/vnc/xstartup`, linked to `~/.vnc/xstartup` by manifest entry `vnc_virtual_desktop_xstartup` |

```bash
cd ~/GitHub/dotfiles
uv run python src/deploy_configs.py
```

### Enable

A user unit normally dies with the last session, which for a headless box means
it dies when you close SSH. Lingering is what keeps it up across reboots with
nobody logged in:

```bash
loginctl enable-linger jason
systemctl --user daemon-reload
systemctl --user enable --now vncserver@1
```

`@1` is the display number, so this listens on **5901**. Point TigerVNC Viewer at
`<host>:5901`, not the bare IP - a bare IP means 5900, which nothing is serving.

### Check

```bash
systemctl --user status vncserver@1
ss -lntp | grep 590
```

From another machine:

```bash
nc -z -G 2 <host> 5901 && echo open
```

### Stop

```bash
systemctl --user stop vncserver@1        # this boot
systemctl --user disable --now vncserver@1   # and across reboots
```

### Notes

- Geometry and depth are baked into `ExecStart` in the unit. Change them there
  and `daemon-reload`, not in a local copy.
- `-localhost no` is what makes it reachable off-box; TigerVNC binds loopback
  only by default. VncAuth means the `~/.vnc/passwd` blob is the only gate, so
  this belongs on the LAN, not on anything port-forwarded.
- No firewall work is needed on NukBuntu - ufw is disabled there.

## Install TightVNC on Windows

- Follow instructions in [setup_windows_chocolatey.md](setup_windows_chocolatey.md)

- Install TightVNC using Chocolatey:

```powershell
choco install tightvnc
```

- Open the application from the start menu `TightVNC Control Interface`

- Set a primary password, be careful as it will stop accepting new characters

- Connect using a VNC Client and this machine's IP Address
