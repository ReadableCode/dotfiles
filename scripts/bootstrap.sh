#!/bin/bash
# Bare machine -> cloned, synced, deployed, packages installed.
#
# Covers macOS, Linux, WSL and Termux. Every step is idempotent, so this doubles
# as a repair tool: a second run on a working machine should change nothing.
#
# From a bare machine:
#   curl -fsSL https://raw.githubusercontent.com/ReadableCode/dotfiles/master/scripts/bootstrap.sh | bash
#
# From an existing clone:
#   bash scripts/bootstrap.sh --dry-run
#
# Options:
#   --credentials URL   clone this credentials repo (repeatable). These are ssh
#                       working repos on specific machines, so the URLs are not
#                       stored here - see cloning_credentials_repos.md in the
#                       personal credentials repo for the list.
#   --root DIR          repos root (default: $HOME/GitHub, or $HOME/GitHubWSL if
#                       that already exists and $HOME/GitHub does not)
#   --dry-run           report what would happen and change nothing
#   --yes               never prompt
#   --skip-apps         skip the package install step
#   --help

set -o pipefail

DOTFILES_URL="https://github.com/ReadableCode/dotfiles.git"

DRY_RUN=""
ASSUME_YES=""
SKIP_APPS=""
REPOS_ROOT=""
CREDENTIALS_URLS=""
MANUAL_NOTES=""

# %%
# Output helpers #

if [ -t 1 ] && [ -z "$NO_COLOR" ]; then
    C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_GREEN=$'\033[32m'
    C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_CYAN=$'\033[36m'
else
    C_RESET=""; C_BOLD=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_CYAN=""
fi

step() { printf '\n%s==> %s%s\n' "$C_BOLD$C_CYAN" "$*" "$C_RESET"; }
ok()   { printf '    %sok%s      %s\n' "$C_GREEN" "$C_RESET" "$*"; }
skip() { printf '    %sskip%s    %s\n' "$C_GREEN" "$C_RESET" "$*"; }
todo() { printf '    %swould%s   %s\n' "$C_YELLOW" "$C_RESET" "$*"; }
warn() { printf '    %swarn%s    %s\n' "$C_YELLOW" "$C_RESET" "$*"; }
fail() { printf '    %sfail%s    %s\n' "$C_RED" "$C_RESET" "$*" >&2; }

note_manual() { MANUAL_NOTES="$MANUAL_NOTES$1
"; }

# Run a command unless this is a dry run. Prints what it is about to do.
run() {
    if [ -n "$DRY_RUN" ]; then
        todo "$*"
        return 0
    fi
    "$@"
}

confirm() {
    [ -n "$ASSUME_YES" ] && return 0
    [ -n "$DRY_RUN" ] && return 0
    printf '    %s [y/N] ' "$1"
    read -r reply
    case "$reply" in [Yy]*) return 0 ;; *) return 1 ;; esac
}

# %%
# Arguments #

while [ $# -gt 0 ]; do
    case "$1" in
        --credentials) CREDENTIALS_URLS="$CREDENTIALS_URLS $2"; shift 2 ;;
        --root)        REPOS_ROOT="$2"; shift 2 ;;
        --dry-run)     DRY_RUN=1; shift ;;
        --yes|-y)      ASSUME_YES=1; shift ;;
        --skip-apps)   SKIP_APPS=1; shift ;;
        --help|-h)     sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)             fail "unknown option: $1"; exit 2 ;;
    esac
done

# %%
# Platform #

detect_platform() {
    if [ -n "$TERMUX_VERSION" ] || [ -d /data/data/com.termux ]; then
        echo termux
    elif [ "$(uname)" = "Darwin" ]; then
        echo mac
    elif [ "$(uname)" = "Linux" ]; then
        if grep -qi microsoft /proc/version 2>/dev/null; then echo wsl; else echo linux; fi
    else
        echo unsupported
    fi
}

PLATFORM="$(detect_platform)"

step "Platform"
if [ "$PLATFORM" = "unsupported" ]; then
    fail "unsupported platform: $(uname). Use scripts/bootstrap.ps1 on Windows."
    exit 1
fi
ok "$PLATFORM ($(uname -s) $(uname -m))"
[ -n "$DRY_RUN" ] && warn "dry run: nothing will be changed"

# %%
# Repos root #

