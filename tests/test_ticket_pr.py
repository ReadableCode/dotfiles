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
        "git@github.com:hellofresh/na-finops.git",
        "https://github.com/hellofresh/na-finops.git",
        "https://github.com/hellofresh/na-finops",
        "ssh://git@github.com/hellofresh/na-finops.git",
    ],
)
def test_resolve_repo_parses_origin_urls(monkeypatch, url):
    monkeypatch.setattr(ticket_pr, "git_output", lambda *a: url)
    assert ticket_pr.resolve_repo(None) == "hellofresh/na-finops"


def test_resolve_repo_explicit_wins(monkeypatch):
    monkeypatch.setattr(
        ticket_pr, "git_output", lambda *a: pytest.fail("should not call git")
    )
    assert ticket_pr.resolve_repo("owner/name") == "owner/name"


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
            "csmith1133",
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
