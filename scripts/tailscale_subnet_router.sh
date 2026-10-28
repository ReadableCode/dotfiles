#!/usr/bin/env bash
# tailscale_subnet_router.sh - keep this host advertising the given subnet
# routes to the tailnet and not accepting any, so a device away from home
# reaches LAN addresses over Tailscale through it.
#
#   tailscale_subnet_router.sh [--check] <cidr>[,<cidr>...]
#
# The routes come from the host's inventory record (`tailscale.advertise_routes`
# in <context>_hosts.json); src/tailscale_routes.py reads the record and calls
# this on a machine with a checkout, and a host without one (an Unraid box)
# gets the routes rendered into its own cron line by its deploy. Plain bash and
# sed so it runs where there is no python. Doc: docs/setup_tailscale.md,
# "Subnet routers".
#
# Each run reads the prefs and changes nothing when they already match, so it
# is safe on a short timer; that timer is what keeps a stray `tailscale up`
# (which resets every flag it is not given) from dropping the routes for good.
# It asserts two things:
#   - AdvertiseRoutes holds every route given. An exit node already advertised
#     (0.0.0.0/0 and ::/0) is kept; one that is not is not added.
#   - accept-routes is off. A Linux box inside the LAN that accepts the LAN
#     route sends its own LAN traffic into Tailscale and loses the network,
#     and a router sits on the LAN it routes, so accepting buys it nothing.
#
# Needs the right to change prefs: root, the user Tailscale names as operator
# (`tailscale set --operator=<user>` once), or the signed-in user of the macOS
# app. Prints one line when it changes something and nothing otherwise. A
# route is used only once it is approved for the node in the admin console.
#
# --check prints the current state and exits 1 when it differs, changing
# nothing.

set -euo pipefail

check=0
want=""
for arg in "$@"; do
    case "$arg" in
    --check) check=1 ;;
    -*)
        echo "usage: $0 [--check] <cidr>[,<cidr>...]" >&2
        exit 2
        ;;
    *) want="$arg" ;;
    esac
done
if [ -z "$want" ]; then
    echo "usage: $0 [--check] <cidr>[,<cidr>...]" >&2
    exit 2
fi

ts="$(command -v tailscale || true)"
for candidate in /usr/local/sbin/tailscale /Applications/Tailscale.app/Contents/MacOS/Tailscale; do
    if [ -z "$ts" ] && [ -x "$candidate" ]; then
        ts="$candidate"
    fi
done
if [ -z "$ts" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') tailscale_subnet_router: no tailscale binary on this host" >&2
    exit 1
fi

# `debug prefs` is JSON; with the whitespace removed the two fields read as
# "AdvertiseRoutes":[...] (or null) and "RouteAll":true|false.
flat="$("$ts" debug prefs | tr -d ' \t\r\n')"
routes="$(sed -n 's/.*"AdvertiseRoutes":\[\([^]]*\)\].*/\1/p' <<<"$flat")"

has_route() {
    case ",$routes," in
    *",\"$1\","*) return 0 ;;
    *) return 1 ;;
    esac
}

exit_node=false
if has_route "0.0.0.0/0" && has_route "::/0"; then
    exit_node=true
fi

accept_routes=true
case "$flat" in
*'"RouteAll":false'*) accept_routes=false ;;
esac

missing=""
IFS=',' read -r -a wanted <<<"$want"
for route in "${wanted[@]}"; do
    if ! has_route "$route"; then
        missing="$missing $route"
    fi
done

state="advertise=[${routes//\"/}] accept-routes=$accept_routes"
if [ -z "$missing" ] && [ "$accept_routes" = false ]; then
    if [ "$check" -eq 1 ]; then
        echo "ok: $state"
    fi
    exit 0
fi

if [ "$check" -eq 1 ]; then
    echo "drift: $state, want $want advertised and accept-routes=false"
    exit 1
fi

"$ts" set --advertise-routes="$want" --advertise-exit-node="$exit_node" --accept-routes=false
echo "$(date '+%Y-%m-%d %H:%M:%S') tailscale_subnet_router: was $state, now advertising $want (exit node $exit_node), accept-routes=false"
