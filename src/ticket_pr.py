#!/usr/bin/env python3
"""Ticket + PR workflow harness shared by company repos.

Stdlib-only on purpose: callable from any repo with a bare ``python3``, no venv or
installed CLIs required. Credentials come from the calling repo's env file:

    python3 ~/GitHub/dotfiles/src/ticket_pr.py --env-file .env create-ticket \
        --project ACME --type Task --summary "Do the thing"

Subcommands: create-ticket, get-ticket, add-comment, create-pr, pr-status,
update-branch, request-review, review-queue, pr-diff, pr-review. get-ticket
returns everything on the ticket in one call (fields, description, every
comment, every attachment downloaded to disk), so a caller never has to go to
the Jira API on its own; add-comment is the way to keep a ticket up to date.
review-queue, pr-diff and pr-review are the reviewer's side: which open PRs
across a set of repos wait on this account, one PR's metadata with its diff on
disk, and the approve / request-changes / comment call. Every subcommand honors
the global ``--dry-run``
flag, which prints the HTTP request(s) it would make and returns canned
identifiers instead of touching the network - use it to exercise calling
workflows without creating real tickets/PRs.

Env keys used (values win in the order: real environment, then --env-file files):

    Jira:   JIRA_SERVER (host or URL), JIRA_USER (email), JIRA_TOKEN,
            JIRA_PROJECT (optional default for --project)
    GitHub: GITHUB_TOKEN_ENV naming the var that holds the PAT (e.g.
            GITHUB_TOKEN_ENV=GH_PAT_ACME - the per-account convention the
            credentials repos use, so each client env file pins its own
            account and two accounts can never be confused), or a direct
            GITHUB_TOKEN / GH_TOKEN. No gh CLI fallback: gh has ONE active
            account, so falling back from a client repo could silently act
            as the wrong one.
    Bitbucket Cloud: BITBUCKET_USER (Atlassian account email) plus
            BITBUCKET_TOKEN_ENV naming the var holding the API token
            (same indirection convention as GitHub), or a direct
            BITBUCKET_TOKEN. Auth is Basic email:token.

The PR provider (GitHub vs Bitbucket Cloud) is detected from the origin
remote's host, so the same subcommands work in any checkout. A "bitbucket:" or
"github:" prefix on --repo pins the provider regardless of the checkout (e.g.
--repo bitbucket:workspace/slug); an unprefixed --repo with no usable origin
remote is assumed to be GitHub.

The last line of stdout for each subcommand is a single JSON object so calling
agents/scripts can parse results without scraping prose.
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

GITHUB_API = "https://api.github.com"
GITHUB_GRAPHQL = "https://api.github.com/graphql"
BITBUCKET_API = "https://api.bitbucket.org/2.0"
CHECKS_PER_PAGE = 100


# ---------------------------------------------------------------- env files


def parse_env_file(path):
    """Parse a simple KEY=VALUE dotenv file (comments, blanks, export, quotes)."""
    env = {}
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
                val = val[1:-1]
            if key:
                env[key] = val
    return env


def load_env_files(paths):
    """Load env files into os.environ without overriding already-set variables."""
    for path in paths:
        if not os.path.isfile(path):
            raise SystemExit(f"env file not found: {path}")
        for key, val in parse_env_file(path).items():
            os.environ.setdefault(key, val)


def require_env(*names):
    values = [os.environ.get(name, "") for name in names]
    missing = [name for name, val in zip(names, values) if not val]
    if missing:
        raise SystemExit(
            f"missing required env var(s): {', '.join(missing)} "
            "(set them in the environment or pass --env-file)"
        )
    return values if len(values) > 1 else values[0]


# ---------------------------------------------------------------- http core


def http_json(method, url, headers, payload=None, dry_run=False, timeout=60, tolerate=()):
    """
    One JSON round-trip. In dry-run mode, print the request and return None.
    HTTP status codes listed in ``tolerate`` return None instead of exiting
    (for endpoints a token may legitimately be unable to reach).
    """
    if dry_run:
        print(f"[dry-run] {method} {url}")
        if payload is not None:
            print("  " + json.dumps(payload, indent=2).replace("\n", "\n  "))
        return None
    body = json.dumps(payload).encode() if payload is not None else None
    # No content type on a bodiless call: Bitbucket 400s an empty POST (approve,
    # request-changes) that claims to carry JSON.
    all_headers = {"Content-Type": "application/json", **headers} if body is not None else dict(headers)
    request = urllib.request.Request(url, data=body, method=method, headers=all_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as err:
        if err.code in tolerate:
            return None
        detail = err.read().decode(errors="replace")[:2000]
        raise SystemExit(f"{method} {url} failed: HTTP {err.code}\n{detail}")
    except urllib.error.URLError as err:
        raise SystemExit(f"{method} {url} failed: {err.reason}")
    return json.loads(raw) if raw.strip() else {}


def http_bytes(url, headers, timeout=120):
    """Raw GET for a file (an attachment); Jira redirects to its file store."""
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as err:
        raise SystemExit(f"GET {url} failed: HTTP {err.code}")
    except urllib.error.URLError as err:
        raise SystemExit(f"GET {url} failed: {err.reason}")


def body_text(args):
    """The --body-file contents when given, else the --body text."""
    if args.body_file:
        with open(args.body_file, encoding="utf-8") as handle:
            return handle.read()
    return args.body or ""


def emit(human, result):
    """Print a human-readable line, then the machine-readable JSON result last."""
    print(human)
    print(json.dumps(result))


# ---------------------------------------------------------------- jira


def jira_base():
    server = require_env("JIRA_SERVER")
    if not server.startswith(("http://", "https://")):
        server = "https://" + server
    return server.rstrip("/")


def jira_headers():
    user, token = require_env("JIRA_USER", "JIRA_TOKEN")
    encoded = base64.b64encode(f"{user}:{token}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def jira_find_user(base, headers, query):
    """Return an assignee field dict for Cloud (accountId) or Server (name)."""
    for param in ("query", "username"):  # Cloud uses query=, Server uses username=
        url = f"{base}/rest/api/2/user/search?" + urllib.parse.urlencode({param: query})
        try:
            users = http_json("GET", url, headers)
        except SystemExit:
            continue
        if users:
            user = users[0]
            if user.get("accountId"):
                return {"accountId": user["accountId"]}
            if user.get("name"):
                return {"name": user["name"]}
    return None


def cmd_create_ticket(args):
    base, headers = jira_base(), jira_headers()
    project = args.project or os.environ.get("JIRA_PROJECT", "")
    if not project:
        raise SystemExit("no Jira project: pass --project or set JIRA_PROJECT")
    fields = {
        "project": {"key": project},
        "issuetype": {"name": args.type},
        "summary": args.summary,
        "description": args.description,
    }
    if args.label:
        fields["labels"] = args.label
    assignee = args.assignee if args.assignee is not None else os.environ.get("JIRA_USER", "")
    if assignee and assignee.lower() != "none":
        if args.dry_run:
            print(f"[dry-run] would look up assignee {assignee!r} via /rest/api/2/user/search")
        else:
            field = jira_find_user(base, headers, assignee)
            if field is None:
                print(f"WARNING: no Jira user matched {assignee!r}; leaving ticket unassigned")
            else:
                fields["assignee"] = field
    response = http_json("POST", f"{base}/rest/api/2/issue", headers,
                         payload={"fields": fields}, dry_run=args.dry_run)
    key = response["key"] if response else "DRY-0"
    url = f"{base}/browse/{key}"
    emit(f"Created {key}: {url}", {"key": key, "url": url})


JIRA_TICKET_FIELDS = ("summary,status,issuetype,priority,assignee,reporter,labels,"
                      "created,updated,parent,description,attachment")


def cmd_get_ticket(args):
    """
    Everything on the ticket in one call: the fields, the description, every
    comment and every attachment (downloaded, local paths in the result).
    Comment images are issue attachments that the comment body only names, so
    the attachment list is how a caller sees what a comment shows.
    """
    base, headers = jira_base(), jira_headers()
    url = f"{base}/rest/api/2/issue/{args.key}?fields={JIRA_TICKET_FIELDS}"
    issue = http_json("GET", url, headers, dry_run=args.dry_run)
    if issue is None:  # dry run
        return
    fields = issue.get("fields", {})
    key = issue.get("key", args.key)
    directory = args.attachments_dir or os.path.join(tempfile.gettempdir(), "ticket_pr", key)
    result = {
        "key": key,
        "summary": fields.get("summary"),
        "status": (fields.get("status") or {}).get("name"),
        "type": (fields.get("issuetype") or {}).get("name"),
        "priority": (fields.get("priority") or {}).get("name"),
        "assignee": (fields.get("assignee") or {}).get("displayName"),
        "reporter": (fields.get("reporter") or {}).get("displayName"),
        "labels": fields.get("labels") or [],
        "created": fields.get("created"),
        "updated": fields.get("updated"),
        "parent": (fields.get("parent") or {}).get("key"),
        "description": fields.get("description") or "",
        "comments": jira_comments(base, headers, key),
        "attachments": jira_attachments(headers, fields.get("attachment") or [], directory),
        "url": f"{base}/browse/{key}",
    }
    saved = ""
    if result["attachments"]:
        saved = f", {len(result['attachments'])} attachments in {directory}"
    emit(
        f"{result['key']} [{result['status']}] {result['summary']} "
        f"({len(result['comments'])} comments{saved})",
        result,
    )


def jira_attachments(headers, attachments, directory):
    """Download every attachment into ``directory`` and describe each with its local path."""
    saved = []
    if attachments:
        os.makedirs(directory, exist_ok=True)
    for attachment in attachments:
        path = os.path.join(directory, attachment["filename"])
        with open(path, "wb") as handle:
            handle.write(http_bytes(attachment["content"], headers))
        saved.append({
            "filename": attachment["filename"],
            "author": (attachment.get("author") or {}).get("displayName"),
            "created": attachment.get("created"),
            "mime_type": attachment.get("mimeType"),
            "size": attachment.get("size"),
            "path": path,
        })
    return saved


def cmd_add_comment(args):
    """Post a comment (Jira wiki markup) so the ticket stays current from the thread."""
    base, headers = jira_base(), jira_headers()
    body = body_text(args)
    if not body.strip():
        raise SystemExit("empty comment: pass --body or --body-file")
    response = http_json("POST", f"{base}/rest/api/2/issue/{args.key}/comment", headers,
                         payload={"body": body}, dry_run=args.dry_run)
    comment_id = response["id"] if response else "0"
    url = f"{base}/browse/{args.key}?focusedCommentId={comment_id}"
    emit(f"Commented on {args.key}: {url}", {"key": args.key, "id": comment_id, "url": url})


def jira_comments(base, headers, key, page_size=100):
    """
    Every comment on the issue, oldest first. The comment endpoint is paged
    (Jira caps a page well below "all of them" on busy tickets), so walk
    startAt until total is reached rather than trusting one response.
    """
    comments, start = [], 0
    while True:
        query = urllib.parse.urlencode({"startAt": start, "maxResults": page_size})
        page = http_json("GET", f"{base}/rest/api/2/issue/{key}/comment?{query}", headers)
        batch = page.get("comments", [])
        for comment in batch:
            comments.append({
                "author": (comment.get("author") or {}).get("displayName"),
                "created": comment.get("created"),
                "body": comment.get("body") or "",
            })
        start += len(batch)
        if not batch or start >= page.get("total", 0):
            return comments


# ---------------------------------------------------------------- github


def github_token():
    """
    The PAT for THIS repo's GitHub account. GITHUB_TOKEN_ENV (set in the
    calling repo's env file) names the variable holding the token, so each
    client env file pins its own account's PAT by name; GITHUB_TOKEN/GH_TOKEN
    still work directly. Deliberately no ``gh auth token`` fallback - gh has
    one active account, and a silent fallback from a client repo could create
    PRs or request reviews as the wrong identity.
    """
    indirect = os.environ.get("GITHUB_TOKEN_ENV", "")
    if indirect:
        token = os.environ.get(indirect, "")
        if not token:
            raise SystemExit(f"GITHUB_TOKEN_ENV names {indirect!r}, which is empty or unset")
        return token
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        token = os.environ.get(var, "")
        if token:
            return token
    raise SystemExit(
        "no GitHub token: set GITHUB_TOKEN_ENV=<var naming the PAT> "
        "(or GITHUB_TOKEN directly) in the env file"
    )


def github_headers():
    return {
        "Authorization": f"Bearer {github_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def git_output(*cmd):
    proc = subprocess.run(["git", *cmd], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(cmd)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def resolve_repo(explicit):
    """owner/name from --repo, else from the current directory's origin remote."""
    if explicit:
        return explicit.partition(":")[2] if explicit.startswith(("bitbucket:", "github:")) else explicit
    url = git_output("remote", "get-url", "origin")
    match = re.search(r"(?:github\.com|bitbucket\.org)[:/](.+?)(?:\.git)?/?$", url)
    if not match:
        raise SystemExit(f"cannot parse owner/repo from origin remote: {url}")
    return match.group(1)


