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
# The list is shown as already-installed vs pending, then one question asks
# whether to go through the pending apps at all. Saying yes asks about each
# app in turn - install, not now, or ignore on this machine - and only after
# the last answer does anything install, all of it in one go. An ignored app is
# written to ~/.dotfiles_ignored_apps (src/app_lists.py owns that file) and
# never offered here again; every run that leaves one out names the file at its
# end, since deleting the line is how to be offered it again. Ignoring needs
# the manager argument, so the installers without one (Termux, MSYS2) offer
# only yes or no.
#
# OFFER_IGNORED=1 is the other way back, and what installmissing sets: the
# ignored apps are asked about with the rest, marked, and each one answered
# yes is taken out of the ignore file.
#
# Environment:
#   OFFER_IGNORED=1  ask about the apps this machine ignores too; a yes un-ignores the app
#   ASSUME_YES=1   install everything pending without prompting (used by bootstrap)
#   DRY_RUN=1      print what would be installed and change nothing
#   APP_PHASE      unset: ask, then install. ask: ask, then append the chosen
#                  apps to $APP_PLAN as "label<TAB>app" lines instead of
#                  installing. install: install what $APP_PLAN holds for this
#                  label, asking nothing. src/refresh_machine.py runs every
#                  installer once per phase, so myupdater asks every question
#                  for every package manager before the first install starts.
#   APP_PLAN       the file the two phases share

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
    echo "Not offered, ignored on this machine by $(app_lists_py --ignore-path) (delete a line there, or run installmissing, to be offered it again):"
    printf '  %s\n' "$@"
}

# Ask about each pending app, filling chosen and to_ignore. Enter or EOF means
# not now, and q leaves the rest for next time. An app in offered_ignored is
# one this machine ignores, asked about because OFFER_IGNORED is set.
ask_each_app() {
    local manager="$1" app answer
    shift
    for app in "$@"; do
        if [ "${#offered_ignored[@]}" -gt 0 ] && printf '%s\n' "${offered_ignored[@]}" | grep -qxF "$app"; then
            read -r -p "  $app (ignored here): [y]es, and stop ignoring / [N]ot now / [q]uit asking: " answer || answer=q
        elif [ -n "$manager" ]; then
            read -r -p "  $app: [y]es / [N]ot now / [i]gnore here / [q]uit asking: " answer || answer=q
        else
            read -r -p "  $app: [y]es / [N]o / [q]uit asking: " answer || answer=q
        fi
        case "$answer" in
            [Yy]*) chosen+=("$app") ;;
            [Ii]*) [ -n "$manager" ] && to_ignore+=("$app") ;;
            [Qq]*) echo "  The rest are offered again next time."; return 0 ;;
        esac
    done
}

# The install phase: install what the ask phase queued for this label.
install_planned() {
    local label="$1" queued app
    local -a planned=()
    if [ -f "$APP_PLAN" ]; then
        while IFS=$'\t' read -r queued app; do
            [ "$queued" = "$label" ] && [ -n "$app" ] && planned+=("$app")
        done < "$APP_PLAN"
    fi
    if [ "${#planned[@]}" -eq 0 ]; then
        echo "Nothing chosen for $label."
        return 0
    fi
    echo "Installing ${#planned[@]} $label apps: ${planned[*]}"
    if [ -n "$DRY_RUN" ]; then
        echo "DRY_RUN set — not installing."
        return 0
    fi
    install_apps "${planned[@]}"
}

install_from_list() {
    local label="$1" list_file="$2" manager="$3"

    if [ "$APP_PHASE" = "install" ]; then
        install_planned "$label"
        return
    fi

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
                # with OFFER_IGNORED these are asked about too, and a yes un-ignores them
                [ -z "$OFFER_IGNORED" ] || offered+=("$app")
            else
                offered+=("$app")
            fi
        done
        pending=()
        [ "${#offered[@]}" -eq 0 ] || pending=("${offered[@]}")
    fi
    local -a offered_ignored=()
    if [ -n "$OFFER_IGNORED" ] && [ "${#ignored_here[@]}" -gt 0 ]; then
        offered_ignored=("${ignored_here[@]}")
    fi

    if [ "${#pending[@]}" -eq 0 ]; then
        echo
        echo "Everything on the list is already installed${ignored_here[0]:+ or ignored here}."
        [ "${#ignored_here[@]}" -eq 0 ] || ignored_note "${ignored_here[@]}"
        return 0
    fi

    echo
    echo "Not installed (${#pending[@]}):"
    local mark
    for app in "${pending[@]}"; do
        mark=""
        if [ "${#offered_ignored[@]}" -gt 0 ] && printf '%s\n' "${offered_ignored[@]}" | grep -qxF "$app"; then
            mark="  (ignored here until you say yes)"
        fi
        printf '  %s%s\n' "$app" "$mark"
    done

    local -a chosen=("${pending[@]}")
    local -a to_ignore=()

    if [ -z "$ASSUME_YES" ]; then
        echo
        read -r -p "Go through the ${#pending[@]} $label apps not installed? [y/N] " answer || answer=""
        case "$answer" in
            [Yy]*)
                chosen=()
                ask_each_app "$manager" "${pending[@]}"
                ;;
            *)
                echo "Skipping $label for now; it is offered again next time."
                [ "${#ignored_here[@]}" -eq 0 ] || ignored_note "${ignored_here[@]}"
                return 0
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

    local -a wanted=()
    if [ "${#offered_ignored[@]}" -gt 0 ] && [ "${#chosen[@]}" -gt 0 ]; then
        for app in "${chosen[@]}"; do
            if printf '%s\n' "${offered_ignored[@]}" | grep -qxF "$app"; then
                wanted+=("$app")
            fi
        done
    fi
    if [ "${#wanted[@]}" -gt 0 ]; then
        if [ -n "$DRY_RUN" ]; then
            echo "DRY_RUN set — would stop ignoring on this machine: ${wanted[*]}"
        elif app_lists_py --unignore "$manager" "${wanted[@]}" >/dev/null; then
            echo "No longer ignored on this machine: ${wanted[*]}"
            local -a still=()
            for app in "${ignored_here[@]}"; do
                printf '%s\n' "${wanted[@]}" | grep -qxF "$app" || still+=("$app")
            done
            ignored_here=()
            [ "${#still[@]}" -eq 0 ] || ignored_here=("${still[@]}")
        else
            echo "Could not write this machine's ignore file; ${wanted[*]} stay ignored." >&2
        fi
    fi

    if [ "${#chosen[@]}" -eq 0 ]; then
        echo "Nothing selected for $label."
        [ "${#ignored_here[@]}" -eq 0 ] || ignored_note "${ignored_here[@]}"
        return 0
    fi

    if [ "$APP_PHASE" = "ask" ]; then
        for app in "${chosen[@]}"; do
            printf '%s\t%s\n' "$label" "$app"
        done >> "$APP_PLAN"
        echo "Queued ${#chosen[@]} $label apps to install after the last question: ${chosen[*]}"
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
