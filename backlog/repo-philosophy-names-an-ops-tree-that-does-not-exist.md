# repo_philosophy: says personal_dev keeps its jobs in ops/, but they are in src/

    found:  2026-09-29
    status: open
    verify: grep -n "ops/" docs/repo_philosophy.md; ls ../personal_dev/ops ../personal_dev/src

`docs/repo_philosophy.md` describes a layout `personal_dev` does not have, so
a reader looking for a homelab job is sent to a folder that is not there.

## Evidence

`docs/repo_philosophy.md`, two places:

    84:  | Scheduled jobs | the dev repo's `ops/` when they run on a client machine; `personal_dev/ops/` for the homelab |
    165: rotation, the usage monitor — live in its `ops/` tree.

In the `personal_dev` checkout:

    ls: /Users/jason/GitHub/personal_dev/ops: No such file or directory

The jobs those lines name are all under `personal_dev/src/`:
`bitwarden.py`, `backup_postgres.py`, `backup_docker_apps.py`,
`rotate_logs.py`, `claude_usage_monitor.py`. The cron entries in
`server_configs/system_configs/elitedesk/cron/jason.cron` call them there, for
example `uv run src/backup_postgres.py`.

## fix

One of two, depending on which side is intended:

- The layout is intended: change both lines in `docs/repo_philosophy.md` to say
  `src/`.
- The doc is intended: move the five job scripts to `personal_dev/ops/`, update
  the cron lines in `server_configs` and the Bitwarden Dockerfile, and update
  `personal_dev`'s `CLAUDE.md` and `README.md`.

## blast radius

The first is a doc edit and disturbs nothing. The second changes the paths the
nightly backups run from: a cron line left on the old path fails that night's
backup and mails "Cron Job Failed".

## not doing yet

Which side is intended is not known. `personal_dev`'s own docs were updated on
2026-09-29 to describe what is on disk, which is `src/`.
