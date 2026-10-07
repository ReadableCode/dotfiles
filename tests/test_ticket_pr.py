"""Unit tests for src/ticket_pr.py — no network, no credentials."""

import json
import re
import urllib.parse

import pytest

from src import ticket_pr

# ---------------------------------------------------------------- env files


def test_parse_env_file(tmp_path):
    env_file = tmp_path / "test.env"
    env_file.write_text(
        "# comment\n"
        "\n"
        "PLAIN=value\n"
        "export EXPORTED=yes\n"
        'QUOTED="with spaces"\n'
        "SINGLE='single'\n"
        "EQUALS=a=b=c\n"
        "not a kv line\n"
    )
    parsed = ticket_pr.parse_env_file(str(env_file))
    assert parsed == {
        "PLAIN": "value",
        "EXPORTED": "yes",
        "QUOTED": "with spaces",
        "SINGLE": "single",
        "EQUALS": "a=b=c",
    }


def test_load_env_files_does_not_override_real_env(tmp_path, monkeypatch):
    env_file = tmp_path / "test.env"
    env_file.write_text("TICKET_PR_TEST_A=from_file\nTICKET_PR_TEST_B=from_file\n")
    monkeypatch.setenv("TICKET_PR_TEST_A", "from_env")
    monkeypatch.delenv("TICKET_PR_TEST_B", raising=False)
    ticket_pr.load_env_files([str(env_file)])
    import os

    assert os.environ["TICKET_PR_TEST_A"] == "from_env"
    assert os.environ["TICKET_PR_TEST_B"] == "from_file"


def test_load_env_files_missing_file():
    with pytest.raises(SystemExit):
        ticket_pr.load_env_files(["/nonexistent/path.env"])


# ---------------------------------------------------------------- github auth


