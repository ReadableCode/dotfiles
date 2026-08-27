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

The script bodies are deliberately **not** reproduced in this doc. They used to
be, and the copy here had already drifted from the real script (it was missing
the `&`, so following the doc gave you a start script that never returned).

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

`@1` is the display number, so this listens on **5901**. Point VNC Viewer at
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