step "Repos root"
if [ -z "$REPOS_ROOT" ]; then
    # Task 03 keeps GitHubWSL as a legacy root; use it only if it already exists
    # and the standard root does not, so no machine gets migrated by surprise.
    if [ ! -d "$HOME/GitHub" ] && [ -d "$HOME/GitHubWSL" ]; then
        REPOS_ROOT="$HOME/GitHubWSL"
    else
        REPOS_ROOT="$HOME/GitHub"
    fi
fi
if [ -d "$REPOS_ROOT" ]; then
    skip "$REPOS_ROOT exists"
else
    run mkdir -p "$REPOS_ROOT" && ok "created $REPOS_ROOT"
fi
DOTFILES_DIR="$REPOS_ROOT/dotfiles"

# %%
# Prerequisites #

have() { command -v "$1" >/dev/null 2>&1; }

step "Package manager"
case "$PLATFORM" in
    mac)
        if have brew; then
            skip "homebrew present ($(brew --version 2>/dev/null | head -1))"
        else
            warn "homebrew missing"
            if confirm "install homebrew?"; then
                run /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
                # Apple silicon puts brew outside the default PATH until a shell restart.
                [ -x /opt/homebrew/bin/brew ] && eval "$(/opt/homebrew/bin/brew shellenv)"
            else
                note_manual "install homebrew: https://brew.sh"
            fi
        fi
        ;;
    linux|wsl)
        if have apt; then
            skip "apt present"
        elif have dnf; then
            skip "dnf present (fedora family)"
        else
            warn "neither apt nor dnf found - packages will be skipped"
        fi
        ;;
    termux)
        if have pkg; then skip "pkg present"; else fail "pkg not found in termux"; fi
        ;;
esac

step "git"
if have git; then
    skip "git present ($(git --version))"
else
    warn "git missing"
    case "$PLATFORM" in
        mac)        run brew install git ;;
        linux|wsl)  run sudo apt update && run sudo apt install -y git ;;
        termux)     run pkg install -y git ;;
    esac
fi

step "uv"
if have uv; then
    skip "uv present ($(uv --version 2>/dev/null))"
elif [ "$PLATFORM" = "termux" ]; then
    # uv has no termux build; the src/ tooling is skipped there instead of failing.
    warn "uv is not available on termux - skipping the python steps"
    note_manual "termux: src/ tooling (clone_repos, deploy_configs) needs uv and is not run here"
else
    warn "uv missing"
    if confirm "install uv?"; then
        run sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
        [ -x "$HOME/.local/bin/uv" ] && PATH="$HOME/.local/bin:$PATH"
    else
        note_manual "install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    fi
fi

# %%
# dotfiles #

step "dotfiles clone"
if [ -d "$DOTFILES_DIR/.git" ]; then
    skip "$DOTFILES_DIR already cloned"
else
    # https, not ssh: a bare machine has no GitHub key yet. Switch the remote to
    # ssh later if you want to push from this machine.
    run git clone "$DOTFILES_URL" "$DOTFILES_DIR" || { fail "could not clone dotfiles"; exit 1; }
    ok "cloned dotfiles"
    note_manual "dotfiles remote is https; switch to ssh to push from this machine"
fi

# %%
# Credentials repos #

