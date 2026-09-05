"""Unit tests for src/ticket_pr.py — no network, no credentials."""

import json

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
        ["--dry-run", "create-ticket", "--project", "FFF", "--summary", "Test ticket"],
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
        "?fields=summary,status,assignee,issuetype,description"
    ) in out


def test_get_ticket_reports_description(monkeypatch, capsys):
    monkeypatch.setenv("JIRA_SERVER", "example.atlassian.net")
    monkeypatch.setenv("JIRA_USER", "user@example.com")
    monkeypatch.setenv("JIRA_TOKEN", "token")
    issue = {
        "key": "ACME-401",
        "fields": {
            "summary": "Fix the thing",
            "status": {"name": "In Progress"},
            "issuetype": {"name": "Bug"},
            "assignee": {"displayName": "Sam"},
            "description": "Steps:\n1. run it\n2. watch it break",
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
    ticket_pr.main(["get-ticket", "--key", "ACME-401"])
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "ACME-401 [In Progress] Fix the thing (2 comments)"
    result = json.loads(out.strip().splitlines()[-1])
    assert result == {
        "key": "ACME-401",
        "summary": "Fix the thing",
        "status": "In Progress",
        "type": "Bug",
        "assignee": "Sam",
        "description": "Steps:\n1. run it\n2. watch it break",
        "comments": [
            {"author": "Alex", "created": "2026-09-01T10:00:00.000+0000", "body": "Repro attached"},
            {"author": "Sam", "created": "2026-09-02T10:00:00.000+0000", "body": "On it"},
        ],
        "url": "https://example.atlassian.net/browse/ACME-401",
    }
    assert sum("/comment?" in c for c in calls) == 2


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
    monkeypatch.setattr(ticket_pr, "git_output", lambda *a: "FFF-0-test-branch")
    out = _run_cli(
        ["--dry-run", "create-pr", "--repo", "owner/name", "--title", "FFF-0 Test"],
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
