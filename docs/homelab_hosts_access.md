# Homelab hosts: access facts an agent needs

The inventory (`personal_credentials/personal_hosts.json`) is the source of
truth for addresses and users. This doc holds the facts that are not in it:
the things that silently fail a plausible remote workflow.

## elitedesk (192.168.86.179)

- **Git origin hub** for the credentials repos. `~/GitHub/<repo>` there is a
  non-bare checkout with `receive.denyCurrentBranch=updateInstead`, so a push
  from any machine lands in its working tree. Never delete a repo dir on that
  box; a checkout with no remote is a hub. A push is refused while the hub's
  worktree is dirty, so commit hub-side edits first. Everything else in
  `~/GitHub` has a normal forge origin.
- **Never `sudo` or `sudo -n` there from an agent.** There is no passwordless
  sudo, and every failed attempt emails me a security alert (mail_badpass +
  ssmtp root forward, kept on deliberately). Read what is
  readable as jason; the backup jobs avoid sudo through the docker group.
- Docker needs root; automation runs from root's crontab by design. See
  `homelab_deployments.md`.

## nukbuntu (192.168.86.139)

- Headless with no console session: every DRM output is disconnected and gdm
  sits at the greeter. Nothing that needs display `:0` works; that is why it
  runs the Xtigervnc virtual desktop.
- Its ssh key is not registered on GitHub, so GitHub pulls fail there. Forward
  the agent for a one-off (`ssh-add` locally, `ssh -A -o ControlPath=none`,
  `ssh-add -d` after). Its key does reach elitedesk, so the credentials repo
  pulls unaided.
- sudo needs a password (no NOPASSWD); root-side work is mine. Probing sudo
  here is harmless, unlike elitedesk.
- jason is in the docker group; app data lives in `/home/jason/docker_app_data`,
  not `/dockerAppData`. It is the observability node (loki, alloy, syslog-ng
  on UDP+TCP 514) defined in the Docker repo with configs in server_configs.

## behemoth (192.168.86.31, Unraid)

- `root@192.168.86.31` via `/usr/bin/ssh` (behemoth.local only resolves while
  avahi is alive). Docker is managed through the Unraid UI, not the Docker
  repo. Syslog is RAM-only and forwarded to nukbuntu; the kernel ring buffer
  is forwarded separately by a RAM-resident script
  (`server_configs/system_configs/behemoth`), so a dropped boot flash leaves
  its kernel lines in `docker_app_data/syslog/remote/Behemoth/kernel.*.log`
  on nukbuntu even though every binary under /usr, rsyslogd included, dies
  with the stick. There is no console when that happens: ssh accepts and
  resets, the web UI dies within the hour, containers keep running. Power
  cycle; the evidence is already on nukbuntu.
- Boot flash since 2026-09-12: a 128 GB stick in the upper of the two black
  USB 2.0 ports on the rear panel (the PNY that dropped twice lived in the
  lower one). The license is on the motherboard TPM, so a stick swap needs
  no key replacement. Unraid waits 30 s at boot for a FAT volume labelled
  exactly `UNRAID`; the USB Creator left the label as `BOOT` once. The
  weekly flash zip from the appdata.backup plugin is copied to nukbuntu's
  `backups` Samba share (`docker_app_data/backups/behemoth_flash/`, newest
  eight kept); procedure in `server_configs/system_configs/behemoth/README.md`.
- UPS: CyberPower PR1500LCDRT2U on USB, monitored by the desertwitch NUT
  plugin (`nut-dw`), not apcupsd. CyberPower's USB interrupt pipe goes silent
  and usbhid-ups marks data stale; the fix is `pollonly` on line 9 of
  `ups.conf` (lines 1-8 are GUI-reserved and regenerated, 9-18 persist).
  Persistent copy: `/boot/config/plugins/nut-dw/ups/ups.conf`. Apply through
  Settings > NUT Settings > NUT Configuration Editor.
- arr stack: Sonarr v4 on :8989 (container binhex-sonarr, API key in
  `/mnt/user/appdata/binhex-sonarr/config.xml`); NZBGet on :6789 (creds in
  `binhex-nzbget/nzbget.conf`); Deluge console needs
  `connect 127.0.0.1:58846` with the localclient creds from
  `binhex-delugevpn/auth`. No ffprobe on the host: borrow bazarr's
  (`docker exec bazarr ffprobe ...`, TV at /tv).
- Sonarr quality profile "Anime Dub (English required)" (id 8) only accepts
  dub or dual-audio releases, so new episodes wait for a dub (Crunchyroll dubs
  lag simulcast by weeks). The default "Any" profile (id 1) has no language
  rule. The arr lookup endpoints do not reliably report presence; check the
  library records instead.

## Home Assistant (192.168.86.201, HAOS VM)

- Internet URL `https://homeassistant.tinkernet.me`; REST API works there
  with the long-lived token. Creds are `HOME_ASSISTANT_*` in dotfiles' `.env`;
  grep the one key you need, never `source` the whole file.
- SSH is the Advanced SSH & Web Terminal add-on (user hassio, password). The
  `ha` CLI needs a login shell (`bash -l -c 'ha ...'`) for its supervisor
  token.
- Config mirror: `personal-automation/src/pull_home_assistant_configs.py`
  pulls the tree into `server_configs/application_configs/homeassistant/`
  (non-secret) and `personal_credentials/homeassistant/` (secrets). Root-only
  files (`.storage/auth`, `auth.session`, homekit `*.state`) are unreadable
  over the add-on; only `ha backups new` captures them.

## The desk

Envy (16 GB Mac mini) is the always-on console and stays; real work runs on
remote targets over VS Code Remote and ssh, never remote desktop. See
`plan_desk_dev_topology.md`.
