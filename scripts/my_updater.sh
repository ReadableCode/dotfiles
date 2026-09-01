#!/bin/bash

# OS package updates for macOS/Linux — the `updatepackages` step, nothing more.
# Repo pulls and config deploys live in the shell functions (.shared_aliases):
# `myupdater` runs pullrepos → clonerepos → updatepackages → deployconfigs →
# prune, deploying AFTER the package updates in case an upgrade clobbers a
# linked config.
#
# On Linux, on top of the package upgrade, three things are re-checked EVERY run
# and repaired in place after a [y/N] — each one is a state a release upgrade or
# a vendor installer silently breaks, and each one used to be a manual step in
# the docs that nobody remembers to run:
#   check_apt_sources()      third-party apt sources the upgrader switched off
#   run_mapped_checks()      whatever check scripts THIS host's inventory entry
#                            maps to it (the "updater" block in a sibling
#                            credentials repo's <context>_hosts.json) — see the
#                            Host-mapped checks section below
#   check_release_upgrade()  a DISTRO RELEASE upgrade (24.04 → 26.04), capped
#                            PER HOST by the same updater block — that repo's
#                            docs say why the cap exists and how to raise it
# All three are no-ops once healthy, so the normal run prints where it stands
# and changes nothing. macOS and Windows are untouched by all of it — Windows
# lives in application_configs/powershell.
#
# NO PER-PACKAGE OR PER-CONTEXT SPECIAL CASES HERE. Individual packages are
# installed by the app_lists/ + scripts/install_*.sh path and upgraded by the
# bulk apt/dnf/brew commands below, whatever they are. If a package needs a
# third-party apt source first (VS Code, Chrome) that is one-time machine setup
# and belongs in docs/setup_linux_workstation.md, not here. A check that only
# one context's machines need (a work VPN client, say) lives in a repo that
# context owns and is wired up per host through the inventory — a vendor
# health check lived inline here until 2026-08-31 and ran (as a no-op) on every
# personal machine too. A fastfetch install path lived here until the same day
# and was pure duplication: it was already in app_lists/linux_apps.txt the whole
# time, and the "missing package" it worked around was just 24.04 predating
# fastfetch's arrival in the Ubuntu archive (24.10). Don't re-add their like.

echo "#################   Updating Packages   #####################"

# Function for updating & upgrading macOS with Brew and system updates
update_macos() {
    echo "Checking for macOS System Updates..."
    sudo softwareupdate -i -a
    echo "Updating Brew..."
    brew update
    echo "Upgrading Brew packages..."
    brew upgrade
    echo "Upgrading Brew casks..."
    brew upgrade --cask
    brew upgrade --cask --greedy
    echo "Cleaning up Brew..."
    brew cleanup
}

# Function for updating & upgrading a Debian/Ubuntu system with apt
update_apt() {
    echo "Updating apt repositories..."
    sudo apt update
    echo "Upgrading packages..."
    sudo apt -y upgrade
    echo "Running distribution upgrade..."
    sudo apt -y dist-upgrade
    echo "Removing unused packages..."
    sudo apt -y autoremove
    echo "Running full upgrade..."
    sudo apt -y full-upgrade
}

# Function for updating & upgrading a Fedora/RHEL system with dnf
update_dnf() {
    echo "Refreshing metadata and upgrading packages..."
    sudo dnf -y upgrade --refresh
    echo "Removing unused packages..."
    sudo dnf -y autoremove
}

##############################   Third-party apt sources   ##############################

# A release upgrade sets Enabled: no on EVERY third-party source in
# sources.list.d and rewrites the old .list files as deb822 .sources. Nothing
# re-enables them, so the app just stops updating -- silently, with apt exiting
# 0 the whole time. That is how `code` sat on 1.71.0 from Sept 2022 through the
# 21.10 -> 24.04 upgrade until 2026-08-31. Repairing this by hand is exactly the
# failure mode myupdater exists to prevent, so it happens here, every run.
#
# Deliberately generic: no package is named anywhere below. A well-behaved
# third-party .deb registers its own apt source and key from its postinst, so
# the repair is to re-run the OWNING package's own hook and let the vendor write
# whatever it currently considers correct -- current suite, current key, current
# format. We find that owner by matching the dead source's URI host against the
# postinst scripts of installed packages.

# Hostname out of a source file's URI, whatever the format. An install-media
# URI is `cdrom:[Xubuntu 21.10 _Impish Indri_ ...]/` — it has no host and the
# label contains spaces, so name it rather than parsing it.
apt_source_host() {
    if grep -qE '(URIs:[[:space:]]*|deb[[:space:]]+)cdrom:' "$1" 2>/dev/null; then
        printf 'cdrom (install media)'
        return 0
    fi
    grep -ohE '(https?|ftp):[^ ]*' "$1" 2>/dev/null \
        | head -n1 | sed -E 's|^[a-z]+:(//)?||; s|/.*||'
}

# The suite/codename a source is pinned to: `Suites: x` (deb822) or the field
# after the URI (one-line). Empty for flat repos ending in `/`.
apt_source_suite() {
    local suite
    suite="$(sed -n 's/^[[:space:]]*Suites:[[:space:]]*\([^[:space:]]*\).*/\1/p' "$1" 2>/dev/null | head -n1)"
    [ -z "$suite" ] && suite="$(awk '/^[[:space:]]*#?[[:space:]]*deb/ {for(i=1;i<=NF;i++) if($i ~ /:\/\//) {print $(i+1); exit}}' "$1" 2>/dev/null)"
    printf '%s' "$suite"
}

