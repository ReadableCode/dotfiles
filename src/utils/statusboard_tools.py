# %%
# Imports #

import json
import os
import re
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
    if panel.get("log_link"):
        _validate_log_link(panel, config_path)


def _validate_log_link(panel, config_path):
    """
    ``log_link`` makes an ssh_command panel's output rows clickable: ``pattern``
    is a regex whose first capture group pulls a job token out of each output
    line, and ``command`` is the remote command (with ``{job}`` substituted)
    the TUI streams in a follow pane when the row is clicked.
    """
    prefix = f"Statusboard panel '{panel['name']}' in {config_path}"
    if panel["type"] != "ssh_command":
        raise ValueError(f"{prefix}: log_link is only supported on ssh_command panels")
    log_link = panel["log_link"]
    if not isinstance(log_link, dict) or not log_link.get("pattern") or not log_link.get("command"):
        raise ValueError(f"{prefix}: log_link must be a mapping with 'pattern' and 'command' keys")
    try:
        compiled = re.compile(log_link["pattern"])
    except re.error as error:
        raise ValueError(f"{prefix}: log_link pattern does not compile: {error}")
    if compiled.groups < 1:
        raise ValueError(f"{prefix}: log_link pattern needs a capture group (the job token)")
    if "{job}" not in log_link["command"]:
        raise ValueError(f"{prefix}: log_link command must contain a {{job}} placeholder")


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


