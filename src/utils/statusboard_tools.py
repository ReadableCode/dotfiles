# %%
# Imports #

import json
import os
import subprocess
import time
from datetime import datetime

import requests
import yaml
from utils.inventory_tools import (
    credentials_context,
    find_credentials_dirs,
    find_inventory_paths,
)

# %%
# Variables #

PANEL_TYPES = ("ssh_command", "github_prs", "bitbucket_prs")

# Per-type defaults: refresh interval (seconds) and, where relevant, timeouts
DEFAULT_INTERVALS = {"ssh_command": 300, "github_prs": 180, "bitbucket_prs": 180}
DEFAULT_SSH_TIMEOUT = 60
DEFAULT_HTTP_TIMEOUT = 30
DEFAULT_GITHUB_API = "https://api.github.com"
BITBUCKET_API = "https://api.bitbucket.org/2.0"

# ssh options used for every panel connection: never prompt (this runs
# unattended in a long-lived TUI), fail fast when a hop is unreachable, and
# accept-new host keys so a fresh machine with the credentials repos cloned
# works without hand-seeding known_hosts (changed keys still hard-fail).
SSH_BASE_OPTIONS = (
    "-T",
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=10",
    "-o", "StrictHostKeyChecking=accept-new",
)


# %%
# Results #


class PanelResult:
    """
    Outcome of one panel fetch.

    kind is "ansi" (body: raw terminal text to render as-is) or "links"
    (body: list of {"text", "url", "meta"} rows the TUI turns into clickable
    lines). A failed fetch has ok=False and the error text in body.
    """

    def __init__(self, ok, kind, body, summary=""):
        self.ok = ok
        self.kind = kind
        self.body = body
        self.summary = summary
        self.fetched_at = time.time()

    @classmethod
    def error(cls, message):
        return cls(False, "ansi", str(message), "error")


# %%
# Config discovery #


def discover_statusboard_configs(credentials_root, repo_root=None):
    """
    Locate every statusboard config to load: an optional ``statusboard.yaml``
    in the dotfiles repo root (tracked, so secrets-free panels only) plus, for
    each sibling ``*_credentials`` repo, an optional ``<context>_statusboard.yaml``
    - the same overlay pattern deploy_configs uses for manifests. Returns a
    list of (config_path, base_dir) pairs, overlays sorted for determinism.
    """
    configs = []
    if repo_root:
        main_config = os.path.join(repo_root, "statusboard.yaml")
        if os.path.exists(main_config):
            configs.append((main_config, repo_root))
    for credentials_dir in find_credentials_dirs(credentials_root):
        overlay = os.path.join(credentials_dir, f"{credentials_context(credentials_dir)}_statusboard.yaml")
        if os.path.exists(overlay):
            configs.append((overlay, credentials_dir))
    return configs


def load_panels(credentials_root, repo_root=None, config_path=None):
    """
    Load every discovered statusboard config, returning (panels, config_paths).
    Each panel is stamped with ``_base_dir`` (its config's repo root, which
    env_file paths resolve against and whose host inventory is searched first)
    and ``_config`` (for error messages). Panel names must be unique across
    ALL loaded configs.

    Passing config_path (the --config test escape hatch) loads only that file,
    base_dir its containing directory, skipping discovery.
    """
    if config_path:
        located = [(config_path, os.path.dirname(os.path.abspath(config_path)))]
    else:
        located = discover_statusboard_configs(credentials_root, repo_root)
    panels = []
    seen: dict = {}
    for path, base_dir in located:
        for panel in _parse_config_file(path):
            if panel["name"] in seen:
                raise ValueError(
                    f"Duplicate statusboard panel name '{panel['name']}' in {path} "
                    f"(already defined in {seen[panel['name']]})"
                )
            seen[panel["name"]] = path
            panel["_base_dir"] = base_dir
            panel["_config"] = path
            panels.append(panel)
    return panels, [path for path, _ in located]


