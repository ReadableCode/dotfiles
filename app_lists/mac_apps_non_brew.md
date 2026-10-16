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

## Xcode (MacBookProM5 only)

Xcode-beta and its iOS and watchOS simulator runtimes, for building iPhone,
iPad and Apple Watch apps. Installed on MacBookProM5 and no other Mac: Envy
and any other Mac keep only the Command Line Tools Homebrew brings. Steps and
the reason for the scope in `docs/setup_xcode_beta.md`.
