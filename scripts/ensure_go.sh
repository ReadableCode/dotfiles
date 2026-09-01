#!/bin/bash
# ensure_go.sh - resolve a usable Go toolchain on this machine, installing one
# if there is none. Covers linux (dnf/apt/pacman/zypper/apk), mac, wsl, termux
# and msys2, with the official tarball as the last resort.
#
# stdout is ONLY the absolute path to go, so a caller can use it directly:
#
#   go_bin="$(scripts/ensure_go.sh)" || return 1
#   "$go_bin" build .
#
# Progress and errors go to stderr. Nothing here is interactive beyond the sudo
# password prompt the package manager raises, so it is safe to call from the
# `cmdr` shell shim on first use.
#
# Usage:
#   ensure_go.sh              resolve, installing if needed
#   ensure_go.sh --check      resolve only, never install (exit 1 = missing)
#   ensure_go.sh --quiet      no progress chatter (failures still print)
#   ensure_go.sh --help

set -o pipefail

# go_apps/*/go.mod all declare `go 1.26.x`. A toolchain from 1.21 onward
# downloads a newer one on demand (GOTOOLCHAIN=auto is the default), so 1.21 is
# the real floor rather than 1.26 - but anything older cannot build these
# modules at all, which is exactly what Ubuntu 22.04's golang-go (1.18) is. A
# distro package below the floor is treated as absent and the tarball wins.
GO_MIN_MAJOR=1
GO_MIN_MINOR=21

CHECK_ONLY=""
QUIET=""

while [ $# -gt 0 ]; do
    case "$1" in
        --check)   CHECK_ONLY=1; shift ;;
        --quiet|-q) QUIET=1; shift ;;
        --help|-h) sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)         echo "ensure_go.sh: unknown option: $1" >&2; exit 2 ;;
    esac
done

say()  { [ -n "$QUIET" ] || printf 'ensure_go: %s\n' "$*" >&2; }
warn() { printf 'ensure_go: %s\n' "$*" >&2; }

have() { command -v "$1" >/dev/null 2>&1; }

# Run a privileged command. A PATH lookup for sudo only - never a probe of
# whether escalation would succeed, because some hosts mail on every failed
# sudo (docs/unified_cli_tui.md).
sudo_run() {
    if [ "$(id -u)" = "0" ]; then
        "$@"
    elif have sudo; then
        sudo "$@"
    else
        warn "root is needed for: $*"
        return 1
    fi
}

# %%
# Finding an existing toolchain #

go_new_enough() {
    # `go version` prints e.g. "go version go1.26.7 linux/amd64".
    local bin="$1" raw major minor
    raw="$("$bin" version 2>/dev/null)" || return 1
    raw="${raw#*go version go}"
    major="${raw%%.*}"
    raw="${raw#*.}"
    minor="${raw%%[!0-9]*}"
    case "$major$minor" in *[!0-9]*|"") return 1 ;; esac
    [ "$major" -gt "$GO_MIN_MAJOR" ] && return 0
    [ "$major" -eq "$GO_MIN_MAJOR" ] && [ "$minor" -ge "$GO_MIN_MINOR" ]
}

find_go() {
    # PATH first, then the install roots that are commonly NOT on PATH: the
    # official tarball's /usr/local/go, homebrew on apple silicon, Fedora's
    # golang layout, msys2's mingw prefix, termux's $PREFIX.
    local candidate
    for candidate in \
        "$(command -v go 2>/dev/null)" \
        /usr/local/go/bin/go \
        /opt/homebrew/bin/go \
        /usr/local/bin/go \
        /usr/lib/golang/bin/go \
        /mingw64/bin/go \
        "${PREFIX:-/nonexistent}/bin/go" \
        "$HOME/.local/go/bin/go"
    do
        [ -n "$candidate" ] || continue
        [ -x "$candidate" ] || continue
        if go_new_enough "$candidate"; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

# %%
# Installing #

detect_platform() {
    if [ -n "$TERMUX_VERSION" ] || [ -d /data/data/com.termux ]; then
        echo termux
    elif [ -n "$MSYSTEM" ]; then
        echo msys2
    elif [ "$(uname)" = "Darwin" ]; then
        echo mac
    elif [ "$(uname)" = "Linux" ]; then
        if grep -qi microsoft /proc/version 2>/dev/null; then echo wsl; else echo linux; fi
    else
        echo unsupported
    fi
}

install_from_package_manager() {
    local platform="$1"
    case "$platform" in
        mac)
            have brew || { warn "homebrew is not installed - see scripts/bootstrap.sh"; return 1; }
            say "installing go with homebrew"
            brew install go
            ;;
        termux)
            have pkg || return 1
            say "installing golang with pkg"
            pkg install -y golang
            ;;
        msys2)
            have pacman || return 1
            say "installing mingw-w64-x86_64-go with pacman"
            pacman -S --needed --noconfirm mingw-w64-x86_64-go
            ;;
        linux|wsl)
            # Package names differ per family; the first manager present wins,
            # matching how scripts/my_updater.sh picks one.
            if have dnf; then
                say "installing golang with dnf"
                sudo_run dnf install -y golang
            elif have apt-get; then
                say "installing golang-go with apt"
                sudo_run apt-get update && sudo_run apt-get install -y golang-go
            elif have pacman; then
                say "installing go with pacman"
                sudo_run pacman -S --needed --noconfirm go
            elif have zypper; then
                say "installing go with zypper"
                sudo_run zypper --non-interactive install go
            elif have apk; then
                say "installing go with apk"
                sudo_run apk add --no-cache go
            else
                warn "no supported package manager found"
                return 1
            fi
            ;;
        *)
            return 1
            ;;
    esac
}

