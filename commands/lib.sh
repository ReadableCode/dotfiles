#!/usr/bin/env bash
# Step functions for dotfiles commands (darwin + linux). Sourced by cmdr,
# never executed directly. Each step is a function; <step>_check is its
# read-only drift probe (exit nonzero = drift found). cmdr exports:
#   CMDR_REPO_DIR  this repo's checkout (the dotfiles dir)
#   CMDR_GIT_DIR   the parent holding all sibling repos

# --- update ---

dotfiles_pull() {
    # Pull before anything else so configs_deploy links the latest configs.
    git -C "$CMDR_REPO_DIR" pull --ff-only \
        || echo "WARNING: dotfiles pull failed (offline or diverged) - resolve manually in $CMDR_REPO_DIR"
}

dotfiles_pull_check() {
    git -C "$CMDR_REPO_DIR" fetch --quiet || { echo "dotfiles: fetch failed (offline?)"; return 0; }
    local behind
    behind=$(git -C "$CMDR_REPO_DIR" rev-list --count 'HEAD..@{u}' 2>/dev/null || echo 0)
    if [ "${behind:-0}" -gt 0 ]; then
        echo "dotfiles: $behind commit(s) behind origin"
        return 1
    fi
    echo "dotfiles: up to date"
}

configs_deploy() {
    (cd "$CMDR_REPO_DIR" && uv run python src/deploy_configs.py)
}

configs_deploy_check() {
    # status is read-only and already exits nonzero when anything needs
    # attention (see run_status in deploy_configs.py).
    (cd "$CMDR_REPO_DIR" && uv run python src/deploy_configs.py status)
}

packages_upgrade() {
    case "$(uname)" in
      Darwin)
        echo "Checking for macOS system updates..."
        sudo softwareupdate -i -a
        echo "Updating and upgrading brew..."
        brew update
        brew upgrade
        brew upgrade --cask
        brew upgrade --cask --greedy
        brew cleanup
        ;;
      Linux)
        # dnf first: Fedora ships both dnf and (sometimes) an apt shim.
        if command -v dnf >/dev/null 2>&1; then
            sudo dnf -y upgrade --refresh
            sudo dnf -y autoremove
        elif command -v apt >/dev/null 2>&1; then
            sudo apt update
            sudo apt -y upgrade
            sudo apt -y dist-upgrade
            sudo apt -y autoremove
        else
            echo "neither dnf nor apt found, skipping package upgrades"
        fi
        ;;
    esac
}

packages_upgrade_check() {
    case "$(uname)" in
      Darwin)
        local outdated
        outdated=$(brew outdated --quiet | wc -l | tr -d ' ')
        if [ "$outdated" -gt 0 ]; then
            echo "brew: $outdated package(s) outdated:"
            brew outdated
            return 1
        fi
        echo "brew: everything up to date"
        ;;
      Linux)
        if command -v dnf >/dev/null 2>&1; then
            # dnf check-update exits 100 when updates exist, 0 when clean.
            dnf -q check-update
            local rc=$?
            if [ "$rc" -eq 100 ]; then
                echo "dnf: updates available"
                return 1
            elif [ "$rc" -ne 0 ]; then
                echo "dnf: check failed (rc=$rc)"
            else
                echo "dnf: up to date"
            fi
        elif command -v apt >/dev/null 2>&1; then
            # No 'apt update' here: that needs sudo and a check must stay
            # read-only, so the count is as fresh as the last index refresh.
            local upgradable
            upgradable=$(apt list --upgradable 2>/dev/null | grep -c upgradable)
            if [ "${upgradable:-0}" -gt 0 ]; then
                echo "apt: $upgradable package(s) upgradable (as of last index refresh)"
                return 1
            fi
            echo "apt: up to date (as of last index refresh)"
        fi
        ;;
    esac
}

sysinfo() {
    fastfetch
}

# --- demo (safe: echo and sleep only) ---

demo_hello() {
    echo "hello from $(hostname) ($(uname))"
}

demo_tick() {
    for i in 1 2 3; do
        echo "tick $i"
        sleep 1
    done
}

demo_tick_check() {
    echo "demo: nothing would change"
}

demo_done() {
    echo "demo complete"
}