def resolve_provider(explicit):
    """'github' or 'bitbucket', from --repo's prefix else the origin remote host."""
    if explicit and explicit.startswith("bitbucket:"):
        return "bitbucket"
    if explicit and explicit.startswith("github:"):
        return "github"
    try:
        url = git_output("remote", "get-url", "origin")
    except SystemExit:
        return "github"
    return "bitbucket" if "bitbucket.org" in url else "github"


def resolve_pr(repo, headers, number):
    """Fetch the PR by number, or find the open PR for the current branch."""
    if number:
        return http_json("GET", f"{GITHUB_API}/repos/{repo}/pulls/{number}", headers)
    branch = git_output("rev-parse", "--abbrev-ref", "HEAD")
    owner = repo.split("/")[0]
    query = urllib.parse.urlencode({"head": f"{owner}:{branch}", "state": "open"})
    pulls = http_json("GET", f"{GITHUB_API}/repos/{repo}/pulls?{query}", headers)
    if not pulls:
        raise SystemExit(f"no open PR found for branch {branch!r} in {repo}")
    return pulls[0]


# ---------------------------------------------------------------- bitbucket


def bitbucket_token():
    """
    The API token for THIS repo's Bitbucket workspace. Same indirection
    convention as GitHub: BITBUCKET_TOKEN_ENV (set in the calling repo's env
    file) names the variable holding the token so each client env file pins
    its own account; BITBUCKET_TOKEN still works directly.
    """
    indirect = os.environ.get("BITBUCKET_TOKEN_ENV", "")
    if indirect:
        token = os.environ.get(indirect, "")
        if not token:
            raise SystemExit(f"BITBUCKET_TOKEN_ENV names {indirect!r}, which is empty or unset")
        return token
    token = os.environ.get("BITBUCKET_TOKEN", "")
    if token:
        return token
    raise SystemExit(
        "no Bitbucket token: set BITBUCKET_TOKEN_ENV=<var naming the API token> "
        "(or BITBUCKET_TOKEN directly) in the env file"
    )


