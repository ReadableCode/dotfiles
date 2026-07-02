# Homelab Deployments

How self-hosted apps are deployed and managed across the homelab. Written
2026-07-02 after setting up the herdstone media remote and the elitedesk
auto-deploy pipeline.

## Hosts

| Host | IP | OS / access | Role |
|------|----|-------------|------|
| elitedesk | 192.168.86.179 | Ubuntu, `ssh jason@` (docker needs sudo) | Main docker app server (~25 containers) |
| behemoth | 192.168.86.31 | unraid, `ssh root@` | Primary media stack + storage (docker managed via unraid UI, not the Docker repo) |
| nukbuntu | — | Ubuntu | Has a compose file with plex/sonarr/radarr but does **not** currently run media services |
| raspberrypi4 | — | Raspbian | Compose file has plex/jellyfin; not part of the active media stack |

Media services actually running (2026-07):

- **behemoth**: sonarr :8989, radarr :7878, radarr-4k :7879, plex :32400
- **elitedesk**: sonarr :8989, radarr :7878, plex :32400 (host network)

## Repo layout (side-by-side clones at `~/GitHub` on every machine)

Compose build contexts and env paths are relative (`../<repo>`), so the same
layout must exist on the Mac and on the servers.

| Repo | Role |
|------|------|
| `Docker` | Compose files, one per host. `docker_compose_projects.yaml` = the elitedesk stack. `scripts/git_pull.sh` + `scripts/redeploy.sh` = auto-deploy. |
| `personal_credentials` | `personal.env` (KEY="value" secrets) and `hosts.json` (herdstone machine/service inventory). **Hosted on elitedesk itself** — its origin is local, so automation must never pull it (listed in `~/GitHub/.skiprepos`). |
| `server_configs` | SWAG reverse-proxy confs per host: `application_configs/swag/<host>/proxy-confs/<app>.subdomain.conf`. |
| `dotfiles` | Ansible INI inventory (`inventory/hosts`), `go_apps/git_puller` (bulk repo puller, reads `.skiprepos`), `triggers/` crontab snapshots per host. |
| `herdstone` | Machine herd monitor + media remote (CLI/TUI/web). Web UI container `herdstone_web` :8787. |
| app repos | `load-log`, `Assistant`, `CrownCentral`, `duck_db_api`, `postgrest-auth`, `website`, `charlie-personal-website` — each built into containers by the Docker repo. |

## Auto-deploy pipeline (elitedesk)

Push to master/main of a mapped repo → live within 5 minutes. Implemented in
`Docker/scripts/git_pull.sh` (repo→services map inside) + `redeploy.sh`,
run from **root's crontab**:

```cron
*/5 * * * * bash /home/jason/GitHub/Docker/scripts/git_pull.sh >> /home/jason/logs/git_pull_redeploy.log 2>&1
```

Key behaviors:

- Runs entirely as root (docker requires it here — keep it that way); git uses
  jason's key via `GIT_SSH_COMMAND` and auto-adds `safe.directory` per repo.
  Side effect: `.git` metadata in these repos becomes root-owned; manual pulls
  there need `sudo git pull`.
- Only master/main deploys; repos on other branches are skipped.
- Rebuilds **only** the changed repo's services — image-only containers
  (sonarr, radarr, plex, swag, ...) are never touched.
- A change to the `Docker` repo itself runs a plain `up -d` (recreates only
  services whose compose config changed).
- Ignore list: `~/GitHub/.skiprepos` (one repo name per line; shared with the
  go git_puller). Contains `personal_credentials`.
- Because `personal_credentials` is never pulled, after editing
  `personal.env`/`hosts.json` on elitedesk run:
  `sudo bash ~/GitHub/Docker/scripts/redeploy.sh herdstone-web`
- Manual force-redeploy any service the same way:
  `sudo bash ~/GitHub/Docker/scripts/redeploy.sh <service> [service...]`
- This replaced the old single-repo `charlie-personal-website/redeploy.sh`
  root cron entry (2026-07).
- The fourteen_foods server runs the same pattern separately
  (`fourteen_foods/backend/scripts/git_pull.sh`, user `svc_linux`).

## Compose conventions (`Docker/docker_compose_projects.yaml`)

- elitedesk uses **legacy `docker-compose` v1** (hyphen) — the `docker compose`
  plugin is not installed; always `sudo`.
- Service pattern: `image: <name>_image`, `container_name` snake_case,
  `build.context: ../<repo>[/subdir]`, `TZ: America/Chicago`,
  `restart: unless-stopped`, quoted ports.
- Secrets: `env_file: ../personal_credentials/personal.env`. Naming:
  `<SERVICE>_<HOST>_API_KEY`; `PLEX_TOKEN` is account-level and works on
  every Plex server signed into the account.
- Python apps: `python:3.14-slim` base + uv copied from
  `ghcr.io/astral-sh/uv`, `uv sync --frozen --no-dev` in two layers
  (deps, then project). Run the venv entry point directly in CMD —
  `uv run` re-syncs dev deps on every container start.
- Gotcha: bind-mounting a host file that doesn't exist yet makes docker
  create an empty **directory** at that path on the host — check the source
  file landed (got committed/pulled) before `up`.
- herdstone_web specifics: `HERDSTONE_HOSTS=/config/hosts.json` +
  `../personal_credentials/hosts.json:/config/hosts.json:ro` mount.

## SWAG / reverse proxy (elitedesk)

- `swag` container, duckdns + wildcard cert (`SUBDOMAINS=wildcard`) — new
  subdomains need **no** DNS/cert changes, only a proxy conf.
- New app recipe: copy an existing `<app>.subdomain.conf` in
  `server_configs/application_configs/swag/elitedesk/proxy-confs/`; set
  `server_name <app>.*`, `$upstream_app <container_name>`, `$upstream_port`.
- Private apps get basic auth at server scope:
  `auth_basic "Restricted Access"; auth_basic_user_file /config/nginx/.htpasswd;`
- Websocket apps (Streamlit, NiceGUI) work through the stock
  `include /config/nginx/proxy.conf` — no extra Upgrade headers needed.
- Deploying a conf change: get the conf into swag's `/config/nginx/proxy-confs/`
  and restart the swag container.

## Herdstone quick reference

- Inventory: `~/GitHub/personal_credentials/hosts.json` — hosts + the services
  each offers; `api_key_env` names the env var holding each service's key.
  Adding a sonarr/radarr/plex instance is config-only.
- `herdstone media search|seasons|add`, `herdstone tui`, `herdstone web`.
- Sonarr/Radarr **lookup endpoints omit presence detail** (Radarr `hasFile`,
  Sonarr season statistics) — statuses must come from library records
  (`/api/v3/movie`, `/api/v3/series`), which herdstone does.
