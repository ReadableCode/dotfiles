# Client Credentials Repos (`*_credentials`)

The public dotfiles repo holds **all the logic** and none of the secrets. Every
private context — personal machines, and each client/employer — gets its own
private repo named `<context>_credentials`, cloned **next to** the dotfiles
checkout (e.g. `~/GitHub/personal_credentials`, `~/GitHub/acme_credentials`).
Each one acts as that context's private dotfiles repo. Nothing client-private
(names, hostnames, configs, keys) ever lives in the public repo — every tool
here discovers the private repos generically by globbing `../*_credentials`.

## What a credentials repo contains

For a repo named `acme_credentials` (context token `acme` = the directory name
minus the `_credentials` suffix):

| File | Purpose |
|------|---------|
| `acme_manifest.yaml` | Optional **overlay deploy manifest** — same entry schema as `deploy_manifest.yaml`, but its `repo:` paths are relative to `acme_credentials/`. Loaded automatically by `src/deploy_configs.py`; see [deploy_configs.md](./deploy_configs.md). |
| `acme_hosts.json` | Optional **host inventory** — same schema as the personal `hosts.json`. Legacy fallback: a bare `hosts.json` is used when the prefixed file is absent. |
| config payloads | The actual private files the overlay manifest links into place (client `.env` files, MCP configs, per-repo Claude settings, workspace variants, ...). |
| anything else | Credentials, keys, notes — the repo is private, so it can hold whatever that context needs. |

Both files are optional per repo; a repo contributes only what it declares.

### When an overlay must NOT follow the credentials clone

A credentials repo is cloned on every machine that needs that context's
secrets, the client's own machines included. Config that must reach only
*some* of them therefore cannot live in an overlay gated by that clone. Any
sibling repo can carry its own overlay by declaring `<dirname>_manifest.yaml`
(and/or `<dirname>_removals.yaml`) — full directory name, no suffix dropped —
so a repo like `acme_dev` that is cloned only on personal machines gates its
entries by its own presence. Secret payloads still stay in the credentials
repo; the narrower overlay just points `repo:` back across at them with a
matching `requires:`.

## How the dotfiles tools consume them

- **Deploy** — `deploy_configs.py` loads `deploy_manifest.yaml` plus every
  discovered `<context>_manifest.yaml` (sorted, entry names must be unique
  across all manifests). Overlay `repo:` paths resolve against the overlay's
  own root; `{repo_parent}` always expands to the dotfiles checkout's parent.
- **Host validation** — manifest `hosts:` filters are validated against the
  **union** of every `*_credentials` inventory, so personal manifests can
  target client boxes and vice versa without any cross-references in code. A
  machine with no credentials repos skips the check.
- **Shell ssh aliases** — the shell startup files build ssh aliases from every
  `*_credentials` inventory they find, so cloning a client's credentials repo
  onto a machine is all it takes to get that client's hosts.

  There is **one implementation** of that, for every shell: `src/ssh_aliases.py`
  reads the inventories and prints ready-to-eval alias definitions in the
  caller's syntax (`--format bash` / `--format powershell`; `--format json` to
  inspect the set as data). `application_configs/bash/.shared_aliases` evals the
  bash output and `application_configs/powershell/powershell_aliases.ps1`
  invokes the PowerShell output, so jump resolution, port handling, user
  selection and vnc aliases cannot drift between the two the way the old
  hand-synced `_load_ssh_hosts` / `Import-SshHostAliases` twins could. The
  script is stdlib-only, so a bare `python3` runs it at shell startup before any
  venv exists; a machine without a usable Python simply gets no ssh aliases.

  An **alias name must be a bare word** (`^[A-Za-z0-9_][A-Za-z0-9_.-]*$`) —
  these definitions are `eval`'d, so anything else raises and the generator
  exits non-zero, leaving the shell with **no ssh aliases at all** rather than
  quietly dropping the one entry. That means a bad name in a client inventory
  also costs that machine its personal aliases: deliberate, so a broken
  inventory gets fixed instead of going unnoticed. An unreadable inventory
  *file* is the softer case — it warns and only costs that context.

  A host may also declare `vnc_aliases` (with an optional `vnc_hostname` when
  the screen-sharing target differs from the ssh one, e.g. a Tailscale address).
  These become `open vnc://user@host` aliases and are emitted **on macOS only**,
  in whichever shell asked — the gate is the platform, not the shell, because
  nothing off macOS has a `vnc://` handler.

