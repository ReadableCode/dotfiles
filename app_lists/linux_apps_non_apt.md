# Tools not in apt

## uv

### Install uv on Linux

- Install with script:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
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
