#!/bin/bash
# Prep a Linux machine to serve as a T3 Code server (SSH environment or the
# always-on `t3 service install` boot service).
# Two prereqs are handled here:
#   1. Node ^22.16 || ^23.11 || >=24.10 resolvable from a NON-INTERACTIVE shell
#      (that's how T3's SSH launcher sees it).
#   2. A C++ toolchain — the npm `t3` package depends on node-pty, which ships
#      no linux-x64 prebuild, so npm compiles it from source on install. With
#      no g++ the build dies as a bare `make ... Error 127` and `npx t3 ...`
#      then exits 1 printing NOTHING, which is a miserable thing to debug.
# Agent CLIs (`claude`, ...) still need to be installed and authed separately.
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

ensure_cxx_toolchain() {
    if command -v c++ >/dev/null 2>&1 || command -v g++ >/dev/null 2>&1; then
        echo "C++ toolchain present — node-pty can build."
        return 0
    fi
    echo "No C++ compiler on PATH; the npm t3 install would fail building node-pty."
    local install_cmd=""
    if command -v dnf >/dev/null 2>&1; then
        install_cmd="dnf install -y gcc-c++ make"
    elif command -v apt-get >/dev/null 2>&1; then
        install_cmd="apt-get install -y build-essential"
    elif command -v pacman >/dev/null 2>&1; then
        install_cmd="pacman -S --needed --noconfirm gcc make"
    else
        echo "ERROR: unknown package manager — install a C++ compiler (g++) by hand." >&2
        return 1
    fi
    echo "Installing it: sudo $install_cmd"
    # shellcheck disable=SC2086
    sudo $install_cmd
}

# A non-interactive shell won't source .bashrc nvm hooks, so check the way T3
# will see it: bare PATH lookup.
node_ok=false
if command -v node >/dev/null 2>&1; then
    current="$(node -v | tr -d v)"
    if version_ok "$current"; then
        echo "node $current already satisfies T3's requirement."
        node_ok=true
    else
        echo "node $current on PATH is too old for T3."
    fi
fi

if [ "$node_ok" = true ]; then
    ensure_cxx_toolchain
    echo "Done. Verify from another machine: ssh <this-host> 'node -v'"
    exit 0
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

ensure_cxx_toolchain

echo "Done. Verify from another machine: ssh <this-host> 'node -v'"
