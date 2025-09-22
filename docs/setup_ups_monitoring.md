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
RUN_AS_USER root
NOTIFYCMD /sbin/upssched
NOTIFYFLAG ONBATT EXEC
NOTIFYFLAG ONLINE EXEC
NOTIFYFLAG LOWBATT EXEC
NOTIFYFLAG SHUTDOWN EXEC
```

### Map events to actions

create upssched.conf to map events → actions
Create /etc/nut/upssched.conf:

```ini
CMDSCRIPT /etc/nut/upssched-cmd
PIPEFN /var/run/nut/upssched.pipe
LOCKFN /var/run/nut/upssched.lock

# example behavior:
# when going on battery, start a 30s timer named onbatt
AT ONBATT * START-TIMER onbatt 30
# if power returns, cancel the timer
AT ONLINE * CANCEL-TIMER onbatt
# if timer expires or low battery, execute immediate action
AT LOWBATT * EXECUTE emergency-shutdown
AT ONBATT * START-TIMER earlyshutdown 300
AT ONLINE * CANCEL-TIMER earlyshutdown
AT SHUTDOWN * EXECUTE emergency-shutdown
```

### Command dispatcher script

write the command dispatcher script (CMDSCRIPT) that upssched will call
Create /etc/nut/upssched-cmd (make executable chmod 755 /etc/nut/upssched-cmd). Minimal example:

```bash
#!/bin/sh
# upssched-cmd: called by upssched with one argument = command name (e.g. emergency-shutdown)
CMD="$1"
case "$CMD" in
  onbatt)
    logger -t upssched "ONBATT timer expired"
    ;;
  emergency-shutdown)
    logger -t upssched "Triggering cluster shutdown"
    # call your python controller here (replace with full path)
    /usr/local/bin/cluster_shutdown.py --reason nut_lowbat
    ;;
  *)
    logger -t upssched "Unknown upssched-cmd: $CMD"
    ;;
esac
```

permissions & ownership
upssched runs as the user defined by RUN_AS_USER in upsmon.conf (default root or nut). Ensure that user can execute /etc/nut/upssched-cmd and your Python script and can create/write the pipe/lock paths (or put them somewhere writable by that user).

reload/restart and test flow

sudo systemctl restart nut-server nut-monitor

# trigger test by simulating an event

sudo -u <run_as_user> /sbin/upssched test ONBATT cyberpower

# or use upsschedctl to force timers

sudo upsschedctl start onbatt 5

Check /var/log/syslog or journalctl -t upssched for messages from upssched and upssched-cmd.

notes / tips (brief)

Use START-TIMER name seconds to delay action so you can cancel if power returns.

Use EXECUTE name to call your CMDSCRIPT immediately.

Keep the CMDSCRIPT tiny and let your robust Python program handle SSH + shutdown logic.

Test with upssched test and upsschedctl before relying on real battery events.

That’s it — wire upsmon → upssched → /etc/nut/upssched-cmd → your Python script. Tell me the exact path of your Python caller and the RUN_AS_USER if you want the single-line test command to exercise it.
