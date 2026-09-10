# Mac Disk Cleanup

`scripts/mac_cleanup_all.py` reclaims disk on a Mac. Dry run by default; it
prints a before/after usage bar and what each step would remove.

```bash
uv run python scripts/mac_cleanup_all.py              # dry run, report only
uv run python scripts/mac_cleanup_all.py --delete     # user-owned steps
sudo python3 scripts/mac_cleanup_all.py --delete      # root-owned steps
```

Two passes are needed and they are not interchangeable. `package_caches`
shells out to `uv`/`npm`/`brew`, which must run as the login user, so it is
skipped under sudo. `powerlog` and `logstore` delete under `/private/var/db`
and are skipped without it. Neither pass is a superset of the other.

## The steps

| Step | What it removes | Root |
|------|-----------------|------|
| `purge_paths` | regrowing updater/`ShipIt` junk in `~/Library/Caches` | no |
| `vscode_extensions` | superseded VS Code extension versions | no |
| `brew_staging` | interrupted cask/keg installs `brew cleanup` cannot see | no |
| `browser_caches` | Chrome/Edge caches, **skipped while the browser runs** | no |
| `app_logs` | rotated app logs; the live log is left alone | no |
| `package_caches` | uv/npm/brew caches, via each tool's own prune | no |
| `powerlog` | `PerfPowerTelemetry` DB leak, above a 2 GB threshold | yes |
| `logstore` | unified-logging archive via `log erase`, above 2 GB | yes |

Quit Chrome and Edge before a run that should include their caches — that is
usually the largest single user-owned item, and the step refuses to touch a
running browser rather than corrupt its profile.

## Why it measures the way it does

Two classes of overstatement were found and fixed; both are easy to
reintroduce.

**Apparent size is not reclaimed size.** `dir_size` counts `st_blocks`, not
`st_size`, skips symlinks via `lstat`, and counts a hardlinked inode once —
which is how `du` arrives at its number. A run that claimed 13.62 GB freed
8.26 GB before this. It is also why deleting a `uv` cache frees far less than
its size: most of it is hardlinked into project `.venv` directories, which
keep the data alive.

**Measure the directory the prune command will actually act on.** A host that
redirects its caches (Envy points `UV_CACHE_DIR` / `HOMEBREW_CACHE` at an
external SSD, see `setup_mac_workstation.md`) does not keep them under `~`.
`PACKAGE_CACHES` therefore asks each tool where its cache is — `uv cache dir`,
`brew --cache`, `npm config get cache` — through a login shell, because the
redirect is an export. Hardcoding the default paths measured one directory and
pruned another: the 2026-09-09 dry run claimed 4.63 GB of internal-disk cache
that `uv cache prune` would never have touched.

**Freeing another volume is not freeing this one.** Sizes on a volume other
than `$HOME`'s are printed but excluded from the total, since the total is
shown against the internal disk's bar.

## What it deliberately does not touch

Spotlight and the on-device intelligence stores are the largest rebuildable
data on a dev Mac — `~/Library/Metadata/CoreSpotlight`,
`~/Library/Biome/sets`, and the `hybridsearchd` / `naturallanguaged` daemon
containers together ran ~10 GB here. They are excluded on purpose: every byte
regenerates, the rebuild pins `mdworker`/`mds_stores` at high CPU and memory
for hours, and it returns to the same size. Shrinking them durably means
changing *what* gets indexed (Spotlight Privacy exclusions for large dev
trees) and reindexing once — a deliberate act, not a cleanup step.
