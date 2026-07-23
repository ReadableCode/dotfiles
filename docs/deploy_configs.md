# Deploying Configs with the Manifest

All repo-path → system-path config mappings for the public dotfiles live in
one file at the repo root: [`deploy_manifest.yaml`](../deploy_manifest.yaml).
Sibling `*_credentials` repos can contribute **overlay manifests** with the
same schema (see below). One command deploys (or dry-runs, or health-checks)
every config for the current machine — the per-app `ln -s` / `mklink` blocks
that used to live in the setup docs are gone.

## Commands

```bash
cd ~/GitHub/dotfiles

# Deploy every applicable entry for this machine (idempotent - a second
# run right after a first reports zero changes)
uv run python src/deploy_configs.py

# Read-only report: current health of every entry PLUS what deploy would do
# about anything unhealthy. Exits non-zero on drift, so it can run from cron.
uv run python src/deploy_configs.py status

# Remove managed links that no manifest entry wants any more. Dry run by
# default; --apply actually deletes. See "Removing an entry" below.
uv run python src/deploy_configs.py prune
uv run python src/deploy_configs.py prune --apply
```

There used to be separate `--dry-run` and `--status` modes; they showed the
same classification, so they are collapsed into the single `status` command
(`--status` and `--dry-run` still work as aliases). Output is an aligned,
colored table when writing to a terminal (set `NO_COLOR` to disable colors).

## Manifest entry schema

```yaml
- name: zshrc
  repo: application_configs/bash/.zshrc   # relative to the repo root
  dest:
    darwin: ~/.zshrc                      # omit a platform to skip it there
    linux: ~/.zshrc
    windows: ~/AppData/...                # only if the app is deployed on Windows
  hosts: [ENVY, ELITEDESK]                # optional: limit to specific hostnames
                                          # (overlay manifests only, see below)
  method: symlink | none                  # default symlink
  note: free text caveat
```

Every name in a `hosts:` filter must exist in the host inventory — the
**union** of every sibling `*_credentials` repo's inventory file
(`<context>_hosts.json`, falling back to legacy `hosts.json` when the prefixed
file is absent) — the single source of truth for machine names. Loading fails
loudly on an unknown name, so a typo or an invented hostname can't silently
deploy to (or skip) the wrong machines. Machines with no credentials repo (and
therefore no inventory) skip the check. The unit tests also check the real
manifests against the real inventories when present.

Because each machine only clones **its own** credentials repos, `hosts:`
filters are only allowed in **overlay manifests** — an overlay travels with
the inventory that knows its names, while a filter in the main
`deploy_manifest.yaml` would fail validation on any machine that clones a
different subset (e.g. a client laptop with only its own inventory). Loading
rejects a `hosts:` filter in the main manifest with an error saying which
overlay to move the entry to; an entry whose *file* lives in dotfiles can
still deploy host-filtered from an overlay by pointing `repo:` back across,
e.g. `repo: ../dotfiles/application_configs/claude/settings.json`.

Entries with `method: none` are inventory-only: they document apps that
intentionally do **not** use links (e.g. nvim on Windows via
`XDG_CONFIG_HOME`, the PowerShell profile via dot-sourcing), so the manifest
is a complete inventory of deployed configs, not just a link list.

## Overlay manifests from `*_credentials` repos

Private configs never live in this public repo — they live in sibling
credentials repos (see
[client_credentials_repos.md](./client_credentials_repos.md)). On every run,
`deploy_configs.py` loads `deploy_manifest.yaml` first and then discovers one
optional overlay per directory matching `../*_credentials` (sorted for
determinism): `<context>_manifest.yaml`, where `<context>` is the directory
name minus the `_credentials` suffix — e.g. `acme_credentials` contributes
`acme_manifest.yaml`. Overlay entries use the exact same schema; the only
difference is that their `repo:` paths resolve against **that credentials
repo's root**, not the dotfiles root. The `{repo_parent}` placeholder always
expands to the dotfiles checkout's parent (e.g. `~/GitHub`) no matter which
manifest an entry came from.

Entry `name`s must be unique across **all** loaded manifests — a duplicate
fails loudly naming both manifest files. The loaded set is printed as a
one-liner at the top of every run (e.g.
`manifests: deploy_manifest.yaml + 1 overlays (acme_manifest.yaml)`).
`--manifest <file>` loads only that single file (repo paths relative to the
dotfiles root) and skips overlay discovery — a test escape hatch.

### Host / platform variant files

A `repo` path is resolved against variant files named `<base>.<token>.<ext>`
(single lowercase token — the repo-wide convention, see `CLAUDE.md`), in this
order:

1. **Exact hostname** — `settings.envy.json`. The short (pre-dot) hostname is
   matched case-insensitively, so host `ENVY.ASUSROUTER` matches token `envy`
   and `MacbookProM5` matches `macbookprom5`.
2. **Platform** — `settings.darwin.json` or `settings.mac.json` on macOS,
   `settings.linux.json`, `settings.windows.json`.
3. **Bare default** — `settings.json` itself.

If neither a matching variant nor the bare file exists but variants for
*other* hosts do (e.g. `workspace.<host>.code-workspace` with no bare
`workspace.code-workspace`), the entry is skipped as `SKIP_VARIANT` — so
adding a variant file for a new host needs **no manifest change**. Context
tags (e.g. `settings.acme.json`) are never auto-resolved.

`dest` values support two placeholders:

- `{host}` — the lowercase short hostname (same token as variant filenames).
- `{repo_parent}` — the directory containing the repo checkout (e.g.
  `~/GitHub`), used for the VS Code workspace links that must live next to
  the sibling project folders they reference.

## How deployment behaves

