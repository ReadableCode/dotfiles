behemoth drive positions, looking at the server from the front.
columns left to right, drives top to bottom. same order as before.

serials are full, as printed on the drive label and as unraid shows them.
match on serial, never on position: the array slot numbers do not follow the
physical order, and the linux device names (sdb, sdc, ...) change on reboot.

column 1, left looking from front
top
ZGY8ZPK3         4tb  seagate ST4000VN008     disk10
ZGY8ZP2Z         4tb  seagate ST4000VN008     disk12
ZJV1S0KB         12tb seagate ST12000VN0007   disk8
ZDHAS31C         4tb  seagate ST4000VN008     disk14
ZDHAS916         4tb  seagate ST4000VN008     disk9
bottom

column 2
top
WD-WCC7K7TLEVLE  4tb  wd WD40EFRX             disk6
WD-WCC7K3DNAHDA  4tb  wd WD40EFRX             disk4
WD-WCC7K4SY2Z4Z  4tb  wd WD40EFRX             disk1
ZGY761QE         4tb  seagate ST4000VN008     disk11
ZGY8C9ZW         4tb  seagate ST4000VN008     disk13
bottom

column 3, right looking from front
top
ZRT18XFK         12tb seagate ST12000NT001    parity
WS23L2YN         4tb  seagate ST4000NE001     disk7
ZRT18WHH         12tb seagate ST12000NT001    disk2
WD-WCC7K0DPE7Y1  4tb  wd WD40EFRX             disk3
ZZ30MKQY         12tb seagate ST12000VN0008   disk5
bottom

history

2026-09-27, disk5 rebuild onto ZZ30MKQY finished at 14:25 after 22 hours 15
minutes with nothing wrong: every md error counter zero, no parity mismatches,
no kernel disk errors, every link at 6.0 gbps throughout. parity is valid again.

2026-09-26, power supply, every sata data cable and the 4-way sata power
splitter for column 3 replaced, after three days of rebuilds that died part
way on link drops. the splitter was the fault. what pointed at power was the
drives' own smart power cycle count (attribute 12), read while the server
stayed up:

ZZ30MKQY         disk5   578, at 33 power-on hours. it was 3 when installed
WS23L2YN         disk7   7774
everything else          42 to 247

a count that climbs while the server has not restarted means that drive's
power feed is dropping. disk5 and disk7 both hung off the old splitter, which
fed the bottom four bays of column 3. disk2 (77) and disk3 (247) were on it
too and look normal. no count has moved since the new splitter went in,
through the whole rebuild.

2026-09-23, column 3 bottom, disk5: WD-WCC7K4NHXD19 (4tb wd WD40EFRX) was
disabled by unraid after 308 write errors and replaced with ZZ30MKQY (12tb
seagate ironwolf ST12000VN0008, dom 21jun2026, fw SC60). the old drive passed
smart with zero reallocated and zero pending sectors; it failed on writes with
ABRT / internal target failure at the ata layer. it sat in the bay whose power
was dropping, so it may be a good drive. it has not been retested.

earlier, date not recorded, column 1 position 4 / disk14: ZDHAS31C was going
to be replaced with a 12tb seagate whose serial ended a973, but that drive
arrived already failed, so the swap was reverted and ZDHAS31C went back in.
it is still there. this is why a replacement drive gets smart checked before
it is assigned to a slot.

worth watching

WD-WCC7K0DPE7Y1  disk3   38,580 entries in its own ata error log, all from
                         before the power and cable swap. it read its whole
                         4tb span during the rebuild without adding one.
ZDHAS31C         disk14  48 reallocated sectors and 4 crc errors, not moving.
WS23L2YN         disk7   power cycle count 7774, see 2026-09-26.

which controller each drive is on

useful for tracing cables, since there is no backplane. ports are numbered by
the kernel, nothing is silkscreened. this is the cabling from 2026-09-26, read
on 2026-09-28. it changes whenever a cable moves, so read it again on behemoth
before trusting it:

    for d in /sys/block/sd?; do p=$(readlink -f $d); echo "$(echo $p | grep -oE '[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]' | tail -1) $(echo $p | grep -oE 'ata[0-9]+' | head -1) $(lsblk -dno SERIAL /dev/${d##*/})"; done | grep ata | sort -V

0000:01:00.1  amd chipset, motherboard headers   disk1, disk4, disk11, disk13
0000:05:00.0  marvell 88SE9215 card              disk2, disk3, disk5, disk7
0000:06:00.0  marvell 88SE9215 card              disk8, disk9, disk12, disk14
0000:07:00.0  marvell 88SE9215 card              disk10, parity
0000:0a:00.0  amd fch                            disk6

the bottom four drives of column 3 share both the 05:00.0 card and one power
splitter, so when those four misbehave together the kernel log cannot tell a
data fault from a power fault. the power cycle count can.

each marvell card puts its four ports behind one pcie 2.0 x1 lane, so the two
12tb drives on 05:00.0 share it.

23 sata ports enumerated, 15 drives, so spare ports exist. the case has no
spare bays, so a drive has to come out before one goes in.
