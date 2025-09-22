# Setup NUT (Network UPS Tools)

## Setup on Linux (raspberry pi)

### Installing NUT (Network UPS Tools)

```bash
sudo apt update
sudo apt install -y nut nut-server nut-client
```

### Define the UPS in /etc/nut/ups.conf

- To get the info to fill this in, you can run:

```bash
lsusb
```

- Edit the file `/etc/nut/ups.conf` and add your UPS configuration. For example:

```ini
[cyberpower]
    driver = usbhid-ups
    port = auto
    desc = "CyberPower CP850PFCLCDa"
```

- or

```ini
[cyberpower]
    driver = usbhid-ups
    port = auto
    desc = "Cyber Power System, Inc. PR1500LCDRT2U UPS
```

### Configure NUT

- Edit `/etc/nut/nut.conf` and set the mode to `standalone`:

```ini
MODE=standalone
```

### Enable and start

```bash
sudo systemctl enable nut-server
sudo systemctl enable nut-monitor

sudo systemctl start nut-server
sudo systemctl start nut-monitor

```

### Check the current status

- You can check the status of your UPS with:

```bash
upsc cyberpower@localhost
```
