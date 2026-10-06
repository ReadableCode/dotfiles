# Sourced by EVERY zsh - interactive, login, scripts, launchd jobs, agent tool
# calls. Deliberately silent: no echo, no banner. A stdio MCP server is started
# through a shell, and anything on stdout there breaks the JSON-RPC framing.
#
# Machine-local exports live in ~/.zshenv.local (per-host variants only, see
# the zshenv_local manifest entry). They are here rather than in ~/.zshrc.local
# because .zshrc is interactive-only: exports placed there are invisible to
# every script and daemon, which on Envy silently refilled the internal disk
# the external-SSD cache redirect exists to protect.

[[ -f "$HOME/.cargo/env" ]] && . "$HOME/.cargo/env"

[[ -f ~/.zshenv.local ]] && source ~/.zshenv.local

# Microsoft's SQL Server ODBC driver (msodbcsql17, brew) dlopens libssl from
# /opt/homebrew/opt/openssl/lib, the `openssl` alias, and only accepts 1.x or
# 3.x. Since brew moved the alias to openssl@4 (2026-10) every pyodbc connect
# fails with "OpenSSL library could not be loaded". Putting openssl@3 first on
# the loader path is what the driver needs; no other installed binary links a
# library by one of these leaf names at a different version. Drop this once
# the driver formula depends on openssl@3 again (verify: strings
# /opt/homebrew/lib/libmsodbcsql.17.dylib | grep opt/openssl).
if [[ -f /opt/homebrew/lib/libmsodbcsql.17.dylib && -d /opt/homebrew/opt/openssl@3/lib ]]; then
    export DYLD_LIBRARY_PATH="/opt/homebrew/opt/openssl@3/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
fi
