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
#   check_vpn_client_health()  zstunnel left disabled / without a restart policy
#   check_release_upgrade()  a DISTRO RELEASE upgrade (24.04 → 26.04), capped
#                            PER HOST by the release policy in this machine's
#                            credentials repo so it can never outrun the VPN
#                            client — read that file for why the cap exists and
#                            how to raise it
# All three are no-ops once healthy, so the normal run prints where it stands
# and changes nothing. macOS and Windows are untouched by all of it — Windows
# lives in application_configs/powershell.
#
# NO PER-PACKAGE SPECIAL CASES HERE. Individual packages are installed by the
# app_lists/ + scripts/install_*.sh path and upgraded by the bulk apt/dnf/brew
# commands below, whatever they are. If a package needs a third-party apt
# source first (VS Code, Chrome) that is one-time machine setup and belongs in
# docs/setup_linux_workstation.md, not here. Zscaler is the sole exception, and
# only because it is the CEILING on release upgrades, not to install it — see
# vpn_client_standing(). A fastfetch install path lived here until 2026-08-31
# and was pure duplication: it was already in app_lists/linux_apps.txt the whole
# time, and the "missing package" it worked around was just 24.04 predating
# fastfetch's arrival in the Ubuntu archive (24.10). Don't re-add its like.

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
# would 404 even if switched back on. Local data, so it works with the VPN down.
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

##############################   VPN client health   ##############################

# The one package allowed a special case in this script, and only because a
# broken tunnel costs the work the tunnel is for.
#
# The Zscaler installer starts zstunnel for the current session but never
# enables it, and it ships no restart policy -- so the VPN is dead after the
# next boot or the first crash. EVERY client install re-breaks this: the
# 1.5.0.41 -> 3.7.2.31 upgrade on 2026-08-31 reset the unit to disabled and
# deleted the drop-in below. A one-time manual fix therefore does not hold,
# which is why it is re-checked here on every run. Prints nothing once healthy.
check_vpn_client_health() {
    local dropin=/etc/systemd/system/zstunnel.service.d/restart.conf
    [ -d /opt/zscaler ] || return 0
    command -v systemctl &> /dev/null || return 0

    # A removed client leaves the directory standing: dpkg keeps the config
    # files (rc state) and the vendor's installer leaves /opt/zscaler holding
    # only UninstallApplication, so testing the directory alone reports a
    # healthy client that is not on the machine. Checking for the daemon itself
    # is what distinguishes them -- this exact state came out of the 24.04 ->
    # 26.04 upgrade on 2026-08-31, and the old directory test said nothing.
    if [ ! -x /opt/zscaler/bin/zstunnel ]; then
        echo ""
        echo "############   Checking VPN Client   ############"
        echo "The Zscaler client is GONE: /opt/zscaler is still here, its binaries are not."
        case "$(dpkg-query -W -f='${Status}' zscaler-client 2>/dev/null)" in
          *config-files*) echo "dpkg confirms it: removed but not purged, config files kept." ;;
        esac
        echo ""
        echo "A release upgrade removes this client outright when the new release drops a"
        echo "library it depends on. This is the one repair here that CANNOT be automatic:"
        echo "the client is in no apt source, so the installer has to be downloaded from the"
        echo "Zscaler portal by hand. Once you have it:"
        echo "    sudo apt purge zscaler-client"
        echo "    sudo apt install ./zscaler-client_<version>_amd64.deb"
        echo ""
        echo "If that install fails on missing libraries, the release dropped something the"
        echo "client still declares -- see docs/setup_linux_workstation.md, 'After a release"
        echo "upgrade', for what that looks like and where this machine's repair notes live."
        echo "Re-run myupdater afterwards either way: it enables the service the installer"
        echo "leaves off."
        return 0
    fi

    systemctl list-unit-files zstunnel.service &> /dev/null || return 0

    local enabled="" needs_dropin=""
    systemctl is-enabled zstunnel &> /dev/null || enabled="no"
    [ -f "$dropin" ] || needs_dropin="yes"
    [ -z "$enabled" ] && [ -z "$needs_dropin" ] && return 0

    echo ""
    echo "############   Checking VPN Client   ############"
    [ -n "$enabled" ] && echo "zstunnel is NOT enabled at boot -- the VPN will be dead after the next reboot."
    [ -n "$needs_dropin" ] && echo "zstunnel has no restart policy -- a crash leaves the tunnel down until noticed."
    echo "(a Zscaler install resets both; see docs/setup_linux_workstation.md)"

    confirm "Enable zstunnel at boot and install the restart drop-in?" || return 0

    [ -n "$enabled" ] && sudo systemctl enable zstunnel > /dev/null 2>&1
    if [ -n "$needs_dropin" ]; then
        sudo mkdir -p "$(dirname "$dropin")"
        printf '[Service]\nRestart=always\nRestartSec=5s\n' | sudo tee "$dropin" > /dev/null
    fi
    sudo systemctl daemon-reload
    echo "Done: $(systemctl is-enabled zstunnel 2>/dev/null), $(systemctl is-active zstunnel 2>/dev/null)."
}