### Inventory `jump:` — hosts behind a VPN another machine holds

A host record may name another host in the **same inventory** that can reach
it:

```json
{
  "name": "acme-vm-01",
  "hostname": "172.20.10.101",
  "user": "svc_linux",
  "aliases": ["sshacmevm"],
  "jump": "sshacme"
}
```

The generated alias then carries the hop — `ssh -J user@jump:port
user@target` — so a machine that is **not** on the VPN reaches the target
through the machine that is. The hop is resolved at shell-startup time and
dropped when the alias is built **on the jump machine itself**, which is
already inside the VPN.

This deliberately keeps the chain in the inventory rather than in any
machine's `~/.ssh/config`: nothing outside the repo constellation needs
editing, every machine that clones the credentials repo gets it on every
platform, and there is one source of truth to change when an address moves.
It is the same reasoning — and the same resulting argv — as
`build_ssh_argv` in the sibling `status_board` repo (see that repo's
README), which builds its own `-J` chain for `ssh_command` panels.

Requirements are the board's: non-interactive key auth to both hops, and
`AllowTcpForwarding` on the jump host's sshd (the default, and true of
Windows OpenSSH Server).

The one thing aliases cannot cover is a tool that addresses the target by
**raw IP** and shells out to ssh itself (an rsync job pulling a cache off
such a VM) — it never sees a shell alias. For that case the same hop is
mirrored in an ssh_config *fragment*: the base `~/.ssh/config` (dotfiles
`application_configs/ssh/config`, deployed by `personal_manifest.yaml` on
personal machines only) is nothing but `Include config.d/*.conf`, and each
overlay deploys its own `~/.ssh/config.d/<context>.conf` — a client's jump
fragment lives in `acme_credentials/ssh/` but deploys from the `acme_dev`
overlay, because the hop is wrong on the client's own machines. Keep a
fragment in sync with its inventory when an address moves; the inventory
stays the source of truth.

Deploying a client's configs on a machine therefore requires exactly two
clones: `dotfiles` and that client's `*_credentials` repo. Entries whose
destinations live inside other repo checkouts should use the manifest
`requires:` precondition so they follow the clones.

## Hosting: repo on a Linux host, cloned over ssh

A credentials repo does not need a git forge. The canonical copy is a
**normal working clone in a Linux machine's repos dir** — the same pattern as
`personal_credentials` — and every other machine clones straight from it over
ssh:

```bash
# the canonical copy lives on a Linux host, e.g.
#   /home/user/GitHub/acme_credentials   (a plain working repo, not bare)

# make pushes from clones update its working tree (refused if it is dirty)
git -C /home/user/GitHub/acme_credentials config receive.denyCurrentBranch updateInstead

# on each machine that needs it
git clone user@linux-host:/home/user/GitHub/acme_credentials ~/GitHub/acme_credentials
```

Do NOT host the canonical copy on a **Windows** machine. Windows OpenSSH's
default shell is `cmd.exe`, which breaks git's server-side transport (it does
not strip the single quotes git wraps around the repo path, and the ssh URL's
absolute `/C:/...` path form is rejected by Windows git). Fixing that needs
either admin rights (registry `DefaultShell` change) or wrapper shims —
neither is acceptable here. A client machine whose repos should live on its
own hardware but is Windows-only gets its canonical hosted on the homelab
Linux box instead; Windows machines work fine as clone *clients*.

When the origin is a **laptop** that is often asleep or off-network, that only
blocks `git pull`/`push` against it — existing clones keep working fully
offline, since every clone has the complete history. Sync when the laptop is
reachable; nothing else degrades.