# The installed package whose postinst registers this URI host, or nothing.
# dpkg leaves info files behind after removal, so the Status check matters --
# only an installed package can actually re-register anything.
apt_source_owner() {
    local host="$1" info pkg
    [ -n "$host" ] || return 1
    for info in /var/lib/dpkg/info/*.postinst; do
        [ -f "$info" ] || continue
        grep -q "$host" "$info" 2>/dev/null || continue
        pkg="$(basename "$info" .postinst)"
        pkg="${pkg%%:*}"   # strip the :arch that multiarch info files carry
        dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null \
            | grep -q 'install ok installed' || continue
        printf '%s' "$pkg"
        return 0
    done
    return 1
}

# True when a source is switched off: deb822 Enabled: no, or a one-line file
# whose every deb line is commented out.
apt_source_disabled() {
    grep -qi '^[[:space:]]*Enabled:[[:space:]]*no' "$1" 2>/dev/null && return 0
    grep -qE '^[[:space:]]*deb' "$1" 2>/dev/null && return 1
    grep -qE '^[[:space:]]*#[[:space:]]*deb' "$1" 2>/dev/null
}

# True when a suite names an Ubuntu release that is already dead, so the source
# would 404 even if switched back on. Local data, so it works offline.
apt_suite_is_eol() {
    local days
    [ -n "$1" ] || return 1
    command -v ubuntu-distro-info &> /dev/null || return 1
    days="$(ubuntu-distro-info --series="$1" --days=eol 2>/dev/null)"
    case "$days" in ''|*[!0-9-]*) return 1 ;; esac
    [ "$days" -le 0 ]
}

# Re-run a package's own registration hook. This is what dpkg itself runs on
# configure, and these hooks are written to be idempotent (guarded writes, rm -f
# then ln -s), which is why re-running is safe. It also works with the source
# still disabled and the network down -- an `apt-get install --reinstall` could
# not, because a disabled source means apt has no candidate to reinstall FROM.
# Executed directly, never via `sh <file>`: these hooks do not agree on a shell
# (google-chrome-stable's is #!/bin/sh, code's is #!/usr/bin/env bash and uses
# bashisms), so forcing an interpreter breaks half of them. They ship 0755, so
# the shebang does the right thing on its own.
apt_rerun_owner_hook() {
    local hook="/var/lib/dpkg/info/$1.postinst"
    [ -x "$hook" ] || return 1
    sudo "$hook" configure > /dev/null 2>&1
}

check_apt_sources() {
    local dir=/etc/apt/sources.list.d f base host suite owner repaired=0 cruft
    command -v apt &> /dev/null || return 0
    [ -d "$dir" ] || return 0

    echo ""
    echo "############   Checking Third-Party Apt Sources   ############"

    # Backups the upgrader and dpkg leave behind. Inert — apt never reads them —
    # but they are what makes this directory unreadable, and a stale .save gets
    # mistaken for a live source.
    #
    # Only the REDUNDANT ones are offered for deletion. A backup whose source no
    # longer exists in any live form is the last surviving record of a repo that
    # was dropped entirely, which is worth more than the tidiness: on this
    # machine kubernetes.list.distUpgrade is the only place the pinned v1.29
    # repo URL still exists, and kubectl is frozen because of it. Deleting that
    # would destroy the evidence of why.
    local orphans="" stem
    cruft=""
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        stem="$(basename "$f")"
        stem="${stem%.save}"; stem="${stem%.distUpgrade}"
        stem="${stem%.list}"; stem="${stem%.sources}"
        if [ -f "$dir/$stem.list" ] || [ -f "$dir/$stem.sources" ]; then
            cruft="$cruft $f"
        else
            orphans="$orphans $f"
        fi
    done < <(find "$dir" -maxdepth 1 \( -name '*.save' -o -name '*.distUpgrade' \) 2>/dev/null | sort)

    if [ -n "$orphans" ]; then
        echo ""
        echo "NOTE: these backups are all that is left of sources with no live counterpart."
        echo "      Whatever they configured is no longer being updated on this machine."
        # shellcheck disable=SC2086
        for f in $orphans; do
            echo "  $(basename "$f"): $(grep -hoE '(https?|ftp)://[^ ]+' "$f" 2>/dev/null | head -n1)"
        done
        echo "      Keeping them — re-add the repo if you still want it, then they can go."
    fi

    if [ -n "$cruft" ]; then
        echo ""
        echo "Leftover backup files whose source still exists (apt ignores these):"
        # shellcheck disable=SC2086
        printf '  %s\n' $cruft
        # shellcheck disable=SC2086
        if confirm "Delete these $(printf '%s\n' $cruft | wc -w) redundant backup file(s)?"; then
            # shellcheck disable=SC2086
            sudo rm -f $cruft && echo "Deleted."
        fi
    fi

    for f in "$dir"/*.sources "$dir"/*.list; do
        [ -f "$f" ] || continue
        apt_source_disabled "$f" || continue

        base="$(basename "$f")"
        host="$(apt_source_host "$f")"
        suite="$(apt_source_suite "$f")"
        echo ""
        echo "DISABLED: $base  (host ${host:-unknown}${suite:+, suite $suite})"

        # An install-media source is never worth reviving; it points at the ISO
        # this machine was installed from.
        if grep -qi '^[[:space:]]*URIs:[[:space:]]*cdrom:\|^[[:space:]]*#\?[[:space:]]*deb[[:space:]]*cdrom:' "$f" 2>/dev/null; then
            echo "  This is the install ISO, not a network repo -- nothing to revive."
            confirm "  Delete $base?" && sudo rm -f "$f" && echo "  Deleted."
            continue
        fi

        if owner="$(apt_source_owner "$host")"; then
            echo "  Owned by installed package '$owner', which registers this source itself."
            [ -n "$suite" ] && apt_suite_is_eol "$suite" \
                && echo "  (its pinned suite '$suite' is past EOL; the hook will write the current one)"
            if confirm "  Re-run $owner's own registration hook to restore it?"; then
                if apt_rerun_owner_hook "$owner"; then
                    # The hook writes the vendor's own filename. Leaving the old
                    # disabled file behind would give apt two entries for one
                    # repo and a duplicate-source warning on every update.
                    sudo rm -f "$f"
                    repaired=1
                    echo "  Restored by $owner and removed the stale $base."
                else
                    echo "  $owner's hook failed; leaving $base alone."
                fi
            fi
            continue
        fi

        # No installed package self-registers this, so there is no hook to run
        # and nothing here can repair it. It is already inert, so removing it
        # costs nothing -- and `add-apt-repository` is the way back if wanted.
        echo "  No installed package registers this source, so it cannot be repaired here."
        [ -n "$suite" ] && apt_suite_is_eol "$suite" \
            && echo "  Its suite '$suite' is also past EOL, so it would 404 if switched on."
        confirm "  Delete $base?" && sudo rm -f "$f" && echo "  Deleted."
    done

    [ "$repaired" -eq 1 ] && echo "" \
        && echo "Sources were restored, so the upgrade below will pick up what they carry."
    return 0
}

##############################   Updater policy   ##############################

# Anything host-specific is declared PER HOST in the credentials repo that owns
# the host, never in dotfiles. This repo is cloned onto every machine, so a
# value written here would speak for machines nobody has checked. Each sibling
# <context>_credentials repo already carries that context's host inventory
# (<context>_hosts.json, the same files ssh_aliases.py and deploy_configs.py
# read), so an "updater" block on a host's entry is where its updater
# decisions live: release ceiling, upgrade cadence, mapped check scripts. The
# block sits on the HOST entry only — no group or context defaults — so a
# machine is governed only by an entry that names it, and cloning another
# context's credentials repo changes nothing here.
#
# src/updater_policy.py (stdlib-only, bare python3, like ssh_aliases.py) does
# the lookup. No python3 or a broken inventory means the policy is unknown,
# and unknown means don't move: the release check says so and skips, mapped
# checks run nothing, package updates still happen.
REPO_PARENT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
POLICY_HELPER="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/src/updater_policy.py"

# Short pre-dot hostname, lowercased — only used in messages; the helper does
# its own matching against the inventory names and aliases the same way.
POLICY_HOST="$(hostname 2>/dev/null | cut -d. -f1 | tr '[:upper:]' '[:lower:]')"

policy_available() {
    command -v python3 &> /dev/null && [ -f "$POLICY_HELPER" ]
}

# Value of a dotted key inside THIS host's updater block, e.g.
# `policy_lookup release_ceiling.ubuntu`. Lists come back comma-joined; a
# missing host or key comes back empty. stderr is left alone on purpose: a
# broken inventory complains on the terminal while the captured value stays
# empty, so breakage is loud and the updater still fails safe.
policy_lookup() {
    policy_available || return 0
    python3 "$POLICY_HELPER" --root "$REPO_PARENT" "$1"
}

# Named by every message that asks you to change the policy. Prints the
# inventory files found, or where one would live when there are none — a
# machine whose credentials repo is not cloned has no policy at all, and
# saying so beats naming a path that does not exist.
policy_location() {
    local files=""
    policy_available && files="$(python3 "$POLICY_HELPER" --root "$REPO_PARENT" --where 2>/dev/null)"
    if [ -n "$files" ]; then
        printf '%s' "$files" | tr '\n' ' ' | sed 's/ *$//'
    else
        printf '%s' "$REPO_PARENT/<context>_credentials/<context>_hosts.json"
    fi
}

##############################   Host-mapped checks   ##############################

# Context-specific health checks never live in this script. A host's updater
# block maps it to check scripts by path relative to the repo parent dir, so
# the code lives in whichever repo should share it — a work context's checks
# go in that context's own working repo where teammates get them too, and a
# machine whose inventory entry has no mapping runs nothing and holds none of
# the code. Two keys are consulted:
#   post_update_check     run after the package upgrade, no arguments
#   release_preflight     run before the release-upgrade prompt, passed
#                         --target <version>
# The scripts are standalone by contract: they print their own findings, ask
# their own [y/N] before repairing anything, and must no-op quietly when
# healthy. Exit codes are not acted on here.
run_mapped_checks() {
    local key="$1"; shift
    local paths path
    paths="$(policy_lookup "$key")"
    [ -n "$paths" ] || return 0
    for path in ${paths//,/ }; do
        if [ -f "$REPO_PARENT/$path" ]; then
            bash "$REPO_PARENT/$path" "$@"
        else
            echo ""
            echo "WARNING: this host maps $key to $path, but nothing is at"
            echo "         $REPO_PARENT/$path — clone the repo that carries it. Skipping."
        fi
    done
    return 0
}

##############################   Release upgrades   ##############################

# True when $1 <= $2 as dotted versions. sort -V so 26.04 beats 24.04 and 9
# doesn't beat 10.
version_le() {
    [ "$1" = "$2" ] && return 0
    [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n1)" = "$1" ]
}

# Ask once, default no. Returns non-zero for anything that isn't an explicit
# yes, including a non-terminal stdin — myupdater must never block or upgrade
# unattended.
confirm() {
    local reply=""
    if [ ! -t 0 ]; then
        echo "Not running on a terminal, so not prompting. Re-run myupdater interactively to upgrade."
        return 1
    fi
    printf '%s [y/N] ' "$1"
    read -r reply
    case "$reply" in
      [yY]|[yY][eE][sS]) return 0 ;;
      *) echo "Skipped. myupdater will offer again next run."; return 1 ;;
    esac
}

# The release do-release-upgrade would move this machine to, as major.minor, or
# nothing. It prints "New release '26.04.1 LTS' available." and exits 0 when one
# is offered, exits 1 otherwise. It honors Prompt= in
# /etc/update-manager/release-upgrades, so with Prompt=lts it will not name an
# interim release at all.
ubuntu_offered_release() {
    do-release-upgrade -c 2>&1 \
        | sed -n "s/.*New release '\([0-9]\{1,\}\.[0-9]\{1,\}\).*/\1/p" \
        | head -n1
}

