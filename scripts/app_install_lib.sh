#!/bin/bash
# Shared helpers for the per-platform app installers.
#
# A caller defines two functions and then calls install_from_list:
#
#   list_installed          prints every already-installed package name, one per line
#   install_apps            installs the package names passed as arguments
#
#   source "$SCRIPT_DIR/app_install_lib.sh"
#   install_from_list "apt" "$APP_LIST" apt
#
# The optional third argument is the package manager, as src/app_lists.py names
# it; with it, the names this machine's contexts add for that manager (each
# member context's <context>_app_lists.yaml) join the list. A lookup that fails
# installs nothing rather than a list that only looks complete.
#
# The list is shown as already-installed vs pending, then a single prompt covers
# every pending app at once: install them all, not now, or ignore some or all of
# them on this machine. An ignored app is written to ~/.dotfiles_ignored_apps
# (src/app_lists.py owns that file) and never offered here again; every run
# that leaves one out names the file at its end, since deleting the line is
# how to be offered it again. Ignoring needs the manager argument, so the
# installers without one (Termux, MSYS2) keep the plain skip.
#
# Environment:
#   ASSUME_YES=1   install everything pending without prompting (used by bootstrap)
#   DRY_RUN=1      print what would be installed and change nothing

read_app_list() {
    # Strips CRs, blank lines, "#" comment lines and trailing "# ..." comments, so an
    # app can be commented out for one run and the file reverted afterwards.
    tr -d '\r' < "$1" | awk '{sub(/#.*/, ""); gsub(/^[ \t]+|[ \t]+$/, ""); if (length) print}'
}

# src/app_lists.py with the given arguments: context app lists and the ignore file.
app_lists_py() {
    local dotfiles
    dotfiles="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    if ! command -v uv >/dev/null 2>&1; then
        echo "uv not found, so this machine's context app lists cannot be read" >&2
        return 1
    fi
    uv run --project "$dotfiles" python "$dotfiles/src/app_lists.py" "$@"
}

# The apps left out because this machine ignores them, and where to undo that.
ignored_note() {
    [ "$#" -gt 0 ] || return 0
    echo
    echo "Not offered, ignored on this machine by $(app_lists_py --ignore-path) (delete a line there to be offered it again):"
    printf '  %s\n' "$@"
}

install_from_list() {
    local label="$1" list_file="$2" manager="$3"

    if [ ! -f "$list_file" ]; then
        echo "App list not found: $list_file" >&2
        return 1
    fi

    # No mapfile here: macOS still ships bash 3.2 and install_mac_apps.sh runs on it.
    local -a apps installed pending
    apps=()
    installed=()
    pending=()
    local line
    while IFS= read -r line; do
        apps+=("$line")
    done < <(read_app_list "$list_file")

    if [ -n "$manager" ]; then
        local extra
        if ! extra="$(app_lists_py --overlay "$manager")"; then
            echo "Could not read this machine's context app lists for $manager; installing nothing." >&2
            return 1
        fi
        while IFS= read -r line; do
            [ -n "$line" ] || continue
            if [ "${#apps[@]}" -eq 0 ] || ! printf '%s\n' "${apps[@]}" | grep -qixF "$line"; then
                apps+=("$line")
            fi
        done <<< "$extra"
    fi

    if [ "${#apps[@]}" -eq 0 ]; then
        echo "No apps listed in $list_file — nothing to do."
        return 0
    fi

    local already
    already="$(list_installed | tr -d '\r' | sort -u)"

    local app
    for app in "${apps[@]}"; do
        if printf '%s\n' "$already" | grep -qxF "$app"; then
            installed+=("$app")
        else
            pending+=("$app")
        fi
    done

    echo
    echo "########## $label: ${#apps[@]} apps in $(basename "$list_file")${manager:+ plus the context app lists} ##########"

    if [ "${#installed[@]}" -gt 0 ]; then
        echo
        echo "Already installed (${#installed[@]}):"
        printf '  %s\n' "${installed[@]}"
    fi

    local -a ignored_here=()
    if [ -n "$manager" ] && [ "${#pending[@]}" -gt 0 ]; then
        local skipped
        if ! skipped="$(printf '%s\n' "${pending[@]}" | app_lists_py --ignored "$manager")"; then
            echo "Could not read this machine's ignore file; installing nothing." >&2
            return 1
        fi
        local -a offered=()
        for app in "${pending[@]}"; do
            if printf '%s\n' "$skipped" | grep -qxF "$app"; then
                ignored_here+=("$app")
            else
                offered+=("$app")
            fi
        done
        pending=()
        [ "${#offered[@]}" -eq 0 ] || pending=("${offered[@]}")
    fi

    if [ "${#pending[@]}" -eq 0 ]; then
        echo
        echo "Everything on the list is already installed${ignored_here[0]:+ or ignored here}."
        [ "${#ignored_here[@]}" -eq 0 ] || ignored_note "${ignored_here[@]}"
        return 0
    fi

    echo
    echo "Not installed (${#pending[@]}):"
    local index=1
    for app in "${pending[@]}"; do
        printf '  %3d) %s\n' "$index" "$app"
        index=$((index + 1))
    done

    local -a chosen=("${pending[@]}")
    local -a to_ignore=()

    if [ -z "$ASSUME_YES" ]; then
        echo
        if [ -n "$manager" ]; then
            read -r -p "Install all ${#pending[@]}? [Y]es / [n]ot now / [i]gnore all here / numbers to ignore here (e.g. 3 7): " answer
        else
            read -r -p "Install all ${#pending[@]}? [Y]es / [n]o / numbers to skip (e.g. 3 7): " answer
        fi

        case "$answer" in
            [Nn]*)
                echo "Skipping $label for now; it is offered again next time."
                [ "${#ignored_here[@]}" -eq 0 ] || ignored_note "${ignored_here[@]}"
                return 0
                ;;
            ""|[Yy]*)
                ;;
            [Ii]*)
                if [ -n "$manager" ]; then
                    to_ignore=("${pending[@]}")
                    chosen=()
                fi
                ;;
            *)
                chosen=()
                local skip=" $answer "
                index=1
                for app in "${pending[@]}"; do
                    if [[ "$skip" != *" $index "* ]]; then
                        chosen+=("$app")
                    elif [ -n "$manager" ]; then
                        to_ignore+=("$app")
                    fi
                    index=$((index + 1))
                done
                ;;
        esac
    fi

    if [ "${#to_ignore[@]}" -gt 0 ]; then
        if [ -n "$DRY_RUN" ]; then
            echo "DRY_RUN set — would ignore on this machine: ${to_ignore[*]}"
        elif app_lists_py --ignore "$manager" "${to_ignore[@]}" >/dev/null; then
            ignored_here+=("${to_ignore[@]}")
        else
            echo "Could not write this machine's ignore file; ${to_ignore[*]} will be offered again." >&2
        fi
    fi

    if [ "${#chosen[@]}" -eq 0 ]; then
        echo "Nothing selected for $label."
        [ "${#ignored_here[@]}" -eq 0 ] || ignored_note "${ignored_here[@]}"
        return 0
    fi

    echo
    echo "Installing ${#chosen[@]} apps: ${chosen[*]}"

    if [ -n "$DRY_RUN" ]; then
        echo "DRY_RUN set — not installing."
        [ "${#ignored_here[@]}" -eq 0 ] || ignored_note "${ignored_here[@]}"
        return 0
    fi

    install_apps "${chosen[@]}"
    local status=$?
    [ "${#ignored_here[@]}" -eq 0 ] || ignored_note "${ignored_here[@]}"
    return "$status"
}
