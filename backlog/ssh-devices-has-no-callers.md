# ssh_devices: dead script, described wrongly in CLAUDE.md

    found:  2026-09-30
    status: open
    verify: git grep -ln "ssh_devices" -- ':!src/ssh_devices.py'

On 2026-09-30 the verify line printed only `CLAUDE.md`.

## Evidence

- Nothing imports or runs `src/ssh_devices.py`: no alias, cron entry, systemd
  unit, command or other module, in this repo or any sibling.
- `CLAUDE.md:232` says it "pulls configs from devices over ssh". The code
  polls CPU and free disk on inventory hosts with paramiko, using
  `SSH_PASSWORD` from this repo's `.env`.
- readable-utils `ssh_tools` / `host_stats_tools` and the `status_board` repo
  already cover host stats.

## fix

    git rm src/ssh_devices.py

Then delete the `ssh_devices.py` line from `CLAUDE.md`. Check whether
`SSH_PASSWORD` in `.env` has any other reader before removing it.

## blast radius

None: nothing calls it.

## not doing yet

Recorded during a placement audit; deletions are batched with the other
dotfiles cleanups.
