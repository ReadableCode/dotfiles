"""Unit tests for src/ticket_pr.py — no network, no credentials."""

import json
import re

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
    monkeypatch.setattr(
        ticket_pr, "git_output", lambda *a: pytest.fail("should not call git")
    )
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
    monkeypatch.setattr(
        ticket_pr, "git_output", lambda *a: "git@bitbucket.org:ws/slug.git"
    )
    assert ticket_pr.resolve_provider(None) == "bitbucket"
    monkeypatch.setattr(
        ticket_pr, "git_output", lambda *a: "git@github.com:owner/name.git"
    )
    assert ticket_pr.resolve_provider(None) == "github"


def test_resolve_provider_bitbucket_prefix(monkeypatch):
    monkeypatch.setattr(
        ticket_pr, "git_output", lambda *a: pytest.fail("should not call git")
    )
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
    assert report["ignored"] == [
        {"name": "Mergeable: HelloTech approval", "bucket": "pending"}
    ]


def test_rollup_carries_a_failed_checks_details():
    entries = [
        {"name": "SonarQube Code Analysis", "bucket": "fail",
         "details": {"details_url": "https://sonar/x", "title": "Quality Gate failed",
                     "summary": "2 new issues"}},
        {"name": "linter", "bucket": "pass", "details": {"details_url": None}},
    ]
    report = ticket_pr.rollup(entries, [])
    assert report["failed"] == ["SonarQube Code Analysis"]
    assert report["failed_details"] == [
        {"name": "SonarQube Code Analysis", "details_url": "https://sonar/x",
         "title": "Quality Gate failed", "summary": "2 new issues"}
    ]


def test_check_run_details_reads_output_and_link():
    run = {"details_url": "https://ci/run/1", "output": {"title": "t", "summary": "s"}}
    assert ticket_pr.check_run_details(run) == {"details_url": "https://ci/run/1",
                                                "title": "t", "summary": "s"}
    assert ticket_pr.check_run_details({}) == {"details_url": None, "title": None,
                                               "summary": None}


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
            "attachment": [{
                "filename": "layout.png", "mimeType": "image/png", "size": 3,
                "created": "2026-09-02T10:00:00.000+0000", "author": {"displayName": "Sam"},
                "content": "https://example.atlassian.net/rest/api/3/attachment/content/1"}],
        },
    }
    # two pages of one comment each: the walker must follow startAt to total
    pages = {
        "startAt=0": {"total": 2, "comments": [
            {"author": {"displayName": "Alex"}, "created": "2026-09-01T10:00:00.000+0000",
             "body": "Repro attached"}]},
        "startAt=1": {"total": 2, "comments": [
            {"author": {"displayName": "Sam"}, "created": "2026-09-02T10:00:00.000+0000",
             "body": "On it"}]},
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
    assert out.splitlines()[0] == (
        f"ACME-401 [In Progress] Fix the thing (2 comments, 1 attachments in {tmp_path})"
    )
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
        "attachments": [{
            "filename": "layout.png", "author": "Sam", "created": "2026-09-02T10:00:00.000+0000",
            "mime_type": "image/png", "size": 3, "path": str(saved)}],
        "url": "https://example.atlassian.net/browse/ACME-401",
    }
    assert sum("/comment?" in c for c in calls) == 2


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
        "key": "ACME-401", "id": "0",
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


def test_get_ticket_no_comments(monkeypatch, capsys):
    monkeypatch.setenv("JIRA_SERVER", "example.atlassian.net")
    monkeypatch.setenv("JIRA_USER", "user@example.com")
    monkeypatch.setenv("JIRA_TOKEN", "token")
    issue = {"key": "ACME-402", "fields": {"summary": "Quiet", "status": {"name": "To Do"}}}
    monkeypatch.setattr(
        ticket_pr, "http_json",
        lambda m, url, *a, **k: {"total": 0, "comments": []} if "/comment?" in url else issue,
    )
    ticket_pr.main(["get-ticket", "--key", "ACME-402"])
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "ACME-402 [To Do] Quiet (0 comments)"
    assert json.loads(out.strip().splitlines()[-1])["comments"] == []


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
    monkeypatch.setattr(
        ticket_pr, "git_output", lambda *a: pytest.fail("should not call git")
    )
    assert ticket_pr.repo_spec("github:owner/name") == ("github", "owner/name")
    assert ticket_pr.repo_spec("bitbucket:ws/slug") == ("bitbucket", "ws/slug")


def test_review_queue_defaults_to_the_origin_repo(monkeypatch, capsys):
    monkeypatch.setattr(ticket_pr, "git_output", lambda *a: "git@github.com:owner/name.git")
    out = _run_cli(["--dry-run", "review-queue"], monkeypatch, capsys)
    assert "[dry-run] would list open PRs in github:owner/name" in out


def _bb_pull(pr_id, title, author, reviewers, participants=(), draft=False):
    return {
        "id": pr_id, "title": title, "author": author, "reviewers": list(reviewers),
        "participants": list(participants), "draft": draft,
        "source": {"branch": {"name": f"ACME-{pr_id}"}}, "destination": {"branch": {"name": "master"}},
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
        1: None, 2: "own", 3: "not_requesting", 4: "draft", 5: "approved", 6: None,
    }
    assert result["prs"][5]["commits_since_my_approval"] == 1
    assert result["skipped"] == {"own": 1, "not_requesting": 1, "draft": 1, "approved": 1}
    assert "pull-requests/6 Approved, pushed to since (re-review: 1 commit(s) since your approval)" in out


