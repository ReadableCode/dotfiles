# Setup Tailscale

## Linux

### Install Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
# Change this to your local LAN subnet
sudo tailscale up --advertise-exit-node --advertise-routes=192.168.86.0/24
sudo systemctl enable --now tailscaled
```

#### To enable the subnet routing:

Go to the Tailscale admin panel: https://login.tailscale.com/admin/machines

Find the new system

Click the 3-dot menu → Enable subnet routes

This allows other Tailscale devices (like your laptop or phone) to reach anything on your local LAN via this system.

#### To enable the exit node:

Go to the Tailscale admin panel: https://login.tailscale.com/admin/machines

Find the new system

Click the 3-dot menu → Enable exit node

This allows other Tailscale devices (like your laptop or phone) to use this system as a VPN exit node.

#### To fix warning message:

```bash
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
  