def _parse_config_file(config_path):
    """Parse one statusboard config and validate the panel schema, returning a list of panel dicts."""
    with open(config_path, "r", encoding="utf-8") as file_handle:
        panels = yaml.safe_load(file_handle) or []
    if not isinstance(panels, list):
        raise ValueError(f"Statusboard config {config_path} must be a YAML list of panels")
    for panel in panels:
        _validate_panel(panel, config_path)
        panel.setdefault("interval", DEFAULT_INTERVALS[panel["type"]])
    return panels


def _validate_panel(panel, config_path):
    if not isinstance(panel, dict) or "name" not in panel or "type" not in panel:
        raise ValueError(f"Statusboard panel must be a mapping with 'name' and 'type' keys ({config_path}): {panel}")
    if panel["type"] not in PANEL_TYPES:
        raise ValueError(
            f"Statusboard panel '{panel['name']}' in {config_path} has unknown type '{panel['type']}' "
            f"(expected one of {', '.join(PANEL_TYPES)})"
        )
    required = {
        "ssh_command": ("host", "command"),
        "github_prs": ("token_env",),
        "bitbucket_prs": ("workspace", "username_env", "app_password_env"),
    }[panel["type"]]
    missing = [key for key in required if not panel.get(key)]
    if missing:
        raise ValueError(
            f"Statusboard panel '{panel['name']}' in {config_path} "
            f"(type {panel['type']}) is missing required keys: {', '.join(missing)}"
        )


# %%
# Host inventory #


def load_inventory_hosts(inventory_path):
    """Parse one hosts.json-style inventory and return its full host records."""
    with open(inventory_path, "r", encoding="utf-8") as file_handle:
        inventory = json.load(file_handle)
    return inventory.get("hosts", [])


def find_host(token, base_dir, credentials_root):
    """
    Resolve a panel's host token (inventory ``name`` or one of its
    ``aliases``, case-insensitive) to its full inventory record. The config's
    own credentials repo inventory is searched first, then every other sibling
    inventory, so a panel travels with the repo that knows its hosts but can
    still reference machines declared elsewhere.
    """
    inventory_paths = []
    for filename in (f"{credentials_context(base_dir)}_hosts.json", "hosts.json"):
        path = os.path.join(base_dir, filename)
        if os.path.exists(path):
            inventory_paths.append(path)
            break
    inventory_paths += [path for path in find_inventory_paths(credentials_root) if path not in inventory_paths]
    wanted = token.strip().lower()
    for path in inventory_paths:
        for host in load_inventory_hosts(path):
            names = [host.get("name", "")] + list(host.get("aliases", []))
            if any(name.lower() == wanted for name in names if name):
                return host
    raise ValueError(
        f"Host '{token}' not found in any host inventory "
        f"({', '.join(inventory_paths) or 'no inventories found'})"
    )


def ssh_destination(host):
    """user@hostname for a resolved inventory record (user optional in the record)."""
    user = host.get("user")
    return f"{user}@{host['hostname']}" if user else host["hostname"]


def build_ssh_argv(panel, credentials_root, local_hostname=""):
    """
    Build the full ssh argv for an ssh_command panel, resolving ``host`` and
    the optional ``jump`` hop from the host inventories.

    The jump hop is injected as ``-J user@host:port`` so the chain lives
    entirely in the panel config + inventories - deliberately NOT in any
    machine's ~/.ssh/config, so the board works identically on every machine
    that has the credentials repos cloned. When the board is already running
    ON the jump machine (local_hostname matches), the hop is skipped.
    """
    target = find_host(panel["host"], panel["_base_dir"], credentials_root)
    argv = ["ssh", *SSH_BASE_OPTIONS]
    jump_token = panel.get("jump")
    if jump_token:
        jump = find_host(jump_token, panel["_base_dir"], credentials_root)
        local_short = (local_hostname or "").split(".")[0].lower()
        jump_names = [jump.get("name", "")] + list(jump.get("aliases", []))
        if local_short not in [name.split(".")[0].lower() for name in jump_names if name]:
            spec = ssh_destination(jump)
            if jump.get("port"):
                spec += f":{jump['port']}"
            argv += ["-J", spec]
    if target.get("port"):
        argv += ["-p", str(target["port"])]
    argv += [ssh_destination(target), panel["command"]]
    return argv


# %%
# Secrets #


