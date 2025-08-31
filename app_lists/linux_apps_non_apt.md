# Tools not in apt

## uv

### Install uv on Linux

- Install with script:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

- This is availble with dnf on Fedora so dont need install script but ther are other steps

```bash
# 1) fix missing libcrypt.so.1
sudo dnf install -y libxcrypt-compat

# 2) (already installed 3.10.12) tell uv to use it in THIS repo
uv python pin 3.10.12

# 3) create/refresh venv + deps
uv sync

```

## VSCode on Fedora

RHEL, Fedora, and CentOS based distributions

We currently ship the stable 64-bit VS Code for RHEL, Fedora, or CentOS based distributions in a yum repository.

Install the key and yum repository by running the following script:

```bash
sudo rpm --import https://packages.microsoft.com/keys/microsoft.asc
echo -e "[code]\nname=Visual Studio Code\nbaseurl=https://packages.microsoft.com/yumrepos/vscode\nenabled=1\nautorefresh=1\ntype=rpm-md\ngpgcheck=1\ngpgkey=https://packages.microsoft.com/keys/microsoft.asc" | sudo tee /etc/yum.repos.d/vscode.repo > /dev/null
```

Then update the package cache and install the package using dnf (Fedora 22 and above):

```bash
dnf check-update
sudo dnf install code # or code-insiders
```

Or on older versions using yum:

```bash
yum check-update
sudo yum install code # or code-insiders
```

Note

Due to the manual signing process and the publishing system we use, the yum repo could lag behind by up to three hours and not immediately get the latest version of VS Code

## Parsec on Fedora

- Install Flatpak support if needed

```bash
sudo dnf install flatpak
```

- Add Flathub (if not already added)

```bash
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
```

- Install Parsec

```bash
flatpak install flathub com.parsecgaming.parsec
```

- Install NVidia Drivers

```bash
sudo dnf install akmod-nvidia xorg-x11-drv-nvidia-cuda nvidia-settings
sudo dnf install \
  https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm \
  https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm
```

- For Intel/AMD

```bash
flatpak install flathub org.freedesktop.Platform.VAAPI.Intel//23.08
flatpak install flathub org.freedesktop.Platform.VAAPI.AMD//23.08
```

- For NVIDIA

```bash
flatpak install flathub org.freedesktop.Platform.GL.nvidia-$(nvidia-smi --query-gpu=driver_version --format=csv,noheader)//23.08
```

- Restart your computer before it will take effect.

## KDE Connect

- is in dnf but needs to be enabled after installation

```bash
sudo dnf install gnome-shell-extension-gsconnect
```

- Need to log out and log back in for the changes to take effect.

```bash
gnome-extensions enable gsconnect@andyholmes.github.io
```

- Phone icon will appear in the system tray.

## Discord

```bash
flatpak install -y flathub com.discordapp.Discord
```

## FB Messenger

```bash
flatpak install -y flathub com.sindresorhus.Caprine
```