go_tarball_arch() {
    case "$(uname -m)" in
        x86_64|amd64)   echo amd64 ;;
        aarch64|arm64)  echo arm64 ;;
        armv7l|armv6l)  echo armv6l ;;
        i386|i686)      echo 386 ;;
        *)              return 1 ;;
    esac
}

install_from_tarball() {
    # The route docs/setup_go.md documents by hand for the Raspberry Pi, and the
    # only one that works when the distro package is too old for go_apps/*.
    local platform="$1" os arch version url tmp
    case "$platform" in
        linux|wsl) os=linux ;;
        mac)       os=darwin ;;
        *)         return 1 ;;
    esac
    arch="$(go_tarball_arch)" || { warn "no go tarball for $(uname -m)"; return 1; }

    local fetch=""
    if have curl; then fetch="curl -fsSL"; elif have wget; then fetch="wget -qO-"; else
        warn "neither curl nor wget is available to download go"
        return 1
    fi

    version="$($fetch 'https://go.dev/VERSION?m=text' 2>/dev/null | head -n 1)"
    case "$version" in
        go[0-9]*) ;;
        *) warn "could not read the current go version from go.dev"; return 1 ;;
    esac

    url="https://go.dev/dl/${version}.${os}-${arch}.tar.gz"
    tmp="$(mktemp -d)" || return 1
    say "downloading $version for ${os}-${arch}"
    if have curl; then
        curl -fsSL -o "$tmp/go.tar.gz" "$url" || { rm -rf "$tmp"; warn "download failed: $url"; return 1; }
    else
        wget -qO "$tmp/go.tar.gz" "$url" || { rm -rf "$tmp"; warn "download failed: $url"; return 1; }
    fi

    # Replace only a directory that actually holds a go toolchain, so a typo or
    # an unrelated /usr/local/go can never turn this into a blind rm -rf.
    if [ -e /usr/local/go ]; then
        if [ -x /usr/local/go/bin/go ] || [ -f /usr/local/go/VERSION ]; then
            say "replacing the existing toolchain in /usr/local/go"
            sudo_run rm -rf /usr/local/go || { rm -rf "$tmp"; return 1; }
        else
            warn "/usr/local/go exists but is not a go toolchain - leaving it alone"
            rm -rf "$tmp"
            return 1
        fi
    fi

    say "extracting to /usr/local/go"
    sudo_run tar -C /usr/local -xzf "$tmp/go.tar.gz"
    local status=$?
    rm -rf "$tmp"
    [ "$status" -eq 0 ] || return 1

    # ~/.bashrc puts /usr/local/go/bin on PATH when it exists, so this is only
    # for the caller's current process.
    say "installed $version (open a new shell to get go on PATH)"
}

# %%
# Main #

if go_bin="$(find_go)"; then
    printf '%s\n' "$go_bin"
    exit 0
fi

if [ -n "$CHECK_ONLY" ]; then
    warn "no go toolchain (>= ${GO_MIN_MAJOR}.${GO_MIN_MINOR}) found"
    exit 1
fi

PLATFORM="$(detect_platform)"
if [ "$PLATFORM" = "unsupported" ]; then
    warn "unsupported platform: $(uname). Use scripts/ensure_go.ps1 on Windows."
    exit 1
fi

say "no go toolchain found on this $PLATFORM machine - installing one"
# >&2 on the whole install, because stdout here belongs to the caller: dnf,
# brew and pacman all print their transaction tables to stdout, and without
# this the caller gets a package list glued onto the front of the go path.
install_from_package_manager "$PLATFORM" >&2

if go_bin="$(find_go)"; then
    say "using $go_bin ($("$go_bin" version 2>/dev/null))"
    printf '%s\n' "$go_bin"
    exit 0
fi

# No package, a package below the floor, or an install that could not complete
# (no sudo). All the same situation from here: get the toolchain straight from
# go.dev. Any error from the attempt above is already on stderr.
say "no usable go from the package manager - falling back to the official tarball"
install_from_tarball "$PLATFORM" >&2      # same reason as above

if go_bin="$(find_go)"; then
    say "using $go_bin ($("$go_bin" version 2>/dev/null))"
    printf '%s\n' "$go_bin"
    exit 0
fi

warn "could not install go automatically - see docs/setup_go.md"
exit 1
