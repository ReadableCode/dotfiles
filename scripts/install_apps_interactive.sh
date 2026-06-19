#!/usr/bin/env bash
#
# install_apps_interactive.sh
#
# Interactively pick apps from the app_lists/ folder (with checkboxes) and
# install the selected ones.
#
# Supported platforms / package managers:
#   - macOS               -> Homebrew (app_lists/Brewfile)
#   - Debian/Ubuntu/...    -> apt      (app_lists/linux_apps.txt)
#   - Arch/Manjaro/...     -> pacman   (app_lists/linux_apps.txt)
#
# The checkbox UI uses `whiptail` or `dialog` when available, and falls back
# to a pure-bash toggle menu otherwise (so it works on a bare system too).
#
# Usage:
#   scripts/install_apps_interactive.sh [app_list_file]
#
# If an app list file is passed it overrides the auto-detected default.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_LISTS_DIR="$SCRIPT_DIR/../app_lists"

# --- Package-manager detection -------------------------------------------

PM=""              # one of: brew, apt, pacman
DEFAULT_LIST=""    # default app list for the detected platform

detect_pm() {
    case "$(uname -s)" in
        Darwin)
            PM="brew"
            DEFAULT_LIST="$APP_LISTS_DIR/Brewfile"
            ;;
        Linux)
            if command -v apt-get >/dev/null 2>&1; then
                PM="apt"
            elif command -v pacman >/dev/null 2>&1; then
                PM="pacman"
            else
                echo "Error: no supported package manager found (need apt or pacman)." >&2
                exit 1
            fi
            DEFAULT_LIST="$APP_LISTS_DIR/linux_apps.txt"
            ;;
        *)
            echo "Error: unsupported operating system: $(uname -s)" >&2
            exit 1
            ;;
    esac
}

# --- App list parsing -----------------------------------------------------
#
# Populates two parallel arrays:
#   NAMES[]  - the package name to display / install
#   KINDS[]  - "cask" for Homebrew casks, "" otherwise
#
# The Brewfile uses lines like:  brew "bat"   /   cask "firefox"
# The linux_apps.txt files are one bare package name per line.

NAMES=()
KINDS=()

parse_list() {
    local list_file="$1"
    local line name

    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%$'\r'}"                 # strip CR from CRLF files
        line="${line#"${line%%[![:space:]]*}"}"  # ltrim
        line="${line%"${line##*[![:space:]]}"}"   # rtrim
        [ -z "$line" ] && continue
        case "$line" in
            \#*) continue ;;                 # skip comments
        esac

        if [ "$PM" = "brew" ]; then
            # Match: brew "name"  or  cask "name"  (also handles unquoted)
            case "$line" in
                brew\ *)
                    name="${line#brew }"
                    name="${name//\"/}"
                    name="${name// /}"
                    NAMES+=("$name"); KINDS+=("")
                    ;;
                cask\ *)
                    name="${line#cask }"
                    name="${name//\"/}"
                    name="${name// /}"
                    NAMES+=("$name"); KINDS+=("cask")
                    ;;
                *) ;;  # ignore tap/mas/other directives
            esac
        else
            NAMES+=("$line"); KINDS+=("")
        fi
    done < "$list_file"
}

# --- Selection UIs --------------------------------------------------------
#
# Each UI sets the SELECTED[] array of indices (into NAMES) chosen by the user.

SELECTED=()

select_with_whiptail() {
    local ui="$1"   # whiptail or dialog
    local args=() i tag label result status

    for i in "${!NAMES[@]}"; do
        label="${NAMES[$i]}"
        [ -n "${KINDS[$i]}" ] && label="$label (${KINDS[$i]})"
        # tag=index, description=name, initial state OFF
        args+=("$i" "$label" "OFF")
    done

    # Capture the space-separated list of selected tags from stderr.
    set +e
    result="$("$ui" --separate-output \
        --checklist "Select apps to install (space to toggle, enter to confirm):" \
        25 70 16 "${args[@]}" 3>&1 1>&2 2>&3)"
    status=$?
    set -e

    if [ "$status" -ne 0 ]; then
        echo "Selection cancelled." >&2
        exit 0
    fi

    for tag in $result; do
        tag="${tag//\"/}"
        SELECTED+=("$tag")
    done
}

