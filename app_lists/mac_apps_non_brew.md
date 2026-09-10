# macOS installs that are not a Brewfile entry

Everything that *is* a plain Homebrew formula or cask lives in a list with an installer:

| List | Installer |
|------|-----------|
| `Brewfile` | `scripts/install_mac_apps.sh` |

What is left here needs a tap that has to be trusted first, a vendor installer, or the
App Store, none of which a Brewfile can express. `scripts/bootstrap.sh` prints a pointer
to this file at the end of a run.

## SQL Server ODBC driver on macOS (msodbcsql17)

Needed only on machines that run pyodbc code against SQL Server. Connection
strings name "ODBC Driver 17 for SQL Server", so install 17, not 18.

Not in the Brewfile on purpose: Microsoft's tap needs an explicit `brew trust`
before it installs, which would fail a fresh machine's unattended `brew bundle`
run.

```bash
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew trust microsoft/mssql-release
HOMEBREW_ACCEPT_EULA=Y brew install msodbcsql17
odbcinst -q -d    # the list should include [ODBC Driver 17 for SQL Server]
```

If pyodbc still reports the driver missing after that, the pip wheel is
ignoring Homebrew's config; point it there explicitly with
`export ODBCSYSINI=/opt/homebrew/etc`.

## Logitech apps

Installed from Logitech's own installers, not Homebrew:

- Logi Options
- Logitech G Hub

## App Store apps

- WireGuard
- GLKVM