def resolve_secret(panel, key):
    """
    Look up the env var named by panel[key]: the real environment wins, then
    the panel's optional ``env_file`` (path relative to the panel's config
    repo - so tokens live in the gitignored/private env files, never in the
    statusboard configs themselves).
    """
    var_name = panel[key]
    value = os.environ.get(var_name)
    if value:
        return value
    env_file = panel.get("env_file")
    if env_file:
        env_path = os.path.join(panel["_base_dir"], os.path.expanduser(env_file))
        if not os.path.exists(env_path):
            raise ValueError(f"Panel '{panel['name']}': env_file {env_path} does not exist")
        value = _parse_env_file(env_path).get(var_name)
        if value:
            return value
    raise ValueError(
        f"Panel '{panel['name']}': env var {var_name} is not set"
        + (f" and not found in {panel['env_file']}" if panel.get("env_file") else " (no env_file configured)")
    )


def _parse_env_file(path):
    """KEY=value lines (optional ``export``, quotes stripped); comments and non-kv lines ignored."""
    values = {}
    with open(path, "r", encoding="utf-8") as file_handle:
        for line in file_handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.replace("export ", "", 1).strip()
            value = value.strip().strip("'\"")
            if key:
                values[key] = value
    return values


# %%
# Fetchers #


def fetch_ssh_command(panel, credentials_root, local_hostname=""):
    """Run the panel's command over ssh (through the jump hop if configured) and capture its output."""
    argv = build_ssh_argv(panel, credentials_root, local_hostname)
    timeout = panel.get("timeout", DEFAULT_SSH_TIMEOUT)
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL
        )
    except subprocess.TimeoutExpired:
        return PanelResult.error(f"ssh timed out after {timeout}s: {' '.join(argv[:-1])}")
    except FileNotFoundError:
        return PanelResult.error("ssh not found on PATH")
    if completed.returncode != 0 and not completed.stdout.strip():
        detail = completed.stderr.strip() or f"ssh exited {completed.returncode}"
        return PanelResult.error(detail)
    return PanelResult(True, "ansi", completed.stdout.rstrip(), f"exit {completed.returncode}")


def fetch_github_prs(panel):
    """PRs whose review is requested from the token's account, via the GitHub search API."""
    token = resolve_secret(panel, "token_env")
    api = panel.get("api_url", DEFAULT_GITHUB_API).rstrip("/")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    user_response = requests.get(f"{api}/user", headers=headers, timeout=DEFAULT_HTTP_TIMEOUT)
    if user_response.status_code != 200:
        return PanelResult.error(f"GitHub /user returned {user_response.status_code} (bad/expired token?)")
    login = user_response.json()["login"]
    # A fine-grained token only surfaces repos it was granted, so a panel's
    # scope is primarily the TOKEN's repo selection; the optional ``search``
    # qualifiers refine on top (e.g. -repo:owner/name to keep two panels of
    # the same account from overlapping when one token sees everything).
    query = f"is:open is:pr archived:false review-requested:{login} {panel.get('search', '')}".strip()
    search_response = requests.get(
        f"{api}/search/issues",
        params={"q": query, "sort": "updated", "per_page": 50},
        headers=headers,
        timeout=DEFAULT_HTTP_TIMEOUT,
    )
    if search_response.status_code != 200:
        return PanelResult.error(f"GitHub search returned {search_response.status_code}: {search_response.text[:200]}")
    rows = []
    for item in search_response.json().get("items", []):
        repo = item["repository_url"].split("/repos/", 1)[-1]
        rows.append(
            {
                "text": f"{repo}#{item['number']}  {item['title']}",
                "url": item["html_url"],
                "meta": f"by {item['user']['login']} · updated {_age(item['updated_at'])} ago",
            }
        )
    # SAML orgs silently drop their repos from search results (a plain 200
    # with fewer items, no marker header) until the token is SSO-authorized -
    # probe each org the account belongs to, or an unauthorized token looks
    # like an empty review queue forever.
    blocked = _github_sso_blocked_orgs(api, headers)
    if blocked:
        return PanelResult.error(
            f"search results exclude SAML org(s) {', '.join(blocked)} - authorize the PAT "
            f"(github.com -> Settings -> Developer settings -> your token -> Configure SSO); "
            f"{len(rows)} PRs visible without them ({login})"
        )
    return PanelResult(True, "links", rows, f"{len(rows)} awaiting review ({login})")


