#!/usr/bin/env python3
"""Ticket + PR workflow harness shared by company repos.

Stdlib-only on purpose: callable from any repo with a bare ``python3``, no venv or
installed CLIs required. Credentials come from the calling repo's env file:

    python3 ~/GitHub/dotfiles/src/ticket_pr.py --env-file .env create-ticket \
        --project FFF --type Task --summary "Do the thing"

Subcommands: create-ticket, get-ticket, create-pr, pr-status, request-review.
Every subcommand honors the global ``--dry-run`` flag, which prints the HTTP
request(s) it would make and returns canned identifiers instead of touching the
network — use it to exercise calling workflows without creating real tickets/PRs.

Env keys used (values win in the order: real environment, then --env-file files):

    Jira:   JIRA_SERVER (host or URL), JIRA_USER (email), JIRA_TOKEN,
            JIRA_PROJECT (optional default for --project)
    GitHub: GITHUB_TOKEN or GH_TOKEN; falls back to ``gh auth token`` when gh
            is installed and logged in.

The last line of stdout for each subcommand is a single JSON object so calling
agents/scripts can parse results without scraping prose.
"""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

GITHUB_API = "https://api.github.com"
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


def http_json(method, url, headers, payload=None, dry_run=False, timeout=60):
    """One JSON round-trip. In dry-run mode, print the request and return None."""
    if dry_run:
        print(f"[dry-run] {method} {url}")
        if payload is not None:
            print("  " + json.dumps(payload, indent=2).replace("\n", "\n  "))
        return None
    body = json.dumps(payload).encode() if payload is not None else None
    all_headers = {"Content-Type": "application/json", **headers}
    request = urllib.request.Request(url, data=body, method=method, headers=all_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")[:2000]
        raise SystemExit(f"{method} {url} failed: HTTP {err.code}\n{detail}")
    except urllib.error.URLError as err:
        raise SystemExit(f"{method} {url} failed: {err.reason}")
    return json.loads(raw) if raw.strip() else {}


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


def cmd_get_ticket(args):
    base, headers = jira_base(), jira_headers()
    url = f"{base}/rest/api/2/issue/{args.key}?fields=summary,status,assignee,issuetype"
    issue = http_json("GET", url, headers, dry_run=args.dry_run)
    if issue is None:  # dry run
        return
    fields = issue.get("fields", {})
    assignee = (fields.get("assignee") or {}).get("displayName")
    result = {
        "key": issue.get("key", args.key),
        "summary": fields.get("summary"),
        "status": (fields.get("status") or {}).get("name"),
        "type": (fields.get("issuetype") or {}).get("name"),
        "assignee": assignee,
        "url": f"{base}/browse/{issue.get('key', args.key)}",
    }
    emit(f"{result['key']} [{result['status']}] {result['summary']}", result)


# ---------------------------------------------------------------- github


def github_token():
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        token = os.environ.get(var, "")
        if token:
            return token
    gh = shutil.which("gh")
    if gh:
        proc = subprocess.run([gh, "auth", "token"], capture_output=True, text=True)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    raise SystemExit(
        "no GitHub token: set GITHUB_TOKEN in the env file, or install + log in to gh"
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
        return explicit
    url = git_output("remote", "get-url", "origin")
    match = re.search(r"github\.com[:/](.+?)(?:\.git)?/?$", url)
    if not match:
        raise SystemExit(f"cannot parse owner/repo from origin remote: {url}")
    return match.group(1)


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


def cmd_create_pr(args):
    repo = resolve_repo(args.repo)
    headers = github_headers()
    head = args.head or git_output("rev-parse", "--abbrev-ref", "HEAD")
    base = args.base
    if not base:
        if args.dry_run:
            base = "<default-branch>"
        else:
            base = http_json("GET", f"{GITHUB_API}/repos/{repo}", headers)["default_branch"]
    body = args.body or ""
    if args.body_file:
        with open(args.body_file, encoding="utf-8") as handle:
            body = handle.read()
    payload = {"title": args.title, "head": head, "base": base, "body": body, "draft": args.draft}
    response = http_json("POST", f"{GITHUB_API}/repos/{repo}/pulls", headers,
                         payload=payload, dry_run=args.dry_run)
    number = response["number"] if response else 0
    url = response["html_url"] if response else f"https://github.com/{repo}/pull/0"
    emit(f"Created PR #{number}: {url}", {"number": number, "url": url})


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
    """All checks for a commit as [{name, bucket}], newest run per name winning."""
    latest = {}  # name -> (started_at, bucket)
    page = 1
    while True:
        query = urllib.parse.urlencode({"per_page": CHECKS_PER_PAGE, "page": page})
        data = http_json("GET", f"{GITHUB_API}/repos/{repo}/commits/{sha}/check-runs?{query}",
                         headers)
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
    return [{"name": name, "bucket": bucket} for name, (_, bucket) in sorted(latest.items())]


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
    headers = github_headers()
    if args.dry_run:
        print(f"[dry-run] would poll checks for PR #{args.pr or '<current branch>'} in {repo}")
        emit("dry run", {"failed": [], "pending": [], "passed": 0, "skipped": 0,
                         "ignored": [], "green": True, "dry_run": True})
        return
    deadline = time.monotonic() + args.timeout
    while True:
        pull = resolve_pr(repo, headers, args.pr)  # refetched each poll: pushes move the head sha
        entries = collect_check_entries(repo, pull["head"]["sha"], headers)
        report = rollup(entries, args.ignore)
        if not args.wait or report["failed"] or not report["pending"]:
            break
        if time.monotonic() >= deadline:
            report["timed_out"] = True
            break
        print(f"waiting on {len(report['pending'])} check(s): "
              f"{', '.join(report['pending'][:5])} ...", flush=True)
        time.sleep(args.interval)
    report.update({"pr": pull["number"], "url": pull["html_url"]})
    state = "GREEN" if report["green"] else ("FAILED" if report["failed"] else "PENDING")
    emit(f"PR #{pull['number']} checks: {state} "
         f"(pass={report['passed']} fail={len(report['failed'])} "
         f"pending={len(report['pending'])} skip={report['skipped']} "
         f"ignored={len(report['ignored'])})", report)


def cmd_request_review(args):
    repo = resolve_repo(args.repo)
    headers = github_headers()
    pull = None if args.dry_run else resolve_pr(repo, headers, args.pr)
    number = pull["number"] if pull else (args.pr or 0)
    http_json("POST", f"{GITHUB_API}/repos/{repo}/pulls/{number}/requested_reviewers", headers,
              payload={"reviewers": args.reviewer}, dry_run=args.dry_run)
    if args.dry_run:
        return
    refreshed = http_json("GET", f"{GITHUB_API}/repos/{repo}/pulls/{number}", headers)
    logins = [user["login"] for user in refreshed.get("requested_reviewers", [])]
    missing = [login for login in args.reviewer if login not in logins]
    if missing:
        raise SystemExit(f"review request did not stick for: {', '.join(missing)} "
                         f"(currently requested: {logins})")
    emit(f"Requested review on PR #{number} from: {', '.join(logins)}",
         {"number": number, "requested_reviewers": logins})


# ---------------------------------------------------------------- cli


def build_parser():
    parser = argparse.ArgumentParser(
        description="Jira ticket + GitHub PR workflow harness (see module docstring)")
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

    get_ticket = sub.add_parser("get-ticket", help="fetch a Jira ticket's status summary")
    get_ticket.add_argument("--key", required=True, help="issue key, e.g. FFF-401")
    get_ticket.set_defaults(func=cmd_get_ticket)

    create_pr = sub.add_parser("create-pr", help="open a GitHub PR for the current branch")
    create_pr.add_argument("--repo", help="owner/name (default: parsed from origin remote)")
    create_pr.add_argument("--title", required=True)
    create_pr.add_argument("--body", help="PR body text")
    create_pr.add_argument("--body-file", help="file containing the PR body")
    create_pr.add_argument("--head", help="head branch (default: current branch)")
    create_pr.add_argument("--base", help="base branch (default: repo default branch)")
    create_pr.add_argument("--draft", action="store_true")
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

    review = sub.add_parser("request-review", help="request PR reviewers via the REST API")
    review.add_argument("--repo", help="owner/name (default: parsed from origin remote)")
    review.add_argument("--pr", type=int, help="PR number (default: current branch's open PR)")
    review.add_argument("--reviewer", action="append", required=True,
                        help="GitHub login; repeatable")
    review.set_defaults(func=cmd_request_review)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    load_env_files(args.env_file)
    args.func(args)


if __name__ == "__main__":
    main()
