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

2026-09-23, column 3 bottom, disk5: WD-WCC7K4NHXD19 (4tb wd WD40EFRX) was
disabled by unraid after 308 write errors and replaced with ZZ30MKQY (12tb
seagate ironwolf ST12000VN0008, dom 21jun2026, fw SC60). the old drive passed
smart with zero reallocated and zero pending sectors; it failed on writes with
ABRT / internal target failure at the ata layer, so suspect the cable too.

earlier, date not recorded, column 1 position 4 / disk14: ZDHAS31C was going
to be replaced with a 12tb seagate whose serial ended a973, but that drive
arrived already failed, so the swap was reverted and ZDHAS31C went back in.
it is still there. this is why a replacement drive gets smart checked before
it is assigned to a slot.

which controller each drive is on

useful for tracing cables, since there is no backplane. ports are numbered by
the kernel, nothing is silkscreened.

0000:01:00.1  amd chipset, motherboard headers   disk2, disk5, disk11, disk12
0000:05:00.0  marvell 88SE9215 card              disk9
0000:06:00.0  marvell 88SE9215 card              disk1, disk4, disk7, disk10
0000:07:00.0  marvell 88SE9215 card              disk3, disk6, disk8, disk13
0000:0a:00.0  amd fch                            parity, disk14

23 sata ports enumerated, 15 drives, so spare ports exist. the case has no
spare bays, so a drive has to come out before one goes in.
