#!/usr/bin/env python3
import datetime
import sys

# NUT calls your script with the command name as the first argument
event = sys.argv[1] if len(sys.argv) > 1 else "UNKNOWN"

with open("/etc/nut/power_shutdown_stage_1.log", "a") as f:
    f.write(f"[{datetime.datetime.now()}] Event: {event}\n")
    f.flush()