def bitbucket_headers():
    user = require_env("BITBUCKET_USER")
    encoded = base64.b64encode(f"{user}:{bitbucket_token()}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def bb_paginate(url, headers):
    """Yield every item from a Bitbucket paged collection (follows .next)."""
    while url:
        data = http_json("GET", url, headers)
        yield from data.get("values", [])
        url = data.get("next")


def bb_resolve_pr(repo, headers, number):
    """Fetch the Bitbucket PR by id, or find the open PR for the current branch."""
    base_url = f"{BITBUCKET_API}/repositories/{repo}/pullrequests"
    if number:
        return http_json("GET", f"{base_url}/{number}", headers)
    branch = git_output("rev-parse", "--abbrev-ref", "HEAD")
    query = urllib.parse.urlencode({"q": f'source.branch.name = "{branch}" AND state = "OPEN"'})
    pulls = list(bb_paginate(f"{base_url}?{query}", headers))
    if not pulls:
        raise SystemExit(f"no open PR found for branch {branch!r} in {repo}")
    return pulls[0]


def bb_pr_url(pull, repo):
    return (pull.get("links", {}).get("html", {}) or {}).get(
        "href", f"https://bitbucket.org/{repo}/pull-requests/{pull.get('id', 0)}")


def bucket_bitbucket_status(status):
    state = (status.get("state") or "").upper()
    if state == "SUCCESSFUL":
        return "pass"
    if state == "INPROGRESS":
        return "pending"
    if state == "STOPPED":
        return "skip"
    return "fail"  # FAILED / ERROR


def cmd_create_pr(args):
    repo = resolve_repo(args.repo)
    head = args.head or git_output("rev-parse", "--abbrev-ref", "HEAD")
    body = body_text(args)

    if resolve_provider(args.repo) == "bitbucket":
        if args.label:
            print("WARNING: --label is ignored on Bitbucket (PRs have no label API)",
                  file=sys.stderr)
        headers = bitbucket_headers()
        base = args.base
        if not base:
            if args.dry_run:
                base = "<default-branch>"
            else:
                base = http_json("GET", f"{BITBUCKET_API}/repositories/{repo}",
                                 headers)["mainbranch"]["name"]
        payload = {
            "title": args.title,
            "description": body,
            "source": {"branch": {"name": head}},
            "destination": {"branch": {"name": base}},
            "draft": args.draft,
        }
        response = http_json("POST", f"{BITBUCKET_API}/repositories/{repo}/pullrequests",
                             headers, payload=payload, dry_run=args.dry_run)
        number = response["id"] if response else 0
        url = bb_pr_url(response or {}, repo)
        emit(f"Created {'draft ' if args.draft else ''}PR #{number}: {url}",
             {"number": number, "url": url, "draft": args.draft})
        return

    headers = github_headers()
    base = args.base
    if not base:
        if args.dry_run:
            base = "<default-branch>"
        else:
            base = http_json("GET", f"{GITHUB_API}/repos/{repo}", headers)["default_branch"]
    payload = {"title": args.title, "head": head, "base": base, "body": body, "draft": args.draft}
    response = http_json("POST", f"{GITHUB_API}/repos/{repo}/pulls", headers,
                         payload=payload, dry_run=args.dry_run)
    number = response["number"] if response else 0
    url = response["html_url"] if response else f"https://github.com/{repo}/pull/0"
    if args.label:
        # Labels live on the issues endpoint; add them after the PR exists.
        http_json("POST", f"{GITHUB_API}/repos/{repo}/issues/{number}/labels", headers,
                  payload={"labels": args.label}, dry_run=args.dry_run)
    emit(f"Created {'draft ' if args.draft else ''}PR #{number}: {url}",
         {"number": number, "url": url, "labels": args.label, "draft": args.draft})


def bucket_check_run(run):
    if run.get("status") != "completed":
        return "pending"
    conclusion = (run.get("conclusion") or "").lower()
    if conclusion in ("success", "neutral"):
        return "pass"
    if conclusion in ("skipped", "cancelled"):
        return "skip"
    return "fail"  # failure, timed_out, action_required, startup_failure, stale


def bucket_commit_status(status):
    state = (status.get("state") or "").lower()
    if state == "success":
        return "pass"
    if state == "pending":
        return "pending"
    return "fail"  # failure, error


def collect_check_entries(repo, sha, headers):
    """
    All checks for a commit as ([{name, bucket}], check_runs_visible).

    check_runs_visible is False when the check-runs API 403s: fine-grained
    PATs cannot be granted the Checks permission AT ALL (a GitHub limitation -
    it briefly existed and was pulled; only GitHub Apps get it), so with such
    a token only legacy commit statuses are reported and callers must surface
    that the Actions-based checks are invisible rather than implying green.
    """
    latest = {}  # name -> (started_at, bucket)
    page = 1
    check_runs_visible = True
    while True:
        query = urllib.parse.urlencode({"per_page": CHECKS_PER_PAGE, "page": page})
        data = http_json("GET", f"{GITHUB_API}/repos/{repo}/commits/{sha}/check-runs?{query}",
                         headers, tolerate=(403,))
        if data is None:
            check_runs_visible = False
            break
        runs = data.get("check_runs", [])
        for run in runs:
            name = run.get("name") or "<unnamed>"
            stamp = run.get("started_at") or ""
            if name not in latest or stamp >= latest[name][0]:
                latest[name] = (stamp, bucket_check_run(run))
        if len(runs) < CHECKS_PER_PAGE:
            break
        page += 1
    combined = http_json("GET", f"{GITHUB_API}/repos/{repo}/commits/{sha}/status", headers)
    for status in combined.get("statuses", []):  # already latest-per-context
        name = status.get("context") or "<unnamed>"
        latest[name] = ("", bucket_commit_status(status))
    entries = [{"name": name, "bucket": bucket} for name, (_, bucket) in sorted(latest.items())]
    return entries, check_runs_visible


def rollup(entries, ignore_substrings):
    """Pure rollup of [{name, bucket}] into a green/failed/pending report."""
    ignored, failed, pending = [], [], []
    passed = skipped = 0
    for entry in entries:
        name, bucket = entry["name"], entry["bucket"]
        if any(sub.lower() in name.lower() for sub in ignore_substrings):
            ignored.append({"name": name, "bucket": bucket})
        elif bucket == "fail":
            failed.append(name)
        elif bucket == "pending":
            pending.append(name)
        elif bucket == "pass":
            passed += 1
        else:
            skipped += 1
    return {
        "failed": failed,
        "pending": pending,
        "passed": passed,
        "skipped": skipped,
        "ignored": ignored,
        "green": not failed and not pending,
    }


def cmd_pr_status(args):
    repo = resolve_repo(args.repo)
    provider = resolve_provider(args.repo)
    if args.dry_run:
        print(f"[dry-run] would poll checks for PR #{args.pr or '<current branch>'} in {repo}")
        emit("dry run", {"failed": [], "pending": [], "passed": 0, "skipped": 0,
                         "ignored": [], "green": True, "dry_run": True})
        return
    headers = bitbucket_headers() if provider == "bitbucket" else github_headers()
    deadline = time.monotonic() + args.timeout
    while True:
        # refetched each poll: pushes move the head sha
        if provider == "bitbucket":
            pull = bb_resolve_pr(repo, headers, args.pr)
            sha = pull["source"]["commit"]["hash"]
            statuses = bb_paginate(
                f"{BITBUCKET_API}/repositories/{repo}/commit/{sha}/statuses", headers)
            entries = sorted(
                ({"name": s.get("key") or s.get("name") or "<unnamed>",
                  "bucket": bucket_bitbucket_status(s)} for s in statuses),
                key=lambda e: e["name"])
            check_runs_visible = True  # one status system; nothing hidden by token type
        else:
            pull = resolve_pr(repo, headers, args.pr)
            entries, check_runs_visible = collect_check_entries(repo, pull["head"]["sha"], headers)
        report = rollup(entries, args.ignore)
        report["check_runs_visible"] = check_runs_visible
        if not args.wait or report["failed"] or not report["pending"]:
            break
        if time.monotonic() >= deadline:
            report["timed_out"] = True
            break
        print(f"waiting on {len(report['pending'])} check(s): "
              f"{', '.join(report['pending'][:5])} ...", flush=True)
        time.sleep(args.interval)
    if provider == "bitbucket":
        report.update({"pr": pull["id"], "url": bb_pr_url(pull, repo)})
    else:
        report.update({"pr": pull["number"], "url": pull["html_url"]})
    state = "GREEN" if report["green"] else ("FAILED" if report["failed"] else "PENDING")
    if not report["check_runs_visible"]:
        print("WARNING: check runs (GitHub Actions) are NOT visible to this token - "
              "fine-grained PATs cannot be granted the Checks permission (GitHub limitation); "
              "this report covers legacy commit statuses only")
    emit(f"PR #{report['pr']} checks: {state} "
         f"(pass={report['passed']} fail={len(report['failed'])} "
         f"pending={len(report['pending'])} skip={report['skipped']} "
         f"ignored={len(report['ignored'])})", report)


def cmd_update_branch(args):
    """
    Merge the base branch into the PR's head branch server-side, clearing
    GitHub's "This branch is out-of-date with the base branch" state.

    Server-side on purpose: the local checkout may be dirty or on another
    branch, and a local merge would need a clean tree plus a push. GitHub does
    the merge commit itself, which also means the caller never resolves
    conflicts by accident -- a conflicting update returns 422 and is reported as
    such so a human can do the merge deliberately.
    """
    repo = resolve_repo(args.repo)
    if resolve_provider(args.repo) == "bitbucket":
        raise SystemExit("update-branch is GitHub-only; Bitbucket has no equivalent endpoint")
    headers = github_headers()
    if args.dry_run:
        print(f"[dry-run] would update PR #{args.pr or '<current branch>'} in {repo} from its base")
        emit("dry run", {"updated": False, "dry_run": True})
        return
    pull = resolve_pr(repo, headers, args.pr)
    number, base = pull["number"], pull["base"]["ref"]
    # Compare base..head: "behind_by" is how many base commits the branch lacks.
    comparison = http_json(
        "GET", f"{GITHUB_API}/repos/{repo}/compare/{base}...{pull['head']['sha']}", headers)
    behind = (comparison or {}).get("behind_by", 0)
    if not behind:
        emit(f"PR #{number} is already up to date with {base}",
             {"pr": number, "base": base, "behind_by": 0, "updated": False,
              "url": pull["html_url"]})
        return
    # 422 = the merge would conflict, or the branch moved since the sha we sent.
    result = http_json(
        "PUT", f"{GITHUB_API}/repos/{repo}/pulls/{number}/update-branch", headers,
        payload={"expected_head_sha": pull["head"]["sha"]}, tolerate=(422,))
    if result is None:
        raise SystemExit(
            f"PR #{number} is {behind} commit(s) behind {base} and GitHub refused the update "
            f"(HTTP 422). Usually a merge conflict, sometimes a concurrent push. Merge {base} "
            f"into the branch by hand, resolve, and push.")
    emit(f"PR #{number} updated from {base} (was {behind} commit(s) behind) - "
         f"this pushes a merge commit, so CI will re-run",
         {"pr": number, "base": base, "behind_by": behind, "updated": True,
          "message": result.get("message"), "url": pull["html_url"]})


def bb_find_member(workspace, headers, query):
    """Match a workspace member by nickname or display name (case-insensitive)."""
    wanted = query.lower()
    for member in bb_paginate(f"{BITBUCKET_API}/workspaces/{workspace}/members", headers):
        user = member.get("user", {})
        names = {(user.get("nickname") or "").lower(), (user.get("display_name") or "").lower()}
        if wanted in names:
            return user
    return None


def cmd_request_review(args):
    repo = resolve_repo(args.repo)
    if resolve_provider(args.repo) == "bitbucket":
        headers = bitbucket_headers()
        pull = None if args.dry_run else bb_resolve_pr(repo, headers, args.pr)
        number = pull["id"] if pull else (args.pr or 0)
        workspace = repo.split("/")[0]
        reviewers = [] if args.dry_run else [
            {"account_id": r["account_id"]} for r in pull.get("reviewers", [])
            if r.get("account_id")
        ]
        for name in args.reviewer:
            if args.dry_run:
                print(f"[dry-run] would look up workspace member {name!r}")
                continue
            user = bb_find_member(workspace, headers, name)
            if user is None or not user.get("account_id"):
                raise SystemExit(f"no Bitbucket workspace member matched {name!r}")
            entry = {"account_id": user["account_id"]}
            if entry not in reviewers:
                reviewers.append(entry)
        # Requesting review means the PR is done cooking - clear the draft flag
        # in the same PUT that sets the reviewers.
        was_draft = bool(pull and pull.get("draft"))
        payload = {"title": pull["title"] if pull else "<title>", "reviewers": reviewers,
                   "draft": False}
        http_json("PUT", f"{BITBUCKET_API}/repositories/{repo}/pullrequests/{number}",
                  headers, payload=payload, dry_run=args.dry_run)
        if args.dry_run:
            return
        refreshed = http_json("GET", f"{BITBUCKET_API}/repositories/{repo}/pullrequests/{number}",
                              headers)
        if refreshed.get("draft"):
            raise SystemExit(f"PR #{number} is still marked draft after the update")
        names = [r.get("display_name") or r.get("nickname") or "?"
                 for r in refreshed.get("reviewers", [])]
        ready_note = " (marked ready for review)" if was_draft else ""
        emit(f"Requested review on PR #{number} from: {', '.join(names)}{ready_note}",
             {"number": number, "requested_reviewers": names, "marked_ready": was_draft})
        return

    headers = github_headers()
    pull = None if args.dry_run else resolve_pr(repo, headers, args.pr)
    number = pull["number"] if pull else (args.pr or 0)
    # Requesting review means the PR is done cooking - clear the draft flag
    # first. REST cannot un-draft a PR; only the GraphQL mutation can.
    was_draft = bool(pull and pull.get("draft"))
    if args.dry_run:
        print(f"[dry-run] would mark PR #{number} ready for review if still a draft")
    elif was_draft:
        mutation = ("mutation($id: ID!) { markPullRequestReadyForReview("
                    "input: {pullRequestId: $id}) { pullRequest { isDraft } } }")
        result = http_json("POST", GITHUB_GRAPHQL, headers,
                           payload={"query": mutation,
                                    "variables": {"id": pull["node_id"]}})
        if result.get("errors"):
            raise SystemExit(f"failed to mark PR #{number} ready for review: "
                             f"{result['errors']}")
    http_json("POST", f"{GITHUB_API}/repos/{repo}/pulls/{number}/requested_reviewers", headers,
              payload={"reviewers": args.reviewer}, dry_run=args.dry_run)
    if args.dry_run:
        return
    refreshed = http_json("GET", f"{GITHUB_API}/repos/{repo}/pulls/{number}", headers)
    if refreshed.get("draft"):
        raise SystemExit(f"PR #{number} is still marked draft after the ready-for-review mutation")
    logins = [user["login"] for user in refreshed.get("requested_reviewers", [])]
    missing = [login for login in args.reviewer if login not in logins]
    if missing:
        raise SystemExit(f"review request did not stick for: {', '.join(missing)} "
                         f"(currently requested: {logins})")
    ready_note = " (marked ready for review)" if was_draft else ""
    emit(f"Requested review on PR #{number} from: {', '.join(logins)}{ready_note}",
         {"number": number, "requested_reviewers": logins, "marked_ready": was_draft})


# ---------------------------------------------------------------- review


BB_QUEUE_FIELDS = "%2Bvalues.reviewers,%2Bvalues.participants,%2Bvalues.draft"
DRAFT_TITLE = re.compile(r"^\s*(\[WIP\]|WIP\b|Draft:)", re.IGNORECASE)
REVIEW_EVENTS = {"approve": "APPROVE", "request-changes": "REQUEST_CHANGES", "comment": "COMMENT"}


def repo_spec(spec):
    """(provider, owner/name) for one --repo value."""
    return resolve_provider(spec), resolve_repo(spec)


def queue_skip(own, draft, requested, approved_current):
    """Why a PR is not waiting on this account's review, or None when it is."""
    if own:
        return "own"
    if draft:
        return "draft"
    if not requested:
        return "not_requesting"
    if approved_current:
        return "approved"
    return None


def github_queue(repo, headers, me):
    """
    Open PRs in a GitHub repo. Submitting a review drops the reviewer from
    requested_reviewers, so being listed there means the PR is waiting.
    """
    query = urllib.parse.urlencode({"state": "open", "per_page": 100})
    entries = []
    for pull in http_json("GET", f"{GITHUB_API}/repos/{repo}/pulls?{query}", headers):
        author = pull["user"]["login"]
        requested = me in [user["login"] for user in pull.get("requested_reviewers", [])]
        draft = bool(pull.get("draft"))
        entries.append({
            "provider": "github", "repo": repo, "pr": pull["number"], "title": pull["title"],
            "author": author, "source": pull["head"]["ref"], "destination": pull["base"]["ref"],
            "url": pull["html_url"], "draft": draft, "review_requested": requested,
            "my_state": None, "commits_since_my_approval": None,
            "skip": queue_skip(author == me, draft, requested, False),
        })
    return entries


def bitbucket_queue(repo, headers, me):
    """
    Open PRs in a Bitbucket repo. Bitbucket keeps an approver in reviewers for
    good, so an approval only settles a PR until its source branch moves: count
    the commits dated after it, parsed, since the two stamps carry different
    UTC offsets.
    """
    base_url = f"{BITBUCKET_API}/repositories/{repo}/pullrequests"
    entries = []
    for pull in bb_paginate(f"{base_url}?state=OPEN&pagelen=50&fields={BB_QUEUE_FIELDS}", headers):
        author = pull.get("author") or {}
        mine = next((p for p in pull.get("participants", [])
                     if (p.get("user") or {}).get("uuid") == me), {})
        state = mine.get("state")
        since = None
        if state == "approved":
            approved_at = datetime.fromisoformat(mine["participated_on"])
            commits = http_json("GET", f"{base_url}/{pull['id']}/commits?pagelen=50&fields=values.date",
                                headers)
            since = sum(datetime.fromisoformat(c["date"]) > approved_at for c in commits.get("values", []))
        draft = bool(pull.get("draft") or DRAFT_TITLE.match(pull["title"]))
        requested = me in [r.get("uuid") for r in pull.get("reviewers", [])]
        entries.append({
            "provider": "bitbucket", "repo": repo, "pr": pull["id"], "title": pull["title"],
            "author": author.get("display_name"), "source": pull["source"]["branch"]["name"],
            "destination": pull["destination"]["branch"]["name"],
            "url": bb_pr_url(pull, repo), "draft": draft, "review_requested": requested,
            "my_state": state, "commits_since_my_approval": since,
            "skip": queue_skip(author.get("uuid") == me, draft, requested, state == "approved" and not since),
        })
    return entries


def cmd_review_queue(args):
    """
    Every open PR across the given repos, each with ``skip`` naming why it is
    not waiting on this account's review (own, not_requesting, draft, approved)
    or null when it is. The account is whoever the token belongs to, looked up
    once per provider.
    """
    specs = [repo_spec(spec) for spec in args.repo or [None]]
    if args.dry_run:
        for provider, repo in specs:
            print(f"[dry-run] would list open PRs in {provider}:{repo}")
        emit("dry run", {"prs": [], "skipped": {}, "dry_run": True})
        return
    accounts, prs = {}, []
    for provider, repo in specs:
        if provider == "bitbucket":
            headers = bitbucket_headers()
            if provider not in accounts:
                accounts[provider] = http_json("GET", f"{BITBUCKET_API}/user", headers)["uuid"]
            prs += bitbucket_queue(repo, headers, accounts[provider])
        else:
            headers = github_headers()
            if provider not in accounts:
                accounts[provider] = http_json("GET", f"{GITHUB_API}/user", headers)["login"]
            prs += github_queue(repo, headers, accounts[provider])
    skipped = {}
    for pr in prs:
        if pr["skip"]:
            skipped[pr["skip"]] = skipped.get(pr["skip"], 0) + 1
            continue
        since = pr["commits_since_my_approval"]
        note = f" (re-review: {since} commit(s) since your approval)" if since else ""
        print(f"{pr['url']} {pr['title']}{note}")
    waiting = sum(not pr["skip"] for pr in prs)
    counts = ", ".join(f"{n} {reason}" for reason, n in skipped.items()) or "none"
    emit(f"{waiting} awaiting review; skipped {sum(skipped.values())}: {counts}",
         {"prs": prs, "skipped": skipped})


def github_pr_files(repo, number, headers):
    files, page = [], 1
    while True:
        query = urllib.parse.urlencode({"per_page": 100, "page": page})
        batch = http_json("GET", f"{GITHUB_API}/repos/{repo}/pulls/{number}/files?{query}", headers)
        files += [{"path": f["filename"], "status": f["status"],
                   "previous_path": f.get("previous_filename"),
                   "additions": f["additions"], "deletions": f["deletions"]} for f in batch]
        if len(batch) < 100:
            return files
        page += 1


def cmd_pr_diff(args):
    """
    One PR's metadata and per-file line counts, with the full unified diff
    written to disk, so a reviewer never goes to the API on its own.
    """
    provider, repo = repo_spec(args.repo)
    path = args.out or os.path.join(tempfile.gettempdir(), "ticket_pr",
                                    f"{repo.replace('/', '_')}_{args.pr}.diff")
    if args.dry_run:
        print(f"[dry-run] would fetch PR #{args.pr} in {provider}:{repo} and write its diff to {path}")
        emit("dry run", {"pr": args.pr, "diff_path": path, "dry_run": True})
        return
    if provider == "bitbucket":
        headers = bitbucket_headers()
        base_url = f"{BITBUCKET_API}/repositories/{repo}/pullrequests/{args.pr}"
        pull = http_json("GET", base_url, headers)
        # diff and diffstat 302 to a signed URL; urllib follows it with the auth header
        diff = http_bytes(f"{base_url}/diff", headers)
        files = [{"path": (s.get("new") or s.get("old") or {}).get("path"), "status": s.get("status"),
                  "previous_path": (s.get("old") or {}).get("path") if s.get("status") == "renamed" else None,
                  "additions": s.get("lines_added"), "deletions": s.get("lines_removed")}
                 for s in bb_paginate(f"{base_url}/diffstat", headers)]
        result = {
            "pr": pull["id"], "title": pull["title"],
            "author": (pull.get("author") or {}).get("display_name"),
            "source": pull["source"]["branch"]["name"],
            "destination": pull["destination"]["branch"]["name"],
            "head": pull["source"]["commit"]["hash"], "description": pull.get("description") or "",
            "url": bb_pr_url(pull, repo),
        }
    else:
        headers = github_headers()
        base_url = f"{GITHUB_API}/repos/{repo}/pulls/{args.pr}"
        pull = http_json("GET", base_url, headers)
        diff = http_bytes(base_url, {**headers, "Accept": "application/vnd.github.diff"})
        files = github_pr_files(repo, args.pr, headers)
        result = {
            "pr": pull["number"], "title": pull["title"], "author": pull["user"]["login"],
            "source": pull["head"]["ref"], "destination": pull["base"]["ref"],
            "head": pull["head"]["sha"], "description": pull.get("body") or "", "url": pull["html_url"],
        }
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(diff)
    result.update({"files": files, "diff_path": path})
    emit(f"PR #{result['pr']} {result['title']}: {len(files)} files, diff in {path}", result)


def cmd_pr_review(args):
    """
    Approve, request changes on, or comment on a PR. GitHub takes all three as
    one review. Bitbucket has no review object: the body goes up as a PR
    comment and the vote is its own bodiless POST, sent after the comment so
    the author sees the reason with it.
    """
    provider, repo = repo_spec(args.repo)
    body = body_text(args).strip()
    if not body and (args.action == "comment" or (provider == "github" and args.action == "request-changes")):
        raise SystemExit(f"empty review body: {args.action} needs --body or --body-file")
    if provider == "bitbucket":
        headers = bitbucket_headers()
        base_url = f"{BITBUCKET_API}/repositories/{repo}/pullrequests/{args.pr}"
        comment_id = None
        if body:
            response = http_json("POST", f"{base_url}/comments", headers,
                                 payload={"content": {"raw": body}}, dry_run=args.dry_run)
            comment_id = response["id"] if response else 0
        state = "commented"
        if args.action != "comment":
            response = http_json("POST", f"{base_url}/{args.action}", headers, dry_run=args.dry_run)
            state = response.get("state") if response else args.action
        url = f"https://bitbucket.org/{repo}/pull-requests/{args.pr}"
        emit(f"PR #{args.pr} {args.action}: {state} {url}",
             {"pr": args.pr, "action": args.action, "state": state, "comment_id": comment_id, "url": url})
        return
    headers = github_headers()
    payload = {"event": REVIEW_EVENTS[args.action]}
    if body:
        payload["body"] = body
    response = http_json("POST", f"{GITHUB_API}/repos/{repo}/pulls/{args.pr}/reviews", headers,
                         payload=payload, dry_run=args.dry_run)
    state = response["state"] if response else REVIEW_EVENTS[args.action]
    url = response["html_url"] if response else f"https://github.com/{repo}/pull/{args.pr}"
    emit(f"PR #{args.pr} {args.action}: {state} {url}",
         {"pr": args.pr, "action": args.action, "state": state, "url": url})


# ---------------------------------------------------------------- cli


def build_parser():
    parser = argparse.ArgumentParser(
        description="Jira ticket + GitHub/Bitbucket PR workflow harness (see module docstring)")
    parser.add_argument("--env-file", action="append", default=[],
                        help="dotenv file(s) to load; repeatable; real env vars win")
    parser.add_argument("--dry-run", action="store_true",
                        help="print requests instead of sending them; return canned ids")
    sub = parser.add_subparsers(dest="command", required=True)

    ticket = sub.add_parser("create-ticket", help="create a Jira ticket, print its key + URL")
    ticket.add_argument("--project", help="Jira project key (default: JIRA_PROJECT env)")
    ticket.add_argument("--type", default="Task", help="issue type name (default: Task)")
    ticket.add_argument("--summary", required=True)
    ticket.add_argument("--description", default="")
    ticket.add_argument("--assignee",
                        help="email/name to assign (default: JIRA_USER; 'none' to skip)")
    ticket.add_argument("--label", action="append", default=[], help="label; repeatable")
    ticket.set_defaults(func=cmd_create_ticket)

    get_ticket = sub.add_parser(
        "get-ticket",
        help="fetch everything on a Jira ticket: fields, description, comments, attachments")
    get_ticket.add_argument("--key", required=True, help="issue key, e.g. ACME-401")
    get_ticket.add_argument("--attachments-dir",
                            help="where attachments are saved (default: <tmp>/ticket_pr/<KEY>)")
    get_ticket.set_defaults(func=cmd_get_ticket)

    comment = sub.add_parser("add-comment", help="post a comment on a Jira ticket")
    comment.add_argument("--key", required=True, help="issue key, e.g. ACME-401")
    comment.add_argument("--body", help="comment text (Jira wiki markup)")
    comment.add_argument("--body-file", help="file containing the comment text")
    comment.set_defaults(func=cmd_add_comment)

    create_pr = sub.add_parser("create-pr", help="open a GitHub PR for the current branch")
    create_pr.add_argument("--repo", help="owner/name (default: parsed from origin remote)")
    create_pr.add_argument("--title", required=True)
    create_pr.add_argument("--body", help="PR body text")
    create_pr.add_argument("--body-file", help="file containing the PR body")
    create_pr.add_argument("--head", help="head branch (default: current branch)")
    create_pr.add_argument("--base", help="base branch (default: repo default branch)")
    create_pr.add_argument("--draft", action="store_true", default=True,
                           help="open as a draft PR (the default)")
    create_pr.add_argument("--no-draft", dest="draft", action="store_false",
                           help="open ready for review instead of as a draft")
    create_pr.add_argument("--label", action="append", default=[],
                           help="PR label to add after creation; repeatable (GitHub only)")
    create_pr.set_defaults(func=cmd_create_pr)

    status = sub.add_parser("pr-status", help="bucket a PR's checks into a green/failed report")
    status.add_argument("--repo", help="owner/name (default: parsed from origin remote)")
    status.add_argument("--pr", type=int, help="PR number (default: current branch's open PR)")
    status.add_argument("--ignore", action="append", default=[],
                        help="ignore checks whose name contains this substring; repeatable "
                             "(e.g. --ignore approval for human-approval gates)")
    status.add_argument("--wait", action="store_true",
                        help="poll until no checks are pending (returns early on any failure)")
    status.add_argument("--interval", type=int, default=90, help="poll interval seconds")
    status.add_argument("--timeout", type=int, default=3600, help="max wait seconds")
    status.set_defaults(func=cmd_pr_status)

    update = sub.add_parser("update-branch",
                            help="merge the base branch into the PR branch (GitHub only)")
    update.add_argument("--repo", help="owner/name (default: parsed from origin remote)")
    update.add_argument("--pr", type=int, help="PR number (default: current branch's open PR)")
    update.set_defaults(func=cmd_update_branch)

    review = sub.add_parser("request-review", help="request PR reviewers via the REST API")
    review.add_argument("--repo", help="owner/name (default: parsed from origin remote)")
    review.add_argument("--pr", type=int, help="PR number (default: current branch's open PR)")
    review.add_argument("--reviewer", action="append", required=True,
                        help="GitHub login / Bitbucket nickname or display name; repeatable")
    review.set_defaults(func=cmd_request_review)

    queue = sub.add_parser("review-queue",
                           help="open PRs across repos, each marked with whether it waits on this account")
    queue.add_argument("--repo", action="append",
                       help="github:owner/name or bitbucket:workspace/slug; repeatable "
                            "(default: parsed from origin remote)")
    queue.set_defaults(func=cmd_review_queue)

    pr_diff = sub.add_parser("pr-diff", help="a PR's metadata and file stats, with its full diff on disk")
    pr_diff.add_argument("--repo", help="owner/name (default: parsed from origin remote)")
    pr_diff.add_argument("--pr", type=int, required=True, help="PR number")
    pr_diff.add_argument("--out", help="diff path (default: <tmp>/ticket_pr/<owner>_<name>_<pr>.diff)")
    pr_diff.set_defaults(func=cmd_pr_diff)

    pr_review = sub.add_parser("pr-review", help="approve, request changes on, or comment on a PR")
    pr_review.add_argument("--repo", help="owner/name (default: parsed from origin remote)")
    pr_review.add_argument("--pr", type=int, required=True, help="PR number")
    pr_review.add_argument("--action", required=True, choices=sorted(REVIEW_EVENTS))
    pr_review.add_argument("--body", help="review text, posted as the author will read it")
    pr_review.add_argument("--body-file", help="file containing the review text")
    pr_review.set_defaults(func=cmd_pr_review)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    load_env_files(args.env_file)
    args.func(args)


if __name__ == "__main__":
    main()
