# Debian / Raspberry Pi OS release upgrades

`scripts/my_updater.sh` does these, through `debian_release_upgrade()`. This
page is the list of things that went wrong doing it for real on 2026-09-19, so
the next run does not rediscover them.

Run it the normal way. There is no separate command:

```bash
myupdater
```

It upgrades packages on the current release first (a Debian upgrade requires
that), then offers the release step, then verifies the result.

## How it is meant to go

1. **Ceiling.** The host's inventory entry declares how far it may go:
   `updater: { release_ceiling: { debian: "13" } }`. No ceiling, no upgrade -
   an unknown ceiling means don't move.
2. **One release at a time.** Debian supports n -> n+1 only. 11 -> 13 is two
   runs with a reboot between, never one jump.
3. **Source preflight.** Every apt source naming the current codename is
   probed for the target suite *before* anything is rewritten, and a single
   miss aborts with the URL named. This is the check that stops a machine
   being stranded with no resolvable packages.
4. **Rewrite and upgrade.** Each source file is backed up as
   `<file>.<codename>.bak`, then the codename is replaced.
5. **Verify.** `debian_upgrade_verify()` refuses to call it done unless every
   package is configured, sshd parses and is enabled, and `raspi-firmware`
   (where present) is `ii`.
6. **Reboot**, by hand, once verify passes.

## The pitfalls

### A failed full-upgrade leaves the machine unbootable and says nothing

The big one. On both pi3a and pi4a the trixie `full-upgrade` stopped partway
and left **~490 packages** unpacked-but-unconfigured, including `systemd`,
`udev`, `openssh-server`, `libc-bin` and `python3`. `apt-get` exited non-zero
and that was the only signal. A reboot there is how a box does not come back.

`debian_upgrade_verify()` now catches this, and the upgrade retries once
(`dpkg --configure -a`, `-f install`, `full-upgrade`) before reporting. Check
it by hand with:

```bash
dpkg -l | awk 'NR>5' | grep -vE '^(ii|rc)'
```

`rc` means removed-but-configured and is normal after any upgrade. Anything
else is not.

### A file owned by two packages stops the whole transaction

What actually caused the above:

```
trying to overwrite '/usr/lib/aarch64-linux-gnu/lxpanel/plugins/batt.so',
which is also in package lxplug-batt (0.23)
```

Trixie's `lxpanel` ships plugin files that the Raspberry Pi archive's obsolete
`lxplug-*` packages also own. One collision blocked `libglib2.0-0t64`, and
everything depending on it cascaded.

**Remove the obsolete package, do not force the overwrite.** On Pi OS the
`lxplug-*` set is superseded by `wfplug-*`, which trixie installs anyway:

```bash
sudo apt-get remove -y $(dpkg -l | awk '/lxplug/ {print $2}')
sudo dpkg --configure -a
sudo apt-get -f install
```

`--force-overwrite` papers over the collision and leaves two packages claiming
one file. It is also, correctly, the kind of flag an agent will be blocked
from running.

### bookworm moved the boot partition, and raspi-firmware fails silently

On a Pi upgraded from bullseye, the FAT partition is still mounted at `/boot`,
but bookworm's `raspi-firmware` expects `/boot/firmware`:

```
Error: missing /boot/firmware, did you forget to mount it?
dpkg: error processing package raspi-firmware (--configure)
```

The package goes `iF` and the new kernel never reaches the boot partition.
Fix, on pi4a's real PARTUUID - read yours from `/etc/fstab` first:

```bash
sudo cp -n /etc/fstab /etc/fstab.bullseye.bak
sudo umount /boot
sudo mkdir -p /boot/firmware
sudo sed -i 's|^\(PARTUUID=<boot-partuuid>[[:space:]]\+\)/boot\([[:space:]]\)|\1/boot/firmware\2|' /etc/fstab
sudo systemctl daemon-reload
sudo mount /boot/firmware
sudo dpkg --configure -a
```

Unmounting `/boot` does **not** risk the boot: the Pi's bootloader reads the
FAT partition directly off the card, so where Linux mounts it is irrelevant.
Anchor the `sed` to the boot PARTUUID so the root entry cannot be touched.

### The reboot window is long, and looks exactly like a lockout

pi4a answered ICMP and served its Docker containers on 80/443 for **over ten
minutes** after the reboot was issued, with sshd already stopped. That is a
slow shutdown, not a failed boot, and it is easy to misdiagnose - it was
misdiagnosed on the day.

Wait for the machine, and confirm with `uptime -s` afterwards. If `uptime -s`
is later than when you were scanning, you were watching it shut down.

### An auto-revert timer will eat an interactive login

Arming a `systemd-run --on-active=NNmin` rollback before `tailscale up` is
sound, but the timer fired three times before the auth URL was clicked and
tore tailscaled down each time. Either allow a generous window or cancel the
timer once the change itself is proven safe.

### Third-party sources without a codename are invisible to the preflight

The preflight only probes sources naming the current codename. Sources that
pin a bare suite (`stable`, `release`) are neither rewritten nor checked, so
their problems surface mid-upgrade instead:

- grafana's signing key had expired (`EXPKEYSIG 963FA27710458545`)
- syncthing's source named component `release`, which does not exist

Neither blocks an upgrade, but both mean those repos have quietly not updated
for a long time. Worth an `apt-get update` and a read of the warnings before
starting.

### Watch out for the shell, not just the machine

Two self-inflicted ones worth remembering:

- `pgrep -f apt-get` **matches your own ssh command line**, so it never reports
  idle. Test `sudo fuser /var/lib/dpkg/lock-frontend` instead.
- `pkill -f <pattern>` has the same flaw with teeth: if the pattern appears
  anywhere in the ssh command you are running, `pkill` **kills your own
  session**, and everything after it in that command never runs. The output
  simply stops mid-script, which reads like the machine died. Kill by PID (the
  service's own pid file) or match the executable with `pkill -x <name>`.
- `!` in a double-quoted `awk` sent through `tmux send-keys` hits bash history
  expansion (`-bash: !~: event not found`) and the command silently never runs.
  Put anything non-trivial in a script file and run that.
