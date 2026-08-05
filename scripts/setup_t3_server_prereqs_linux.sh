#!/bin/bash
# Prep a Linux machine to serve as a T3 Code SSH environment.
# T3's SSH launcher needs Node ^22.16 || ^23.11 || >=24.10 resolvable from a
# NON-INTERACTIVE shell; it starts the headless t3 server itself, so Node is
# the only prereq this script handles (agent CLIs like `claude` still need to
# be installed and authed separately).
# Idempotent: safe to re-run. See docs/setup_t3_code.md.

set -euo pipefail

NODE_MAJOR_TARGET=24

version_ok() {
    local major minor
    major="$(echo "$1" | cut -d. -f1)"
    minor="$(echo "$1" | cut -d. -f2)"
    if [ "$major" -ge 25 ]; then return 0; fi
    if [ "$major" -eq 24 ] && [ "$minor" -ge 10 ]; then return 0; fi
    if [ "$major" -eq 23 ] && [ "$minor" -ge 11 ]; then return 0; fi
    if [ "$major" -eq 22 ] && [ "$minor" -ge 16 ]; then return 0; fi
    return 1
}

# A non-interactive shell won't source .bashrc nvm hooks, so check the way T3
# will see it: bare PATH lookup.
if command -v node >/dev/null 2>&1; then
    current="$(node -v | tr -d v)"
    if version_ok "$current"; then
        echo "node $current already satisfies T3's requirement — nothing to do."
        exit 0
    fi
    echo "node $current on PATH is too old for T3."
fi

export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    echo "nvm not found — installing to $NVM_DIR"
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
fi
# shellcheck disable=SC1091
. "$NVM_DIR/nvm.sh"

nvm install "$NODE_MAJOR_TARGET"
node_bin="$(dirname "$(nvm which "$NODE_MAJOR_TARGET")")"

# Symlink into ~/.local/bin so non-interactive shells (no nvm hook) find it.
mkdir -p "$HOME/.local/bin"
for tool in node npm npx; do
    ln -sf "$node_bin/$tool" "$HOME/.local/bin/$tool"
done
echo "Linked node/npm/npx from $node_bin into ~/.local/bin"

case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo "WARNING: ~/.local/bin is not on this shell's PATH. T3 needs it on" \
            "the NON-INTERACTIVE PATH (e.g. via ~/.profile or PermitUserEnvironment)" \
            "— verify with: ssh <this-host> 'node -v'" >&2 ;;
esac

echo "Done. Verify from another machine: ssh <this-host> 'node -v'"