# Release date of an Ubuntu version like 26.04, from distro-info's local CSV
# (fields: version,codename,series,created,release,eol,...). The version column
# carries the " LTS" suffix on LTS rows, hence the second match.
ubuntu_release_date() {
    awk -F, -v v="$1" '$1 == v || $1 == v" LTS" { print $5; exit }' \
        /usr/share/distro-info/ubuntu.csv 2>/dev/null
}

# Installed packages apt cannot re-download, because nothing in any enabled
# source provides them. A release upgrade files these under Obsolete and then
# REMOVES any whose dependencies the new release no longer satisfies, in the
# same batch as ordinary cruft, without singling them out.
#
# That is how the 24.04 -> 26.04 upgrade on 2026-08-31 removed a vendor .deb
# outright here: it hard-depended on a library (no alternative listed) that
# 26.04 dropped, so apt removed it, and being in no repo it could not be
# reinstalled afterwards. kubectl, google-drive-ocamlfuse and realvnc-vnc-server
# were flagged Obsolete in the same run and survived, because their dependencies
# still resolved -- so "Obsolete" alone is not the warning, and there is no
# reliable way to test the target release's dependencies from here. Listing the
# exposed packages BEFORE the upgrade is what is possible: it names them while
# there is still a working machine to fetch installers with.
unsourced_packages() {
    local pkgs
    command -v apt-mark &> /dev/null || return 0
    pkgs="$(apt-mark showmanual 2>/dev/null)"
    [ -n "$pkgs" ] || return 0
    # Testing `Candidate:` here does NOT work, and looked like it did: apt counts
    # /var/lib/dpkg/status as a source at priority 100, so a package no repo
    # carries still reports a candidate -- its own installed version. kubectl
    # reads `Candidate: 1.29.15-1.1` on this machine with no repo behind it.
    # The version table's origin lines are the real answer: a package with any
    # origin other than dpkg's own status file is downloadable, one with none is
    # not. An Installed: of (none) is an already-removed package still holding
    # config files, which has nothing left to lose.
    #
    # Deliberate word splitting: one apt-cache call for the whole list.
    # shellcheck disable=SC2086
    apt-cache policy $pkgs 2>/dev/null | awk '
        function flush() {
            if (pkg != "" && inst != "" && inst != "(none)" && !sourced) print pkg
        }
        /^[^[:space:]]/ { flush(); pkg = $1; sub(/:$/, "", pkg); inst = ""; sourced = 0 }
        /^[[:space:]]+Installed:/ { inst = $2 }
        # Origin lines only: "<priority> <source>", priority all digits.
        /^[[:space:]]+[0-9]+[[:space:]]+[^[:space:]]/ {
            if ($2 != "/var/lib/dpkg/status") sourced = 1
        }
        END { flush() }
    '
}

