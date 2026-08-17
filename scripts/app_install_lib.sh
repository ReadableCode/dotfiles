#!/bin/bash
# Shared helpers for the per-platform app installers.
#
# A caller defines two functions and then calls install_from_list:
#
#   list_installed          prints every already-installed package name, one per line
#   install_apps            installs the package names passed as arguments
#
#   source "$SCRIPT_DIR/app_install_lib.sh"
#   install_from_list "apt" "$APP_LIST"
#
# The list is shown as already-installed vs pending, then a single prompt covers
# every pending app at once: accept them all, decline, or type the numbers to skip.
#
# Environment:
#   ASSUME_YES=1   install everything pending without prompting (used by bootstrap)
#   DRY_RUN=1      print what would be installed and change nothing

read_app_list() {
    # Strips CRs, blank lines, "#" comment lines and trailing "# ..." comments, so an
    # app can be commented out for one run and the file reverted afterwards.
    tr -d '\r' < "$1" | awk '{sub(/#.*/, ""); gsub(/^[ \t]+|[ \t]+$/, ""); if (length) print}'
}

install_from_list() {
    local label="$1" list_file="$2"

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
    echo "########## $label: ${#apps[@]} apps in $(basename "$list_file") ##########"

    if [ "${#installed[@]}" -gt 0 ]; then
        echo
        echo "Already installed (${#installed[@]}):"
        printf '  %s\n' "${installed[@]}"
    fi

    if [ "${#pending[@]}" -eq 0 ]; then
        echo
        echo "Everything on the list is already installed."
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

    if [ -z "$ASSUME_YES" ]; then
        echo
        read -r -p "Install all ${#pending[@]}? [Y]es / [n]o / numbers to skip (e.g. 3 7): " answer

        case "$answer" in
            [Nn]*)
                echo "Skipping $label."
                return 0
                ;;
            ""|[Yy]*)
                ;;
            *)
                chosen=()
                local skip=" $answer "
                index=1
                for app in "${pending[@]}"; do
                    if [[ "$skip" != *" $index "* ]]; then
                        chosen+=("$app")
                    fi
                    index=$((index + 1))
                done
                ;;
        esac
    fi

    if [ "${#chosen[@]}" -eq 0 ]; then
        echo "Nothing selected for $label."
        return 0
    fi

    echo
    echo "Installing ${#chosen[@]} apps: ${chosen[*]}"

    if [ -n "$DRY_RUN" ]; then
        echo "DRY_RUN set — not installing."
        return 0
    fi

    install_apps "${chosen[@]}"
}
