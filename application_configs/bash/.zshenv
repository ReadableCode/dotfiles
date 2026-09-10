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