def build_ssh_argv(panel, credentials_root, local_hostname="", command=None):
    """
    Build the full ssh argv for an ssh_command panel, resolving ``host`` and
    the optional ``jump`` hop from the host inventories. ``command`` overrides
    the panel's own command (same host/hop chain) - used by the log-follow
    pane to stream a tail over the connection the panel already defines.

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
    argv += [ssh_destination(target), command or panel["command"]]
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
    """
    Every open PR the token's account is waiting on or waited for, across all
    repos the token can see (search-wide - no per-repo config): PRs whose
    review is requested, PRs already reviewed (badged "waiting on author" when
    the account's latest review requested changes and nothing was pushed
    since), and the account's own open PRs with their aggregate review status.
    """
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
    def search(qualifiers):
        query = f"is:open is:pr archived:false {qualifiers} {panel.get('search', '')}".strip()
        response = requests.get(
            f"{api}/search/issues",
            params={"q": query, "sort": "updated", "per_page": 50},
            headers=headers,
            timeout=DEFAULT_HTTP_TIMEOUT,
        )
        if response.status_code != 200:
            raise ValueError(f"GitHub search returned {response.status_code}: {response.text[:200]}")
        return response.json().get("items", [])

    requested = search(f"review-requested:{login}")
    reviewed = search(f"reviewed-by:{login} -author:{login}")
    mine = search(f"author:{login}")
    review_states, review_commits = {}, {}
    for item in {i["html_url"]: i for i in requested + reviewed + mine}.values():
        states, commits = _pr_review_states(api, headers, item)
        review_states[item["html_url"]] = states
        review_commits[item["html_url"]] = commits
    # Two signals unstick a changes-requested PR, probed with one PR-detail
    # call each (only for that subset, to keep the extra API calls rare):
    # appearing in requested_reviewers again means the author explicitly
    # re-requested me (submitting a review clears me from that list, and a
    # team request matches the search but not the list); a head sha that
    # moved past the sha my review was submitted against means the author
    # pushed since - GitHub keeps my blocking review active across pushes,
    # so without this the PR would sit at "you requested changes" forever.
    rerequested, updated_since = set(), set()
    requested_urls = {i["html_url"] for i in requested}
    for item in {i["html_url"]: i for i in requested + reviewed}.values():
        url = item["html_url"]
        if review_states.get(url, {}).get(login) != "CHANGES_REQUESTED":
            continue
        repo = item["repository_url"].split("/repos/", 1)[-1]
        response = requests.get(
            f"{api}/repos/{repo}/pulls/{item['number']}", headers=headers, timeout=DEFAULT_HTTP_TIMEOUT
        )
        if response.status_code != 200:
            continue
        detail = response.json()
        reviewers = [user.get("login") for user in detail.get("requested_reviewers", [])]
        head_sha = (detail.get("head") or {}).get("sha")
        reviewed_sha = review_commits.get(url, {}).get(login)
        if url in requested_urls and login in reviewers:
            rerequested.add(url)
        elif head_sha and reviewed_sha and head_sha != reviewed_sha:
            updated_since.add(url)
    rows, summary = classify_github_prs(
        login, requested, reviewed, mine, review_states, rerequested, updated_since
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
    return PanelResult(True, "links", rows, f"{summary} ({login})")


def _pr_review_states(api, headers, item):
    """
    Latest submitted review state per reviewer login for one search item
    (chronological walk, so later reviews overwrite earlier ones; a DISMISSED
    review resets that reviewer to no active state). Returns
    (states, commit_ids): commit_ids maps each active reviewer to the head
    sha their latest review was submitted against, so callers can tell
    whether the branch has moved since.
    """
    repo = item["repository_url"].split("/repos/", 1)[-1]
    response = requests.get(
        f"{api}/repos/{repo}/pulls/{item['number']}/reviews",
        params={"per_page": 100},
        headers=headers,
        timeout=DEFAULT_HTTP_TIMEOUT,
    )
    if response.status_code != 200:
        return {}, {}
    states: dict = {}
    commits: dict = {}
    for review in response.json():
        user = (review.get("user") or {}).get("login")
        state = review.get("state")
        # PENDING = the caller's own unsubmitted draft (the API never shows
        # anyone else's) - kept so the board can flag it: the author cannot
        # see a draft, so it reads as "no review yet" to everyone else.
        if not user or state not in ("APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED", "PENDING"):
            continue
        states[user] = None if state == "DISMISSED" else state
        commits[user] = review.get("commit_id")
    active = {user: state for user, state in states.items() if state}
    return active, {user: commits.get(user) for user in active}


def classify_github_prs(login, requested, reviewed, mine, review_states, rerequested=frozenset(),
                        updated_since=frozenset()):
    """
    Turn the three searches into ordered, badged link rows. Returns
    (rows, summary). ``rerequested`` is the set of PR urls where I appear in
    requested_reviewers DESPITE having a changes-requested review - only an
    explicit re-request by the author puts me back there, so those PRs return
    to "needs my review". ``updated_since`` is the set of PR urls whose head
    moved past the sha my changes-requested review was submitted against -
    the author pushed something (maybe an unrelated merge, but a second look
    beats never seeing it again), so those also return to "needs my review";
    an explicit re-request wins when both signals are present. Buckets, in
    display order:

    - my UNSUBMITTED draft review (state PENDING): flagged loudest - a draft
      is invisible to the author, so until I hit "Submit review" nobody knows
      I responded and everyone is waiting on everyone;
    - "changes requested" by me, not re-requested (a team-level request
      matches the search without putting me back personally) and nothing
      pushed since: waiting on the AUTHOR, not on me;
    - review requested and I have not blocked it - including re-requests
      and new pushes after my changes-requested review, marked so I know
      it's round two;
    - reviewed with only a comment and no pending request: soft state, shown
      so it isn't forgotten;
    - my own open PRs, with the aggregate verdict of everyone else's reviews;
    - DRAFT PRs - anyone's, mine included - greyed at the very bottom:
      parked on purpose, nothing for anyone to approve yet.

    Approved-by-me PRs with no new request are dropped - nothing is waited on.
    """
    drafts, need, waiting, commented, own, parked = [], [], [], [], [], []
    seen = set()
    for item in requested + reviewed:
        if item["html_url"] in seen:
            continue
        seen.add(item["html_url"])
        if item.get("draft"):
            parked.append(_github_row(item, "◌", "dim", "draft · parked, nothing to approve", dim=True))
            continue
        my_state = review_states.get(item["html_url"], {}).get(login)
        is_requested = any(i["html_url"] == item["html_url"] for i in requested)
        if my_state == "PENDING":
            drafts.append(_github_row(item, "✏", "bold red", "UNSUBMITTED draft review - the author can't see it"))
        elif my_state == "CHANGES_REQUESTED" and item["html_url"] in rerequested:
            need.append(_github_row(item, "●", "bold cyan", "re-requested after your changes"))
        elif my_state == "CHANGES_REQUESTED" and item["html_url"] in updated_since:
            need.append(_github_row(item, "●", "bold cyan", "updated since your changes - re-review?"))
        elif my_state == "CHANGES_REQUESTED":
            waiting.append(_github_row(item, "✋", "bold yellow", "you requested changes"))
        elif is_requested:
            need.append(_github_row(item, "●", "bold cyan", None))
        elif my_state == "COMMENTED":
            commented.append(_github_row(item, "💬", "dim", "you commented"))
    for item in mine:
        if item.get("draft"):
            parked.append(_github_row(item, "◌", "dim", "your draft · parked, nothing to approve", dim=True))
            continue
        others = {u: s for u, s in review_states.get(item["html_url"], {}).items() if u != login}
        own.append(_github_row(item, "⬆", "bold magenta", f"your PR · {_own_pr_verdict(others)}"))
    rows = drafts + need + waiting + commented + own + parked
    summary = f"{len(need)} to review · {len(waiting)} on author · {len(own)} yours"
    if drafts:
        summary = f"{len(drafts)} UNSUBMITTED · {summary}"
    if parked:
        summary += f" · {len(parked)} parked"
    return rows, summary


def _own_pr_verdict(others):
    """Aggregate verdict of everyone else's reviews on one of my own PRs."""
    if "CHANGES_REQUESTED" in others.values():
        return "✗ changes requested"
    if "APPROVED" in others.values():
        return "✓ approved"
    return "⧗ awaiting review"


