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
