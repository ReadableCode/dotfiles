# zephyrus: the agent server stops being reachable when its lid closes or it reboots

    found:  2026-10-02
    status: open
    verify: ssh jason@192.168.86.170 'busctl get-property org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager HandleLidSwitch HandleLidSwitchExternalPower; grep AutomaticLogin /etc/gdm/custom.conf'

JasonZephyrus is the always-on agent server (`docs/plan_desk_dev_topology.md`,
"Agent server and T3 Connect slots"). It holds a T3 Connect slot and shares
its own GNOME session over VNC through gnome-remote-desktop
(`docs/setup_vnc_server.md`, "GNOME session sharing"). Two things still need
someone at the laptop.

## Evidence

Read on 2026-10-02:

- Lid: `HandleLidSwitch=s "suspend"`, `HandleLidSwitchExternalPower=s ""`
  (empty falls back to `HandleLidSwitch`), `HandleLidSwitchDocked=s "ignore"`.
  Closing the lid suspends it, on power or not, unless it is docked. Nothing
  in dotfiles or server_configs sets a lid policy.
- Idle, logged in: jason's `sleep-inactive-ac-type 'nothing'`, so a session
  signed in at the laptop never idles it to sleep on AC.
- Idle, at the login screen: fixed 2026-10-02. GDM's own settings
  suspended after 15 minutes on AC, ssh not counting as activity, and did so
  mid-way through the Fedora 44 download. The `zephyrus_gdm_no_idle_suspend`
  system entry in personal_manifest.yaml now sets the greeter to `'nothing'`
  on AC (read it with `DCONF_PROFILE=gdm`; without it gsettings reads the
  default profile and still says `'suspend'`).
- Login: `/etc/gdm/custom.conf` has a `[daemon]` section and no
  `AutomaticLogin`. gnome-remote-desktop shares only a logged-in session, so
  after a reboot VNC serves nothing until someone signs in at the laptop.
  The T3 service is a lingering user unit, so T3 itself comes back on its own.

## fix

1. Lid: a logind drop-in, `/etc/systemd/logind.conf.d/lid.conf`, with
   `HandleLidSwitch=ignore` and `HandleLidSwitchExternalPower=ignore`, as a
   `method: system` entry in personal_manifest.yaml (payload in
   `server_configs/system_configs/jasonzephyrus/`, like the sudoers file),
   `reload: systemctl kill -s HUP systemd-logind`. Passwordless sudo is in
   place there, so the deployer can place it.
2. Login: GDM auto-login for jason, `AutomaticLoginEnable=True` and
   `AutomaticLogin=jason` under `[daemon]` in `/etc/gdm/custom.conf`, same
   kind of entry. Then test, after a reboot, whether gnome-remote-desktop can
   still read its VNC password: it keeps it in the login keyring, which an
   auto-login leaves locked. If it cannot, decide between an empty keyring
   password and another way to hold the credential.

## blast radius

- Ignoring the lid means a closed laptop in a bag stays awake and warm.
- Auto-login means anyone who powers it on gets jason's desktop with
  passwordless sudo.
- Neither touches any other machine.

## not doing yet

Both are policy calls about a laptop that also travels, and the keyring
question in step 2 needs a real reboot to answer.
