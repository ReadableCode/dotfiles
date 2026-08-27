#!/usr/bin/env bash
# Step functions for dotfiles commands (darwin + linux). Sourced by cmdr,
# never executed directly. Each step is a function; <step>_check is its
# read-only drift probe (exit nonzero = drift found). cmdr exports:
#   CMDR_REPO_DIR  this repo's checkout (the dotfiles dir)
#   CMDR_GIT_DIR   the parent holding all sibling repos

# --- deploy ---

configs_deploy() {
    # --problems: changes only, not the healthy/not-applicable census -
    # the TUI pane (and a human) needs signal, not inventory.
    (cd "$CMDR_REPO_DIR" && uv run python src/deploy_configs.py --problems)
}

configs_deploy_check() {
    # status is read-only and already exits nonzero when anything needs
    # attention (see run_status in deploy_configs.py).
    (cd "$CMDR_REPO_DIR" && uv run python src/deploy_configs.py status --problems)
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

# --- pull (the gitpullall flow) ---

repos_pull() {
    # Exec the existing git_puller binary: the pulls fan out in goroutines
    # there, so concurrency is preserved, not reimplemented.
    local arch os bin
    arch=$(uname -m)
    os=$(uname -s | tr '[:upper:]' '[:lower:]')
    bin="$CMDR_GIT_DIR/dotfiles/go_apps/git_puller/git_puller"
    if [ "$os" = "darwin" ]; then
        if [ "$arch" = "arm64" ] || [ "$arch" = "aarch64" ]; then
            bin="${bin}_mac_arm"
        else
            bin="${bin}_mac_x86"
        fi
    elif [ "$os" = "linux" ]; then
        if [ "$arch" = "arm64" ] || [ "$arch" = "aarch64" ]; then
            bin="${bin}_arm"
        fi
    fi
    chmod +x "$bin"
    "$bin" -path "$CMDR_GIT_DIR" -r
}

repos_pull_check() {
    # Read-only twin of repos_pull: fetch every repo CONCURRENTLY (one
    # background job each, mirroring git_puller's fan-out) and report which
    # are behind their upstream. Quiet repos print nothing.
    local tmp dir name count=0
    tmp=$(mktemp -d) || return 0
    for dir in "$CMDR_GIT_DIR"/*/; do
        [ -d "$dir/.git" ] || continue
        name=$(basename "$dir")
        count=$((count + 1))
        (
            if ! git -C "$dir" fetch --quiet 2>/dev/null; then
                echo "  $name: fetch failed (offline or no remote)"
                exit 0
            fi
            behind=$(git -C "$dir" rev-list --count 'HEAD..@{u}' 2>/dev/null || echo 0)
            if [ "${behind:-0}" -gt 0 ]; then
                echo "  $name: $behind commit(s) behind"
                echo "$name" >> "$tmp/.drift"
            fi
        ) > "$tmp/$name.out" 2>&1 &
    done
    wait
    cat "$tmp"/*.out 2>/dev/null
    local drifted=0
    [ -f "$tmp/.drift" ] && drifted=$(wc -l < "$tmp/.drift" | tr -d ' ')
    rm -rf "$tmp"
    if [ "$drifted" -gt 0 ]; then
        echo "checked $count repos concurrently: $drifted behind"
        return 1
    fi
    echo "checked $count repos concurrently: all up to date"
}

repos_clone() {
    (cd "$CMDR_REPO_DIR" && uv run python src/clone_repos.py)
}

repos_clone_check() {
    # cmdr's built-in already knows the yaml and exits 1 on missing repos.
    "$CMDR_BIN" repos ensure --check
}

configs_prune() {
    # --apply on purpose: the removals files are a committed list of paths
    # that must not exist, so every machine has to act on them (see the
    # gitpullall comments and docs/deploy_configs.md).
    (cd "$CMDR_REPO_DIR" && uv run python src/deploy_configs.py prune --apply)
}

configs_prune_check() {
    # Bare prune is the dry run.
    (cd "$CMDR_REPO_DIR" && uv run python src/deploy_configs.py prune)
}
