# Setup Tailscale

## Linux

### Install Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --advertise-routes=192.168.86.0/24  # Change this to your local LAN subnet
sudo systemctl enable --now tailscaled
```

- Final Step (if you want subnet routing to work):
  Go to the Tailscale admin panel: https://login.tailscale.com/admin/machines

  Find the new system

  Click the 3-dot menu → Enable subnet routes

  This allows other Tailscale devices (like your laptop or phone) to reach anything on your local LAN via this system.