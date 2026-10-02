# Linux installs that are not a plain package name

Everything that *is* a plain package name now lives in a list with an installer:

| List | Installer |
|------|-----------|
| `linux_apps.txt` | `scripts/install_linux_apps.sh` (apt) |
| `linux_apps_wsl.txt` | `scripts/install_linux_apps_wsl.sh` (apt, CLI subset) |
| `linux_apps_dnf.txt` | `scripts/install_linux_apps_dnf.sh` (Fedora) |
| `linux_apps_flatpak.txt` | `scripts/install_linux_apps_flatpak.sh` (flathub) |

What is left here needs a third-party repo, a vendor script, hardware-specific
packages, or a step after the install — none of which a package list can express.
`scripts/bootstrap.sh` prints a pointer to this file at the end of a run.

## uv

Not packaged for apt. Fedora has it in dnf, but the install script works everywhere:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

`scripts/bootstrap.sh` runs this for you if `uv` is missing.

If `uv` came from dnf instead (`/usr/bin/uv`), that package ships `/etc/uv/uv.toml`
with `python-downloads = "manual"` and `python-preference = "system"`, and uv merges it
under the user config. A repo pinning a Python the machine lacks then fails `uv sync` with
"No interpreter found", and a repo without a `.python-version` gets `/usr/bin/python3`,
which has no headers, so a package with no wheel for that version fails to build with
"Python.h: No such file or directory". The `uv_config` entry in `deploy_manifest.yaml`
deploys `~/.config/uv/uv.toml` with `python-downloads = "automatic"` and
`python-preference = "managed"`, which take precedence, so uv picks and downloads Pythons
the same way it does on macOS.

On Fedora, uv needs `libxcrypt-compat` (in `linux_apps_dnf.txt`) or it fails to start.
Then, in a repo:

```bash
uv python pin 3.10.12   # only if the pinned version differs from the system one
uv sync
```

## VS Code on Fedora

Needs the Microsoft repo added before `dnf install code` will resolve, so it cannot go
in `linux_apps_dnf.txt`:

```bash
sudo rpm --import https://packages.microsoft.com/keys/microsoft.asc
echo -e "[code]\nname=Visual Studio Code\nbaseurl=https://packages.microsoft.com/yumrepos/vscode\nenabled=1\nautorefresh=1\ntype=rpm-md\ngpgcheck=1\ngpgkey=https://packages.microsoft.com/keys/microsoft.asc" | sudo tee /etc/yum.repos.d/vscode.repo > /dev/null
dnf check-update
sudo dnf install code
```

The yum repo can lag the current release by up to three hours.

## Parsec on Fedora: GPU drivers

Parsec itself is in `linux_apps_flatpak.txt`. Hardware acceleration is not — the driver
packages depend on the GPU in the machine.

NVIDIA:

```bash
sudo dnf install \
  https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm \
  https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm
sudo dnf install akmod-nvidia xorg-x11-drv-nvidia-cuda nvidia-settings
flatpak install flathub org.freedesktop.Platform.GL.nvidia-$(nvidia-smi --query-gpu=driver_version --format=csv,noheader)//23.08
```

Intel / AMD:

```bash
flatpak install flathub org.freedesktop.Platform.VAAPI.Intel//23.08
flatpak install flathub org.freedesktop.Platform.VAAPI.AMD//23.08
```

Reboot before any of this takes effect.