# Codename for an Ubuntu version like 26.04 -> resolute. Same CSV row as
# ubuntu_release_date, third column; lets the version-shaped values in the
# policy file reach the series-shaped helpers above.
ubuntu_series_for_version() {
    awk -F, -v v="$1" '$1 == v || $1 == v" LTS" { print $3; exit }' \
        /usr/share/distro-info/ubuntu.csv 2>/dev/null
}

# Bare major.minor from anything distro-info hands back. `--release` prints
# "26.04 LTS" for an LTS row, and that suffix breaks every comparison here:
# sort -V orders "26.04" before "26.04 LTS", so a ceiling of 26.04 looked
# LOWER than the 26.04 release it was written for and the capped branch fired
# telling you to set 'ubuntu=26.04 LTS'. Compare and print numbers only.
ubuntu_bare_version() {
    printf '%s' "${1%% *}"
}

# Where this release stands: what the newest stable is, and how long this one
# has left. distro-info ships the dates locally, so this still reports when the
# network or the archive is unreachable.
ubuntu_release_standing() {
    local ver="$1" series newest newest_ver eol_days warn
    command -v ubuntu-distro-info &> /dev/null || return 0

    newest="$(ubuntu-distro-info --stable 2>/dev/null)"
    [ -n "$newest" ] && newest_ver="$(ubuntu-distro-info --series="$newest" -r 2>/dev/null)"
    [ -n "$newest_ver" ] && echo "Newest:   Ubuntu $newest_ver ($newest)"

    series=$( . /etc/os-release && printf '%s' "${VERSION_CODENAME:-}" )
    [ -n "$series" ] || return 0
    eol_days="$(ubuntu-distro-info --series="$series" --days=eol 2>/dev/null)"
    case "$eol_days" in ''|*[!0-9-]*) return 0 ;; esac

    warn="$(policy_lookup eol_warn_days)"
    case "$warn" in ''|*[!0-9]*) warn=180 ;; esac

    if [ "$eol_days" -le 0 ]; then
        echo "EOL:      Ubuntu $ver IS PAST END OF LIFE — no security updates. Upgrade now."
    elif [ "$eol_days" -le "$warn" ]; then
        echo "EOL:      $eol_days days left on $ver — inside the $warn-day window, upgrade soon."
    else
        echo "EOL:      $eol_days days left on $ver"
    fi
}

