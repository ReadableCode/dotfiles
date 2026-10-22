# nukbuntu: 85 OS packages behind and a reboot pending

    found:  2026-10-22
    status: open
    verify: ssh jason@192.168.86.139 'apt list --upgradable 2>/dev/null | grep -vc Listing; ls /var/run/reboot-required 2>&1; uptime -p'

nukbuntu (Ubuntu 24.04.4 LTS, the observability node) has its containers,
repos and dotfiles on automatic loops, but its OS packages only move when
someone runs `myupdater`, and nothing schedules that. unattended-upgrades is
enabled, so security updates land, and one of them is waiting on a reboot;
everything else waits for a manual run.

Evidence, 2026-10-22:

    apt list --upgradable         85
    /var/run/reboot-required      present
    systemctl is-enabled unattended-upgrades   enabled
    uptime                        up 3 weeks, 2 days

## fix

From Envy:

    ssh -t jason@192.168.86.139 'bash -ic myupdater'
    ssh -t jason@192.168.86.139 'sudo reboot'

`myupdater` (`src/refresh_machine.py --packages`) upgrades the packages, then
pulls, clones and deploys; it asks before any repair or release upgrade.

## blast radius

The reboot stops monitoring and logging for a minute or two: uptime-kuma,
prometheus, loki, the syslog receiver (behemoth's forwarded logs are dropped
while it is down) and the `backups` Samba share. Every container comes back
on its own (`restart: unless-stopped`).

## not doing yet

Needs sudo with a password on nukbuntu, so it is yours to run. Whether
nukbuntu should run `myupdater` on a schedule is a separate decision: no
machine does today, by design, because it can prompt.
