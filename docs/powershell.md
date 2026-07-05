# Powershell

## Making Symbolic Links

> Dotfiles config links are not created by hand anymore — they are driven by
> `deploy_manifest.yaml` via
> `uv run python src/deploy_configs.py` (see [deploy_configs.md](./deploy_configs.md)).
> With Developer Mode enabled, real symlinks work without admin; the deploy
> falls back to a copy otherwise. Avoid hard links for git-tracked files —
> see [sym_linking_and_hard_linking.md](./sym_linking_and_hard_linking.md).
> The commands below are a general reference for one-off links.

- open powershell as admin (not needed for symlinks if Developer Mode is on)

- make directories if not exist:

```bash
mkdir ~\.config\nvim
```

- cd to directory where the symbolic link is to be placed:

```bash
cd ~\.config\nvim
```

- create the symbolic link:

  - For files:

  ```bash
  cmd /c mklink <name_of_link> <target>
  ```

  - For directories:

  ```bash
  cmd /c mklink /D <name_of_link> <target>
  ```
