# Sym Linking and Hard Linking

> Dotfiles config deployment is manifest-driven — see
> [deploy_configs.md](./deploy_configs.md). The commands here are a general
> reference for one-off links.

## Why not hard links for git-tracked files

A hard link is a second directory entry for the **same inode**. Git does not
update files in place: on `checkout`/`pull` it writes a **new** file (new
inode) and swaps it into the working tree. Any hard link you made beforehand
still points at the *old* inode — the old content — while the repo copy moves
on. Nothing errors; the deployed file just silently stops updating. Everything
*looks* deployed, which makes this the worst kind of drift.

Symlinks do not have this problem: they point at the *path*, so they always
resolve to whatever content git last wrote there.

Rules of thumb:

- Prefer a **symlink** (on Windows: works without admin once Developer Mode
  is enabled — Settings → System → For developers).
- If symlinks are denied (locked-down machine), `src/deploy_configs.py` falls
  back to a **hard link** automatically. Because of the inode problem above,
  run `uv run python src/deploy_configs.py status` (or a re-deploy) after
  `git pull` on those machines — an orphaned hard link shows up as
  `NOT_A_LINK` and deploy re-links it.
- **Never copy** a config into place — a copy has no tie to the repo at all
  and silently drifts with nothing to catch it.
- Better still, use config-path indirection when the app supports it, so no
  link is needed at all (nvim via `XDG_CONFIG_HOME` set in
  `application_configs/powershell/powershell_aliases.ps1`, git via
  `include.path` / `core.excludesFile`).

## Linux

### Sym Linking on Linux

- To Create at a specific directory

```bash

ln -s source_file myfile

```

- To Create at current directory

```bash

ln -s /path/to/src/file

```

For example, linking a VS Code settings file out of the repo:

```bash
ln -s /home/jason/HelloFresh/GDrive/Projects/dotfiles/application_configs/vscode/settings.json /home/jason/.config/Code/User/settings.json
```

### Hard linking on Linux

`ln` without `-s` creates a hard link. Do **not** use this for files inside a
git repo (see above) — the examples that used to live here hard-linked
`.code-workspace` files into the repo and went stale on the next pull. Use a
symlink instead.

## Windows

### Sym Linking on Windows

With Developer Mode enabled (Settings → System → For developers), symlinks
work from a normal PowerShell — no admin needed. Note: `-Path` is the new
link you are creating, `-Target` is the file that already exists.

```powershell
New-Item -ItemType SymbolicLink `
  -Path "C:\Users\jason\GitHub\yoga7i.code-workspace" `
  -Target "C:\Users\jason\GitHub\dotfiles\application_configs\vscode\workspace.yoga7i.code-workspace"
```

```powershell
New-Item -ItemType SymbolicLink `
  -Path "C:\Users\16937827583938060798\HelloFreshProjects\hellofresh.code-workspace" `
  -Target "C:\Users\16937827583938060798\HelloFreshProjects\dotfiles\application_configs\vscode\workspace.hellofresh.code-workspace"
```

Or with `cmd`'s `mklink` (elevated prompt required without Developer Mode):

```powershell
cmd /c mklink "C:\Users\jason\GitHub\ultrapocket.code-workspace" "C:\Users\jason\GitHub\dotfiles\application_configs\vscode\workspace.ultrapocket.code-workspace"
```

(These workspace links are exactly what
`uv run python src/deploy_configs.py` now creates via the `vscode_workspace`
manifest entry — the commands remain here only as one-off reference.)

### If symlinks are not available (hard-link fallback)

On locked-down machines without Developer Mode or admin rights,
`src/deploy_configs.py` falls back to a **hard link** — creating one needs no
special rights on the same NTFS volume. Never a copy: a copy has no tie to
the repo at all. The one-off manual equivalent:

```powershell
New-Item -ItemType HardLink `
  -Path "C:\Users\jason.christiansen\GitHub\fflap-2229.code-workspace" `
  -Target "C:\Users\jason.christiansen\GitHub\dotfiles\application_configs\vscode\workspace.fflap-2229.code-workspace"
```

The trade-off (see the inode section above): `git pull` orphans hard links
when it rewrites a file. That drift is not silent here —
`uv run python src/deploy_configs.py status` compares inodes and reports an
orphaned hard link as `NOT_A_LINK`, and a re-deploy re-links it. On these
machines, run `status` or deploy after pulling.
