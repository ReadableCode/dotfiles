# raspberrypi4a: still on the 2023 Foundation kernel, not the Debian one

    found:  2026-09-20
    status: open
    verify: ssh pi@192.168.86.22 'uname -r; dpkg -l | awk "/^ii/ && /linux-image|raspberrypi-kernel/ {print \$2}"'

raspberrypi4a runs **6.1.21-v8+** from 2023 while every other Pi on trixie runs
6.18.x. It kept `raspberrypi-kernel 1:1.20230405-1`, the Foundation package that
stopped being updated after bullseye, and never picked up `linux-image-rpi-v8`,
the Debian meta-package trixie uses. Both release upgrades went straight past
it.

Everything works. The old kernel supports KMS fine once `dtoverlay=vc4-kms-v3d`
is set (it was not, which is what made wayvnc show a grey screen until
2026-09-20), so the desktop, wayvnc and Docker are all healthy on it.

## Evidence

    pi4a   kernel=6.1.21-v8+        kernel pkg: raspberrypi-kernel
    pi3    kernel=6.18.50+rpt-rpi-v8  kernel pkgs: linux-image-rpi-v8 ...
    pi4    kernel=6.18.29+rpt-rpi-v8  kernel pkgs: linux-image-rpi-v8 ...

`/boot/firmware/kernel8.img` on pi4a is dated 2023-05-09.

## fix

    ssh pi@192.168.86.22 'sudo apt-get install -y linux-image-rpi-v8 raspi-firmware'
    # then reboot and confirm uname -r reports 6.18.x

## blast radius

**This is the risky one, and the reason it is here rather than done.** It
replaces the kernel and rewrites `/boot/firmware`. pi4a's case is permanently
sealed, so the SD card cannot be removed, and it has no monitor or keyboard: if
it does not boot there is no recovery path at all. Its boot partition has
already been relocated once (`/boot` -> `/boot/firmware`, 2026-09-19).

Do not attempt this without a way back - a spare screen on the HDMI port, or
accepting the box may be lost. `/boot/firmware/config.txt.pre-kms.bak` is the
only backup currently on it.

## not doing yet

No benefit that is worth an unrecoverable boot risk. The box is fully working
on the old kernel. Worth doing only alongside something that gives physical
access, or if a future package genuinely requires 6.12+.
