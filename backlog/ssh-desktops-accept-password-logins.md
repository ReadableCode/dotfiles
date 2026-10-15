# ssh: the desktops still accept password logins

    found:  2026-10-15
    status: open
    verify: for h in 192.168.86.131 192.168.86.94 192.168.86.170; do ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o PubkeyAuthentication=no jason@$h true 2>&1 | tail -1; done

A line that lists `password` or `keyboard-interactive` means that box still
takes a typed password over ssh; the target state is `Permission denied
(publickey)` on every line.

## Evidence

On 2026-10-15 the two portables were switched to key-only logins (the
`Key-only logins` steps in `docs/setup_mac_workstation.md` and
`docs/setup_windows_ssh_server.md`) and verified:

    jason@macbookprom5.local: Permission denied (publickey).
    jason@ultrapocket: Permission denied (publickey).

The three desktops were left as they were. Same probe, same day:

    RyzenWhite     jason@192.168.86.94: Permission denied (publickey,password,keyboard-interactive).
    JasonZephyrus  jason@192.168.86.170: Permission denied (publickey,gssapi-keyex,gssapi-with-mic,password).

Envy, read locally: `/etc/ssh/sshd_config.d/` holds only `100-macos.conf`, and
no file under `/etc/ssh` sets `PasswordAuthentication` or
`KbdInteractiveAuthentication`, so both are at their default of yes.

All three listen on the home LAN and the tailnet only; nothing forwards port
22 from the router. The exposure is a password prompt reachable by anything on
either network.

## fix

Each one is the documented step for its platform, run once key login from
Envy is confirmed (it is, for all three, as of 2026-10-15).

Envy (macOS), from a local terminal:

    printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\n' | sudo tee /etc/ssh/sshd_config.d/000-key-only.conf

RyzenWhite (Windows), in an admin PowerShell: add the two lines ABOVE the
`Match Group administrators` block of `C:\ProgramData\ssh\sshd_config`, then

    & 'C:\Program Files\OpenSSH\sshd.exe' -t -f C:\ProgramData\ssh\sshd_config
    Restart-Service sshd

JasonZephyrus (Fedora): the stock `sshd_config` starts with
`Include /etc/ssh/sshd_config.d/*.conf` and ships `50-redhat.conf`; sshd keeps
the first value it reads, so a file sorting before it wins:

    printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\n' | sudo tee /etc/ssh/sshd_config.d/00-key-only.conf
    sudo sshd -t && sudo systemctl restart sshd

`/etc/ssh` on Zephyrus is not readable as `jason`, so the Include line and the
`50-redhat.conf` name are from Fedora's defaults, not read from the box;
check them with sudo before relying on the sort order.

Then re-run `verify:`, and add a "done on <machine> <date>" line to the two
setup docs. There is no sshd setup doc for the Linux workstations;
`docs/setup_local_ai.md` is the closest home for the Zephyrus step.

## blast radius

Anything that logs into these three by typed password stops working. Key-based
access keeps working and is what every tool in this repo uses: the `ssh<name>`
aliases, `fleet_check.py`, `gitpullall`, the status board panels. Envy's
`id_rsa` is authorized on all three. Not checked: whether the phone's Termux
setup (`docs/setup_android_termux.md`), any VS Code Remote-SSH profile, or the
M5 and UltraPocket's own keys ever log into the desktops by password. The
physical console is unaffected.

## not doing yet

Jason's call on 2026-10-15: the portables got key-only because they leave the
house; the desktops don't travel and are fine to leave alone (said of
Zephyrus specifically, and the same reasoning covers Envy and RyzenWhite).
This entry records that decision and the one-line check, not an open task.
If it is ever picked up: run the blast-radius checks above first so no device
is left with password as its only way in.
