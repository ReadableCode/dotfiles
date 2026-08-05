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

# Redraw the fleet-wide deployment map without deploying anything.
# See "The deployment map" below; a deploy does this automatically.
uv run python src/deploy_configs.py map
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

## Overlay manifests from sibling repos

Private configs never live in this public repo — they live in sibling
credentials repos (see
[client_credentials_repos.md](./client_credentials_repos.md)). On every run,
`deploy_configs.py` loads `deploy_manifest.yaml` first and then discovers one
optional overlay per sibling **overlay repo** (sorted for determinism):
`<context>_manifest.yaml`. Overlay entries use the exact same schema; the only
difference is that their `repo:` paths resolve against **that overlay repo's
root**, not the dotfiles root. The `{repo_parent}` placeholder always expands
to the dotfiles checkout's parent (e.g. `~/GitHub`) no matter which manifest an
entry came from.

An overlay repo is either of:

- any directory matching `../*_credentials` — `<context>` is the directory name
  minus the suffix, so `acme_credentials` contributes `acme_manifest.yaml`;
- **any other sibling repo that opts in** by declaring a manifest named after
  itself — `<context>` is the full directory name, so `acme_dev` contributes
  `acme_dev_manifest.yaml`.

The opt-in form exists because a credentials repo travels to every machine that
needs that context's secrets — including the client's own machines. Config that
must reach *some* of those machines and not others cannot be gated by that
clone, so it lives in a repo with the narrower clone set and rides that repo's
own overlay instead. Entries there still point `repo:` back across at the
credentials repo (`repo: ../acme_credentials/<file>`, with a matching
`requires:`) when the payload itself is a secret that must stay private.

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


## The deployment map

Every deploy also redraws a **map of the whole fleet**: what each manifest
entry is, which machines it reaches, and the exact path it lands on. It is
built by `src/deploy_map.py` from the same `load_manifests()` + `build_plan()`
the deployer runs — executed once per machine in the host inventories — so it
can never drift from the manifests the way a hand-kept diagram would.

Two files are written, side by side:

| File | What it is |
| --- | --- |
| `deploy_map.html` | One self-contained page (no network, no build step), four views: **Disk** (default), **Fleet**, **Matrix** and **Destinations** — see below. Open it straight from the repo. |
| `deploy_map.json` | The same dataset, indented — the diffable half, so a pull request shows *which* link changed rather than one 350 KB blob. |

The four views answer different questions:

- **Disk** — *where does this file on disk come from?* Source files on the
  left, the places they land on the right, clustered by the kind of place
  (`~`, `~/.claude`, and inside a checkout: claude files / secrets / other)
  rather than by machine. Two things make it a disk view rather than a fleet
  one: `{host}` stays symbolic, so `~/GitHub/{host}.code-workspace` is one node
  instead of one per machine; and sources are keyed by the **resolved file**,
  so an overlay entry pointing at `../dotfiles/...` shares a node with the
  dotfiles entry that owns it. A dashed square marks a **folder link** — a
  manifest entry whose source is a directory — and its card lists what is
  inside that directory right now, which is how you check that, say, a repo's
  Claude memories really are riding along with the link.
- **Fleet** — the original constellation: which machine receives which entry.
- **Matrix** — the entry × machine grid, colour-coded with *why* each empty
  cell is empty.
- **Destinations** — the filesystem tree the links land in, as deployed
  (per-machine paths expanded).

Both files land in the **personal credentials repo**, and only when that repo
is cloned on the machine running the deploy:

```
~/GitHub/personal_credentials/deploy_map.{html,json}
```

That gate is the point. The map names every machine and every context at once,
so it must never appear in a client's repo — and it must never appear in this
public one. A work machine holding only a client's credentials repo silently
skips the step (`map: personal_credentials is not cloned here - skipped`).
Nothing is committed automatically; the files just change in that repo, and
`git diff` there is the review.

The map is written to be a **pure function of the manifests**, so a diff always
means the fleet actually changed:

- No timestamps, no "generated on <host>" line.
- Paths are folded back to `~`, with forward slashes, so regenerating from
  Windows and from macOS produces the same file.
- `requires:` preconditions are treated as met (`build_plan(...,
  assume_requires=True)`). A machine that is missing a checkout would really
  report `skip_requires`, but the map would then change shape depending on
  which machine happened to redraw it. Platform blocks, `hosts:` filters and
  per-host variant files *are* evaluated for real, per machine.

Colours and clusters come from the data, not from a hardcoded list: the
dotfiles manifest is always the first (shared) cluster, and every other context
takes the next palette slot in alphabetical order. An overlay named
`<context>_<gate>` folds into `<context>` when that credentials repo is also
cloned, so one context stays one circle.

`--no-map` skips the redraw for a single deploy; `deploy_configs.py map`
redraws without deploying. Drawing the map is best effort — if it fails, it
prints a warning and the deploy result still stands.

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
- `<context>_removals.yaml` in any sibling overlay repo (discovered exactly like
  `<context>_manifest.yaml` — `*_credentials` repos, plus any sibling that opts
  in by declaring one — so a client's dead paths stay in that client's private
  repo).

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
