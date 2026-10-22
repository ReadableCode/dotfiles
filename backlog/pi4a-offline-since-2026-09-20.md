# raspberrypi4a: offline since 2026-09-20, powered off or not booting

    found:  2026-10-22
    status: open
    verify: ping -c2 192.168.86.22; tailscale status | grep raspberrypi4a

raspberrypi4a (192.168.86.22, Pi 4 Model B, boots from the SD card sealed in
its case, no SSD) has not been on the network for a month. Nothing answers at
its address, not even ARP, so it is off or stuck before the network comes up;
it is not an ssh or tailscale fault.

Evidence, 2026-10-22:

    ping 192.168.86.22                 100.0% packet loss
    elitedesk: ip neigh 192.168.86.22  INCOMPLETE
    tailscale: raspberrypi4a           offline, last seen 31d ago
    k3s: last heartbeat                2026-09-20T23:43:35Z

The last heartbeat is the evening of the day its boot config was changed:
`dtoverlay=vc4-kms-v3d` was added to `/boot/firmware/config.txt` on
2026-09-20 to fix wayvnc's grey screen, a day after `/boot` was moved to
`/boot/firmware` (see pi4a-old-foundation-kernel). A boot that fails after
that edit fits the timing, but nothing confirms it; a power loss fits too.

## fix

In person:

1. Power LED on? If not, check the supply and the outlet.
2. Plug a screen into its HDMI port (micro-HDMI 0) and power cycle it; read
   where boot stops.
3. If it stops at the firmware or kernel, the change to undo is the KMS
   overlay: the case is sealed, so boot it with a keyboard and screen, or
   accept that it may be lost. `/boot/firmware/config.txt.pre-kms.bak` is the
   pre-change copy on the card.

Once it is back on the network:

    ssh pi@192.168.86.22 'sudo /usr/local/bin/k3s-agent-uninstall.sh'

then delete the Docker backlog entry k3s-cluster-still-running.

## blast radius

None from looking. Whatever it served (its desktop over wayvnc, its Docker
containers) has been down since 2026-09-20 already.

## not doing yet

Needs hands on the machine and a screen; nothing remote reaches it.
