# raspberrypi0: the SD card is failing and the box cannot install anything

    found:  2026-09-19
    status: open
    verify: ssh pi@192.168.86.14 'sudo dmesg | grep -c "I/O error"; apt-cache policy curl'

raspberrypi0 (192.168.86.14) answers ssh and looks alive, but its storage is
dying. `apt-cache` and `apt-get update` both terminate with a **bus error**,
so no package can be queried or installed, and its apt lists have been frozen
since 2026-04-12. It is the only Pi still on bullseye and the only one with no
uv, no tailscale and no current dotfiles checkout, entirely because of this.

## Evidence

Repeated read failures against the same sector of the card:

    [13841693.008576] I/O error, dev mmcblk0, sector 1065488 op 0x0:(READ) flags 0x0 phys_seg 1 prio class 2
    [13841723.728627] I/O error, dev mmcblk0, sector 1065488 op 0x0:(READ) ...
    [13841755.089478] I/O error, dev mmcblk0, sector 1065488 op 0x0:(READ) ...

277 storage errors in dmesg at the time of writing. apt itself dies rather
than reporting a problem:

    bash: line 1: 13402 Bus error               apt-cache policy curl
    bash: line 3: 13452 Bus error               sudo apt-get update > /dev/null 2>&1

Clearing `/var/cache/apt/*.bin` (the usual fix for a corrupt apt cache) did
not help, which is what rules out software corruption and points at the card.

Its filesystem was created 2022-04-04, so the card has roughly four and a half
years on it.

## fix

New SD card, then reimage. This is hands-on work; there is no remote path,
because the box cannot install the tools that would let it help itself.

Worth capturing what is on it before the card is replaced:

    ssh pi@192.168.86.14 'ls ~/GitHub; crontab -l; systemctl list-units --state=running --no-legend'

## blast radius

None until the card is swapped. Leave it running if it is doing something
useful; reads from good sectors still work. Do NOT attempt a release upgrade
or any large write on it — rewriting the filesystem on a card with read errors
is how it becomes unrecoverable.

## not doing yet

Needs hardware and physical access. Explicitly parked on 2026-09-19: the
decision was to leave pi0 alone until a new card is available rather than risk
finishing it off.