def _github_row(item, badge, badge_style, note, dim=False):
    repo = item["repository_url"].split("/repos/", 1)[-1]
    meta = f"by {item['user']['login']} · updated {_age(item['updated_at'])} ago"
    if note:
        meta += f" · {note}"
    return {
        "badge": badge,
        "badge_style": badge_style,
        "text": f"{repo}#{item['number']}  {item['title']}",
        "url": item["html_url"],
        "meta": meta,
        "dim": dim,
    }


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
    Open PRs that involve the app-password's account - either as a reviewer or
    as the AUTHOR (the github_prs panel shows both, so this one must too) -
    across the panel's ``repos`` list (or every repo in ``workspace`` when
    omitted - slower, one API call per repo page).

    ``participants`` is not in the list endpoint's default serialization, so
    it is requested explicitly; without it every PR would read as "awaiting
    review" regardless of who already approved.
    """
    auth = (resolve_secret(panel, "username_env"), resolve_secret(panel, "app_password_env"))
    user_response = requests.get(f"{BITBUCKET_API}/user", auth=auth, timeout=DEFAULT_HTTP_TIMEOUT)
    if user_response.status_code != 200:
        return PanelResult.error(f"Bitbucket /user returned {user_response.status_code} (bad app password?)")
    uuid = user_response.json()["uuid"]
    workspace = panel["workspace"]
    repos = panel.get("repos") or _bitbucket_workspace_repos(workspace, auth)
    found = []
    for repo in repos:
        url = f"{BITBUCKET_API}/repositories/{workspace}/{repo}/pullrequests"
        params = {
            "q": f'state="OPEN" AND (reviewers.uuid="{uuid}" OR author.uuid="{uuid}")',
            "pagelen": 50,
            "fields": "+values.participants,+values.draft",
        }
        response = requests.get(url, params=params, auth=auth, timeout=DEFAULT_HTTP_TIMEOUT)
        if response.status_code != 200:
            return PanelResult.error(f"Bitbucket {workspace}/{repo} returned {response.status_code}")
        found += [(repo, pr) for pr in response.json().get("values", [])]
    rows, summary = classify_bitbucket_prs(uuid, found)
    return PanelResult(True, "links", rows, f"{summary} ({workspace})")


def classify_bitbucket_prs(uuid, found):
    """
    Turn (repo_slug, pr) pairs into ordered, badged link rows - the Bitbucket
    counterpart of classify_github_prs, using the same badges so both panels
    read the same way. Buckets, in display order:

    - review requested and I have not voted: needs my review;
    - I requested changes: waiting on the AUTHOR, not on me;
    - my own open PRs, with the aggregate verdict of everyone else's votes;
    - draft PRs - anyone's, mine included - greyed at the bottom.

    PRs I already approved are dropped (nothing is waited on). Bitbucket has
    no "commented" participant state, so there is no equivalent of the GitHub
    💬 bucket, and no unsubmitted-draft-review state to flag.
    """
    need, waiting, own, parked = [], [], [], []
    for repo, pr in found:
        author_uuid = (pr.get("author") or {}).get("uuid")
        participants = pr.get("participants") or []
        mine = author_uuid == uuid
        if pr.get("draft"):
            note = "your draft · parked, nothing to approve" if mine else "draft · parked, nothing to approve"
            parked.append(_bitbucket_row(repo, pr, "◌", "dim", note, dim=True))
            continue
        if mine:
            others = [p for p in participants if (p.get("user") or {}).get("uuid") != uuid]
            own.append(_bitbucket_row(repo, pr, "⬆", "bold magenta", f"your PR · {_bitbucket_verdict(others)}"))
            continue
        my_state = next(
            (p.get("state") for p in participants if (p.get("user") or {}).get("uuid") == uuid), None
        )
        if my_state == "approved":
            continue
        if my_state == "changes_requested":
            waiting.append(_bitbucket_row(repo, pr, "✋", "bold yellow", "you requested changes"))
        else:
            need.append(_bitbucket_row(repo, pr, "●", "bold cyan", None))
    rows = need + waiting + own + parked
    summary = f"{len(need)} to review · {len(waiting)} on author · {len(own)} yours"
    if parked:
        summary += f" · {len(parked)} parked"
    return rows, summary


def _bitbucket_verdict(others):
    """Aggregate verdict of everyone else's votes on one of my own PRs."""
    states = [participant.get("state") for participant in others]
    if "changes_requested" in states:
        return "✗ changes requested"
    if "approved" in states:
        return "✓ approved"
    return "⧗ awaiting review"


def _bitbucket_row(repo, pr, badge, badge_style, note, dim=False):
    meta = f"by {pr['author']['display_name']} · updated {_age(pr['updated_on'])} ago"
    if note:
        meta += f" · {note}"
    return {
        "badge": badge,
        "badge_style": badge_style,
        "text": f"{repo}#{pr['id']}  {pr['title']}",
        "url": pr["links"]["html"]["href"],
        "meta": meta,
        "dim": dim,
    }


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
