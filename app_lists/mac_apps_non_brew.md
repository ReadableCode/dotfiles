# macOS installs that are not a Brewfile entry

Everything that *is* a plain Homebrew formula or cask lives in a list with an installer:

| List | Installer |
|------|-----------|
| `Brewfile` | `scripts/install_mac_apps.sh` |

What is left here needs a vendor installer or the App Store, neither of which a
Brewfile can express. `scripts/bootstrap.sh` prints a pointer
to this file at the end of a run.

## Logitech apps

Installed from Logitech's own installers, not Homebrew:

- Logi Options
- Logitech G Hub

## App Store apps

- WireGuard
- GLKVM
