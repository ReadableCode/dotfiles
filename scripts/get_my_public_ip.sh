#!/bin/bash
# Print this network's public IPv4 and IPv6 addresses on their own labeled lines.
# api.ipify.org has only A records and api6.ipify.org only AAAA records, so each
# lookup answers for one address family; "none" means that family has no route out.
v4=$(curl -4 -s -m 8 https://api.ipify.org) || v4=""
v6=$(curl -6 -s -m 8 https://api6.ipify.org) || v6=""
echo "ipv4: ${v4:-none}"
echo "ipv6: ${v6:-none}"