select_with_bash() {
    local checked=() i input idx
    for i in "${!NAMES[@]}"; do checked[$i]=0; done

    while true; do
        printf '\n==== Select apps to install (%s) ====\n\n' "$PM"
        for i in "${!NAMES[@]}"; do
            local mark=" "
            [ "${checked[$i]}" -eq 1 ] && mark="x"
            local label="${NAMES[$i]}"
            [ -n "${KINDS[$i]}" ] && label="$label (${KINDS[$i]})"
            printf '  [%s] %3d) %s\n' "$mark" "$i" "$label"
        done
        printf '\nToggle by number(s), "a" all, "n" none, "d" done, "q" quit: '
        read -r input || input="q"

        case "$input" in
            q|Q) echo "Selection cancelled." >&2; exit 0 ;;
            d|D) break ;;
            a|A) for i in "${!NAMES[@]}"; do checked[$i]=1; done ;;
            n|N) for i in "${!NAMES[@]}"; do checked[$i]=0; done ;;
            *)
                for idx in $input; do
                    case "$idx" in
                        ''|*[!0-9]*) continue ;;
                    esac
                    if [ -n "${NAMES[$idx]+x}" ]; then
                        if [ "${checked[$idx]}" -eq 1 ]; then
                            checked[$idx]=0
                        else
                            checked[$idx]=1
                        fi
                    fi
                done
                ;;
        esac
    done

    for i in "${!NAMES[@]}"; do
        if [ "${checked[$i]}" -eq 1 ]; then
            SELECTED+=("$i")
        fi
    done
}

choose_apps() {
    if command -v whiptail >/dev/null 2>&1; then
        select_with_whiptail whiptail
    elif command -v dialog >/dev/null 2>&1; then
        select_with_whiptail dialog
    else
        select_with_bash
    fi
}

# --- Installation ---------------------------------------------------------

install_selected() {
    local i name kind
    local brew_formulae=() brew_casks=() linux_pkgs=()

    for i in "${SELECTED[@]}"; do
        name="${NAMES[$i]}"
        kind="${KINDS[$i]}"
        case "$PM" in
            brew)
                if [ "$kind" = "cask" ]; then
                    brew_casks+=("$name")
                else
                    brew_formulae+=("$name")
                fi
                ;;
            apt|pacman)
                linux_pkgs+=("$name")
                ;;
        esac
    done

    case "$PM" in
        brew)
            if ! command -v brew >/dev/null 2>&1; then
                echo "Error: Homebrew (brew) is not installed." >&2
                exit 1
            fi
            if [ "${#brew_formulae[@]}" -gt 0 ]; then
                echo "Installing formulae: ${brew_formulae[*]}"
                brew install "${brew_formulae[@]}"
            fi
            if [ "${#brew_casks[@]}" -gt 0 ]; then
                echo "Installing casks: ${brew_casks[*]}"
                brew install --cask "${brew_casks[@]}"
            fi
            ;;
        apt)
            echo "Installing with apt: ${linux_pkgs[*]}"
            sudo apt-get update
            sudo apt-get install -y "${linux_pkgs[@]}"
            ;;
        pacman)
            echo "Installing with pacman: ${linux_pkgs[*]}"
            sudo pacman -Sy --needed "${linux_pkgs[@]}"
            ;;
    esac
}

# --- Main -----------------------------------------------------------------

main() {
    detect_pm

    local list_file="${1:-$DEFAULT_LIST}"
    if [ ! -f "$list_file" ]; then
        echo "Error: app list not found: $list_file" >&2
        exit 1
    fi

    echo "Platform package manager: $PM"
    echo "Using app list: $list_file"

    parse_list "$list_file"
    if [ "${#NAMES[@]}" -eq 0 ]; then
        echo "No apps found in $list_file." >&2
        exit 1
    fi

    choose_apps
    if [ "${#SELECTED[@]}" -eq 0 ]; then
        echo "No apps selected. Nothing to install."
        exit 0
    fi

    install_selected
    echo "Done."
}

main "$@"
