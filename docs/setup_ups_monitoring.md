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

### Setup upsmon to use upssched and to send the selected events

Add / edit in /etc/nut/upsmon.conf (ensure lines exist and are not duplicated):

```bash
RUN_AS_USER nut
NOTIFYCMD /sbin/upssched
NOTIFYFLAG ONBATT EXEC
NOTIFYFLAG ONLINE EXEC
NOTIFYFLAG LOWBATT EXEC
NOTIFYFLAG SHUTDOWN EXEC

MONITOR cyberpower@localhost 1 monuser YOUR_PASSWORD master
```

### Map events to actions

create upssched.conf to map events → actions
Create /etc/nut/upssched.conf:

```ini
CMDSCRIPT /etc/nut/upssched-cmd
PIPEFN /var/run/nut/upssched.pipe
LOCKFN /var/run/nut/upssched.lock

# --- Immediate notifications ---
# Run the script right away when going on battery
AT ONBATT * EXECUTE went-on-battery
# Run the script right away when power returns
AT ONLINE * EXECUTE power-restored

# --- Timer logic (grace periods) ---
# When going on battery, start a 30s timer named onbatt
AT ONBATT * START-TIMER onbatt 30
# If power returns, cancel that timer
AT ONLINE * CANCEL-TIMER onbatt

# Start a 5-minute timer for early shutdown
AT ONBATT * START-TIMER earlyshutdown 300
AT ONLINE * CANCEL-TIMER earlyshutdown

# --- Critical cases ---
# If battery gets low, run the shutdown routine immediately
AT LOWBATT * EXECUTE emergency-shutdown
# If upsmon itself enters shutdown, run the shutdown routine
AT SHUTDOWN * EXECUTE emergency-shutdown
```

- Restart nut monitor

```bash
sudo systemctl restart nut-monitor
```

- To check the logs of the service

```bash
sudo journalctl -u nut-monitor
```

### Setup Users

- Edit /etc/nut/upsd.users to add a user with appropriate permissions. For example:

```ini
[monuser]
    password = YOUR_PASSWORD
    actions = SET
    instcmds = ALL
    upsmon master
```

### Command dispatcher script

write the command dispatcher script (CMDSCRIPT) that upssched will call
Create /etc/nut/upssched-cmd (make executable chmod 755 /etc/nut/upssched-cmd). Minimal example:

```bash
sudo nvim /etc/nut/upssched-cmd
```

- Put in the contents:

```bash
#!/bin/sh
# upssched-cmd: called by upssched with one argument = command name (e.g. emergency-shutdown)
echo "[$(date)] $0 $1" >> /tmp/upssched-test.log
echo "[$(date)] CMD=$1 USER=$(whoami)" >> /tmp/upssched-debug.log
CMD="$1"
case "$CMD" in
  onbatt)
    logger -t upssched "ONBATT timer expired"
    ;;
  went-on-battery)
    logger -t upssched "Power lost (ONBATT)"
    /usr/bin/python3 /etc/nut/power_shutdown_stage_1.py "$CMD" 2>&1 | logger -t upssched-python
    ;;
  power-restored)
    logger -t upssched "Power restored (ONLINE)"
    /usr/bin/python3 /etc/nut/power_shutdown_stage_1.py "$CMD" 2>&1 | logger -t upssched-python

    ;;
  emergency-shutdown)
    logger -t upssched "Triggering cluster shutdown"
    /usr/bin/python3 /etc/nut/power_shutdown_stage_1.py "$CMD" 2>&1 | logger -t upssched-python
    ;;
  *)
    logger -t upssched "Unknown upssched-cmd: $CMD"
    ;;
esac
```

- Set the permissions, upssched runs as the user defined by RUN_AS_USER in upsmon.conf (default root or nut). Ensure that user can execute /etc/nut/upssched-cmd and your Python script and can create/write the pipe/lock paths (or put them somewhere writable by that user).

```bash
sudo chmod 755 /etc/nut/upssched-cmd
```

### Create the python script

```bash
sudo nvim /home/pi/GitHub/Assistant/scripts/power_shutdown_stage_1.py
```

- Put in the contents (example):

```python
#!/usr/bin/env python3
import datetime
import sys

# NUT calls your script with the command name as the first argument
event = sys.argv[1] if len(sys.argv) > 1 else "UNKNOWN"

with open("/etc/nut/power_shutdown_stage_1.log", "a") as f:
    f.write(f"[{datetime.datetime.now()}] Event: {event}\n")
    f.flush()
```

- Make it executable

```bash
sudo chmod +x /home/pi/GitHub/Assistant/scripts/power_shutdown_stage_1.py
```

- Hard link it into place

```bash
sudo ln /home/pi/GitHub/Assistant/scripts/power_shutdown_stage_1.py /etc/nut/power_shutdown_stage_1.py
```

### Create the log file and make it writable

```bash
sudo touch /etc/nut/power_shutdown_stage_1.log
sudo chown root:root /etc/nut/power_shutdown_stage_1.log
sudo chmod 666 /etc/nut/power_shutdown_stage_1.log
```

### Testing

```bash
sudo /etc/nut/upssched-cmd emergency-shutdown
```
