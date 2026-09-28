# behemoth: the drive pulled from disk5 may be good, and has not been tested

    found:  2026-09-28
    status: open
    verify: grep -c "it has not been retested" docs/homelab_unraid_drives.md   # 1 means still open

`WD-WCC7K4NHXD19` (4tb wd WD40EFRX) was disabled by unraid on 2026-09-21 and
replaced on 2026-09-23. The fault turned out to be the sata power splitter
feeding its bay, not necessarily the drive. It is out of the server and
nobody has tested it, so it is neither a known spare nor known scrap.

## Evidence

How it failed, 2026-09-21 07:47:33, on writes:

    disk5      DISK_DSBL    sdd    errors=308    WDC_WD40EFRX-68N32N0_WD-WCC7K4NHXD19
    ata5.00: status: { DRDY DF ERR }   error: { ABRT }
    [sdd] ASC=0x44 ASCQ=0x0          <- internal target failure

Its own SMART counters, read after the failure, showed no media damage:

    Reallocated_Sector_Ct    0
    Current_Pending_Sector   0
    Offline_Uncorrectable    0
    UDMA_CRC_Error_Count     0

The drive that replaced it, in the same bay on the same splitter, then lost
power hundreds of times. `ZZ30MKQY` went from a power cycle count of 3 to 578
in 33 power-on hours while the server stayed up. The splitter was replaced on
2026-09-26 and the count has not moved since, through a 22 hour rebuild that
finished clean on 2026-09-27. Full record in `docs/homelab_unraid_drives.md`.

A drive that loses power mid-write aborts the command, which is what the
kernel logged. That fits a good drive on a bad feed. It does not prove it:
the old drive's own power cycle count was never recorded, and a drive can be
damaged by repeated power loss.

## fix

The drive failed on writes and passed SMART, so a read-only SMART test alone
proves nothing. It needs a full write and read-back.

behemoth has no spare bay. Use a usb sata dock on any linux machine, or a free
sata port on behemoth with the drive sitting outside a bay. Address the drive
by serial, never by `sdX`; on behemoth a wrong letter is an array disk.

    ls /dev/disk/by-id/ | grep WCC7K4NHXD19 | grep -v part   # ata-... on a sata port, usb-... in a dock
    D=/dev/disk/by-id/<the name that printed>
    smartctl -A $D | grep -E "^ *(5|12|197|198|199) "      # note attribute 12 before starting
    badblocks -wsv -b 4096 -o /tmp/nhxd19.bad $D           # four patterns written and read back
    smartctl -t long $D                       # then the drive's own surface scan
    smartctl -l selftest $D                   # when it finishes
    smartctl -A $D | grep -E "^ *(5|12|197|198|199) "

In a usb dock `smartctl` may need `-d sat` to reach the drive. These commands
were written without the drive attached, so treat the first run as the test of
the procedure too.

Good means: `badblocks` reports 0 bad blocks, the long test completes without
error, attributes 5, 197, 198 and 199 are still 0, and attribute 12 rose only
by the times the drive was actually plugged in.

Then record the result in `docs/homelab_unraid_drives.md`, either as a tested
cold spare or as scrap, and delete this entry in the same commit.

## blast radius

`badblocks -w` destroys everything on the drive. What is on it is the copy of
disk5 from 2026-09-21, which the array has moved past: disk5 was rebuilt onto
the new drive and has been written to since. That copy must never go back
into the array, so losing it costs nothing.

On a usb dock the test touches nothing else. On a behemoth sata port it adds
one drive's load to a controller; four passes over 4tb is days of sustained
writes, so keep it off the marvell card that carries disk2 and disk5.

## not doing yet

There is nowhere to put it. The case is full, and no dock or spare machine has
been set aside for the test. It is also not urgent: the array is healthy and
fully protected. The value is knowing whether a cold 4tb spare is on the shelf
the next time one of the eleven 4tb drives fails, since disk14 already shows
48 reallocated sectors.
