# Zed Editor Setup on macOS

## Installation

```bash
brew install --cask zed
```

Or download from [zed.dev](https://zed.dev)

## Configuration File Locations

Zed stores its configuration files in:

```
~/.config/zed/
```

Key files:
- `~/.config/zed/settings.json` - User settings
- `~/.config/zed/keymap.json` - Custom keybindings
- `~/.config/zed/tasks.json` - Task configurations (if used)

## Symlinking Zed Config to Git Repo

### Method 1: Move and Symlink (Recommended)

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
   ```
   settings.json -> /Users/jason/GitHub/dotfiles/application_configs/zed/settings.json
   keymap.json -> /Users/jason/GitHub/dotfiles/application_configs/zed/keymap.json
   ```

### Method 2: Symlink Entire Directory

Alternatively, symlink the entire Zed config directory:

```bash
# Move the entire directory
mv ~/.config/zed ~/GitHub/dotfiles/application_configs/zed

# Create symlink
ln -s ~/GitHub/dotfiles/application_configs/zed ~/.config/zed
```

**Note:** This method will also track other files Zed creates (like database files, state files, etc.), which may not be desirable. Method 1 is more selective.

### Method 3: Using Stow (If Available)

If you use GNU Stow for dotfile management:

```bash
cd ~/GitHub/dotfiles
mkdir -p stow/zed/.config/zed
mv ~/.config/zed/settings.json stow/zed/.config/zed/
mv ~/.config/zed/keymap.json stow/zed/.config/zed/

stow -d stow -t ~ zed
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

## Committing to Git

```bash
cd ~/GitHub/dotfiles
git add application_configs/zed/
git commit -m "Add Zed editor configuration"
git push
```

## Setting Up on a New Machine

On a new Mac:

1. **Clone your dotfiles repo:**
   ```bash
   git clone https://github.com/ReadableCode/dotfiles.git ~/GitHub/dotfiles
   ```

2. **Install Zed:**
   ```bash
   brew install --cask zed
   ```

3. **Remove default configs (if they exist):**
   ```bash
   rm -f ~/.config/zed/settings.json
   rm -f ~/.config/zed/keymap.json
   rm -f ~/.config/zed/tasks.json
   ```

4. **Create symlinks:**
   ```bash
   ln -s ~/GitHub/dotfiles/application_configs/zed/settings.json ~/.config/zed/settings.json
   ln -s ~/GitHub/dotfiles/application_configs/zed/keymap.json ~/.config/zed/keymap.json
   ln -s ~/GitHub/dotfiles/application_configs/zed/tasks.json ~/.config/zed/tasks.json
   ```

## Tips

### Accessing Settings in Zed

- **Open Settings:** `Cmd + ,` or `Zed > Settings`
- **Open Keymap:** `Zed > Settings > Open Keymap` or via command palette (`Cmd + Shift + P`)

### Common Settings Location Quick Reference

```
~/.config/zed/settings.json    # Your personal settings
~/.config/zed/keymap.json      # Keyboard shortcuts
~/.config/zed/tasks.json       # Task runner configs
```

### .gitignore Recommendations

If using Method 2 (symlinking entire directory), add this to your `.gitignore`:

```gitignore
# Ignore Zed state/cache files
application_configs/zed/conversations/
application_configs/zed/copilot/
application_configs/zed/embeddings/
application_configs/zed/languages/
application_configs/zed/node/
application_configs/zed/db/
application_configs/zed/*.log
```

### Automation Script

Create a script to set up symlinks automatically:

```bash
#!/bin/bash
# ~/GitHub/dotfiles/scripts/setup_zed_symlinks.sh

DOTFILES_DIR="$HOME/GitHub/dotfiles"
ZED_CONFIG_DIR="$HOME/.config/zed"
ZED_DOTFILES_DIR="$DOTFILES_DIR/application_configs/zed"

echo "Setting up Zed configuration symlinks..."

# Ensure Zed config directory exists
mkdir -p "$ZED_CONFIG_DIR"

# Symlink each config file
for file in settings.json keymap.json tasks.json; do
    if [ -f "$ZED_DOTFILES_DIR/$file" ]; then
        if [ -L "$ZED_CONFIG_DIR/$file" ]; then
            echo "✓ $file already symlinked"
        elif [ -f "$ZED_CONFIG_DIR/$file" ]; then
            echo "⚠ $file exists, backing up..."
            mv "$ZED_CONFIG_DIR/$file" "$ZED_CONFIG_DIR/$file.backup"
            ln -s "$ZED_DOTFILES_DIR/$file" "$ZED_CONFIG_DIR/$file"
            echo "✓ $file symlinked"
        else
            ln -s "$ZED_DOTFILES_DIR/$file" "$ZED_CONFIG_DIR/$file"
            echo "✓ $file symlinked"
        fi
    fi
done

echo "Done!"
```

Make it executable:
```bash
chmod +x ~/GitHub/dotfiles/scripts/setup_zed_symlinks.sh
```

## Troubleshooting

### Symlink not working
```bash
# Check if symlink is correct
ls -la ~/.config/zed/settings.json

# Remove broken symlink
rm ~/.config/zed/settings.json

# Recreate
ln -s ~/GitHub/dotfiles/application_configs/zed/settings.json ~/.config/zed/settings.json
```

### Zed not picking up changes
Restart Zed after making configuration changes outside the app.

### Permissions issues
Ensure the files have correct permissions:
```bash
chmod 644 ~/GitHub/dotfiles/application_configs/zed/*.json
```