- **Destination missing** → a symlink is created pointing at the repo file.
- **Destination is already the correct link** → no-op.
- **Destination is a wrong-target or dangling link** → the stale link is
  replaced.
- **Destination is a regular file and the repo file exists** → the repo is
  the source of truth: the system file is backed up to
  `data/config_backups/<repo-relative path>.<timestamp>` (gitignored, mtime
  preserved), then **replaced** by the link. Local edits survive only in the
  backup — they are never moved into the repo working tree. Once linked,
  editing the file at the system location edits the repo file, so changes
  show up in `git status` immediately.
- **Destination is a regular file and the repo file does not exist** →
  first-time capture: the system file is the only copy, so it is moved into
  the repo and linked (requires `ingest_system_if_exists=True`; the CLI path
  skips it and reports).
- **Windows**: `os.symlink` works without admin when Developer Mode is
  enabled (Settings → System → For developers). If symlinks are denied
  (locked-down work machines), deploy falls back to a **hard link** — no
  admin needed on the same NTFS volume. An existing correct hard link (same
  inode as the repo file) counts as deployed and is left alone. A copy is
  **never** used — a copy has no tie to the repo at all and silently drifts.
  The hard-link caveat: `git pull` replaces file inodes, orphaning the link —
  `status` catches that (inode no longer matches → `NOT_A_LINK`) and a
  re-deploy re-links it, so run `status`/deploy after pulling on those
  machines. See
  [sym_linking_and_hard_linking.md](./sym_linking_and_hard_linking.md).

## Status classifications

| Status | Meaning |
|--------|---------|
| `OK` | Symlink resolves to the repo file, or a hard link shares its inode. |
| `NOT_DEPLOYED` | Destination missing. |
| `BROKEN_LINK` | Destination is a dangling symlink. |
| `WRONG_TARGET` | Destination is a link resolving somewhere else. |
| `NOT_A_LINK` | Regular file where a link was expected — an unmanaged file or an orphaned hard link (git replaced the inode on pull); the detail says whether its content matches the repo copy or diverges. Deploy backs it up, then replaces it with a link to the repo version. |

Unhealthy rows get a second dimmed line explaining what is wrong and what
`deploy` would do about it. A one-line summary prints last (e.g.
`drift detected: 1 not_a_link, 8 ok`) and the exit code is `0` only when
everything is `OK`.

## Running it automatically

The `myupdater` alias (`scripts/my_updater.sh` on bash machines, the
`myupdater` function in `powershell_aliases.ps1` on Windows) pulls the
dotfiles repo first and then runs a full deploy, so every manual update run
links the latest configs and re-links any hard links the pull orphaned.

To run it from cron (add via `crontab -e` on the machine — cron jobs are
managed per-host, see [homelab_deployments.md](./homelab_deployments.md) for
how the homelab manages its entries):

```cron
# Daily dotfiles drift check at 08:00; only emails/logs on failure output
0 8 * * * cd ~/GitHub/dotfiles && uv run python src/deploy_configs.py status >> ~/GitHub/dotfiles/logs/deploy_status.log 2>&1
```

## Adding a new config

1. Put the file under `application_configs/<app>/`.
2. Add an entry to `deploy_manifest.yaml` with a `dest` for each platform it
   applies to.
3. `uv run python src/deploy_configs.py status`, then deploy.

If the destination already has a live config file, deploy backs it up and
replaces it with a link to the repo version (see behavior above) — so make
sure any local edits worth keeping are in the repo file *before* deploying,
or fish them out of `data/config_backups/` afterwards.


## Removing an entry (and cleaning up its links)

Deploy is manifest-driven: it only ever inspects destinations that a *current*
entry names. So deleting an entry does **not** remove the link it created — the
tool simply stops looking at it, and what is left behind differs per platform:

| Platform | Link type | Left behind after the source file is deleted |
| --- | --- | --- |
| macOS / Linux | symlink | A dangling symlink — visibly broken, but nothing removes it. |
| Windows (admin / Developer Mode) | symlink | Same dangling symlink. |
| Windows (unprivileged) | **hard link** | A **real file holding the old content**. It looks valid, and a hard link has no readable target, so nothing can tell it came from deploy. |

Cleanup is therefore an explicit, committed **list of files that must not
exist**, not something inferred from the filesystem or remembered per machine.
Per-machine state would be useless here: the machine that deletes the manifest
entry is almost never the only machine holding the link, and it has no way to
reach into the others. A committed list travels with the repo, so every machine
cleans itself up on its next prune.

The list lives in a **removals file**:

- `deploy_removals.yaml` in dotfiles, and/or
- `<context>_removals.yaml` in any sibling `*_credentials` repo (discovered
  exactly like `<context>_manifest.yaml`, so a client's dead paths stay in that
  client's private repo).

Entries use the same `dest` / `requires` / `hosts` schema as a manifest entry
but carry **no `repo:` key** — the source file is already gone. `requires` still
gates on the checkout existing, so a repo a machine never cloned has no link to
prune.

So the workflow is:

1. Delete the entry from the manifest.
2. Add its `dest` to the relevant removals file.
3. `prune` (dry run) to see what would go, then `prune --apply`.
4. Once every machine has pruned, the line can be dropped from the file.

`prune` never touches a real directory, removes a file only if a removals entry
names it, cleans up a directory left empty behind a removed file (e.g. a skill
folder), and **ignores any dest a live manifest entry still wants** — so
re-adding an entry beats a stale removals line instead of the two fighting.
Running it twice is a no-op; already-gone paths are just reported as absent.

Pruning is deliberately a separate command: deleting files should never be a
side effect of a routine deploy. `status` still *reports* anything the removals
list still finds on disk (and exits non-zero for it) so a cron drift check
notices.