##############################   Release upgrades   ##############################

# The ceiling is declared PER HOST in the credentials repo that owns the host,
# never in dotfiles. This repo is cloned onto every machine, so a ceiling written
# here would vouch for the VPN client on machines nobody has checked — which is
# exactly the mistake that cost this machine its VPN on 2026-08-31. Each sibling
# <context>_credentials repo already carries that context's host inventory
# (<context>_hosts.json), so <context>_os_release_policy.conf beside it is where
# "the VPN has been checked on this release, on this machine" belongs. Same
# overlay discovery as deploy_configs.py's <context>_manifest.yaml: glob the
# sibling repos, no list of contexts anywhere.
REPO_PARENT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
POLICY_FILES="$(ls "$REPO_PARENT"/*_credentials/*_os_release_policy.conf 2>/dev/null)"

# Short pre-dot hostname, lowercased, as the keys are written: WORKSTATION-1
# becomes workstation-1. Matches how deploy_configs.py resolves host tokens.
POLICY_HOST="$(hostname 2>/dev/null | cut -d. -f1 | tr '[:upper:]' '[:lower:]')"

# Value for a key: host-scoped first ("workstation-1.ubuntu=26.04"), then bare
# ("ubuntu=26.04") as a default for the hosts of whichever repo declares it.
# Host-scoped wins across ALL files before any bare key is considered, so the
# repo that actually names this machine always beats another context's default.
# Tolerates comments, blank lines and surrounding whitespace.
policy_lookup() {
    local key="$1" scope file val
    [ -n "$POLICY_FILES" ] || return 0
    for scope in "${POLICY_HOST:-no-such-host}\." ""; do
        while IFS= read -r file; do
            [ -r "$file" ] || continue
            val="$(sed -n "s/^[[:space:]]*${scope}${key}[[:space:]]*=[[:space:]]*\([^[:space:]#]*\).*/\1/p" \
                "$file" | head -n1)"
            if [ -n "$val" ]; then
                printf '%s' "$val"
                return 0
            fi
        done <<< "$POLICY_FILES"
    done
}

# Named by every message that asks you to change the policy. Prints the files
# found, or where to create one when there are none — a machine whose
# credentials repo is not cloned has no policy at all, and saying so beats
# naming a path that does not exist.
policy_location() {
    if [ -n "$POLICY_FILES" ]; then
        printf '%s' "$POLICY_FILES" | tr '\n' ' ' | sed 's/ *$//'
    else
        printf '%s' "$REPO_PARENT/<context>_credentials/<context>_os_release_policy.conf"
    fi
}

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
# That is how the VPN client vanished here on 2026-08-31: zscaler-client
# 3.7.2.31 hard-depended on libqt5webkit5 (no alternative listed), 26.04 dropped
# that package, so apt removed the client and the machine came back up with no
# VPN and no way to reinstall it offline. kubectl, google-drive-ocamlfuse and
# realvnc-vnc-server were flagged Obsolete in the same run and survived, because
# their dependencies still resolved -- so "Obsolete" alone is not the warning,
# and there is no reliable way to test the target release's dependencies from
# here. Listing the exposed packages BEFORE the upgrade is what is possible:
# it names them while there is still a working machine to fetch installers with.
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
# VPN is down or the archive is unreachable.
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

# The VPN client's age against the release being proposed. Says so when the
# client is older than the release, because that is the one risk in the whole
# upgrade — but does NOT tell you to go install a newer one. Zscaler ships a
# client every few months and the newest one that exists is routinely older
# than the newest Ubuntu, so on a fully up-to-date machine that advice is
# impossible to follow: 3.7.2.31 was installed here 2026-08-31 and still dates
# from 2025-05-29. The date shown is the mtime dpkg preserved from the vendor's
# archive, so it is when Zscaler packaged the binary, not when it was
# installed. Silent on machines with no Zscaler install.
vpn_client_standing() {
    local target="$1" ver packaged target_date
    [ -d /opt/zscaler ] || return 0

    # A removed client leaves /opt/zscaler standing, so reaching this with no
    # daemon means the client is gone rather than merely unreadable -- saying
    # "version unknown" there reads like a parsing hiccup instead of no VPN.
    if [ ! -x /opt/zscaler/bin/zstunnel ]; then
        echo "VPN:      NOT INSTALLED -- /opt/zscaler is a leftover, the client is gone."
        return 0
    fi

    ver="$(sed -n 's/^CLIENT_CONNECTOR_VERSION="\([^"]*\)".*/\1/p' \
        /opt/zscaler/.config/.ZCCVersion 2>/dev/null | head -n1)"
    packaged="$(date -r /opt/zscaler/bin/zstunnel +%Y-%m-%d 2>/dev/null)"
    echo "VPN:      Zscaler Client Connector ${ver:-version unknown}${packaged:+, packaged $packaged}"

    target_date="$(ubuntu_release_date "$target")"
    if [ -n "$packaged" ] && [ -n "$target_date" ] && [[ "$packaged" < "$target_date" ]]; then
        echo ""
        echo "          This client is older than Ubuntu $target (released $target_date), so it"
        echo "          was built before the release it would end up running on. That is normal"
        echo "          and often unavoidable. If Zscaler has a client newer than ${ver:-this one},"
        echo "          install it first; if this is already the newest, go ahead and check the"
        echo "          tunnel once the machine is back up:"
        echo "            systemctl status zstunnel zsaservice && ip addr show zcctun0"
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
        echo "      To go further: confirm the VPN client works on $newest_ver, then set"
        echo "      '$POLICY_HOST.ubuntu=$newest_ver' in $(policy_location)."
    fi

    if version_le "$target" "$ver"; then
        echo "On $ver, which is as new as this machine is allowed to be. Nothing to do."
        return 0
    fi
    # A ceiling naming a release that never shipped cannot be a target.
    if [ -z "$(ubuntu_release_date "$target")" ]; then
        echo ""
        echo "WARNING: the ceiling names Ubuntu $target, which distro-info has never heard of."
        echo "         Fix '$POLICY_HOST.ubuntu=' in $(policy_location); not attempting an upgrade."
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
        echo "         updates. Nothing was done. Confirm the VPN client on $newest_ver and set"
        echo "         '$POLICY_HOST.ubuntu=$newest_ver' in $(policy_location)."
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
    vpn_client_standing "$target"
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
        echo "          hypothetical: it is how 26.04 removed the VPN client on 2026-08-31."
    fi

    echo ""
    echo "Answering yes will:"
    echo "  - upgrade this machine from $ver to $target, which REBOOTS at the end"
    echo "  - ask you about third-party apt sources partway through"
    [ -n "$have_prompt" ] && [ -n "$want_prompt" ] \
        && echo "  - switch this machine to being offered every new release instead of only" \
        && echo "    LTS ones, which is what has been hiding $target from it"
    echo ""
    echo "The upgrade turns off third-party apt sources and resets the VPN service."
    echo "Re-running myupdater afterwards puts both back."
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
    echo "sources this upgrade turned off and the VPN service it reset."
}

fedora_release_upgrade() {
    local ver="$1" ceiling="$2"

    # No query command like do-release-upgrade -c here, so the ceiling IS the
    # target. dnf supports jumping one or two releases; more than that wants
    # intermediate hops, so bump the ceiling in steps if it has drifted far.
    echo ""
    echo "Fedora $ceiling is newer than $ver and within the ceiling."
    confirm "Download the Fedora $ceiling upgrade now?" || return 0

    sudo dnf install -y dnf-plugin-system-upgrade || return 1
    if ! sudo dnf system-upgrade download --releasever="$ceiling"; then
        echo "Download failed — nothing has changed. Resolve the conflicts above and re-run."
        return 1
    fi
    echo ""
    echo "Downloaded. Finish with:  sudo dnf system-upgrade reboot"
    echo "(left to you on purpose — that command reboots immediately)"
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
    if [ -z "$POLICY_FILES" ]; then
        echo "No release policy in any sibling *_credentials repo, skipping (an unknown"
        echo "ceiling means don't move). Expected at $(policy_location)."
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

    ceiling="$(policy_lookup "$id")"
    if [ -z "$ceiling" ]; then
        echo "$pretty: no ceiling declared for '$id' on this host, leaving the release alone."
        echo "Add '$POLICY_HOST.$id=<max VERSION_ID>' to $(policy_location) once you know"
        echo "which release the VPN client supports on this machine."
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
        echo "WARNING: this machine is PAST the ceiling ($ver > $ceiling), so the VPN client"
        echo "         is running on a release nobody signed off on. Either verify support and"
        echo "         raise '$POLICY_HOST.$id=' in $(policy_location), or rebuild onto $ceiling."
        return 0
    fi

    case "$id" in
      ubuntu)
        ubuntu_release_upgrade "$ver" "$ceiling"
        ;;
      fedora)
        if [ "$ver" = "$ceiling" ]; then
            echo "Nothing to do."
        else
            fedora_release_upgrade "$ver" "$ceiling"
        fi
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
    # After the upgrade: if it pulled in a new VPN client, that client just
    # reset its own systemd units, so this has to run downstream of it.
    check_vpn_client_health
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