def test_github_token_prefers_env_var(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tok_env")
    assert ticket_pr.github_token() == "tok_env"


def test_github_token_env_indirection(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN_ENV", "GH_PAT_ACME")
    monkeypatch.setenv("GH_PAT_ACME", "tok_acme")
    assert ticket_pr.github_token() == "tok_acme"


def test_github_token_env_indirection_beats_direct_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tok_wrong_account")
    monkeypatch.setenv("GITHUB_TOKEN_ENV", "GH_PAT_ACME")
    monkeypatch.setenv("GH_PAT_ACME", "tok_acme")
    assert ticket_pr.github_token() == "tok_acme"


def test_github_token_env_indirection_unset_target_errors(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN_ENV", "GH_PAT_ACME")
    monkeypatch.delenv("GH_PAT_ACME", raising=False)
    with pytest.raises(SystemExit, match="GH_PAT_ACME"):
        ticket_pr.github_token()


def test_github_token_errors_when_nothing_available(monkeypatch):
    for var in ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN_ENV"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(SystemExit):
        ticket_pr.github_token()


# ---------------------------------------------------------------- repo parsing


@pytest.mark.parametrize(
    "url",
    [
        "git@github.com:owner/name.git",
        "https://github.com/owner/name.git",
        "https://github.com/owner/name",
        "ssh://git@github.com/owner/name.git",
    ],
)
def test_resolve_repo_parses_origin_urls(monkeypatch, url):
    monkeypatch.setattr(ticket_pr, "git_output", lambda *a: url)
    assert ticket_pr.resolve_repo(None) == "owner/name"


def test_resolve_repo_explicit_wins(monkeypatch):
    monkeypatch.setattr(ticket_pr, "git_output", lambda *a: pytest.fail("should not call git"))
    assert ticket_pr.resolve_repo("owner/name") == "owner/name"


@pytest.mark.parametrize(
    "url",
    [
        "git@bitbucket.org:workspace/slug.git",
        "https://bitbucket.org/workspace/slug.git",
        "https://bitbucket.org/workspace/slug",
    ],
)
def test_resolve_repo_parses_bitbucket_urls(monkeypatch, url):
    monkeypatch.setattr(ticket_pr, "git_output", lambda *a: url)
    assert ticket_pr.resolve_repo(None) == "workspace/slug"


def test_resolve_provider_from_origin(monkeypatch):
    monkeypatch.setattr(ticket_pr, "git_output", lambda *a: "git@bitbucket.org:ws/slug.git")
    assert ticket_pr.resolve_provider(None) == "bitbucket"
    monkeypatch.setattr(ticket_pr, "git_output", lambda *a: "git@github.com:owner/name.git")
    assert ticket_pr.resolve_provider(None) == "github"


def test_resolve_provider_bitbucket_prefix(monkeypatch):
    monkeypatch.setattr(ticket_pr, "git_output", lambda *a: pytest.fail("should not call git"))
    assert ticket_pr.resolve_provider("bitbucket:ws/slug") == "bitbucket"
    assert ticket_pr.resolve_repo("bitbucket:ws/slug") == "ws/slug"


def test_bitbucket_token_env_indirection(monkeypatch):
    monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)
    monkeypatch.setenv("BITBUCKET_TOKEN_ENV", "BB_TOKEN_ACME")
    monkeypatch.setenv("BB_TOKEN_ACME", "sekrit")
    assert ticket_pr.bitbucket_token() == "sekrit"


def test_bitbucket_token_indirection_unset_target_errors(monkeypatch):
    monkeypatch.setenv("BITBUCKET_TOKEN_ENV", "BB_TOKEN_ACME")
    monkeypatch.delenv("BB_TOKEN_ACME", raising=False)
    with pytest.raises(SystemExit):
        ticket_pr.bitbucket_token()


def test_bucket_bitbucket_status():
    assert ticket_pr.bucket_bitbucket_status({"state": "SUCCESSFUL"}) == "pass"
    assert ticket_pr.bucket_bitbucket_status({"state": "INPROGRESS"}) == "pending"
    assert ticket_pr.bucket_bitbucket_status({"state": "STOPPED"}) == "skip"
    assert ticket_pr.bucket_bitbucket_status({"state": "FAILED"}) == "fail"
    assert ticket_pr.bucket_bitbucket_status({}) == "fail"


# ---------------------------------------------------------------- check bucketing


def test_bucket_check_run():
    assert ticket_pr.bucket_check_run({"status": "in_progress"}) == "pending"
    assert ticket_pr.bucket_check_run({"status": "queued"}) == "pending"
    ok = {"status": "completed", "conclusion": "success"}
    assert ticket_pr.bucket_check_run(ok) == "pass"
    assert ticket_pr.bucket_check_run({**ok, "conclusion": "neutral"}) == "pass"
    assert ticket_pr.bucket_check_run({**ok, "conclusion": "skipped"}) == "skip"
    assert ticket_pr.bucket_check_run({**ok, "conclusion": "cancelled"}) == "skip"
    assert ticket_pr.bucket_check_run({**ok, "conclusion": "failure"}) == "fail"
    assert ticket_pr.bucket_check_run({**ok, "conclusion": "timed_out"}) == "fail"
    assert ticket_pr.bucket_check_run({**ok, "conclusion": "action_required"}) == "fail"


def test_bucket_commit_status():
    assert ticket_pr.bucket_commit_status({"state": "success"}) == "pass"
    assert ticket_pr.bucket_commit_status({"state": "pending"}) == "pending"
    assert ticket_pr.bucket_commit_status({"state": "failure"}) == "fail"
    assert ticket_pr.bucket_commit_status({"state": "error"}) == "fail"


def test_rollup_ignores_approval_gate_and_reports_green():
    entries = [
        {"name": "linter", "bucket": "pass"},
        {"name": "Mergeable: HelloTech approval", "bucket": "pending"},
        {"name": "Preview Environment / deploy", "bucket": "skip"},
        {"name": "pr-docker-push", "bucket": "pass"},
    ]
    report = ticket_pr.rollup(entries, ["approval"])
    assert report["green"] is True
    assert report["failed"] == []
    assert report["pending"] == []
    assert report["passed"] == 2
    assert report["skipped"] == 1
    assert report["ignored"] == [{"name": "Mergeable: HelloTech approval", "bucket": "pending"}]


def test_rollup_carries_a_failed_checks_details():
    entries = [
        {
            "name": "SonarQube Code Analysis",
            "bucket": "fail",
            "details": {"details_url": "https://sonar/x", "title": "Quality Gate failed", "summary": "2 new issues"},
        },
        {"name": "linter", "bucket": "pass", "details": {"details_url": None}},
    ]
    report = ticket_pr.rollup(entries, [])
    assert report["failed"] == ["SonarQube Code Analysis"]
    assert report["failed_details"] == [
        {
            "name": "SonarQube Code Analysis",
            "details_url": "https://sonar/x",
            "title": "Quality Gate failed",
            "summary": "2 new issues",
        }
    ]


def test_check_run_details_reads_output_and_link():
    run = {"details_url": "https://ci/run/1", "output": {"title": "t", "summary": "s"}}
    assert ticket_pr.check_run_details(run) == {"details_url": "https://ci/run/1", "title": "t", "summary": "s"}
    assert ticket_pr.check_run_details({}) == {"details_url": None, "title": None, "summary": None}


def test_rollup_not_green_on_failure_or_pending():
    failing = ticket_pr.rollup([{"name": "linter", "bucket": "fail"}], [])
    assert failing["green"] is False and failing["failed"] == ["linter"]
    pending = ticket_pr.rollup([{"name": "wiz", "bucket": "pending"}], [])
    assert pending["green"] is False and pending["pending"] == ["wiz"]


# ---------------------------------------------------------------- dry run (no network)


def _run_cli(argv, monkeypatch, capsys):
    monkeypatch.setattr(
        ticket_pr.urllib.request,
        "urlopen",
        lambda *a, **k: pytest.fail("dry-run must not touch the network"),
    )
    ticket_pr.main(argv)
    return capsys.readouterr().out


def test_create_ticket_dry_run(monkeypatch, capsys):
    monkeypatch.setenv("JIRA_SERVER", "example.atlassian.net")
    monkeypatch.setenv("JIRA_USER", "user@example.com")
    monkeypatch.setenv("JIRA_TOKEN", "token")
    out = _run_cli(
        ["--dry-run", "create-ticket", "--project", "ACME", "--summary", "Test ticket"],
        monkeypatch,
        capsys,
    )
    assert "[dry-run] POST https://example.atlassian.net/rest/api/2/issue" in out
    result = json.loads(out.strip().splitlines()[-1])
    assert result == {"key": "DRY-0", "url": "https://example.atlassian.net/browse/DRY-0"}


def test_get_ticket_dry_run_requests_description(monkeypatch, capsys):
    monkeypatch.setenv("JIRA_SERVER", "example.atlassian.net")
    monkeypatch.setenv("JIRA_USER", "user@example.com")
    monkeypatch.setenv("JIRA_TOKEN", "token")
    out = _run_cli(["--dry-run", "get-ticket", "--key", "ACME-401"], monkeypatch, capsys)
    assert (
        "[dry-run] GET https://example.atlassian.net/rest/api/2/issue/ACME-401"
        "?fields=summary,status,issuetype,priority,assignee,reporter,labels,"
        "created,updated,parent,description,attachment"
    ) in out


def test_get_ticket_reports_everything(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("JIRA_SERVER", "example.atlassian.net")
    monkeypatch.setenv("JIRA_USER", "user@example.com")
    monkeypatch.setenv("JIRA_TOKEN", "token")
    issue = {
        "key": "ACME-401",
        "fields": {
            "summary": "Fix the thing",
            "status": {"name": "In Progress"},
            "issuetype": {"name": "Bug"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "Sam"},
            "reporter": {"displayName": "Alex"},
            "labels": ["mec"],
            "created": "2026-08-30T09:00:00.000+0000",
            "updated": "2026-09-02T10:00:00.000+0000",
            "parent": {"key": "ACME-400"},
            "description": "Steps:\n1. run it\n2. watch it break",
            "attachment": [
                {
                    "filename": "layout.png",
                    "mimeType": "image/png",
                    "size": 3,
                    "created": "2026-09-02T10:00:00.000+0000",
                    "author": {"displayName": "Sam"},
                    "content": "https://example.atlassian.net/rest/api/3/attachment/content/1",
                }
            ],
        },
    }
    # two pages of one comment each: the walker must follow startAt to total
    pages = {
        "startAt=0": {
            "total": 2,
            "comments": [
                {"author": {"displayName": "Alex"}, "created": "2026-09-01T10:00:00.000+0000", "body": "Repro attached"}
            ],
        },
        "startAt=1": {
            "total": 2,
            "comments": [
                {"author": {"displayName": "Sam"}, "created": "2026-09-02T10:00:00.000+0000", "body": "On it"}
            ],
        },
    }
    calls = []

    def fake_http(method, url, headers, **kwargs):
        calls.append(url)
        if "/comment?" in url:
            return next(page for marker, page in pages.items() if marker in url)
        return issue

    monkeypatch.setattr(ticket_pr, "http_json", fake_http)
    monkeypatch.setattr(ticket_pr, "http_bytes", lambda url, headers: b"png")
    ticket_pr.main(["get-ticket", "--key", "ACME-401", "--attachments-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert out.splitlines()[0] == (f"ACME-401 [In Progress] Fix the thing (2 comments, 1 attachments in {tmp_path})")
    result = json.loads(out.strip().splitlines()[-1])
    saved = tmp_path / "layout.png"
    assert saved.read_bytes() == b"png"
    assert result == {
        "key": "ACME-401",
        "summary": "Fix the thing",
        "status": "In Progress",
        "type": "Bug",
        "priority": "High",
        "assignee": "Sam",
        "reporter": "Alex",
        "labels": ["mec"],
        "created": "2026-08-30T09:00:00.000+0000",
        "updated": "2026-09-02T10:00:00.000+0000",
        "parent": "ACME-400",
        "description": "Steps:\n1. run it\n2. watch it break",
        "comments": [
            {"author": "Alex", "created": "2026-09-01T10:00:00.000+0000", "body": "Repro attached"},
            {"author": "Sam", "created": "2026-09-02T10:00:00.000+0000", "body": "On it"},
        ],
        "attachments": [
            {
                "filename": "layout.png",
                "author": "Sam",
                "created": "2026-09-02T10:00:00.000+0000",
                "mime_type": "image/png",
                "size": 3,
                "path": str(saved),
            }
        ],
        "url": "https://example.atlassian.net/browse/ACME-401",
    }
    assert sum("/comment?" in c for c in calls) == 2


def test_search_tickets_dry_run_hits_the_cloud_search_endpoint(monkeypatch, capsys):
    monkeypatch.setenv("JIRA_SERVER", "example.atlassian.net")
    monkeypatch.setenv("JIRA_USER", "user@example.com")
    monkeypatch.setenv("JIRA_TOKEN", "token")
    out = _run_cli(
        ["--dry-run", "search-tickets", "--jql", 'project = ACME AND text ~ "thing"', "--max-results", "5"],
        monkeypatch,
        capsys,
    )
    assert (
        "[dry-run] GET https://example.atlassian.net/rest/api/3/search/jql"
        "?jql=project+%3D+ACME+AND+text+~+%22thing%22"
        "&fields=summary%2Cstatus%2Cissuetype%2Cassignee%2Ccreated%2Cupdated"
        "&maxResults=5"
    ) in out


def test_search_tickets_lists_hits_and_ends_with_json(monkeypatch, capsys):
    monkeypatch.setenv("JIRA_SERVER", "example.atlassian.net")
    monkeypatch.setenv("JIRA_USER", "user@example.com")
    monkeypatch.setenv("JIRA_TOKEN", "token")
    found = {
        "issues": [
            {
                "key": "ACME-7",
                "fields": {
                    "summary": "Pod cannot reach Vault",
                    "status": {"name": "Open"},
                    "issuetype": {"name": "Bug"},
                    "assignee": {"displayName": "Sam"},
                    "created": "2026-09-09T10:00:00.000+0000",
                    "updated": "2026-09-10T10:00:00.000+0000",
                },
            },
            {"key": "ACME-3", "fields": {"summary": "Older", "status": {"name": "Done"}}},
        ]
    }
    monkeypatch.setattr(ticket_pr, "http_json", lambda m, url, *a, **k: found)
    ticket_pr.main(["search-tickets", "--jql", "project = ACME"])
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "2 ticket(s) for: project = ACME"
    assert out.splitlines()[1] == "  ACME-7 [Open] Pod cannot reach Vault"
    result = json.loads(out.strip().splitlines()[-1])
    assert result["jql"] == "project = ACME"
    assert result["tickets"][0] == {
        "key": "ACME-7",
        "summary": "Pod cannot reach Vault",
        "status": "Open",
        "type": "Bug",
        "assignee": "Sam",
        "created": "2026-09-09T10:00:00.000+0000",
        "updated": "2026-09-10T10:00:00.000+0000",
        "url": "https://example.atlassian.net/browse/ACME-7",
    }
    assert result["tickets"][1]["assignee"] is None


def _jira_env(monkeypatch):
    monkeypatch.setenv("JIRA_SERVER", "example.atlassian.net")
    monkeypatch.setenv("JIRA_USER", "user@example.com")
    monkeypatch.setenv("JIRA_TOKEN", "token")


def test_transition_ticket_dry_run_reads_then_posts(monkeypatch, capsys):
    _jira_env(monkeypatch)
    out = _run_cli(["--dry-run", "transition-ticket", "--key", "ACME-401", "--to", "Done"], monkeypatch, capsys)
    assert (
        "[dry-run] GET https://example.atlassian.net/rest/api/2/issue/ACME-401/transitions?expand=transitions.fields"
    ) in out
    assert "[dry-run] POST https://example.atlassian.net/rest/api/2/issue/ACME-401/transitions" in out
    assert json.loads(out.strip().splitlines()[-1])["status"] == "Done"


def test_transition_ticket_lists_options_without_to(monkeypatch, capsys):
    _jira_env(monkeypatch)
    offered = {
        "transitions": [
            {"id": "31", "name": "In Progress", "to": {"name": "In Progress"}},
            {
                "id": "41",
                "name": "Resolve",
                "to": {"name": "Resolved"},
                "fields": {
                    "resolution": {"required": True, "allowedValues": [{"name": "Done"}, {"name": "Won't Do"}]},
                    "comment": {"required": False},
                },
            },
        ]
    }
    calls = []

    def fake_http(method, url, *a, **k):
        calls.append(method)
        return offered

    monkeypatch.setattr(ticket_pr, "http_json", fake_http)
    ticket_pr.main(["transition-ticket", "--key", "ACME-401"])
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "ACME-401 can move via: In Progress, Resolve"
    assert out.splitlines()[1] == "  Resolve needs resolution: Done, Won't Do"
    assert json.loads(out.strip().splitlines()[-1])["transitions"][1] == {
        "id": "41",
        "name": "Resolve",
        "to": "Resolved",
        "required": {"resolution": ["Done", "Won't Do"]},
    }
    assert calls == ["GET"]


def test_transition_ticket_matches_target_status_and_posts_its_id(monkeypatch, capsys):
    _jira_env(monkeypatch)
    offered = {
        "transitions": [
            {"id": "31", "name": "In Progress", "to": {"name": "In Progress"}},
            {"id": "41", "name": "Resolve", "to": {"name": "Resolved"}},
        ]
    }
    posted = {}

    def fake_http(method, url, headers, payload=None, **k):
        if method == "POST":
            posted.update(payload)
            return {}
        return offered

    monkeypatch.setattr(ticket_pr, "http_json", fake_http)
    ticket_pr.main(["transition-ticket", "--key", "ACME-401", "--to", "resolved", "--resolution", "Done"])
    out = capsys.readouterr().out
    assert posted == {"transition": {"id": "41"}, "fields": {"resolution": {"name": "Done"}}}
    assert out.splitlines()[0] == "ACME-401 -> Resolved"
    assert json.loads(out.strip().splitlines()[-1]) == {
        "key": "ACME-401",
        "status": "Resolved",
        "transition": "Resolve",
        "url": "https://example.atlassian.net/browse/ACME-401",
    }


_SAME_NAMED = [
    {"id": "2", "name": "In Progress", "to": {"name": "In Progress"}},
    {"id": "11", "name": "To Do", "to": {"name": "Backlog"}},
    {"id": "21", "name": "In Progress", "to": {"name": "On Hold"}},
]


@pytest.mark.parametrize("order", [_SAME_NAMED, list(reversed(_SAME_NAMED))], ids=["listed", "reversed"])
@pytest.mark.parametrize("to, expected_id", [("In Progress", "2"), ("On Hold", "21")])
def test_transition_ticket_prefers_target_status_over_a_shared_name(monkeypatch, capsys, order, to, expected_id):
    _jira_env(monkeypatch)
    posted = {}

    def fake_http(method, url, headers, payload=None, **k):
        if method == "POST":
            posted.update(payload)
            return {}
        return {"transitions": order}

    monkeypatch.setattr(ticket_pr, "http_json", fake_http)
    ticket_pr.main(["transition-ticket", "--key", "ACME-401", "--to", to])
    assert posted == {"transition": {"id": expected_id}}
    assert capsys.readouterr().out.splitlines()[0] == f"ACME-401 -> {to}"


def test_transition_ticket_refuses_an_ambiguous_name(monkeypatch):
    _jira_env(monkeypatch)
    calls = []

    def fake_http(method, url, *a, **k):
        calls.append(method)
        return {
            "transitions": [
                {"id": "2", "name": "Start", "to": {"name": "In Progress"}},
                {"id": "21", "name": "Start", "to": {"name": "On Hold"}},
            ]
        }

    monkeypatch.setattr(ticket_pr, "http_json", fake_http)
    with pytest.raises(
        SystemExit,
        match=r"'Start' matches more than one transition "
        r"\(2 Start -> In Progress; 21 Start -> On Hold\)",
    ):
        ticket_pr.main(["transition-ticket", "--key", "ACME-401", "--to", "Start"])
    assert calls == ["GET"]


def test_transition_ticket_refuses_an_unknown_target(monkeypatch):
    _jira_env(monkeypatch)
    monkeypatch.setattr(
        ticket_pr,
        "http_json",
        lambda *a, **k: {"transitions": [{"id": "31", "name": "In Progress", "to": {"name": "In Progress"}}]},
    )
    with pytest.raises(SystemExit, match="offers no transition to 'Done'; offered: In Progress"):
        ticket_pr.main(["transition-ticket", "--key", "ACME-401", "--to", "Done"])


def test_add_comment_dry_run(monkeypatch, capsys):
    monkeypatch.setenv("JIRA_SERVER", "example.atlassian.net")
    monkeypatch.setenv("JIRA_USER", "user@example.com")
    monkeypatch.setenv("JIRA_TOKEN", "token")
    out = _run_cli(
        ["--dry-run", "add-comment", "--key", "ACME-401", "--body", "Sheet built, see link"],
        monkeypatch,
        capsys,
    )
    assert "[dry-run] POST https://example.atlassian.net/rest/api/2/issue/ACME-401/comment" in out
    assert '"body": "Sheet built, see link"' in out
    result = json.loads(out.strip().splitlines()[-1])
    assert result == {
        "key": "ACME-401",
        "id": "0",
        "url": "https://example.atlassian.net/browse/ACME-401?focusedCommentId=0",
    }


def test_add_comment_posts_body_file(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("JIRA_SERVER", "example.atlassian.net")
    monkeypatch.setenv("JIRA_USER", "user@example.com")
    monkeypatch.setenv("JIRA_TOKEN", "token")
    body_file = tmp_path / "comment.txt"
    body_file.write_text("Found so far:\n* the missing company is 057\n", encoding="utf-8")
    posted = {}

    def fake_http(method, url, headers, payload=None, **kwargs):
        posted.update(method=method, url=url, payload=payload)
        return {"id": "5235601"}

    monkeypatch.setattr(ticket_pr, "http_json", fake_http)
    ticket_pr.main(["add-comment", "--key", "ACME-401", "--body-file", str(body_file)])
    out = capsys.readouterr().out
    assert posted == {
        "method": "POST",
        "url": "https://example.atlassian.net/rest/api/2/issue/ACME-401/comment",
        "payload": {"body": "Found so far:\n* the missing company is 057\n"},
    }
    assert json.loads(out.strip().splitlines()[-1])["id"] == "5235601"


def test_add_comment_rejects_empty_body(monkeypatch):
    monkeypatch.setenv("JIRA_SERVER", "example.atlassian.net")
    monkeypatch.setenv("JIRA_USER", "user@example.com")
    monkeypatch.setenv("JIRA_TOKEN", "token")
    with pytest.raises(SystemExit, match="empty comment"):
        ticket_pr.main(["add-comment", "--key", "ACME-401", "--body", "  "])


def test_rank_tickets_ranks_each_after_the_previous(monkeypatch, capsys):
    monkeypatch.setenv("JIRA_SERVER", "example.atlassian.net")
    monkeypatch.setenv("JIRA_USER", "user@example.com")
    monkeypatch.setenv("JIRA_TOKEN", "token")
    calls = []

    def fake_http(method, url, headers, payload=None, **kwargs):
        calls.append((method, url, payload))
        return {}

    monkeypatch.setattr(ticket_pr, "http_json", fake_http)
    ticket_pr.main(["rank-tickets", "--keys", "ACME-7", "ACME-3", "ACME-9"])
    out = capsys.readouterr().out
    url = "https://example.atlassian.net/rest/agile/1.0/issue/rank"
    assert calls == [
        ("PUT", url, {"issues": ["ACME-3"], "rankAfterIssue": "ACME-7"}),
        ("PUT", url, {"issues": ["ACME-9"], "rankAfterIssue": "ACME-3"}),
    ]
    assert json.loads(out.strip().splitlines()[-1]) == {"keys": ["ACME-7", "ACME-3", "ACME-9"]}


def test_rank_tickets_rejects_short_or_repeated_lists(monkeypatch):
    monkeypatch.setenv("JIRA_SERVER", "example.atlassian.net")
    monkeypatch.setenv("JIRA_USER", "user@example.com")
    monkeypatch.setenv("JIRA_TOKEN", "token")
    with pytest.raises(SystemExit, match="at least two keys"):
        ticket_pr.main(["rank-tickets", "--keys", "ACME-7"])
    with pytest.raises(SystemExit, match="listed twice"):
        ticket_pr.main(["rank-tickets", "--keys", "ACME-7", "ACME-3", "ACME-7"])


def test_get_ticket_no_comments(monkeypatch, capsys):
    monkeypatch.setenv("JIRA_SERVER", "example.atlassian.net")
    monkeypatch.setenv("JIRA_USER", "user@example.com")
    monkeypatch.setenv("JIRA_TOKEN", "token")
    issue = {"key": "ACME-402", "fields": {"summary": "Quiet", "status": {"name": "To Do"}}}
    monkeypatch.setattr(
        ticket_pr,
        "http_json",
        lambda m, url, *a, **k: {"total": 0, "comments": []} if "/comment?" in url else issue,
    )
    ticket_pr.main(["get-ticket", "--key", "ACME-402"])
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "ACME-402 [To Do] Quiet (0 comments)"
    assert json.loads(out.strip().splitlines()[-1])["comments"] == []


def test_pr_comment_dry_run_posts_an_issue_comment(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    out = _run_cli(
        [
            "--dry-run",
            "pr-comment",
            "--repo",
            "acme/widgets",
            "--pr",
            "7",
            "--body",
            "SonarQube-Integration-Ticket: https://example.atlassian.net/browse/ACME-1",
        ],
        monkeypatch,
        capsys,
    )
    assert "[dry-run] POST https://api.github.com/repos/acme/widgets/issues/7/comments" in out
    assert '"body": "SonarQube-Integration-Ticket: https://example.atlassian.net/browse/ACME-1"' in out
    result = json.loads(out.strip().splitlines()[-1])
    assert result == {"pr": "7", "comment_id": 0, "url": "https://github.com/acme/widgets/pull/7"}


def test_pr_comment_rejects_an_empty_body(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    with pytest.raises(SystemExit, match="empty comment"):
        ticket_pr.main(["--dry-run", "pr-comment", "--repo", "acme/widgets", "--pr", "7"])


def test_pr_comment_bitbucket_posts_a_pr_comment(monkeypatch, capsys):
    monkeypatch.setenv("BITBUCKET_USER", "me@example.com")
    monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
    calls = _record_http(
        monkeypatch,
        {
            "/comments": {
                "id": 91,
                "links": {"html": {"href": "https://bitbucket.org/ws/slug/pull-requests/7#comment-91"}},
            }
        },
    )
    ticket_pr.main(["pr-comment", "--repo", "bitbucket:ws/slug", "--pr", "7", "--body", "Rebased, ready again"])
    assert calls == [
        (
            "POST",
            "https://api.bitbucket.org/2.0/repositories/ws/slug/pullrequests/7/comments",
            {"content": {"raw": "Rebased, ready again"}},
        )
    ]
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1]) == {
        "pr": "7",
        "comment_id": 91,
        "url": "https://bitbucket.org/ws/slug/pull-requests/7#comment-91",
    }


def test_pr_comment_bitbucket_dry_run(monkeypatch, capsys):
    monkeypatch.setenv("BITBUCKET_USER", "me@example.com")
    monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
    out = _run_cli(
        ["--dry-run", "pr-comment", "--repo", "bitbucket:ws/slug", "--pr", "7", "--body", "hi"], monkeypatch, capsys
    )
    assert "[dry-run] POST https://api.bitbucket.org/2.0/repositories/ws/slug/pullrequests/7/comments" in out
    assert json.loads(out.strip().splitlines()[-1]) == {
        "pr": "7",
        "comment_id": 0,
        "url": "https://bitbucket.org/ws/slug/pull-requests/7",
    }


def test_rerun_job_dry_run_hits_the_job_rerun_endpoint(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    out = _run_cli(
        ["--dry-run", "rerun-job", "--repo", "acme/widgets", "--job", "123456"],
        monkeypatch,
        capsys,
    )
    assert "[dry-run] POST https://api.github.com/repos/acme/widgets/actions/jobs/123456/rerun" in out
    result = json.loads(out.strip().splitlines()[-1])
    assert result == {"job": "123456", "url": "https://github.com/acme/widgets/actions/jobs/123456"}


def test_dispatch_workflow_dry_run_posts_ref_and_inputs(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    out = _run_cli(
        [
            "--dry-run",
            "dispatch-workflow",
            "--repo",
            "acme/widgets",
            "--workflow",
            "deploy.yaml",
            "--ref",
            "main",
            "--input",
            "version=1.2.3",
        ],
        monkeypatch,
        capsys,
    )
    assert "[dry-run] POST https://api.github.com/repos/acme/widgets/actions/workflows/deploy.yaml/dispatches" in out
    assert '"inputs": {\n      "version": "1.2.3"\n    }' in out
    assert json.loads(out.strip().splitlines()[-1]) == {
        "workflow": "deploy.yaml",
        "ref": "main",
        "inputs": {"version": "1.2.3"},
        "url": "https://github.com/acme/widgets/actions/workflows/deploy.yaml",
    }


def test_dispatch_workflow_rejects_an_input_without_a_value(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    with pytest.raises(SystemExit, match="KEY=VALUE"):
        ticket_pr.main(
            [
                "--dry-run",
                "dispatch-workflow",
                "--repo",
                "acme/widgets",
                "--workflow",
                "d.yaml",
                "--ref",
                "main",
                "--input",
                "version",
            ]
        )


def _run(run_id, status, conclusion=None, sha="abc", created_at="2026-01-01T00:00:00Z"):
    return {
        "id": run_id,
        "status": status,
        "conclusion": conclusion,
        "event": "release",
        "head_branch": "main",
        "head_sha": sha,
        "display_title": "v1",
        "created_at": created_at,
        "html_url": f"https://github.com/acme/widgets/actions/runs/{run_id}",
    }


NEW_SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
OLD_SHA = "0f9e8d7c6b5a49382716051f2e3d4c5b6a798011"
RUNS_URL = "https://api.github.com/repos/acme/widgets/actions/workflows/deploy.yaml/runs"


def test_workflow_runs_filters_by_branch_and_event(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    seen = []

    def fake_http(method, url, *a, **k):
        seen.append(url)
        return {"workflow_runs": [_run(2, "completed", "success"), _run(1, "completed", "failure")]}

    monkeypatch.setattr(ticket_pr, "http_json", fake_http)
    ticket_pr.main(
        [
            "workflow-runs",
            "--repo",
            "acme/widgets",
            "--workflow",
            "deploy.yaml",
            "--branch",
            "main",
            "--event",
            "release",
            "--limit",
            "2",
        ]
    )
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert seen == [
        "https://api.github.com/repos/acme/widgets/actions/workflows/deploy.yaml/runs"
        "?per_page=2&branch=main&event=release"
    ]
    assert [(r["id"], r["conclusion"]) for r in result["runs"]] == [(2, "success"), (1, "failure")]
    assert result["timed_out"] is None


def _fake_github(monkeypatch, listings, runs_by_id=None):
    """http_json stand-in: the commit lookup resolves to NEW_SHA, each listing poll pops the next response."""
    seen = []
    listings = iter(listings)
    runs_by_id = {k: iter(v) for k, v in (runs_by_id or {}).items()}

    def fake_http(method, url, *a, **k):
        seen.append(url)
        if "/commits/" in url:
            return {"sha": NEW_SHA}
        if url.startswith(RUNS_URL):
            return next(listings)
        run_id = int(url.rsplit("/", 1)[1])
        return next(runs_by_id[run_id])

    monkeypatch.setattr(ticket_pr, "http_json", fake_http)
    monkeypatch.setattr(ticket_pr.time, "sleep", lambda s: None)
    return seen


def test_workflow_runs_wait_without_commit_refuses(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    with pytest.raises(SystemExit, match="--wait needs --commit"):
        ticket_pr.main(["workflow-runs", "--repo", "acme/widgets", "--workflow", "deploy.yaml", "--wait"])


def test_workflow_runs_commit_resolves_once_and_drops_other_shas(monkeypatch, capsys):
    # GitHub once answered per_page=1 with a weeks-old run for another commit
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    seen = _fake_github(
        monkeypatch,
        [
            {
                "workflow_runs": [
                    _run(1, "completed", "success", sha=OLD_SHA),
                    _run(9, "completed", "failure", sha=NEW_SHA),
                ]
            }
        ],
    )
    ticket_pr.main(
        ["workflow-runs", "--repo", "acme/widgets", "--workflow", "deploy.yaml", "--commit", "a1b2c3d4", "--limit", "1"]
    )
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert seen == [
        "https://api.github.com/repos/acme/widgets/commits/a1b2c3d4",
        f"{RUNS_URL}?per_page=1&head_sha={NEW_SHA}",
    ]
    assert [(r["id"], r["sha"]) for r in result["runs"]] == [(9, NEW_SHA)]


def test_workflow_runs_lists_newest_first_whatever_order_github_returns(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    _fake_github(
        monkeypatch,
        [
            {
                "workflow_runs": [
                    _run(1, "completed", "success", created_at="2026-09-16T20:50:55Z"),
                    _run(3, "completed", "success", created_at="2026-10-05T20:16:37Z"),
                    _run(2, "completed", "success", created_at="2026-10-02T22:02:05Z"),
                ]
            }
        ],
    )
    ticket_pr.main(["workflow-runs", "--repo", "acme/widgets", "--workflow", "deploy.yaml"])
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert [r["id"] for r in result["runs"]] == [3, 2, 1]


def test_workflow_runs_wait_keeps_polling_until_the_commits_run_exists(monkeypatch, capsys):
    # right after a merge the newest listed run is the previous commit's finished one
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    seen = _fake_github(
        monkeypatch,
        [
            {"workflow_runs": [_run(4, "completed", "success", sha=OLD_SHA)]},
            {"workflow_runs": [_run(5, "in_progress", sha=NEW_SHA)]},
        ],
        runs_by_id={5: [_run(5, "completed", "success", sha=NEW_SHA)]},
    )
    ticket_pr.main(
        ["workflow-runs", "--repo", "acme/widgets", "--workflow", "deploy.yaml", "--commit", "master", "--wait"]
    )
    out = capsys.readouterr().out
    assert "waiting for a deploy.yaml run on a1b2c3d4e5f6" in out
    assert "waiting on run 5 (in_progress)" in out
    result = json.loads(out.strip().splitlines()[-1])
    assert [(r["id"], r["conclusion"]) for r in result["runs"]] == [(5, "success")]
    assert seen[-1] == "https://api.github.com/repos/acme/widgets/actions/runs/5"


def test_workflow_runs_wait_follows_the_found_run_by_id_not_the_listing(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    seen = _fake_github(
        monkeypatch,
        [{"workflow_runs": [_run(5, "in_progress", sha=NEW_SHA)]}],
        runs_by_id={5: [_run(5, "in_progress", sha=NEW_SHA), _run(5, "completed", "success", sha=NEW_SHA)]},
    )
    ticket_pr.main(
        ["workflow-runs", "--repo", "acme/widgets", "--workflow", "deploy.yaml", "--commit", NEW_SHA, "--wait"]
    )
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert result["runs"][0]["conclusion"] == "success"
    assert sum(u.startswith(RUNS_URL) for u in seen) == 1
    assert seen[-2:] == ["https://api.github.com/repos/acme/widgets/actions/runs/5"] * 2


def test_workflow_runs_wait_times_out_when_the_commits_run_never_appears(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    _fake_github(monkeypatch, [{"workflow_runs": [_run(4, "completed", "success", sha=OLD_SHA)]}] * 3)
    clock = iter([0, 0, 30, 61])
    monkeypatch.setattr(ticket_pr.time, "monotonic", lambda: next(clock))
    ticket_pr.main(
        [
            "workflow-runs",
            "--repo",
            "acme/widgets",
            "--workflow",
            "deploy.yaml",
            "--commit",
            NEW_SHA,
            "--wait",
            "--timeout",
            "60",
        ]
    )
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert result["runs"] == []
    assert result["timed_out"] is True


def test_update_pr_dry_run_patches_the_pull(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    out = _run_cli(
        ["--dry-run", "update-pr", "--repo", "acme/widgets", "--pr", "7", "--title", "ACME-1: new"],
        monkeypatch,
        capsys,
    )
    assert "[dry-run] PATCH https://api.github.com/repos/acme/widgets/pulls/7" in out
    assert json.loads(out.strip().splitlines()[-1]) == {"pr": "7", "updated": ["title"]}


def test_update_pr_sends_only_what_was_given(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    body_file = tmp_path / "body.md"
    body_file.write_text("The design changed; here is what the branch does now.")
    calls = []

    def fake_http_json(method, url, headers, payload=None, **kwargs):
        calls.append((method, url, payload))
        return {"number": 7, "html_url": "https://github.com/acme/widgets/pull/7", "title": "kept"}

    monkeypatch.setattr(ticket_pr, "http_json", fake_http_json)
    out = _run_cli(
        ["update-pr", "--repo", "acme/widgets", "--pr", "7", "--body-file", str(body_file)],
        monkeypatch,
        capsys,
    )
    assert calls == [
        (
            "PATCH",
            "https://api.github.com/repos/acme/widgets/pulls/7",
            {"body": "The design changed; here is what the branch does now."},
        ),
    ]
    assert json.loads(out.strip().splitlines()[-1])["updated"] == ["body"]


def test_update_pr_closes_without_merging(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    calls = []

    def fake_http_json(method, url, headers, payload=None, **kwargs):
        calls.append((method, url, payload))
        return {"number": 7, "html_url": "https://github.com/acme/widgets/pull/7", "title": "kept", "state": "closed"}

    monkeypatch.setattr(ticket_pr, "http_json", fake_http_json)
    out = _run_cli(["update-pr", "--repo", "acme/widgets", "--pr", "7", "--state", "closed"], monkeypatch, capsys)
    assert calls == [("PATCH", "https://api.github.com/repos/acme/widgets/pulls/7", {"state": "closed"})]
    result = json.loads(out.strip().splitlines()[-1])
    assert result["state"] == "closed" and result["updated"] == ["state"]


def test_update_pr_needs_something_to_change(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    with pytest.raises(SystemExit, match="needs --title"):
        _run_cli(["update-pr", "--repo", "acme/widgets", "--pr", "7"], monkeypatch, capsys)


def test_update_pr_is_github_only(monkeypatch, capsys):
    monkeypatch.setenv("BITBUCKET_USER", "me@example.com")
    monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
    with pytest.raises(SystemExit, match="GitHub-only"):
        _run_cli(["update-pr", "--repo", "bitbucket:ws/slug", "--pr", "7", "--title", "x"], monkeypatch, capsys)


def test_archive_repo_dry_run_patches_the_repo(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    out = _run_cli(["--dry-run", "archive-repo", "--repo", "acme/widgets"], monkeypatch, capsys)
    assert "[dry-run] PATCH https://api.github.com/repos/acme/widgets" in out
    assert json.loads(out.strip().splitlines()[-1]) == {"repo": "acme/widgets", "archived": True}


def test_archive_repo_archives_and_unarchives(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    calls = []

    def fake_http_json(method, url, headers, payload=None, **kwargs):
        calls.append((method, url, payload))
        return {"full_name": "acme/widgets", "html_url": "https://github.com/acme/widgets", **payload}

    monkeypatch.setattr(ticket_pr, "http_json", fake_http_json)
    out = _run_cli(["archive-repo", "--repo", "acme/widgets"], monkeypatch, capsys)
    assert json.loads(out.strip().splitlines()[-1])["archived"] is True
    out = _run_cli(["archive-repo", "--repo", "acme/widgets", "--unarchive"], monkeypatch, capsys)
    assert json.loads(out.strip().splitlines()[-1])["archived"] is False
    assert calls == [
        ("PATCH", "https://api.github.com/repos/acme/widgets", {"archived": True}),
        ("PATCH", "https://api.github.com/repos/acme/widgets", {"archived": False}),
    ]


def test_archive_repo_needs_the_repo_named_and_is_github_only(monkeypatch, capsys):
    with pytest.raises(SystemExit):
        _run_cli(["archive-repo"], monkeypatch, capsys)
    monkeypatch.setenv("BITBUCKET_USER", "me@example.com")
    monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
    with pytest.raises(SystemExit, match="GitHub-only"):
        _run_cli(["archive-repo", "--repo", "bitbucket:ws/slug"], monkeypatch, capsys)


def test_job_log_dry_run_hits_the_job_logs_endpoint(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    out = _run_cli(
        ["--dry-run", "job-log", "--repo", "acme/widgets", "--job", "123456"],
        monkeypatch,
        capsys,
    )
    assert "[dry-run] GET https://api.github.com/repos/acme/widgets/actions/jobs/123456/logs" in out
    assert json.loads(out.strip().splitlines()[-1])["job"] == "123456"


def test_job_log_saves_the_log_and_prints_the_matching_lines(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    calls = []

    def fake_job_log(repo, job, headers, timeout=120):
        calls.append((repo, job))
        return "setup ok\nERROR: src/widget.py Imports are incorrectly sorted\nteardown ok\n"

    monkeypatch.setattr(ticket_pr, "github_job_log", fake_job_log)
    out = _run_cli(
        ["job-log", "--repo", "acme/widgets", "--job", "123456", "--grep", "error", "--out-dir", str(tmp_path)],
        monkeypatch,
        capsys,
    )
    assert calls == [("acme/widgets", "123456")]
    assert "ERROR: src/widget.py Imports are incorrectly sorted" in out
    assert "setup ok" not in out
    result = json.loads(out.strip().splitlines()[-1])
    assert result["lines"] == 3 and result["matches"] == 1
    with open(result["path"], encoding="utf-8") as handle:
        assert handle.read().count("\n") == 3


def test_job_log_is_github_only(monkeypatch, capsys):
    monkeypatch.setenv("BITBUCKET_USER", "me@example.com")
    monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
    with pytest.raises(SystemExit, match="GitHub-only"):
        _run_cli(["job-log", "--repo", "bitbucket:ws/slug", "--job", "1"], monkeypatch, capsys)


def test_create_pr_dry_run(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setattr(ticket_pr, "git_output", lambda *a: "ACME-0-test-branch")
    out = _run_cli(
        ["--dry-run", "create-pr", "--repo", "owner/name", "--title", "ACME-0 Test"],
        monkeypatch,
        capsys,
    )
    assert "[dry-run] POST https://api.github.com/repos/owner/name/pulls" in out
    result = json.loads(out.strip().splitlines()[-1])
    assert result["number"] == 0


def test_create_pr_dry_run_with_labels(monkeypatch, capsys):
    """Labels are added via the issues endpoint after the PR is created."""
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setattr(ticket_pr, "git_output", lambda *a: "ABC-0-test-branch")
    out = _run_cli(
        [
            "--dry-run",
            "create-pr",
            "--repo",
            "owner/name",
            "--title",
            "ABC-0 Test",
            "--label",
            "team: alpha",
            "--label",
            "squad: beta",
        ],
        monkeypatch,
        capsys,
    )
    assert "[dry-run] POST https://api.github.com/repos/owner/name/pulls" in out
    assert "[dry-run] POST https://api.github.com/repos/owner/name/issues/0/labels" in out
    result = json.loads(out.strip().splitlines()[-1])
    assert result["labels"] == ["team: alpha", "squad: beta"]


def test_request_review_dry_run(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    out = _run_cli(
        [
            "--dry-run",
            "request-review",
            "--repo",
            "owner/name",
            "--pr",
            "12",
            "--reviewer",
            "reviewer-login",
        ],
        monkeypatch,
        capsys,
    )
    assert "requested_reviewers" in out


def test_pr_status_dry_run_is_parseable(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    out = _run_cli(
        ["--dry-run", "pr-status", "--repo", "owner/name", "--ignore", "approval"],
        monkeypatch,
        capsys,
    )
    result = json.loads(out.strip().splitlines()[-1])
    assert result["dry_run"] is True and result["green"] is True
    assert result["review"]["approved"] is False


def test_pr_status_bitbucket_reports_the_reviewers_votes(monkeypatch, capsys):
    # The regression: an approval was reported as "none yet" because the
    # reviewer's vote was never read. It now rides on every pr-status result.
    monkeypatch.setenv("BITBUCKET_USER", "me@example.com")
    monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
    alex = {"uuid": "{cs}", "display_name": "Alex Reviewer"}
    pull = _bb_pull(
        98,
        "Drop overrides",
        {"uuid": "{me}", "display_name": "Me"},
        [alex, {"uuid": "{pat}", "display_name": "Pat Lee"}],
        [
            {"user": alex, "role": "REVIEWER", "approved": True, "state": "approved"},
            {"user": {"display_name": "Me"}, "role": "PARTICIPANT", "approved": False, "state": None},
        ],
    )
    pull["state"] = "OPEN"
    pull["source"]["commit"] = {"hash": "abc123"}
    _record_http(monkeypatch, {"/pullrequests/98": pull, "/statuses": {"values": []}})
    ticket_pr.main(["pr-status", "--repo", "bitbucket:ws/slug", "--pr", "98"])
    out = capsys.readouterr().out
    assert "review: approved by Alex Reviewer; awaiting Pat Lee" in out
    review = json.loads(out.strip().splitlines()[-1])["review"]
    assert review == {
        "state": "OPEN",
        "draft": False,
        "reviewers": {"Alex Reviewer": "approved", "Pat Lee": None},
        "approved_by": ["Alex Reviewer"],
        "changes_requested_by": [],
        "awaiting": ["Pat Lee"],
        "approved": True,
    }


def test_review_rollup_bitbucket_reports_a_merged_pr():
    pull = _bb_pull(9, "Done", {"display_name": "Me"}, [], [])
    pull["state"] = "MERGED"
    review = ticket_pr.review_rollup_bitbucket(pull)
    assert review["state"] == "MERGED" and review["approved"] is False
    assert ticket_pr.review_line(review) == "PR is MERGED"


def test_review_rollup_github_keeps_the_latest_real_vote_per_login():
    pull = {"state": "open", "draft": True, "requested_reviewers": [{"login": "dana"}]}
    reviews = [
        {"user": {"login": "csmith"}, "state": "CHANGES_REQUESTED", "submitted_at": "2026-09-01T10:00:00Z"},
        {"user": {"login": "csmith"}, "state": "APPROVED", "submitted_at": "2026-09-02T10:00:00Z"},
        {"user": {"login": "csmith"}, "state": "COMMENTED", "submitted_at": "2026-09-03T10:00:00Z"},
        {"user": {"login": "lee"}, "state": "APPROVED", "submitted_at": "2026-09-01T10:00:00Z"},
        {"user": {"login": "lee"}, "state": "DISMISSED", "submitted_at": "2026-09-02T10:00:00Z"},
    ]
    review = ticket_pr.review_rollup_github(pull, reviews)
    assert review["reviewers"] == {"dana": None, "csmith": "approved", "lee": None}
    assert review["approved_by"] == ["csmith"] and review["awaiting"] == ["dana", "lee"]
    assert ticket_pr.review_line(review) == "review: approved by csmith; awaiting dana, lee; still a draft"
    merged = ticket_pr.review_rollup_github({"state": "closed", "merged": True}, [])
    assert merged["state"] == "MERGED"


# ---------------------------------------------------------------- review


def test_http_json_sends_no_content_type_without_a_body(monkeypatch):
    # Bitbucket 400s a bodiless approve / request-changes POST that claims JSON.
    sent = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"state": "approved"}'

    def fake_urlopen(request, timeout):
        sent.append(request)
        return Response()

    monkeypatch.setattr(ticket_pr.urllib.request, "urlopen", fake_urlopen)
    assert ticket_pr.http_json("POST", "https://example.org/approve", {}) == {"state": "approved"}
    ticket_pr.http_json("POST", "https://example.org/comments", {}, payload={"a": 1})
    assert sent[0].data is None and sent[0].get_header("Content-type") is None
    assert sent[1].get_header("Content-type") == "application/json"


def test_github_prefix_pins_the_provider(monkeypatch):
    monkeypatch.setattr(ticket_pr, "git_output", lambda *a: pytest.fail("should not call git"))
    assert ticket_pr.repo_spec("github:owner/name") == ("github", "owner/name")
    assert ticket_pr.repo_spec("bitbucket:ws/slug") == ("bitbucket", "ws/slug")


def test_review_queue_defaults_to_the_origin_repo(monkeypatch, capsys):
    monkeypatch.setattr(ticket_pr, "git_output", lambda *a: "git@github.com:owner/name.git")
    out = _run_cli(["--dry-run", "review-queue"], monkeypatch, capsys)
    assert "[dry-run] would list open PRs in github:owner/name" in out


def _bb_pull(pr_id, title, author, reviewers, participants=(), draft=False):
    return {
        "id": pr_id,
        "title": title,
        "author": author,
        "reviewers": list(reviewers),
        "participants": list(participants),
        "draft": draft,
        "source": {"branch": {"name": f"ACME-{pr_id}"}},
        "destination": {"branch": {"name": "master"}},
        "links": {"html": {"href": f"https://bitbucket.org/ws/slug/pull-requests/{pr_id}"}},
    }


def test_review_queue_bitbucket_marks_what_waits_on_me(monkeypatch, capsys):
    monkeypatch.setenv("BITBUCKET_USER", "me@example.com")
    monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
    me = {"uuid": "{me}", "display_name": "Me"}
    sam = {"uuid": "{sam}", "display_name": "Sam"}
    approved = {"user": me, "state": "approved", "participated_on": "2026-09-10T12:00:00.000000+00:00"}
    pulls = [
        _bb_pull(1, "Fresh work", sam, [me]),
        _bb_pull(2, "Mine", me, []),
        _bb_pull(3, "Asks someone else", sam, []),
        _bb_pull(4, "WIP half done", sam, [me]),
        _bb_pull(5, "Approved, untouched since", sam, [me], [approved]),
        _bb_pull(6, "Approved, pushed to since", sam, [me], [approved]),
    ]
    # 11:30-01:00 is 12:30 UTC (after the approval) and 12:30+01:00 is 11:30 UTC
    # (before it): string comparison gets both wrong, parsed comparison does not.
    commits = {
        5: [{"date": "2026-09-09T08:00:00+00:00"}],
        6: [{"date": "2026-09-10T11:30:00-01:00"}, {"date": "2026-09-10T12:30:00+01:00"}],
    }

    def fake_http(method, url, headers, **kwargs):
        if url.endswith("/2.0/user"):
            return me
        match = re.search(r"/pullrequests/(\d+)/commits", url)
        if match:
            return {"values": commits[int(match.group(1))]}
        return {"values": pulls}

    monkeypatch.setattr(ticket_pr, "http_json", fake_http)
    ticket_pr.main(["review-queue", "--repo", "bitbucket:ws/slug"])
    out = capsys.readouterr().out
    result = json.loads(out.strip().splitlines()[-1])
    assert {pr["pr"]: pr["skip"] for pr in result["prs"]} == {
        1: None,
        2: "own",
        3: "not_requesting",
        4: "draft",
        5: "approved",
        6: None,
    }
    assert result["prs"][5]["commits_since_my_approval"] == 1
    assert result["skipped"] == {"own": 1, "not_requesting": 1, "draft": 1, "approved": 1}
    assert "pull-requests/6 Approved, pushed to since (re-review: 1 commit(s) since your approval)" in out


def test_review_queue_github_needs_a_review_request(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")

    def pull(number, author, requested=(), draft=False):
        return {
            "number": number,
            "title": f"PR {number}",
            "user": {"login": author},
            "draft": draft,
            "requested_reviewers": [{"login": login} for login in requested],
            "head": {"ref": f"b{number}"},
            "base": {"ref": "main"},
            "html_url": f"https://github.com/owner/name/pull/{number}",
        }

    pulls = [pull(1, "sam", ["me"]), pull(2, "me"), pull(3, "sam"), pull(4, "sam", ["me"], draft=True)]
    monkeypatch.setattr(
        ticket_pr,
        "http_json",
        lambda m, url, h, **k: {"login": "me"} if url.endswith("/user") else pulls,
    )
    ticket_pr.main(["review-queue", "--repo", "github:owner/name"])
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert {pr["pr"]: pr["skip"] for pr in result["prs"]} == {
        1: None,
        2: "own",
        3: "not_requesting",
        4: "draft",
    }


def test_pr_diff_bitbucket_writes_the_diff_and_file_stats(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("BITBUCKET_USER", "me@example.com")
    monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
    pull = {
        "id": 7,
        "title": "Add the thing",
        "author": {"display_name": "Sam"},
        "description": "why",
        "source": {"branch": {"name": "ACME-7-thing"}, "commit": {"hash": "abc123"}},
        "destination": {"branch": {"name": "master"}},
        "links": {"html": {"href": "https://bitbucket.org/ws/slug/pull-requests/7"}},
    }
    diffstat = {
        "values": [
            {
                "status": "modified",
                "old": {"path": "src/a.py"},
                "new": {"path": "src/a.py"},
                "lines_added": 3,
                "lines_removed": 1,
            },
            {
                "status": "renamed",
                "old": {"path": "src/b.py"},
                "new": {"path": "src/c.py"},
                "lines_added": 0,
                "lines_removed": 9,
            },
        ]
    }
    # one collection holds general, inline and reply comments; deleted ones stay as tombstones
    comments = {
        "values": [
            {
                "id": 4,
                "user": {"display_name": "Alex"},
                "created_on": "2026-09-14T10:00:00+00:00",
                "content": {"raw": "Dropped it"},
                "inline": {"path": "src/b.py", "from": 8, "to": None},
                "parent": {"id": 1},
            },
            {
                "id": 1,
                "user": {"display_name": "Sam"},
                "created_on": "2026-09-13T09:00:00+00:00",
                "content": {"raw": "Why remove the retry?"},
                "inline": {"path": "src/b.py", "from": 8, "to": None},
            },
            {
                "id": 2,
                "deleted": True,
                "user": {"display_name": "Sam"},
                "created_on": "2026-09-13T09:30:00+00:00",
                "content": {"raw": ""},
            },
            {
                "id": 3,
                "user": {"display_name": "Alex"},
                "created_on": "2026-09-14T09:00:00+00:00",
                "content": {"raw": "Rebased on master"},
            },
        ]
    }
    fetched = []

    def fake_bytes(url, headers):
        fetched.append(url)
        return b"diff --git a/src/a.py b/src/a.py\n"

    def fake_http(method, url, headers, **kwargs):
        if url.endswith("/diffstat"):
            return diffstat
        if "/comments?" in url:
            return comments
        return pull

    monkeypatch.setattr(ticket_pr, "http_json", fake_http)
    monkeypatch.setattr(ticket_pr, "http_bytes", fake_bytes)
    out_path = tmp_path / "pr7.diff"
    ticket_pr.main(["pr-diff", "--repo", "bitbucket:ws/slug", "--pr", "7", "--out", str(out_path)])
    out = capsys.readouterr().out
    result = json.loads(out.strip().splitlines()[-1])
    assert fetched == ["https://api.bitbucket.org/2.0/repositories/ws/slug/pullrequests/7/diff"]
    assert out_path.read_bytes() == b"diff --git a/src/a.py b/src/a.py\n"
    assert out.splitlines()[0] == f"PR #7 Add the thing: 2 files, 3 comments, diff in {out_path}"
    assert result == {
        "pr": 7,
        "title": "Add the thing",
        "author": "Sam",
        "source": "ACME-7-thing",
        "destination": "master",
        "head": "abc123",
        "description": "why",
        "url": "https://bitbucket.org/ws/slug/pull-requests/7",
        "files": [
            {"path": "src/a.py", "status": "modified", "previous_path": None, "additions": 3, "deletions": 1},
            {"path": "src/c.py", "status": "renamed", "previous_path": "src/b.py", "additions": 0, "deletions": 9},
        ],
        "comments": [
            {
                "id": 1,
                "kind": "inline",
                "author": "Sam",
                "created": "2026-09-13T09:00:00+00:00",
                "body": "Why remove the retry?",
                "path": "src/b.py",
                "line": 8,
                "reply_to": None,
                "state": None,
            },
            {
                "id": 3,
                "kind": "comment",
                "author": "Alex",
                "created": "2026-09-14T09:00:00+00:00",
                "body": "Rebased on master",
                "path": None,
                "line": None,
                "reply_to": None,
                "state": None,
            },
            {
                "id": 4,
                "kind": "inline",
                "author": "Alex",
                "created": "2026-09-14T10:00:00+00:00",
                "body": "Dropped it",
                "path": "src/b.py",
                "line": 8,
                "reply_to": 1,
                "state": None,
            },
        ],
        "diff_path": str(out_path),
    }


def test_github_pr_diff_stitches_file_patches_when_the_diff_is_too_large(monkeypatch):
    base = "https://api.github.com/repos/owner/name/pulls/12"
    files = [
        {"filename": "src/a.py", "status": "modified", "patch": "@@ -1 +1 @@\n-x\n+y"},
        {
            "filename": "src/new.py",
            "previous_filename": "src/old.py",
            "status": "renamed",
            "patch": "@@ -1 +1 @@\n-a\n+b",
        },
        {"filename": "data/big.csv", "status": "added"},
    ]
    asked = []

    def fake_bytes(url, headers, tolerate=(), **kwargs):
        asked.append((url, headers.get("Accept"), tolerate))
        # GitHub's answer when a PR's diff is past its size limit
        return None

    monkeypatch.setattr(ticket_pr, "http_bytes", fake_bytes)
    monkeypatch.setattr(ticket_pr, "http_json", lambda method, url, headers, **kwargs: files)
    diff = ticket_pr.github_pr_diff("owner/name", 12, {}).decode()
    assert asked == [(base, "application/vnd.github.diff", (406,))]
    assert diff == (
        "diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-x\n+y\n"
        "diff --git a/src/old.py b/src/new.py\n--- a/src/old.py\n+++ b/src/new.py\n@@ -1 +1 @@\n-a\n+b\n"
        "diff --git a/data/big.csv b/data/big.csv\n--- a/data/big.csv\n+++ b/data/big.csv\n"
        "(no patch from GitHub: file too large or binary)\n"
    )


def test_pr_diff_github_reads_every_kind_of_comment(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    base = "https://api.github.com/repos/owner/name/pulls/12"
    pull = {
        "number": 12,
        "title": "Retry the upload",
        "user": {"login": "sam"},
        "body": "why",
        "head": {"ref": "ACME-12-retry", "sha": "abc123"},
        "base": {"ref": "main"},
        "html_url": "https://github.com/owner/name/pull/12",
    }
    # GitHub keeps them in three places: the conversation, diff lines, and review bodies
    responses = {
        f"{base}/files?": [{"filename": "src/a.py", "status": "modified", "additions": 3, "deletions": 1}],
        "/issues/12/comments?": [
            {"id": 1, "user": {"login": "sam"}, "created_at": "2026-09-12T09:00:00Z", "body": "Ready for a look"}
        ],
        f"{base}/comments?": [
            {
                "id": 3,
                "user": {"login": "sam"},
                "created_at": "2026-09-13T11:00:00Z",
                "body": "Dropped it",
                "path": "src/a.py",
                "line": None,
                "original_line": 40,
                "in_reply_to_id": 2,
            },
            {
                "id": 2,
                "user": {"login": "me"},
                "created_at": "2026-09-13T10:00:00Z",
                "body": "Why the retry?",
                "path": "src/a.py",
                "line": 40,
            },
        ],
        f"{base}/reviews?": [
            {
                "id": 9,
                "user": {"login": "me"},
                "submitted_at": "2026-09-13T10:00:05Z",
                "body": "One question inline",
                "state": "CHANGES_REQUESTED",
            },
            {
                "id": 10,
                "user": {"login": "me"},
                "submitted_at": "2026-09-14T08:00:00Z",
                "body": "",
                "state": "APPROVED",
            },
        ],
    }
    fetched = []

    def fake_http(method, url, headers, **kwargs):
        fetched.append(url)
        if url == base:
            return pull
        return next(resp for marker, resp in responses.items() if marker in url)

    monkeypatch.setattr(ticket_pr, "http_json", fake_http)
    monkeypatch.setattr(ticket_pr, "http_bytes", lambda url, headers, **kwargs: b"diff")
    out_path = tmp_path / "pr12.diff"
    ticket_pr.main(["pr-diff", "--repo", "github:owner/name", "--pr", "12", "--out", str(out_path)])
    out = capsys.readouterr().out
    result = json.loads(out.strip().splitlines()[-1])
    assert out.splitlines()[0] == f"PR #12 Retry the upload: 1 files, 4 comments, diff in {out_path}"
    assert f"{base}/reviews?per_page=100&page=1" in fetched
    assert result["comments"] == [
        {
            "id": 1,
            "kind": "comment",
            "author": "sam",
            "created": "2026-09-12T09:00:00Z",
            "body": "Ready for a look",
            "path": None,
            "line": None,
            "reply_to": None,
            "state": None,
        },
        {
            "id": 2,
            "kind": "inline",
            "author": "me",
            "created": "2026-09-13T10:00:00Z",
            "body": "Why the retry?",
            "path": "src/a.py",
            "line": 40,
            "reply_to": None,
            "state": None,
        },
        {
            "id": 9,
            "kind": "review",
            "author": "me",
            "created": "2026-09-13T10:00:05Z",
            "body": "One question inline",
            "path": None,
            "line": None,
            "reply_to": None,
            "state": "CHANGES_REQUESTED",
        },
        {
            "id": 3,
            "kind": "inline",
            "author": "sam",
            "created": "2026-09-13T11:00:00Z",
            "body": "Dropped it",
            "path": "src/a.py",
            "line": 40,
            "reply_to": 2,
            "state": None,
        },
    ]


def _record_http(monkeypatch, responses):
    calls = []

    def fake_http(method, url, headers, payload=None, **kwargs):
        calls.append((method, url, payload))
        resp = next(resp for suffix, resp in responses.items() if url.endswith(suffix))
        return resp.pop(0) if isinstance(resp, list) else resp

    monkeypatch.setattr(ticket_pr, "http_json", fake_http)
    return calls


def test_pr_review_bitbucket_posts_the_comment_before_the_vote(monkeypatch, capsys):
    monkeypatch.setenv("BITBUCKET_USER", "me@example.com")
    monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
    calls = _record_http(monkeypatch, {"/comments": {"id": 55}, "/request-changes": {"state": "changes_requested"}})
    ticket_pr.main(
        [
            "pr-review",
            "--repo",
            "bitbucket:ws/slug",
            "--pr",
            "7",
            "--action",
            "request-changes",
            "--body",
            "The banner prints too early.",
        ]
    )
    base = "https://api.bitbucket.org/2.0/repositories/ws/slug/pullrequests/7"
    assert calls == [
        ("POST", f"{base}/comments", {"content": {"raw": "The banner prints too early."}}),
        ("POST", f"{base}/request-changes", None),
    ]
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert result["state"] == "changes_requested" and result["comment_id"] == 55


def test_pr_review_bitbucket_approve_is_one_bodiless_post(monkeypatch, capsys):
    monkeypatch.setenv("BITBUCKET_USER", "me@example.com")
    monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
    calls = _record_http(monkeypatch, {"/approve": {"state": "approved"}})
    ticket_pr.main(["pr-review", "--repo", "bitbucket:ws/slug", "--pr", "7", "--action", "approve"])
    assert calls == [
        ("POST", "https://api.bitbucket.org/2.0/repositories/ws/slug/pullrequests/7/approve", None),
    ]
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["state"] == "approved"


def test_pr_review_github_submits_one_review(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    calls = _record_http(
        monkeypatch,
        {"/reviews": {"state": "COMMENTED", "html_url": "https://github.com/owner/name/pull/12#pullrequestreview-1"}},
    )
    ticket_pr.main(
        ["pr-review", "--repo", "github:owner/name", "--pr", "12", "--action", "comment", "--body", "Why the retry?"]
    )
    assert calls == [
        (
            "POST",
            "https://api.github.com/repos/owner/name/pulls/12/reviews",
            {"event": "COMMENT", "body": "Why the retry?"},
        )
    ]
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["state"] == "COMMENTED"


def test_pr_review_rejects_an_empty_body(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    with pytest.raises(SystemExit, match="empty review body"):
        ticket_pr.main(
            ["pr-review", "--repo", "github:owner/name", "--pr", "12", "--action", "request-changes", "--body", "  "]
        )


def test_review_commands_dry_run(monkeypatch, capsys):
    monkeypatch.setenv("BITBUCKET_USER", "me@example.com")
    monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
    out = _run_cli(["--dry-run", "review-queue", "--repo", "bitbucket:ws/slug"], monkeypatch, capsys)
    assert "[dry-run] would list open PRs in bitbucket:ws/slug" in out
    out = _run_cli(["--dry-run", "pr-diff", "--repo", "bitbucket:ws/slug", "--pr", "7"], monkeypatch, capsys)
    assert json.loads(out.strip().splitlines()[-1])["dry_run"] is True
    out = _run_cli(
        ["--dry-run", "pr-review", "--repo", "bitbucket:ws/slug", "--pr", "7", "--action", "approve"],
        monkeypatch,
        capsys,
    )
    assert "[dry-run] POST https://api.bitbucket.org/2.0/repositories/ws/slug/pullrequests/7/approve" in out


# ---------------------------------------------------------------- merge


def _github_pull(state, auto_merge=None):
    return {
        "number": 12,
        "node_id": "PR_node",
        "html_url": "https://github.com/owner/name/pull/12",
        "head": {"sha": "abc123"},
        "mergeable": True,
        "mergeable_state": state,
        "auto_merge": auto_merge,
    }


def test_merge_state_github_reads_a_full_pull_without_another_request(monkeypatch):
    calls = _record_http(monkeypatch, {})
    queued = {"merge_method": "squash", "enabled_by": {"login": "dana"}}
    state = ticket_pr.merge_state_github("owner/name", _github_pull("blocked", queued), {})
    assert state == {
        "mergeable_state": "blocked",
        "auto_merge": True,
        "auto_merge_method": "squash",
        "auto_merge_by": "dana",
    }
    assert calls == []


def test_merge_state_github_refetches_a_pull_found_by_branch(monkeypatch):
    # the list endpoint returns the PR without its merge state
    calls = _record_http(monkeypatch, {"/pulls/12": _github_pull("behind")})
    state = ticket_pr.merge_state_github("owner/name", {"number": 12}, {})
    assert state == {
        "mergeable_state": "behind",
        "auto_merge": False,
        "auto_merge_method": None,
        "auto_merge_by": None,
    }
    assert calls == [("GET", "https://api.github.com/repos/owner/name/pulls/12", None)]


def test_merge_pr_dry_run_is_parseable(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    out = _run_cli(["--dry-run", "merge-pr", "--repo", "owner/name", "--pr", "12"], monkeypatch, capsys)
    assert "[dry-run] would squash-merge PR #12 in owner/name" in out
    assert json.loads(out.strip().splitlines()[-1])["dry_run"] is True


def test_merge_pr_merges_a_clean_pr_pinned_to_its_head(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    calls = _record_http(monkeypatch, {"/merge": {"sha": "def456", "merged": True}, "/pulls/12": _github_pull("clean")})
    ticket_pr.main(["merge-pr", "--repo", "owner/name", "--pr", "12"])
    base = "https://api.github.com/repos/owner/name/pulls/12"
    assert calls == [("GET", base, None), ("PUT", f"{base}/merge", {"merge_method": "squash", "sha": "abc123"})]
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert result["merged"] is True and result["sha"] == "def456"


def test_merge_pr_enables_auto_merge_while_blocked(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    calls = _record_http(
        monkeypatch,
        {
            "/graphql": {"data": {}},
            "/pulls/12": [_github_pull("blocked"), _github_pull("blocked", {"merge_method": "squash"})],
        },
    )
    ticket_pr.main(["merge-pr", "--repo", "owner/name", "--pr", "12"])
    assert [call[:2] for call in calls] == [
        ("GET", "https://api.github.com/repos/owner/name/pulls/12"),
        ("POST", "https://api.github.com/graphql"),
        ("GET", "https://api.github.com/repos/owner/name/pulls/12"),
    ]
    assert calls[1][2]["variables"] == {"id": "PR_node", "method": "SQUASH"}
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert result["auto_merge"] is True and result["merged"] is False


def test_merge_pr_refuses_a_pr_with_a_failing_check(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    calls = _record_http(monkeypatch, {"/pulls/12": _github_pull("unstable")})
    with pytest.raises(SystemExit, match="'unstable'"):
        ticket_pr.main(["merge-pr", "--repo", "owner/name", "--pr", "12"])
    assert calls == [("GET", "https://api.github.com/repos/owner/name/pulls/12", None)]


def test_merge_pr_disables_a_queued_auto_merge(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    calls = _record_http(
        monkeypatch,
        {
            "/graphql": {"data": {}},
            "/pulls/12": [_github_pull("blocked", {"merge_method": "squash"}), _github_pull("blocked")],
        },
    )
    ticket_pr.main(["merge-pr", "--repo", "owner/name", "--pr", "12", "--disable-auto-merge"])
    assert [call[:2] for call in calls] == [
        ("GET", "https://api.github.com/repos/owner/name/pulls/12"),
        ("POST", "https://api.github.com/graphql"),
        ("GET", "https://api.github.com/repos/owner/name/pulls/12"),
    ]
    assert "disablePullRequestAutoMerge" in calls[1][2]["query"]
    assert calls[1][2]["variables"] == {"id": "PR_node"}
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert result["auto_merge"] is False and result["changed"] is True and result["merged"] is False


def test_merge_pr_disable_is_a_no_op_without_auto_merge(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    calls = _record_http(monkeypatch, {"/pulls/12": _github_pull("blocked")})
    ticket_pr.main(["merge-pr", "--repo", "owner/name", "--pr", "12", "--disable-auto-merge"])
    assert calls == [("GET", "https://api.github.com/repos/owner/name/pulls/12", None)]
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert result["auto_merge"] is False and result["changed"] is False


def test_merge_pr_reports_a_rejected_auto_merge(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    _record_http(
        monkeypatch,
        {
            "/graphql": {"errors": [{"message": "Auto merge is not allowed for this repository"}]},
            "/pulls/12": _github_pull("blocked"),
        },
    )
    with pytest.raises(SystemExit, match="Auto merge is not allowed"):
        ticket_pr.main(["merge-pr", "--repo", "owner/name", "--pr", "12"])


def _bb_merge_pull(state="OPEN", vote="approved", draft=False):
    alex = {"uuid": "{alex}", "display_name": "Alex Reviewer"}
    pull = _bb_pull(
        98,
        "Drop overrides",
        {"display_name": "Me"},
        [alex],
        [{"user": alex, "role": "REVIEWER", "state": vote}],
        draft=draft,
    )
    pull["state"] = state
    pull["source"]["commit"] = {"hash": "abc123"}
    return pull


def _bb_env(monkeypatch):
    monkeypatch.setenv("BITBUCKET_USER", "me@example.com")
    monkeypatch.setenv("BITBUCKET_TOKEN", "tok")


BB_PULL_URL = "https://api.bitbucket.org/2.0/repositories/ws/slug/pullrequests/98"


def test_merge_pr_bitbucket_merges_an_approved_pr_with_the_repo_default(monkeypatch, capsys):
    _bb_env(monkeypatch)
    merged = {**_bb_merge_pull(state="MERGED"), "merge_commit": {"hash": "def456"}}
    calls = _record_http(
        monkeypatch, {"/pullrequests/98": _bb_merge_pull(), "/statuses": {"values": []}, "/merge": merged}
    )
    ticket_pr.main(["merge-pr", "--repo", "bitbucket:ws/slug", "--pr", "98"])
    assert calls[-1] == ("POST", f"{BB_PULL_URL}/merge", {"type": "pullrequest"})
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert result["merged"] is True and result["sha"] == "def456" and result["merge_strategy"] is None
    assert result["review"]["state"] == "MERGED"


def test_merge_pr_bitbucket_maps_the_method_to_a_strategy(monkeypatch, capsys):
    _bb_env(monkeypatch)
    merged = {**_bb_merge_pull(state="MERGED"), "merge_commit": {"hash": "def456"}}
    calls = _record_http(
        monkeypatch, {"/pullrequests/98": _bb_merge_pull(), "/statuses": {"values": []}, "/merge": merged}
    )
    ticket_pr.main(["merge-pr", "--repo", "bitbucket:ws/slug", "--pr", "98", "--method", "merge"])
    assert calls[-1][2] == {"type": "pullrequest", "merge_strategy": "merge_commit"}


def test_merge_pr_bitbucket_follows_a_slow_merge_to_its_end(monkeypatch, capsys):
    # A merge past Bitbucket's timeout answers 202 with no body.
    _bb_env(monkeypatch)
    monkeypatch.setattr(ticket_pr.time, "sleep", lambda _s: None)
    merged = {**_bb_merge_pull(state="MERGED"), "merge_commit": {"hash": "def456"}}
    calls = _record_http(
        monkeypatch,
        {"/pullrequests/98": [_bb_merge_pull(), _bb_merge_pull(), merged], "/statuses": {"values": []}, "/merge": {}},
    )
    ticket_pr.main(["merge-pr", "--repo", "bitbucket:ws/slug", "--pr", "98"])
    assert [c[0] for c in calls] == ["GET", "GET", "POST", "GET", "GET"]
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["sha"] == "def456"


@pytest.mark.parametrize(
    "pull, statuses, reason",
    [
        (_bb_merge_pull(vote=None), [], "no approval yet"),
        (_bb_merge_pull(vote="changes_requested"), [], "changes requested by Alex Reviewer"),
        (_bb_merge_pull(draft=True), [], "still a draft"),
        (_bb_merge_pull(state="DECLINED"), [], "it is DECLINED"),
        (_bb_merge_pull(), [{"key": "build", "state": "FAILED"}], "builds not green: build"),
    ],
)
def test_merge_pr_bitbucket_never_merges_a_pr_that_is_not_ready(monkeypatch, pull, statuses, reason):
    _bb_env(monkeypatch)
    calls = _record_http(monkeypatch, {"/pullrequests/98": pull, "/statuses": {"values": statuses}})
    with pytest.raises(SystemExit, match=reason):
        ticket_pr.main(["merge-pr", "--repo", "bitbucket:ws/slug", "--pr", "98"])
    assert all(method == "GET" for method, _url, _payload in calls)


def test_merge_pr_bitbucket_dry_run_is_parseable(monkeypatch, capsys):
    _bb_env(monkeypatch)
    out = _run_cli(["--dry-run", "merge-pr", "--repo", "bitbucket:ws/slug", "--pr", "98"], monkeypatch, capsys)
    assert "[dry-run] would merge PR #98 in ws/slug (repo default strategy) once it is approved" in out
    assert json.loads(out.strip().splitlines()[-1])["dry_run"] is True


def test_merge_pr_bitbucket_has_no_auto_merge_to_disable(monkeypatch):
    _bb_env(monkeypatch)
    with pytest.raises(SystemExit, match="no queued auto-merge"):
        ticket_pr.main(["merge-pr", "--repo", "bitbucket:ws/slug", "--pr", "98", "--disable-auto-merge"])


def test_workflow_runs_jobs_lists_each_runs_jobs(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "t")

    def fake_http(method, url, *a, **k):
        if url.endswith("/actions/runs/7/jobs?per_page=100"):
            return {"jobs": [{"id": 70, "name": "deploy", "status": "completed", "conclusion": "failure"}]}
        return {"workflow_runs": [_run(7, "completed", "failure")]}

    monkeypatch.setattr(ticket_pr, "http_json", fake_http)
    ticket_pr.main(["workflow-runs", "--repo", "acme/widgets", "--workflow", "deploy.yaml", "--limit", "1", "--jobs"])
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert result["runs"][0]["jobs"] == [{"id": 70, "name": "deploy", "status": "completed", "conclusion": "failure"}]


# ---------------------------------------------------------------- activity


def test_activity_window_defaults_to_the_previous_7_days_through_today():
    first, last, start, end = ticket_pr.activity_window(None, "2026-10-06")
    assert (first.isoformat(), last.isoformat()) == ("2026-09-29", "2026-10-06")
    assert (start.date().isoformat(), end.date().isoformat()) == ("2026-09-29", "2026-10-07")
    assert start.hour == end.hour == 0


def test_activity_window_refuses_a_backwards_range():
    with pytest.raises(SystemExit, match="after"):
        ticket_pr.activity_window("2026-10-06", "2026-10-01")


def test_activity_dry_run_touches_nothing(monkeypatch, capsys):
    _jira_env(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    out = _run_cli(
        ["--dry-run", "activity", "--since", "2026-09-01", "--until", "2026-09-07", "--repo", "github:owner/name"],
        monkeypatch,
        capsys,
    )
    result = json.loads(out.strip().splitlines()[-1])
    assert result["window"]["since"] == "2026-09-01"
    assert result["window"]["until"] == "2026-09-07"


def test_activity_bitbucket_keeps_only_my_own_work_inside_the_window(monkeypatch, capsys):
    monkeypatch.setenv("BITBUCKET_USER", "me@example.com")
    monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
    inside, before, after = "2026-09-03T15:00:00+00:00", "2026-08-20T15:00:00+00:00", "2026-09-20T15:00:00+00:00"
    me = {"uuid": "{me}", "display_name": "Me"}
    sam = {"uuid": "{sam}", "display_name": "Sam"}

    def pull(pr_id, author, created, state="OPEN"):
        return {**_bb_pull(pr_id, f"PR {pr_id}", author, []), "created_on": created, "state": state}

    def update(author, at, **changes):
        return {"update": {"author": author, "date": at, "changes": changes}}

    def commit(sha, author, at, message="work"):
        return {
            "hash": sha,
            "date": at,
            "message": message,
            "author": {"raw": "Me <me@example.com>", **({"user": author} if author else {})},
            "links": {"html": {"href": f"https://bitbucket.org/ws/slug/commits/{sha}"}},
        }

    pulls = {
        1: pull(1, me, inside),  # mine, opened inside the window
        2: pull(2, sam, before, state="MERGED"),  # sam's, merged by me
        3: pull(3, sam, before),  # sam's, I only approved and commented
        4: pull(4, me, before),  # mine, but nothing I did falls inside
        5: pull(5, sam, before, state="DECLINED"),  # sam's, declined by me
    }
    activity = {
        1: [
            update(me, inside),  # the creation entry: no changes, already told by "opened"
            update(me, inside, title={"old": "a", "new": "b"}, draft={"old": True, "new": False}),
            update(me, inside, reviewers={"added": [sam]}),
            update(sam, inside, title={"old": "b", "new": "c"}),
        ],
        2: [update(me, inside, status={"old": "open", "new": "fulfilled"})],
        3: [{"approval": {"user": me, "date": inside}}, {"comment": {"user": me, "created_on": inside}}],
        4: [update(me, after, description={"old": "a", "new": "b"})],
        5: [update(me, inside, status={"old": "open", "new": "rejected"})],
    }
    pr_commits = {
        1: [commit("a1", me, inside, "first\n\nbody"), commit("a2", sam, inside), commit("a3", None, inside)],
        2: [commit("b1", sam, inside)],
        3: [],
        4: [commit("d1", me, before)],
        5: [],
    }
    # A page is only the end of the walk when every commit on it is older than
    # the window: page one still holds one inside it, page two holds none.
    branch_pages = {
        "1": {
            "values": [commit("m0", me, after), commit("m1", me, inside), commit("m2", sam, inside)],
            "next": "https://api.bitbucket.org/2.0/repositories/ws/slug/commits/main?page=2",
        },
        "2": {
            "values": [commit("m3", me, before)],
            "next": "https://api.bitbucket.org/2.0/repositories/ws/slug/commits/main?page=3",
        },
    }
    calls = []

    def fake(method, url, headers, **kwargs):
        calls.append(url)
        path = url.split("?")[0]
        if path.endswith("/2.0/user"):
            return me
        if path.endswith("/repositories/ws/slug"):
            return {"mainbranch": {"name": "main"}}
        if path.endswith("/commits/main"):
            page = re.search(r"[?&]page=(\d+)", url)
            return branch_pages[page.group(1) if page else "1"]
        if path.endswith("/pullrequests"):
            return {"values": [{"id": pr_id} for pr_id in pulls]}
        number = int(re.search(r"/pullrequests/(\d+)", path).group(1))
        if path.endswith("/activity"):
            return {"values": activity[number]}
        if path.endswith("/commits"):
            return {"values": pr_commits[number]}
        return pulls[number]

    monkeypatch.setattr(ticket_pr, "http_json", fake)
    ticket_pr.main(
        ["activity", "--no-jira", "--since", "2026-09-01", "--until", "2026-09-07", "--repo", "bitbucket:ws/slug"]
    )
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    assert result["tickets"] == []
    assert {p["pr"]: [a["event"] for a in p["actions"]] for p in result["prs"]} == {
        1: ["opened", "renamed", "ready_for_review", "review_requested"],
        2: ["merged"],
        5: ["closed"],
    }
    assert [c["sha"] for c in result["prs"][0]["commits"]] == ["a1"]
    assert result["prs"][0]["commits"][0]["message"] == "first"
    assert [(p["provider"], p["state"], p["author"]) for p in result["prs"]] == [
        ("bitbucket", "open", "Me"),
        ("bitbucket", "merged", "Sam"),
        ("bitbucket", "declined", "Sam"),
    ]
    assert [c["sha"] for c in result["commits"]] == ["m1"]
    assert not any("page=3" in url for url in calls)
    candidates = urllib.parse.unquote_plus(next(u for u in calls if u.split("?")[0].endswith("/pullrequests")))
    assert "updated_on >=" in candidates and "created_on <" in candidates
    assert all(f"state={state}" in candidates for state in ("OPEN", "MERGED", "DECLINED", "SUPERSEDED"))


def test_activity_no_repos_reads_jira_alone(monkeypatch, capsys):
    _jira_env(monkeypatch)

    def fake(method, url, headers, **kwargs):
        if "/rest/api/" not in url:
            raise AssertionError(url)
        return {"accountId": "acc-me"} if url.endswith("/myself") else {"issues": []}

    monkeypatch.setattr(ticket_pr, "http_json", fake)
    ticket_pr.main(["activity", "--no-repos", "--since", "2026-09-01", "--until", "2026-09-07"])
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert (result["tickets"], result["prs"], result["commits"]) == ([], [], [])


def test_activity_keeps_only_my_own_work_inside_the_window(monkeypatch, capsys):
    _jira_env(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    inside, before, after = "2026-09-03T15:00:00Z", "2026-08-20T15:00:00Z", "2026-09-20T15:00:00Z"

    def history(account, created, field, from_, to):
        return {
            "author": {"accountId": account},
            "created": created,
            "items": [{"fieldId": field, "fromString": from_, "toString": to}],
        }

    changelogs = {
        "ACME-1": [
            history("acc-me", "2026-09-02T10:00:00.000+0000", "status", "Open", "In Progress"),
            history("acc-other", "2026-09-03T10:00:00.000+0000", "status", "In Progress", "Done"),
            history("acc-me", "2026-09-04T10:00:00.000+0000", "assignee", None, "Me"),
            history("acc-me", "2026-08-01T10:00:00.000+0000", "status", "New", "Open"),
        ],
        "ACME-2": [history("acc-other", "2026-09-02T10:00:00.000+0000", "status", "Open", "Done")],
    }

    def pull(number, author, created, merged_at=None):
        return {
            "number": number,
            "title": f"PR {number}",
            "user": {"login": author},
            "created_at": created,
            "merged_at": merged_at,
            "state": "closed" if merged_at else "open",
            "head": {"ref": f"b{number}"},
            "base": {"ref": "master"},
            "html_url": f"https://github.com/owner/name/pull/{number}",
        }

    def commit(sha, login, at, message="work"):
        return {
            "sha": sha,
            "author": {"login": login},
            "commit": {"message": message, "committer": {"date": at}},
            "html_url": f"https://github.com/owner/name/commit/{sha}",
        }

    def event(name, login, at):
        return {"event": name, "actor": {"login": login}, "created_at": at}

    pulls = {
        10: pull(10, "me", inside),  # mine, opened inside the window
        11: pull(11, "sam", before, merged_at=inside),  # sam's, merged by me
        12: pull(12, "sam", before),  # sam's, I only reviewed and commented
        13: pull(13, "me", before),  # mine, but nothing I did falls inside
    }
    timelines = {
        10: [event("renamed", "me", inside), event("renamed", "sam", inside)],
        11: [event("merged", "me", inside), event("reviewed", "me", inside)],
        12: [event("commented", "me", inside), {"event": "reviewed", "user": {"login": "me"}, "submitted_at": inside}],
        13: [event("renamed", "me", after)],
    }
    pr_commits = {
        10: [commit("a1", "me", inside, "first\n\nbody"), commit("a2", "sam", inside)],
        11: [commit("b1", "sam", inside)],
        12: [],
        13: [commit("d1", "me", before)],
    }
    calls = []

    def fake(method, url, headers, **kwargs):
        calls.append(url)
        path = url.split("?")[0]
        if path.endswith("/rest/api/2/myself"):
            return {"accountId": "acc-me"}
        if path.endswith("/rest/api/3/search/jql"):
            return {"issues": [{"key": k, "fields": {"summary": k, "status": {"name": "Done"}}} for k in changelogs]}
        if "/changelog" in path:
            return {"values": changelogs[path.split("/issue/")[1].split("/")[0]], "isLast": True}
        if path.endswith("/user"):
            return {"login": "me"}
        if path.endswith("/search/issues"):
            numbers = [10, 12, 13] if "involves" in url else [11]
            return {
                "items": [{"repository_url": "https://api.github.com/repos/owner/name", "number": n} for n in numbers]
            }
        number = (
            int(re.search(r"/(?:pulls|issues)/(\d+)", path).group(1))
            if re.search(r"/(?:pulls|issues)/\d+", path)
            else None
        )
        if path.endswith("/timeline"):
            return timelines[number]
        if path.endswith(f"/pulls/{number}/commits"):
            return pr_commits[number]
        if number:
            return pulls[number]
        if path.endswith("/repos/owner/name/commits"):
            return [commit("m1", "me", inside), commit("m2", "sam", inside)]
        raise AssertionError(url)

    monkeypatch.setattr(ticket_pr, "http_json", fake)
    ticket_pr.main(["activity", "--since", "2026-09-01", "--until", "2026-09-07", "--repo", "github:owner/name"])
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    assert [t["key"] for t in result["tickets"]] == ["ACME-1"]
    assert result["tickets"][0]["moves"] == [
        {"at": "2026-09-02T10:00:00.000+0000", "from": "Open", "to": "In Progress"}
    ]
    assert {p["pr"]: [a["event"] for a in p["actions"]] for p in result["prs"]} == {
        10: ["opened", "renamed"],
        11: ["merged"],
    }
    assert [c["sha"] for c in result["prs"][0]["commits"]] == ["a1"]
    assert result["prs"][0]["commits"][0]["message"] == "first"
    assert result["prs"][1]["state"] == "merged"
    assert [c["sha"] for c in result["commits"]] == ["m1"]
    commits_url = next(u for u in calls if "/repos/owner/name/commits?" in u)
    assert "author=me" in commits_url and "since=" in commits_url and "until=" in commits_url
    jql = next(u for u in calls if "/search/jql" in u)
    assert "currentUser" in jql


def test_search_queries_split_to_stay_under_the_cap():
    repos = [f"owner/repository-number-{n:02d}" for n in range(15)]
    queries = ticket_pr.search_queries("is:pr involves:me updated:2026-09-01..2026-09-08", repos)
    assert len(queries) > 1
    assert all(len(q) <= ticket_pr.SEARCH_QUERY_LIMIT for q in queries)
    assert all(q.startswith("is:pr involves:me") for q in queries)
    assert sorted(re.findall(r"repo:(\S+)", " ".join(queries))) == sorted(repos)
