# Setup Tailscale

## Linux

### Install Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo systemctl enable --now tailscaled
sudo tailscale up
```

A plain `tailscale up`: no advertised routes, accept-routes left at its Linux
default of off. That is every machine except a subnet router. Accept-routes
must stay off on a Linux box at home: one that accepts the LAN's own route
sends its LAN traffic into Tailscale and loses the network. Never re-run
`tailscale up` with fewer flags to change one setting; it resets every flag
it is not given. Use `tailscale set`.

### Subnet routers

A subnet router advertises the home LAN to the tailnet, which is what lets a
device away from home reach `192.168.86.x` addresses (the inventories and ssh
fragments use them on purpose). Several machines advertise the same route so
it survives any one of them being down; Tailscale picks one online router as
primary and fails over by itself.

A machine is a router because its inventory record says so:

```json
"tailscale": {"advertise_routes": ["192.168.86.0/24"]}
```

Tailscale keeps advertised routes only in its own state (`tailscale set`), so
no deployed file can hold them, and its system policies have no key for them.
`scripts/tailscale_subnet_router.sh` sets them, with accept-routes off, and
changes nothing when they already match. What runs it:

| Host kind | Runs it | How often |
|-----------|---------|-----------|
| A Linux server with a cron declared in server_configs | `python3 -B ~/GitHub/dotfiles/src/tailscale_routes.py` in that crontab | every 10 minutes |
| A machine refreshed by hand (a Mac) | `src/tailscale_routes.py`, step 5c of `refresh_machine.py` | every gitpullall |
| Unraid (no checkout) | a dynamix cron with the routes rendered in, pushed by `server_configs/scripts/deploy_behemoth.sh` | every 10 minutes |

`python3 src/tailscale_routes.py --check` reports whether this machine's
prefs match its record and changes nothing.

New router, once per machine:

1. Add the `tailscale` block to its inventory record.
2. Linux only: turn on IP forwarding (below), and if its cron runs as a user
   rather than root, let that user change prefs:
   `sudo tailscale set --operator=jason`.
3. Admin console, Machines, the machine, Edit route settings: approve
   `192.168.86.0/24`. A route is advertised but unused until approved.
4. Same menu: Disable key expiry, so the router does not drop off the tailnet
   when its key ages out.

#### Exit nodes

An exit node is a separate choice, made with `tailscale set
--advertise-exit-node` and approved in the same Edit route settings dialog.
The subnet router script keeps whatever exit-node setting a machine already
has.

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
netsh interface portproxy add v4tov4 listenport=18501 listenaddress=127.0.0.1 connectport=8501 connectaddress=<remote-host-ip>
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
```

- If it does not have a /etc/sysctl.d directory, use:

Edit the file `/etc/sysctl.conf` and add the following line:

```bash
net.ipv4.ip_forward=1
```

Then run the following command to apply the changes:

```bash
sudo sysctl -p
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
  [repo_context_credentials.md](./repo_context_credentials.md) for the
  inventory schema.
