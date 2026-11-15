#!/bin/bash
# Print this network's public IPv4 and IPv6 addresses on their own labeled lines.
# api.ipify.org has only A records and api6.ipify.org only AAAA records, so each
# lookup answers for one address family; "none" means that family has no route out.
# The hosts do the separating, not curl -4/-6: macOS curl -6 falls back to an
# IPv4-mapped address and would report the IPv4 address as the IPv6 one.
v4=$(curl -s -m 8 https://api.ipify.org) || v4=""
v6=$(curl -s -m 8 https://api6.ipify.org) || v6=""
echo "ipv4: ${v4:-none}"
echo "ipv6: ${v6:-none}"
