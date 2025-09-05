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

1. To link your settings file in a repository to Visual Studio Code

    - Windows: Open powershell as administrator and run the following commands:

        ```powershell
        mv "C:\Users\jason\AppData\Roaming\Code\User\settings.json" "C:\Users\jason\AppData\Roaming\Code\User\settings.json.bak"
        # OR
        rm "C:\Users\jason\AppData\Roaming\Code\User\settings.json"
        cmd /c mklink "C:\Users\jason\AppData\Roaming\Code\User\settings.json" "C:\Users\jason\GitHub\dotfiles\application_configs\vscode\settings.json"
        ```

    - Linux: Open a terminal and run the following commands:

        ```bash
        mv ~/.config/Code/User/settings.json ~/.config/Code/User/settings.json.bak
        ln -s /path/to/settings/in/your/repository.json ~/.config/Code/User/settings.json
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