# Point /etc/update-manager/release-upgrades at the cadence the policy wants,
# creating the key if the file has lost it, and verify it took.
set_release_prompt() {
    local want="$1" file=/etc/update-manager/release-upgrades
    [ -f "$file" ] || return 1
    if grep -qE '^[[:space:]]*Prompt[[:space:]]*=' "$file"; then
        sudo sed -i "s/^[[:space:]]*Prompt[[:space:]]*=.*/Prompt=$want/" "$file" || return 1
    else
        printf 'Prompt=%s\n' "$want" | sudo tee -a "$file" > /dev/null || return 1
    fi
    [ "$(sed -n 's/^[[:space:]]*Prompt[[:space:]]*=[[:space:]]*\([a-z]\{1,\}\).*/\1/p' \
        "$file" 2>/dev/null | head -n1)" = "$want" ]
}

ubuntu_release_upgrade() {
    local ver="$1" ceiling="$2" newest newest_ver target want_prompt have_prompt offered

    ubuntu_release_standing "$ver"

    # The target is worked out from distro-info's LOCAL data, not by asking
    # do-release-upgrade. That command is itself gated by Prompt=: on Prompt=lts
    # it reports nothing about a release sitting right there, which is exactly
    # how this machine got stranded on 24.04 for two years. Deciding locally
    # means there is one plain question to ask — "upgrade or not" — with the
    # Prompt= edit described inside it as a consequence of yes, rather than
    # surfaced as a second question about a config key nobody cares about.
    if ! command -v ubuntu-distro-info &> /dev/null; then
        echo "distro-info is not installed (sudo apt install distro-info), leaving the release alone."
        return 0
    fi
    newest="$(ubuntu-distro-info --stable 2>/dev/null)"
    [ -n "$newest" ] && newest_ver="$(ubuntu_bare_version \
        "$(ubuntu-distro-info --series="$newest" -r 2>/dev/null)")"
    if [ -z "$newest_ver" ]; then
        echo "Could not read the newest release from distro-info, leaving the release alone."
        return 0
    fi

    if version_le "$newest_ver" "$ceiling"; then
        target="$newest_ver"
    else
        target="$ceiling"
        echo ""
        echo "NOTE: Ubuntu $newest_ver is out, but this machine is capped at $ceiling."
        echo "      To go further, raise this host's updater.release_ceiling.ubuntu to"
        echo "      $newest_ver in $(policy_location) — check first what this cap protects"
        echo "      (that repo's docs say what was vetted and how)."
    fi

    if version_le "$target" "$ver"; then
        echo "On $ver, which is as new as this machine is allowed to be. Nothing to do."
        return 0
    fi
    # A ceiling naming a release that never shipped cannot be a target.
    if [ -z "$(ubuntu_release_date "$target")" ]; then
        echo ""
        echo "WARNING: the ceiling names Ubuntu $target, which distro-info has never heard of."
        echo "         Fix this host's updater.release_ceiling.ubuntu in $(policy_location);"
        echo "         not attempting an upgrade."
        return 0
    fi
    # Only reachable when the ceiling is stale, since the newest stable release
    # is never dead. Without this the prompt cheerfully offers a release with no
    # security updates, and the upgrader refuses it later for reasons that read
    # like a bug rather than like a stale line in the policy file.
    if apt_suite_is_eol "$(ubuntu_series_for_version "$target")"; then
        echo ""
        echo "WARNING: the ceiling names Ubuntu $target, which is already past end of life, so"
        echo "         upgrading onto it would land this machine on a release getting no security"
        echo "         updates. Nothing was done. Vet $newest_ver for this host and raise its"
        echo "         updater.release_ceiling.ubuntu in $(policy_location)."
        return 0
    fi
    if ! command -v do-release-upgrade &> /dev/null; then
        echo "do-release-upgrade is missing (sudo apt install ubuntu-release-upgrader-core), skipping."
        return 0
    fi

    want_prompt="$(policy_lookup ubuntu_prompt)"
    have_prompt="$(sed -n 's/^[[:space:]]*Prompt[[:space:]]*=[[:space:]]*\([a-z]\{1,\}\).*/\1/p' \
        /etc/update-manager/release-upgrades 2>/dev/null | head -n1)"
    [ -n "$want_prompt" ] && [ -n "$have_prompt" ] && [ "$have_prompt" = "$want_prompt" ] && have_prompt=""

    echo ""
    echo "Ubuntu $target is out, and this machine is allowed to run it."
    run_mapped_checks release_preflight --target "$target"
    local at_risk
    at_risk="$(unsourced_packages)"
    if [ -n "$at_risk" ]; then
        echo ""
        echo "          These are installed but come from no apt source, so the upgrade will drop"
        echo "          any whose dependencies $target no longer satisfies -- and nothing in this"
        echo "          script can put them back:"
        # shellcheck disable=SC2086
        printf '            %s\n' $at_risk
        echo "          Have their installers downloaded BEFORE you say yes. This is not"
        echo "          hypothetical: 26.04 removed one of these outright on 2026-08-31."
    fi

    echo ""
    echo "Answering yes will:"
    echo "  - upgrade this machine from $ver to $target, which REBOOTS at the end"
    echo "  - ask you about third-party apt sources partway through"
    [ -n "$have_prompt" ] && [ -n "$want_prompt" ] \
        && echo "  - switch this machine to being offered every new release instead of only" \
        && echo "    LTS ones, which is what has been hiding $target from it"
    echo ""
    echo "The upgrade turns off third-party apt sources, and vendor installers it pulls"
    echo "in can reset their own services. Re-running myupdater afterwards repairs the"
    echo "sources and re-runs this host's mapped checks."
    echo ""
    confirm "Upgrade this machine from $ver to $target now?" || return 0

    if [ -n "$have_prompt" ] && [ -n "$want_prompt" ]; then
        if set_release_prompt "$want_prompt"; then
            echo "This machine will now be offered every new release, not just LTS ones."
        else
            echo "Could not change that setting, so the upgrader may still refuse $target."
        fi
    fi

    # Only now ask the upgrader, with the gate out of the way. If it still names
    # nothing, stop rather than run a command that would do nothing.
    offered="$(ubuntu_offered_release)"
    if [ -z "$offered" ]; then
        echo ""
        echo "The upgrader still will not move this machine to $target, so nothing was done."
        echo "Ubuntu gates LTS-to-LTS upgrades until the first point release, so this can"
        echo "just mean $target is not open from $ver yet. myupdater will ask again."
        return 0
    fi

    # Interactive by design: it asks about third-party sources and a reboot.
    sudo do-release-upgrade
    echo ""
    echo "After the reboot, run myupdater again. It puts back the third-party apt"
    echo "sources this upgrade turned off and re-runs this host's mapped checks."
}