def test_review_queue_github_needs_a_review_request(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")

    def pull(number, author, requested=(), draft=False):
        return {
            "number": number, "title": f"PR {number}", "user": {"login": author}, "draft": draft,
            "requested_reviewers": [{"login": login} for login in requested],
            "head": {"ref": f"b{number}"}, "base": {"ref": "main"},
            "html_url": f"https://github.com/owner/name/pull/{number}",
        }

    pulls = [pull(1, "sam", ["me"]), pull(2, "me"), pull(3, "sam"), pull(4, "sam", ["me"], draft=True)]
    monkeypatch.setattr(
        ticket_pr, "http_json",
        lambda m, url, h, **k: {"login": "me"} if url.endswith("/user") else pulls,
    )
    ticket_pr.main(["review-queue", "--repo", "github:owner/name"])
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert {pr["pr"]: pr["skip"] for pr in result["prs"]} == {
        1: None, 2: "own", 3: "not_requesting", 4: "draft",
    }


def test_pr_diff_bitbucket_writes_the_diff_and_file_stats(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("BITBUCKET_USER", "me@example.com")
    monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
    pull = {
        "id": 7, "title": "Add the thing", "author": {"display_name": "Sam"}, "description": "why",
        "source": {"branch": {"name": "ACME-7-thing"}, "commit": {"hash": "abc123"}},
        "destination": {"branch": {"name": "master"}},
        "links": {"html": {"href": "https://bitbucket.org/ws/slug/pull-requests/7"}},
    }
    diffstat = {"values": [
        {"status": "modified", "old": {"path": "src/a.py"}, "new": {"path": "src/a.py"},
         "lines_added": 3, "lines_removed": 1},
        {"status": "renamed", "old": {"path": "src/b.py"}, "new": {"path": "src/c.py"},
         "lines_added": 0, "lines_removed": 9},
    ]}
    fetched = []

    def fake_bytes(url, headers):
        fetched.append(url)
        return b"diff --git a/src/a.py b/src/a.py\n"

    monkeypatch.setattr(
        ticket_pr, "http_json", lambda m, url, h, **k: diffstat if url.endswith("/diffstat") else pull
    )
    monkeypatch.setattr(ticket_pr, "http_bytes", fake_bytes)
    out_path = tmp_path / "pr7.diff"
    ticket_pr.main(["pr-diff", "--repo", "bitbucket:ws/slug", "--pr", "7", "--out", str(out_path)])
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert fetched == ["https://api.bitbucket.org/2.0/repositories/ws/slug/pullrequests/7/diff"]
    assert out_path.read_bytes() == b"diff --git a/src/a.py b/src/a.py\n"
    assert result == {
        "pr": 7, "title": "Add the thing", "author": "Sam", "source": "ACME-7-thing",
        "destination": "master", "head": "abc123", "description": "why",
        "url": "https://bitbucket.org/ws/slug/pull-requests/7",
        "files": [
            {"path": "src/a.py", "status": "modified", "previous_path": None, "additions": 3, "deletions": 1},
            {"path": "src/c.py", "status": "renamed", "previous_path": "src/b.py", "additions": 0, "deletions": 9},
        ],
        "diff_path": str(out_path),
    }


def _record_http(monkeypatch, responses):
    calls = []

    def fake_http(method, url, headers, payload=None, **kwargs):
        calls.append((method, url, payload))
        return next(resp for suffix, resp in responses.items() if url.endswith(suffix))

    monkeypatch.setattr(ticket_pr, "http_json", fake_http)
    return calls


def test_pr_review_bitbucket_posts_the_comment_before_the_vote(monkeypatch, capsys):
    monkeypatch.setenv("BITBUCKET_USER", "me@example.com")
    monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
    calls = _record_http(monkeypatch, {"/comments": {"id": 55},
                                       "/request-changes": {"state": "changes_requested"}})
    ticket_pr.main(["pr-review", "--repo", "bitbucket:ws/slug", "--pr", "7",
                    "--action", "request-changes", "--body", "The banner prints too early."])
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
    calls = _record_http(monkeypatch, {"/reviews": {
        "state": "COMMENTED", "html_url": "https://github.com/owner/name/pull/12#pullrequestreview-1"}})
    ticket_pr.main(["pr-review", "--repo", "github:owner/name", "--pr", "12",
                    "--action", "comment", "--body", "Why the retry?"])
    assert calls == [("POST", "https://api.github.com/repos/owner/name/pulls/12/reviews",
                      {"event": "COMMENT", "body": "Why the retry?"})]
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["state"] == "COMMENTED"


def test_pr_review_rejects_an_empty_body(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    with pytest.raises(SystemExit, match="empty review body"):
        ticket_pr.main(["pr-review", "--repo", "github:owner/name", "--pr", "12",
                        "--action", "request-changes", "--body", "  "])


def test_review_commands_dry_run(monkeypatch, capsys):
    monkeypatch.setenv("BITBUCKET_USER", "me@example.com")
    monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
    out = _run_cli(["--dry-run", "review-queue", "--repo", "bitbucket:ws/slug"], monkeypatch, capsys)
    assert "[dry-run] would list open PRs in bitbucket:ws/slug" in out
    out = _run_cli(["--dry-run", "pr-diff", "--repo", "bitbucket:ws/slug", "--pr", "7"],
                   monkeypatch, capsys)
    assert json.loads(out.strip().splitlines()[-1])["dry_run"] is True
    out = _run_cli(["--dry-run", "pr-review", "--repo", "bitbucket:ws/slug", "--pr", "7",
                    "--action", "approve"], monkeypatch, capsys)
    assert "[dry-run] POST https://api.bitbucket.org/2.0/repositories/ws/slug/pullrequests/7/approve" in out
