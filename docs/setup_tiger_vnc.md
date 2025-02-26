# Setup Tiger VNC (Headless)

- This method is not supported for Wayland.

## Linux

### Install Tiger VNC Linux

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

- Create the startup script:

```bash
nano /home/jason/GitHub/dotfiles/scripts/start_x0vncserver.sh
```

- Add the following:

```bash
#!/bin/bash
printf '%.0s#' {1..100} >> /home/jason/x0vncserver.log
echo $(date) >> /home/jason/x0vncserver.log
/usr/bin/x0vncserver -passwordfile /home/jason/.vnc/passwd -display :0 >> /home/jason/x0vncserver.log 2>&1
echo $! > /home/jason/x0vncserver.pid
exit 0
```

- Create the stop script:

```bash
nano /home/jason/GitHub/dotfiles/scripts/stop_x0vncserver.sh
```

- Add the following:

```bash
#!/bin/bash
sudo pkill X0tigervnc
```

- Make executable:

```bash
chmod +x /home/jason/GitHub/dotfiles/scripts/start_x0vncserver.sh
chmod +x /home/jason/GitHub/dotfiles/scripts/stop_x0vncserver.sh
```

- Make a desktop script to run on startup:

```bash
nano ~/.config/autostart/start_x0vncserver.desktop
```

- Add the following:

```bash
[Desktop Entry]
Type=Application
Exec=/home/jason/GitHub/dotfiles/scripts/start_x0vncserver.sh
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Start x0vncserver
Comment=Start x0vncserver on startup
```

- Make executable:

```bash
chmod +x ~/.config/autostart/start_x0vncserver.desktop
```

- To check status:

```bash
sudo netstat -tuln | grep 5900
```

## Windows (using tight vnc instead)

### Set up Chocolatey using doc

- [Chocolatey](./setup_windows_chocolatey.md)

### Install Tight VNC Windows

```powershell
choco install tightvnc
```

- Open the application from the start menu `TightVNC Control Interface`

- Set a primary password, be careful as it will stop accepting new characters

- Connect using a VNC Client and this machine's IP Address
