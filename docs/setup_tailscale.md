# Setup Tailscale

## Linux

### Install Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
# Change this to your local LAN subnet
sudo tailscale up --advertise-exit-node --advertise-routes=192.168.86.0/24
sudo systemctl enable --now tailscaled
```

#### To enable the subnet routing

Go to the Tailscale admin panel: <https://login.tailscale.com/admin/machines>

Find the new system

Click the 3-dot menu → Enable subnet routes

This allows other Tailscale devices (like your laptop or phone) to reach anything on your local LAN via this system.

#### To enable the exit node

Go to the Tailscale admin panel: <https://login.tailscale.com/admin/machines>

Find the new system

Click the 3-dot menu → Enable exit node

This allows other Tailscale devices (like your laptop or phone) to use this system as a VPN exit node.

#### Using tailscale funnel

- Tailscale Funnel allows you to expose services running on your Tailscale device or another reacable device to the public internet.

- To expose a service running on port 8501 (Streamlit default port) to the public internet, run the following commands:

```bash
tailscale funnel 8501
```

- You can then access the service via the provided public URL.

#### To host streamlit app running on a different device

- on a terminal on the machine with streamlit

```bash
streamlit run web_app.py --server.address=0.0.0.0
```

- on a terminal on the machine with tailscale

```bash
tailscale funnel 18501
```

- Windows: on a new admin terminal on the machine with tailscale

```bash
netsh interface portproxy add v4tov4 listenport=18501 listenaddress=127.0.0.1 connectport=8501 connectaddress=192.168.86.126
```

To list the current portproxy settings, run:

```bash
netsh interface portproxy show v4tov4
```

To disable the portproxy later, run:

```bash
netsh interface portproxy delete v4tov4 listenport=18501 listenaddress=127.0.0.1
```

#### To fix warning message

```plaintext
Unable to relay traffic
This machine has IP forwarding disabled and cannot relay traffic. Please enable IP forwarding on this machine to use relay features like subnets or exit nodes.
```

- If your Linux system has a /etc/sysctl.d directory, use:

```bash
echo 'net.ipv4.ip_forward = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf
echo 'net.ipv6.conf.all.forwarding = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf
sudo sysctl -p /etc/sysctl.d/99-tailscale.conf
# then restart tailscale
sudo tailscale up --reset
sudo tailscale up --advertise-exit-node --advertise-routes=192.168.86.0/24
```

- If it does not have a /etc/sysctl.d directory, use:

Edit the file `/etc/sysctl.conf` and add the following line:

```bash
net.ipv4.ip_forward=1
```

Then run the following command to apply the changes:

```bash
sudo sysctl -p
# then restart tailscale
sudo tailscale up --reset
sudo tailscale up --advertise-exit-node --advertise-routes=192.168.86.0/24
```

## Tailnet DNS

Installing Tailscale changes name resolution on every device that joins. This
section covers getting LAN hostnames back without giving up MagicDNS.

### Why bare hostnames stop resolving

Tailscale installs MagicDNS (`100.100.100.100`) as the device's first resolver
and puts the tailnet domain first in the search list. Names of tailnet members
resolve fine. Every other machine on the same LAN returns NXDOMAIN.

This happens even with the LAN gateway listed under **Global nameservers**.
Global nameservers are a flat fallback set with no per-suffix routing, so a
public resolver answers NXDOMAIN first and that is what comes back. The gateway
is never asked.

The symptom is confusing because it is not all-or-nothing: on one machine, at
one moment, `ssh <box>` works for hosts joined to the tailnet and fails for
hosts that are not, even though both are on the same LAN.

### Fix: split DNS for the LAN suffix

In the admin panel under [DNS](https://login.tailscale.com/admin/dns):

1. **Nameservers → Add nameserver → Custom.** Enter the LAN gateway
   (`192.168.86.1`), turn on **Restrict to domain** (Split DNS), and set the
   domain to the LAN's DNS suffix — UniFi gateways use `localdomain` by
   default. Turn on **Use with exit node** as well (see below).
2. If that same gateway IP is also listed under **Global nameservers**, remove
   it there. The split entry replaces it and is the one that actually routes.
3. **Search Domains → Add search domain** — the same suffix.
4. Leave **Override DNS servers** off and MagicDNS on.

A restricted nameserver is a routing rule rather than a fallback: anything
ending in that suffix goes to the gateway and only there. With the suffix also
in the search list, a bare name becomes `<name>.<suffix>`, routes to the
gateway, and resolves. Tailnet names keep coming from MagicDNS, and everything
else still goes to the global resolvers.

### Use with exit node

Off by default, which means LAN name resolution stops whenever an exit node is
selected. Turn it on if exit nodes are ever used: a subnet route (`/24`) is
more specific than an exit node's `0.0.0.0/0`, so the gateway stays reachable
through the subnet router while general traffic exits elsewhere.

### Verifying

```bash
# the split route reached this device
scutil --dns | grep -B1 -A3 192.168.86.1   # macOS
resolvectl status                          # systemd-resolved

# MagicDNS now forwards the suffix instead of answering NXDOMAIN
dig +short @100.100.100.100 <host>.localdomain

# and the bare name works through the system resolver
dscacheutil -q host -a name <host>         # macOS
getent hosts <host>                        # Linux
```

Tailnet members answer with their `100.x` address, since the tailnet domain is
still the first search domain. Everything else answers with its LAN address.
Both are correct.

### Caveats

- **Off-LAN this needs a subnet router.** Resolving the suffix remotely means
  reaching the gateway, which only works while some node advertises the LAN
  `/24` and is online. On-LAN resolution is unaffected either way.
- **Answers come from DHCP leases.** A host whose lease moves resolves to a
  different address. Give anything you depend on a DHCP reservation.
- **Reservations beat `.local`.** mDNS does not route, so `.local` names are
  dead over Tailscale, and mDNS returns every address a host owns — on a
  dual-homed machine that means wired or wireless at random, which is how you
  end up on a 1x1 Wi-Fi link instead of the GbE port you meant to use.
- **Host inventories should still store reserved IPs, not names.** An IP
  resolves identically from every machine regardless of what that machine's
  resolver, search domains or mDNS stack are doing. See
  [client_credentials_repos.md](./client_credentials_repos.md) for the
  inventory schema.
