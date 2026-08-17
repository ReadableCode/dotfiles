# Setup Tiger VNC (Headless)

- This method is not supported for Wayland.

## Linux

### Install Tiger VNC on Linux

```bash
sudo apt update
sudo apt remove realvnc-vnc-server realvnc-vnc-viewer # if real vnc already installed
sudo apt install tigervnc-scraping-server
mkdir -p ~/.vnc
tigervncpasswd
```

### Configure Tiger VNC

```bash
sudo nano /etc/tigervnc/vncserver-config-defaults
```

Add or change the folling line to this:

```bash
$localhost = "no";
```

### Start Tiger VNC

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

## Install TightVNC on Windows

- Follow instructions in [setup_windows_chocolatey.md](setup_windows_chocolatey.md)

- Install TightVNC using Chocolatey:

```powershell
choco install tightvnc
```

- Open the application from the start menu `TightVNC Control Interface`

- Set a primary password, be careful as it will stop accepting new characters

- Connect using a VNC Client and this machine's IP Address