# What Bodhi (Fedora's release service) says is maintained right now, as raw
# JSON. Fedora ships no offline release database — no distro-info analog — so
# standing and "has this release actually shipped" need the network. Empty
# means unknown, and unknown means don't move.
fedora_current_releases() {
    command -v curl &> /dev/null && command -v python3 &> /dev/null || return 0
    curl -sf --max-time 10 \
        'https://bodhi.fedoraproject.org/releases/?state=current&rows_per_page=100' 2>/dev/null
}

# Newest maintained Fedora out of that payload, or nothing. Only bare F<n>
# rows count — Bodhi lists EPEL and container releases in the same feed.
fedora_newest_release() {
    [ -n "$1" ] || return 0
    printf '%s' "$1" | python3 -c '
import json, re, sys
versions = [int(m.group(1)) for r in json.load(sys.stdin).get("releases", [])
            if (m := re.fullmatch(r"F(\d+)", r.get("name", "")))]
print(max(versions) if versions else "")
' 2>/dev/null
}

# True when Bodhi lists F<ver> as current — released and still supported. The
# metalink for a branched-but-unreleased Fedora already answers, so repo
# availability alone would cheerfully land a machine on a beta.
fedora_release_is_current() {
    local ver="$1" json="$2"
    [ -n "$json" ] || return 1
    printf '%s' "$json" | python3 -c '
import json, sys
sys.exit(0 if any(r.get("name") == "F" + sys.argv[1]
                  for r in json.load(sys.stdin).get("releases", [])) else 1)
' "$ver" 2>/dev/null
}

# Where this release stands: the newest maintained Fedora, and how long this
# one has left. Quiet when Bodhi was unreachable, and quiet about EOL on a
# machine running AHEAD of stable (a beta is not past end of life).
fedora_release_standing() {
    local ver="$1" json="$2" warn
    [ -n "$json" ] || return 0
    warn="$(policy_lookup eol_warn_days)"
    # A Fedora release only lives ~13 months, so the 180-day default the Ubuntu
    # path uses would nag for half of one; 60 still leaves two months to move.
    case "$warn" in ''|*[!0-9]*) warn=60 ;; esac
    printf '%s' "$json" | python3 -c '
import json, re, sys
from datetime import date
ver, warn = sys.argv[1], int(sys.argv[2])
rels = {int(m.group(1)): r.get("eol") or "" for r in json.load(sys.stdin).get("releases", [])
        if (m := re.fullmatch(r"F(\d+)", r.get("name", "")))}
if rels:
    print(f"Newest:   Fedora {max(rels)}")
if not ver.isdigit() or not rels or int(ver) > max(rels):
    sys.exit()
eol = rels.get(int(ver))
if eol is None:
    print(f"EOL:      Fedora {ver} IS PAST END OF LIFE — no security updates. Upgrade now.")
    sys.exit()
try:
    days = (date.fromisoformat(eol) - date.today()).days
except ValueError:
    sys.exit()
if days <= 0:
    print(f"EOL:      Fedora {ver} IS PAST END OF LIFE — no security updates. Upgrade now.")
elif days <= warn:
    print(f"EOL:      {days} days left on Fedora {ver} (until {eol}) — inside the {warn}-day window, upgrade soon.")
else:
    print(f"EOL:      {days} days left on Fedora {ver} (until {eol})")
' "$ver" "$warn" 2>/dev/null
}

# Installed packages no enabled repo serves, as name.arch. Same exposure as
# unsourced_packages above: the upgrade runs as a distro-sync, which keeps such
# a package only while its dependencies still resolve on the new release, and
# nothing can reinstall it afterwards. dnf keeps the "Extra packages" header
# even under -q, so match the rows (name.arch version repo) instead of
# counting lines.
fedora_unsourced_packages() {
    dnf -q list --extras 2>/dev/null \
        | awk 'NF >= 3 && $1 ~ /\./ { print $1 }'
}

