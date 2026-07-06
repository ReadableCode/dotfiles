# Setting up Visual Studio Code

## Installing Visual Studio Code

### Windows

1. Download Visual Studio Code: Visit the official Visual Studio Code site at [https://code.visualstudio.com/](https://code.visualstudio.com/) and download the installer for Windows.

2. Run the installer: Once the installer is downloaded, run it and follow the on-screen instructions to complete the installation.

3. Launch Visual Studio Code: After the installation is complete, launch Visual Studio Code from the Start menu.

### Debian Linux

1. Install Visual Studio Code: Open a terminal and run the following commands to install Visual Studio Code on Debian Linux:

    ```bash
    sudo snap install --classic code
    ```

2. Launch Visual Studio Code: After the installation is complete, you can launch Visual Studio Code from the Applications menu or by running the `code` command in the terminal.

### macOS

- Using Homebrew:
  - Install Homebrew if not installed:

      ```bash
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
      ```

  - If you have Homebrew installed, you can install Visual Studio Code by running the following command in the terminal:

      ```bash
      brew install --cask visual-studio-code
      ```

- Using the official site: Alternatively, you can visit the official Visual Studio Code site at [https://code.visualstudio.com/](https://code.visualstudio.com/) and download the installer for macOS.

## Linking Settings Files

Settings deployment is manifest-driven (entry `vscode_settings` in
`deploy_manifest.yaml` — see
[deploy_configs.md](./deploy_configs.md)):

```bash
cd ~/GitHub/dotfiles
uv run python src/deploy_configs.py status      # preview / drift report
uv run python src/deploy_configs.py             # deploy
```

Notes:

- macOS uses the `settings.mac.json` platform variant (the deployer resolves
  it automatically from the `settings.json` entry); Windows and Linux share
  `settings.json`.
- An existing live `settings.json` is backed up to `data/config_backups/` and
  replaced by a link to the repo version — local-only tweaks survive only in
  the backup.
- On Windows, enable Developer Mode so the deploy can create real symlinks
  without admin; otherwise the deploy falls back to a hard link (never a
  copy). After `git pull` on such machines, run
  `deploy_configs.py status` / re-deploy — it inode-checks hard links and
  re-links any that git orphaned.

### Workspace files

Workspace files are manifest-driven too (entry `vscode_workspace`). The repo
tracks one file per host, named `workspace.<host>.code-workspace` (lowercase
hostname), and the deploy resolves the right one for the current machine and
links it **next to the repo checkout**, e.g.:

```text
~/GitHub/envy.code-workspace -> ~/GitHub/dotfiles/application_configs/vscode/workspace.envy.code-workspace
```

The link must live in the repo's parent directory (`~/GitHub`, or
`~/HelloFreshProjects` on the HelloFresh laptop) because the workspace's
project folders are relative siblings of `dotfiles/`.

For a new machine, add
`application_configs/vscode/workspace.<host>.code-workspace` to the repo and
run the deploy — no manifest change is needed:

```bash
cd ~/GitHub/dotfiles
uv run python src/deploy_configs.py
```

## Installing Extensions

### Python

1. Open Visual Studio Code: Launch Visual Studio Code on either Windows or Debian Linux.

2. Open the Extensions view: Click on the square icon on the left sidebar or press `Ctrl+Shift+X` (Windows) or `Cmd+Shift+X` (Mac).

3. Search for the Python extension: In the search bar of the Extensions view, type "Python" and press Enter.

4. Select the Python extension: Look for the official "Python" extension by Microsoft in the search results and click on the "Install" button.

### Pylance

1. Open Visual Studio Code: Launch Visual Studio Code if it's not already open.

2. Open the Extensions view: Click on the square icon on the left sidebar or press `Ctrl+Shift+X` (Windows) or `Cmd+Shift+X` (Mac).

3. Search for the Pylance extension: In the search bar of the Extensions view, type "Pylance" and press Enter.

4. Select the Pylance extension: Look for the "Pylance" extension by Microsoft in the search results and click on the "Install" button.

### Jupyter

1. Open Visual Studio Code: Launch Visual Studio Code if it's not already open.

2. Open the Extensions view: Click on the square icon on the left sidebar or press `Ctrl+Shift+X` (Windows) or `Cmd+Shift+X` (Mac).

3. Search for the Jupyter extension: In the search bar of the Extensions view, type "Jupyter" and press Enter.

4. Select the Jupyter extension: Look for the "Jupyter" extension by Microsoft in the search results and click on the "Install" button.

### Black Formatter

1. Open Visual Studio Code: Launch Visual Studio Code if it's not already open.

2. Open the Extensions view: Click on the square icon on the left sidebar or press `Ctrl+Shift+X` (Windows) or `Cmd+Shift+X` (Mac).

3. Search for the Black extension: In the search bar of the Extensions view, type "Black" and press Enter.

4. Select the Black extension: Look for the "Black" extension by Microsoft in the search results and click on the "Install" button.

## Signing in with GitHub

1. Open Visual Studio Code: Launch Visual Studio Code on either Windows or Debian Linux.

2. Open the Source Control view: Click on the icon with three horizontal lines and a curved arrow on the left sidebar or press `Ctrl+Shift+G` (Windows) or `Cmd+Shift+G` (Mac).

## If using remote SSH connection with host machine without admin (portable Git and python)

- Set up Visual Studio Code settings to map to non-system level Git

Edit the file at `C:\Users\jason.christiansen\.vscode-server\data\Machine\settings.json`

- Add the following lines to the json file:

```json
{
  "git.path": "C:/Users/jason.christiansen/userapps/PortableGit/bin/git.exe",
  "terminal.integrated.env.windows": {
    "PATH": "C:/Users/jason.christiansen/userapps/PortableGit/bin;C:/Users/jason.christiansen/userapps/PortableGit/usr/bin;${env:PATH}",
    "GIT_SSH": "C:/Users/jason.christiansen/userapps/OpenSSH-Win64/ssh.exe"
  }
}
```

## Handling Remote SSH Connection Issues

### VS Code Remote SSH hangs on a Windows host

**Why this happens:** Every time VS Code updates on your Mac it pushes a new
`code-*.exe` server binary to the Windows host but never kills the old ones.
Multiple server versions end up running simultaneously, each spawning ~10 Node
processes at ~100% CPU each — enough to completely peg a 6-core machine and
cause code actions, formatting, and saves to hang indefinitely. A hard kill of
these processes can also cause VS Code to defensively disable extensions (e.g.
Jupyter) on reconnect as a crash-loop protection measure.

**Fix: kill all server and node processes on the Windows host**

Run in a terminal on the **Windows host** (PowerShell):

```powershell
# Kill all running vscode-server and node processes
Get-Process | Where-Object { $_.Name -like "code-*" } | Stop-Process -Force
Get-Process | Where-Object { $_.Name -eq "node" }     | Stop-Process -Force

# Remove ALL old server binaries for a clean reinstall on next connect
Get-ChildItem $env:USERPROFILE\\.vscode-server\\code-*.exe | Remove-Item -Force
```

Then reconnect from VS Code on your Mac — it will push a fresh server binary.

**After reconnecting:** Check the Extensions panel for any extensions showing
"Enable (Workspace)" — the hard kill may have disabled them as a crash
protection measure. Re-enable and reload when prompted.

**Prevent it recurring:** Pin the server install path in VS Code `settings.json`
so it always uses the same directory across reconnects:

```json
"remote.SSH.serverInstallPath": {
  "192.168.86.126": "%USERPROFILE%\\\\.vscode-server"
}
```