step "Credentials repos"
found_any=""
for dir in "$REPOS_ROOT"/*_credentials; do
    [ -d "$dir/.git" ] || continue
    skip "$(basename "$dir") already cloned"
    found_any=1
done

for url in $CREDENTIALS_URLS; do
    name="$(basename "$url" .git)"
    if [ -d "$REPOS_ROOT/$name/.git" ]; then
        continue
    fi
    run git clone "$url" "$REPOS_ROOT/$name" && ok "cloned $name"
    found_any=1
done

if [ -z "$found_any" ] && [ -z "$CREDENTIALS_URLS" ]; then
    warn "no credentials repo cloned - configs and repo lists that ride them will be missing"
    note_manual "clone your credentials repo(s): bootstrap.sh --credentials <ssh-url> (see cloning_credentials_repos.md)"
fi

# %%
# Python tooling #

# The read-only reports (clone_repos --list, deploy_configs status) are run for
# real even in a dry run - that report is the point of the dry run.
uv_ready() {
    if ! have uv; then
        warn "skipped (uv unavailable)"
        return 1
    fi
    if [ ! -d "$DOTFILES_DIR" ]; then
        warn "skipped (no dotfiles clone yet)"
        return 1
    fi
    return 0
}

step "Dependencies"
if uv_ready; then
    if [ -n "$DRY_RUN" ]; then
        todo "uv sync (in $DOTFILES_DIR)"
    elif ( cd "$DOTFILES_DIR" && uv sync ); then
        ok "dependencies synced"
    else
        fail "uv sync failed - the steps below will not work"
    fi
fi

step "Sibling repos"
if uv_ready; then
    if [ -n "$DRY_RUN" ]; then
        ( cd "$DOTFILES_DIR" && uv run python src/clone_repos.py --list ) || warn "could not list repos (are deps synced?)"
    elif ! ( cd "$DOTFILES_DIR" && uv run python src/clone_repos.py ${ASSUME_YES:+--yes} ); then
        fail "clone_repos failed - sibling repos may be missing"
    fi
fi

step "Deploy configs"
if uv_ready; then
    if [ -n "$DRY_RUN" ]; then
        # status exits non-zero when there is drift; that is a report, not a failure.
        ( cd "$DOTFILES_DIR" && uv run python src/deploy_configs.py status ) || true
    else
        ( cd "$DOTFILES_DIR" && uv run python src/deploy_configs.py ) &&
            ( cd "$DOTFILES_DIR" && uv run python src/deploy_configs.py status ) || true
    fi
fi

# %%
# Packages #

step "Packages"
if [ -n "$SKIP_APPS" ]; then
    skip "--skip-apps given"
else
    installers=""
    case "$PLATFORM" in
        mac)    installers="install_mac_apps.sh" ;;
        wsl)    installers="install_linux_apps_wsl.sh" ;;
        termux) installers="install_android_termux_apps.sh" ;;
        linux)
            # Debian and Fedora families take different lists; flatpak is separate
            # again and only runs where it is actually installed.
            if have apt; then installers="install_linux_apps.sh"; fi
            if have dnf; then installers="$installers install_linux_apps_dnf.sh"; fi
            if have flatpak; then installers="$installers install_linux_apps_flatpak.sh"; fi
            [ -z "$installers" ] && warn "no supported package manager found"
            ;;
    esac

    for installer in $installers; do
        installer_path="$DOTFILES_DIR/scripts/$installer"
        if [ ! -f "$installer_path" ]; then
            fail "installer not found: $installer_path (is this clone up to date?)"
            continue
        fi
        # ASSUME_YES only when the caller asked for it; otherwise the installer's
        # own single prompt still gives a chance to deselect.
        if [ -n "$DRY_RUN" ]; then
            DRY_RUN=1 ASSUME_YES=1 bash "$installer_path"
        else
            ASSUME_YES="$ASSUME_YES" bash "$installer_path"
        fi
    done
fi

# %%
# Go toolchain #

# The app lists carry go, so on most platforms the step above already installed
# it. This one is the guarantee: it also covers --skip-apps, a machine whose
# package manager has no go, and a distro package too old to build go_apps/*.
# cmdr calls the same script on first use, so a machine that skips this here
# still ends up with a toolchain the first time anyone types cmdr.
step "go"
ENSURE_GO="$DOTFILES_DIR/scripts/ensure_go.sh"
if [ ! -f "$ENSURE_GO" ]; then
    fail "not found: $ENSURE_GO (is this clone up to date?)"
elif [ -n "$DRY_RUN" ]; then
    if go_path="$(bash "$ENSURE_GO" --check --quiet)"; then
        skip "go present ($go_path)"
    else
        todo "install a go toolchain"
    fi
elif go_path="$(bash "$ENSURE_GO")"; then
    ok "go ready ($go_path)"
else
    warn "no go toolchain - cmdr and the other go_apps cannot be built"
    note_manual "install go by hand: docs/setup_go.md"
fi

# %%
# What is left #

step "Still manual"
case "$PLATFORM" in
    linux|wsl)
        note_manual "app_lists/linux_apps_non_apt.md: uv script, VS Code dnf repo, flatpak apps, gsconnect enable step"
        ;;
esac
note_manual "OS settings (keyboard, display, power) are not managed - see the docs/setup_*_workstation.md guide for this platform"

if [ -z "$MANUAL_NOTES" ]; then
    ok "nothing outstanding"
else
    printf '%s' "$MANUAL_NOTES" | while IFS= read -r line; do
        [ -n "$line" ] && printf '    %s-%s %s\n' "$C_YELLOW" "$C_RESET" "$line"
    done
fi

step "Done"
if [ -n "$DRY_RUN" ]; then
    ok "dry run complete - re-run without --dry-run to apply"
else
    ok "bootstrap complete. Open a new shell to pick up the deployed shell config."
fi