# Enabled repos that do not serve the target release yet. Third-party repos
# routinely lag a new Fedora by weeks, and system-upgrade download aborts on
# the first dead repo. dnf itself resolves each repo's metalink/baseurl at the
# target releasever, so every URL scheme is handled without parsing repo
# files. makecache cannot be the probe — dnf5 exits 0 with every mirror 404ing
# — so ask each repo for its package list and call empty "not serving". Run
# under sudo so the metadata lands in the root cache the download step reads,
# fetched once. Progress goes to stderr; stdout is the captured result.
fedora_lagging_repos() {
    local target="$1" id lagging=""
    for id in $(dnf -q repolist --enabled 2>/dev/null | awk 'NR > 1 { print $1 }'); do
        echo "  $id" >&2
        [ -n "$(sudo dnf -q repoquery --releasever="$target" --repo="$id" --qf '%{name}\n' 2>/dev/null | head -n1)" ] \
            || lagging="$lagging $id"
    done
    printf '%s' "$lagging"
}

fedora_release_upgrade() {
    local ver="$1" ceiling="$2" json newest target at_risk lagging

    json="$(fedora_current_releases)"
    fedora_release_standing "$ver" "$json"

    case "$ver$ceiling" in *[!0-9]*)
        echo "Fedora releases are plain integers; VERSION_ID '$ver' / ceiling '$ceiling' are not. Skipping."
        return 0 ;;
    esac

    # Unlike Ubuntu there is no offline data and no query command to name the
    # next release, so Bodhi names the newest and the ceiling caps it.
    newest="$(fedora_newest_release "$json")"
    if [ -z "$newest" ]; then
        echo "Cannot reach Bodhi to learn the newest released Fedora (a branched beta's"
        echo "repos already answer, so repo availability proves nothing). Leaving the"
        echo "release alone this run."
        return 0
    fi

    if [ "$newest" -le "$ceiling" ]; then
        target="$newest"
    else
        target="$ceiling"
        echo ""
        echo "NOTE: Fedora $newest is out, but this machine is capped at $ceiling."
        echo "      To go further, raise this host's updater.release_ceiling.fedora to"
        echo "      $newest in $(policy_location) — check first what this cap protects"
        echo "      (that repo's docs say what was vetted and how)."
    fi

    if [ "$target" -le "$ver" ]; then
        echo "On Fedora $ver, which is as new as this machine is allowed to be. Nothing to do."
        return 0
    fi
    # Only reachable when the ceiling is stale: below the newest release yet no
    # longer maintained. Same guard as the Ubuntu path's EOL ceiling.
    if [ "$target" -lt "$newest" ] && ! fedora_release_is_current "$target" "$json"; then
        echo ""
        echo "WARNING: the ceiling names Fedora $target, which is already past end of life, so"
        echo "         upgrading onto it would land this machine on a release getting no security"
        echo "         updates. Nothing was done. Vet $newest for this host and raise its"
        echo "         updater.release_ceiling.fedora in $(policy_location)."
        return 0
    fi
    # dnf system-upgrade supports jumping at most two releases at once.
    if [ $((target - ver)) -gt 2 ]; then
        echo ""
        echo "NOTE: dnf can jump at most two releases at once, so this run steps to"
        echo "      $((ver + 2)) first — run myupdater again after that upgrade to continue"
        echo "      toward $target."
        target=$((ver + 2))
    fi

    echo ""
    echo "Fedora $target is out, and this machine is allowed to run it."
    # The repo preflight below downloads the target release's metadata under
    # sudo, which is minutes of work the final [y/N] would only throw away when
    # there is no terminal to say yes on. Bail here instead of at the prompt.
    if [ ! -t 0 ]; then
        echo "A release upgrade needs a terminal to confirm; re-run myupdater interactively."
        return 0
    fi
    run_mapped_checks release_preflight --target "$target"

    at_risk="$(fedora_unsourced_packages)"
    if [ -n "$at_risk" ]; then
        echo ""
        echo "          These are installed but come from no dnf repo, so the upgrade will drop"
        echo "          any whose dependencies Fedora $target no longer satisfies — and nothing"
        echo "          in this script can put them back:"
        # shellcheck disable=SC2086
        printf '            %s\n' $at_risk
        echo "          kmod-* rows are akmods-built kernel modules and rebuild themselves on"
        echo "          the new kernel; for the rest, have installers downloaded BEFORE you"
        echo "          say yes."
    fi

    echo ""
    echo "Checking every enabled repo answers for Fedora $target (third-party repos often"
    echo "lag a new release, and one dead repo aborts the whole download)..."
    lagging="$(fedora_lagging_repos "$target")"
    if [ -n "$lagging" ]; then
        echo ""
        echo "          These enabled repos do not serve Fedora $target yet:"
        # shellcheck disable=SC2086
        printf '            %s\n' $lagging
        echo "          Wait for them, or disable each one first"
        echo "          ('sudo dnf config-manager setopt <repo>.enabled=0'), accepting that"
        echo "          its packages stop updating until it is re-enabled."
    else
        echo "All enabled repos already serve Fedora $target."
    fi

    echo ""
    echo "Answering yes only DOWNLOADS the upgrade. Nothing changes until you run the"
    echo "reboot command printed at the end, which reboots immediately and installs"
    echo "offline. akmod kernel modules (nvidia) rebuild during the first boot, which"
    echo "can take a few minutes at a black screen — let it finish."
    echo ""
    confirm "Download the Fedora $target upgrade now?" || return 0

    # dnf5 ships system-upgrade in dnf5-plugins; the dnf4 plugin package name
    # (dnf-plugin-system-upgrade) no longer exists, so only install when the
    # subcommand is actually missing.
    if ! dnf system-upgrade --help &> /dev/null; then
        sudo dnf install -y dnf5-plugins || {
            echo "Could not install dnf5-plugins, so there is no system-upgrade command. Stopping."
            return 1
        }
    fi
    if ! sudo dnf system-upgrade download --releasever="$target"; then
        echo "Download failed — nothing has changed. Resolve the errors above and re-run."
        return 1
    fi
    echo ""
    echo "Downloaded. Finish with:  sudo dnf system-upgrade reboot"
    echo "(left to you on purpose — that command reboots immediately)"
    echo "After it settles, run myupdater again: it re-checks this host's mapped checks"
    echo "and whether every repo made the jump."
}

