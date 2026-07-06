# Zed Editor Setup on macOS

## Installation

```bash
brew install --cask zed
```

Or download from [zed.dev](https://zed.dev)

## Configuration File Locations

Zed stores its configuration files in:

```bash
~/.config/zed/
```

Key files:

- `~/.config/zed/settings.json` - User settings
- `~/.config/zed/keymap.json` - Custom keybindings
- `~/.config/zed/tasks.json` - Task configurations (if used)

## Symlinking Zed Config to Git Repo

Zed's settings link is manifest-driven (entry `zed_settings` in
`deploy_manifest.yaml` — see [deploy_configs.md](./deploy_configs.md)):

```bash
cd ~/GitHub/dotfiles
uv run python src/deploy_configs.py status      # preview / drift report
uv run python src/deploy_configs.py             # deploy
```

Notes:

- An existing live `~/.config/zed/settings.json` is backed up to
  `data/config_backups/` and its content ingested into the repo automatically.
- Only `settings.json` is tracked today. If you start using `keymap.json` or
  `tasks.json`, move the file into `application_configs/zed/` and add a
  manifest entry for it.

Verify the link:

```bash
ls -la ~/.config/zed/
```

You should see something like:

```plaintext
settings.json -> /Users/jason/GitHub/dotfiles/application_configs/zed/settings.json
```

## Verification

After symlinking, test that Zed still works:

1. Open Zed
2. Make a change to settings (e.g., change theme)
3. Verify the change appears in your git repo:

   ```bash
   cd ~/GitHub/dotfiles
   git status
   git diff application_configs/zed/settings.json
   ```

### Accessing Settings in Zed

- **Open Settings:** `Cmd + ,` or `Zed > Settings`
