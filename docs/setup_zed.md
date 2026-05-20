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

### Move and Symlink

1. **Create a directory in your dotfiles repo for Zed configs:**

   ```bash
   mkdir -p ~/GitHub/dotfiles/application_configs/zed
   ```

2. **Move existing Zed configs to your repo:**

   ```bash
   # Backup first if you want
   cp -r ~/.config/zed/* ~/GitHub/dotfiles/application_configs/zed/
   
   # Move the actual files
   mv ~/.config/zed/settings.json ~/GitHub/dotfiles/application_configs/zed/settings.json
   mv ~/.config/zed/keymap.json ~/GitHub/dotfiles/application_configs/zed/keymap.json
   
   # If you have tasks.json
   mv ~/.config/zed/tasks.json ~/GitHub/dotfiles/application_configs/zed/tasks.json
   ```

3. **Create symlinks back to Zed's config location:**

   ```bash
   ln -s ~/GitHub/dotfiles/application_configs/zed/settings.json ~/.config/zed/settings.json
   ln -s ~/GitHub/dotfiles/application_configs/zed/keymap.json ~/.config/zed/keymap.json
   
   # If you have tasks.json
   ln -s ~/GitHub/dotfiles/application_configs/zed/tasks.json ~/.config/zed/tasks.json
   ```

4. **Verify the symlinks:**

   ```bash
   ls -la ~/.config/zed/
   ```

   You should see something like:

   ```plaintext
   settings.json -> /Users/jason/GitHub/dotfiles/application_configs/zed/settings.json
   keymap.json -> /Users/jason/GitHub/dotfiles/application_configs/zed/keymap.json
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