# Offer a distro release upgrade, never past the policy ceiling. Idempotent:
# on a machine already at the ceiling it prints where it stands and changes
# nothing, which is the normal outcome on most runs.
check_release_upgrade() {
    echo ""
    echo "############   Checking Distro Release   ############"

    if [ -n "${MYUPDATER_SKIP_RELEASE_UPGRADE:-}" ]; then
        echo "MYUPDATER_SKIP_RELEASE_UPGRADE is set, skipping the release check."
        return 0
    fi
    if [ ! -r /etc/os-release ]; then
        echo "No readable /etc/os-release, cannot identify this distro, skipping."
        return 0
    fi
    if ! policy_available; then
        echo "python3 or src/updater_policy.py is missing, so this host's policy cannot be"
        echo "read. Skipping (an unknown ceiling means don't move)."
        return 0
    fi

    local id ver pretty ceiling
    id=$( . /etc/os-release && printf '%s' "${ID:-}" )
    ver=$( . /etc/os-release && printf '%s' "${VERSION_ID:-}" )
    pretty=$( . /etc/os-release && printf '%s' "${PRETTY_NAME:-$id $ver}" )

    if [ -z "$id" ] || [ -z "$ver" ]; then
        echo "/etc/os-release has no ID/VERSION_ID, skipping."
        return 0
    fi

    ceiling="$(policy_lookup "release_ceiling.$id")"
    if [ -z "$ceiling" ]; then
        echo "$pretty: no ceiling declared for '$id' on this host, leaving the release alone."
        echo "Add updater.release_ceiling.$id to this host's entry ($POLICY_HOST) in"
        echo "$(policy_location) once you have decided the newest release it should run."
        return 0
    fi

    # A ceiling written with a suffix ("26.04 LTS") fails every version compare
    # below, and copying it out of `lsb_release -d` is the obvious way to write
    # it by hand. Take the first field so either spelling works.
    ceiling="${ceiling%% *}"

    echo "Running:  $pretty (VERSION_ID $ver)"
    echo "Ceiling:  $id <= $ceiling"

    if ! version_le "$ver" "$ceiling"; then
        echo ""
        echo "WARNING: this machine is PAST the ceiling ($ver > $ceiling), so it is running a"
        echo "         release nobody signed off on. Either vet this release and raise this"
        echo "         host's updater.release_ceiling.$id in $(policy_location), or rebuild"
        echo "         onto $ceiling."
        return 0
    fi

    case "$id" in
      ubuntu)
        ubuntu_release_upgrade "$ver" "$ceiling"
        ;;
      fedora)
        fedora_release_upgrade "$ver" "$ceiling"
        ;;
      debian)
        if [ "$ver" = "$ceiling" ]; then
            echo "Nothing to do."
        else
            echo "Debian $ceiling is within the ceiling, but a Debian release upgrade means"
            echo "rewriting the codename in /etc/apt/sources.list by hand — not automated here."
        fi
        ;;
      *)
        echo "No release-upgrade path implemented for '$id'; packages are current, release left alone."
        ;;
    esac
}

# Detect the operating system
OS="$(uname)"
case "$OS" in
  "Linux")
    # BEFORE the upgrade, so a source repaired now is one the upgrade below
    # actually reads -- the whole point is that the fix lands in the same run.
    check_apt_sources
    # dnf first: Fedora ships both dnf and (sometimes) an apt shim.
    if command -v dnf &> /dev/null; then
        update_dnf
    elif command -v apt &> /dev/null; then
        update_apt
    else
        echo "Neither dnf nor apt found, skipping package updates."
    fi
    # After the upgrade: if it pulled in a new vendor package, that package may
    # just have reset its own systemd units, so the checks that repair such
    # state run downstream of it.
    run_mapped_checks post_update_check
    # Last: a release upgrade refuses to start on a machine with pending
    # updates anyway.
    check_release_upgrade
    ;;
  "Darwin")
    if command -v brew &> /dev/null; then
        update_macos
    else
        echo "Homebrew not found, attempting macOS system updates without Homebrew."
        sudo softwareupdate -i -a
    fi
    ;;
  *)
    echo "Unsupported operating system: $OS"
    ;;
esac

echo "############ System Info ############"

# Display only. fastfetch is an ordinary entry in app_lists/ (linux_apps.txt,
# linux_apps_wsl.txt, Brewfile, android_termux_apps.txt), so the install scripts
# own installing it like anything else — this script does not.
if command -v fastfetch &> /dev/null; then
    fastfetch
else
    echo "fastfetch is not installed; run the installer for this machine's app list."
fi
