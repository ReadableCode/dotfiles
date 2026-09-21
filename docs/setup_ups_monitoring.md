# Setup NUT (Network UPS Tools) on the UPS pis

raspberrypi3 and raspberrypi3a each have a CyberPower UPS on their USB port
and run NUT for it. An outage goes UPS -> upsmon -> upssched ->
`/etc/nut/upssched-cmd` -> `Assistant/src/power_shutdown_stage_1.py`, which
posts to the ntfy topic `house_power`. raspberrypi3a's UPS is straight off
the mains and pages first; raspberrypi3's is fed by another UPS, so it only
goes on battery once that one is exhausted and is the "getting serious"
page.

Every file under `/etc/nut` and the pull loop that keeps them current come
from the repos through the personal manifest, so nothing below is typed on a
pi. The only manual steps are installing the packages and running the first
deploy.

## What deploys where

`personal_credentials/personal_manifest.yaml`, section "UPS pis", entries
with `method: system` (root-owned copies through `sudo -n`, content-hashed,
each with a reload; see `docs/repo_deploy_configs.md`):

| /etc/nut file | Repo file | Owner, mode | Reload |
|---|---|---|---|
| `nut.conf` | `server_configs/system_configs/raspbian/nut/nut.conf` | root:nut 0640 | restart the driver, upsd and upsmon |
| `ups.conf` | `.../raspbian/nut/ups.<host>.conf` (per-host variant) | root:nut 0640 | same |
| `upsd.users` | `personal_credentials/nut/upsd.users` (password) | root:nut 0640 | restart upsd |
| `upsmon.conf` | `personal_credentials/nut/upsmon.conf` (password) | root:nut 0640 | restart upsmon |
| `upssched.conf` | `.../raspbian/nut/upssched.conf` | root:root 0644 | none, read per event |
| `upssched-cmd` | `.../raspbian/nut/upssched-cmd` | root:root 0755 | none, read per event |

The same section installs `gitpullall.service` and `gitpullall.timer` from
`server_configs/system_configs/raspbian/systemd/` into `/etc/systemd/system`:
every 15 minutes the pi pulls every repo, clones, syncs envs, deploys and
prunes as user pi (`docs/homelab_deployments.md`, "Cron"). That deploy is
what installs the NUT files above and the timer itself.

The Assistant script needs the `Assistant` checkout with its venv synced
(`sync_python_envs.py` does that on every loop) and its `.env` link to
`personal_credentials/personal.env` for the ntfy credentials.

## Bringing up a pi

```bash
sudo apt update
sudo apt install -y nut nut-server nut-client
lsusb        # the UPS should be listed; ups.<host>.conf names its model
```

Then one `gitpullall` by hand. The deploy installs the six NUT files,
restarts the units through their reloads, installs the timer and enables it,
and from there the loop runs itself. Check:

```bash
upsc cyberpower@localhost ups.status        # OL, or OB DISCHRG on battery
systemctl status nut-server nut-monitor gitpullall.timer
uv run python src/deploy_configs.py status  # every nut_* and gitpullall_* row OK
```

## Testing the notification path

Fire one ONLINE event through upssched as pi, exactly as upsmon would. It
runs the power-restored branch of `upssched-cmd` and no timers, so it costs
one ntfy message:

```bash
sudo -u pi env NOTIFYTYPE=ONLINE UPSNAME=cyberpower@localhost /sbin/upssched
journalctl --since "1 min ago" -t upssched -t upssched-python
tail -2 ~/GitHub/Assistant/logs/power_shutdown_stage_1.log
```

A real outage logs `Power lost (ONBATT)`, then `ONBATT timer expired` after
30 seconds and `5 minutes on battery` after five, each with its own ntfy
message, then `Power restored (ONLINE)`.

## Why it is built this way

- **Copies, not links.** upsd and the driver run as user `nut`, which cannot
  follow a link into pi's `0700` home, and dpkg treats every `/etc/nut/*.conf`
  as a conffile. A root-owned copy the deploy re-installs on drift survives
  both.
- **`RUN_AS_USER pi`.** upssched and `upssched-cmd` run as pi so they can
  reach the Assistant venv under `/home/pi`. upsmon's root parent still reads
  `upsmon.conf`, so that file can stay 0640. `upssched.conf` must be readable
  by pi, hence 0644: the trixie package's 0640 root:nut on it is what silenced
  the 2026-09-21 outage (`Can't open /etc/nut/upssched.conf: Permission
  denied` while upsmon kept running).
- **Pipe in /tmp.** The package puts upssched's pipe under `/run/nut/`, which
  is nut:nut 0770, so as pi the timer daemon never started (`Failed to
  connect to parent and failed to create parent: Permission denied` on every
  outage through 2026-08) and the 30-second and 5-minute timers never fired.
  `PIPEFN` and `LOCKFN` point at `/tmp`, which pi can write and
  nut-monitor.service does not privatise.
- **Release upgrades.** The trixie upgrade offered the maintainer's version of
  every edited conffile; on raspberrypi3 that installed `MODE=none` and the
  UPS went unmonitored for two days. Take the local version at the prompt, or
  just let the next loop re-install the repo copies; either way the repo
  files win.