def _github_sso_blocked_orgs(api, headers):
    """
    Org logins whose SAML SSO blocks this token. GitHub returns the account's
    org memberships regardless, but a direct org-resource request 403s with an
    ``X-GitHub-SSO: required`` header until the token is authorized - the only
    reliable signal, since filtered search responses carry no marker.
    """
    orgs_response = requests.get(f"{api}/user/orgs", headers=headers, timeout=DEFAULT_HTTP_TIMEOUT)
    if orgs_response.status_code != 200:
        return []
    blocked = []
    for org in orgs_response.json():
        probe = requests.get(
            f"{api}/orgs/{org['login']}/repos", params={"per_page": 1}, headers=headers,
            timeout=DEFAULT_HTTP_TIMEOUT,
        )
        if probe.status_code == 403 and probe.headers.get("X-GitHub-SSO", "").startswith("required"):
            blocked.append(org["login"])
    return blocked


def fetch_bitbucket_prs(panel):
    """
    Open PRs listing the app-password's account as a reviewer, across the
    panel's ``repos`` list (or every repo in ``workspace`` when omitted -
    slower, one API call per repo page).
    """
    auth = (resolve_secret(panel, "username_env"), resolve_secret(panel, "app_password_env"))
    user_response = requests.get(f"{BITBUCKET_API}/user", auth=auth, timeout=DEFAULT_HTTP_TIMEOUT)
    if user_response.status_code != 200:
        return PanelResult.error(f"Bitbucket /user returned {user_response.status_code} (bad app password?)")
    uuid = user_response.json()["uuid"]
    workspace = panel["workspace"]
    repos = panel.get("repos") or _bitbucket_workspace_repos(workspace, auth)
    rows = []
    for repo in repos:
        url = f"{BITBUCKET_API}/repositories/{workspace}/{repo}/pullrequests"
        params = {"q": f'state="OPEN" AND reviewers.uuid="{uuid}"', "pagelen": 50}
        response = requests.get(url, params=params, auth=auth, timeout=DEFAULT_HTTP_TIMEOUT)
        if response.status_code != 200:
            return PanelResult.error(f"Bitbucket {workspace}/{repo} returned {response.status_code}")
        for pr in response.json().get("values", []):
            rows.append(
                {
                    "text": f"{repo}#{pr['id']}  {pr['title']}",
                    "url": pr["links"]["html"]["href"],
                    "meta": f"by {pr['author']['display_name']} · updated {_age(pr['updated_on'])} ago",
                }
            )
    return PanelResult(True, "links", rows, f"{len(rows)} awaiting review ({workspace})")


def _bitbucket_workspace_repos(workspace, auth):
    """Every repo slug in the workspace (paged)."""
    repos, url = [], f"{BITBUCKET_API}/repositories/{workspace}?pagelen=100&fields=next,values.slug"
    while url:
        response = requests.get(url, auth=auth, timeout=DEFAULT_HTTP_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        repos += [value["slug"] for value in payload.get("values", [])]
        url = payload.get("next")
    return repos


def fetch_panel(panel, credentials_root, local_hostname=""):
    """Dispatch one panel fetch; never raises - errors come back as PanelResult.error."""
    try:
        if panel["type"] == "ssh_command":
            return fetch_ssh_command(panel, credentials_root, local_hostname)
        if panel["type"] == "github_prs":
            return fetch_github_prs(panel)
        return fetch_bitbucket_prs(panel)
    except Exception as error:  # noqa: BLE001 - a panel must never take the board down
        return PanelResult.error(f"{type(error).__name__}: {error}")


def _age(iso_timestamp):
    """ISO timestamp -> compact age string ("5m", "3h", "2d")."""
    clean = iso_timestamp.replace("Z", "+00:00")
    try:
        seconds = int(time.time() - datetime.fromisoformat(clean).timestamp())
    except ValueError:
        return "?"
    if seconds < 3600:
        return f"{max(seconds, 0) // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


# %%
