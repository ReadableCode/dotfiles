# %%
# Imports #

import json
import os
import re

import config_test_utils  # noqa F401
import pytest
import yaml
from utils import statusboard_tools

# %%
# Helpers #


def write_yaml(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        yaml.safe_dump(payload, file_handle)
    return path


def make_credentials_repo(root, context, panels=None, hosts=None):
    """Create a fake <context>_credentials repo with optional statusboard config and inventory."""
    repo = os.path.join(str(root), f"{context}_credentials")
    os.makedirs(repo, exist_ok=True)
    if panels is not None:
        write_yaml(os.path.join(repo, f"{context}_statusboard.yaml"), panels)
    if hosts is not None:
        with open(os.path.join(repo, f"{context}_hosts.json"), "w", encoding="utf-8") as file_handle:
            json.dump({"hosts": hosts}, file_handle)
    return repo


SSH_PANEL = {"name": "vm_jobs", "type": "ssh_command", "host": "sshvm", "jump": "LAPTOP-1", "command": "bash x.sh"}
ACME_HOSTS = [
    {"name": "LAPTOP-1", "hostname": "10.0.0.10", "user": "jdoe", "port": 2222, "aliases": ["jump1"]},
    {"name": "vm-01", "hostname": "10.0.0.20", "user": "svc_acme", "aliases": ["sshvm"]},
]


# %%
# Discovery / loading #


def test_discover_finds_overlays_and_repo_root_config(tmp_path):
    make_credentials_repo(tmp_path, "acme", panels=[])
    make_credentials_repo(tmp_path, "empty")  # no config -> contributes nothing
    repo_root = os.path.join(str(tmp_path), "dotfiles")
    write_yaml(os.path.join(repo_root, "statusboard.yaml"), [])
    configs = statusboard_tools.discover_statusboard_configs(str(tmp_path), repo_root)
    assert [os.path.basename(path) for path, _ in configs] == ["statusboard.yaml", "acme_statusboard.yaml"]


def test_load_panels_stamps_base_dir_and_defaults_interval(tmp_path):
    repo = make_credentials_repo(tmp_path, "acme", panels=[SSH_PANEL])
    panels, config_paths = statusboard_tools.load_panels(str(tmp_path))
    assert len(panels) == 1 and len(config_paths) == 1
    assert panels[0]["_base_dir"] == repo
    assert panels[0]["interval"] == statusboard_tools.DEFAULT_INTERVALS["ssh_command"]


def test_load_panels_rejects_duplicate_names(tmp_path):
    github_panel = {"name": "vm_jobs", "type": "github_prs", "token_env": "T"}
    make_credentials_repo(tmp_path, "aaa", panels=[SSH_PANEL])
    make_credentials_repo(tmp_path, "bbb", panels=[github_panel])
    with pytest.raises(ValueError, match="Duplicate statusboard panel name 'vm_jobs'"):
        statusboard_tools.load_panels(str(tmp_path))


@pytest.mark.parametrize(
    "panel, match",
    [
        ({"name": "x", "type": "nope"}, "unknown type"),
        ({"name": "x", "type": "ssh_command", "host": "h"}, "missing required keys: command"),
        ({"name": "x", "type": "github_prs"}, "missing required keys: token_env"),
        ({"name": "x", "type": "bitbucket_prs", "workspace": "w"}, "missing required keys"),
        ({"type": "ssh_command"}, "'name' and 'type'"),
    ],
)
def test_panel_validation(tmp_path, panel, match):
    make_credentials_repo(tmp_path, "acme", panels=[panel])
    with pytest.raises(ValueError, match=match):
        statusboard_tools.load_panels(str(tmp_path))


GOOD_LOG_LINK = {"pattern": r"^\S+ +(\S+)", "command": "tail -F ~/logs/{job}.log"}


@pytest.mark.parametrize(
    "log_link, match",
    [
        ("nope", "mapping with 'pattern' and 'command'"),
        ({"pattern": r"(\S+)"}, "mapping with 'pattern' and 'command'"),
        ({"pattern": "(", "command": "tail {job}"}, "does not compile"),
        ({"pattern": r"\S+", "command": "tail {job}"}, "needs a capture group"),
        ({"pattern": r"(\S+)", "command": "tail x.log"}, "must contain a {job} placeholder"),
    ],
)
def test_log_link_validation(tmp_path, log_link, match):
    make_credentials_repo(tmp_path, "acme", panels=[dict(SSH_PANEL, log_link=log_link)])
    with pytest.raises(ValueError, match=re.escape(match)):
        statusboard_tools.load_panels(str(tmp_path))


def test_log_link_only_on_ssh_command(tmp_path):
    panel = {"name": "x", "type": "github_prs", "token_env": "T", "log_link": GOOD_LOG_LINK}
    make_credentials_repo(tmp_path, "acme", panels=[panel])
    with pytest.raises(ValueError, match="only supported on ssh_command"):
        statusboard_tools.load_panels(str(tmp_path))


def test_log_link_valid_loads(tmp_path):
    make_credentials_repo(tmp_path, "acme", panels=[dict(SSH_PANEL, log_link=GOOD_LOG_LINK)])
    panels, _ = statusboard_tools.load_panels(str(tmp_path))
    assert panels[0]["log_link"] == GOOD_LOG_LINK


def test_load_panels_single_config_escape_hatch(tmp_path):
    config_path = write_yaml(os.path.join(str(tmp_path), "solo.yaml"), [SSH_PANEL])
    panels, config_paths = statusboard_tools.load_panels("/nonexistent", config_path=config_path)
    assert config_paths == [config_path]
    assert panels[0]["_base_dir"] == str(tmp_path)


# %%
# Host resolution / ssh argv #


def test_find_host_matches_name_and_alias_case_insensitive(tmp_path):
    repo = make_credentials_repo(tmp_path, "acme", hosts=ACME_HOSTS)
    assert statusboard_tools.find_host("SSHVM", repo, str(tmp_path))["hostname"] == "10.0.0.20"
    assert statusboard_tools.find_host("laptop-1", repo, str(tmp_path))["port"] == 2222


def test_find_host_searches_other_inventories(tmp_path):
    make_credentials_repo(tmp_path, "aaa", hosts=ACME_HOSTS)
    other = make_credentials_repo(tmp_path, "bbb", hosts=[])
    assert statusboard_tools.find_host("sshvm", other, str(tmp_path))["user"] == "svc_acme"


def test_find_host_unknown_raises(tmp_path):
    repo = make_credentials_repo(tmp_path, "acme", hosts=ACME_HOSTS)
    with pytest.raises(ValueError, match="Host 'ghost' not found"):
        statusboard_tools.find_host("ghost", repo, str(tmp_path))


def test_build_ssh_argv_with_jump_and_ports(tmp_path):
    repo = make_credentials_repo(tmp_path, "acme", hosts=ACME_HOSTS)
    panel = dict(SSH_PANEL, _base_dir=repo)
    argv = statusboard_tools.build_ssh_argv(panel, str(tmp_path), local_hostname="ENVY")
    assert argv[0] == "ssh"
    assert argv[argv.index("-J") + 1] == "jdoe@10.0.0.10:2222"
    assert argv[-2:] == ["svc_acme@10.0.0.20", "bash x.sh"]


def test_build_ssh_argv_skips_jump_when_running_on_jump_host(tmp_path):
    repo = make_credentials_repo(tmp_path, "acme", hosts=ACME_HOSTS)
    panel = dict(SSH_PANEL, _base_dir=repo)
    argv = statusboard_tools.build_ssh_argv(panel, str(tmp_path), local_hostname="LAPTOP-1.local")
    assert "-J" not in argv


def test_build_ssh_argv_command_override(tmp_path):
    repo = make_credentials_repo(tmp_path, "acme", hosts=ACME_HOSTS)
    panel = dict(SSH_PANEL, _base_dir=repo)
    argv = statusboard_tools.build_ssh_argv(
        panel, str(tmp_path), local_hostname="ENVY", command="tail -F ~/logs/git_pull.log"
    )
    # same chain as the panel's own fetch, only the remote command differs
    assert argv[argv.index("-J") + 1] == "jdoe@10.0.0.10:2222"
    assert argv[-2:] == ["svc_acme@10.0.0.20", "tail -F ~/logs/git_pull.log"]


def test_build_ssh_argv_target_port(tmp_path):
    hosts = [{"name": "boxy", "hostname": "10.0.0.5", "user": "me", "port": 2200}]
    repo = make_credentials_repo(tmp_path, "acme", hosts=hosts)
    panel = {"name": "p", "type": "ssh_command", "host": "boxy", "command": "uptime", "_base_dir": repo}
    argv = statusboard_tools.build_ssh_argv(panel, str(tmp_path))
    assert argv[argv.index("-p") + 1] == "2200"
    assert "-J" not in argv


# %%
# Secrets #


def test_resolve_secret_environment_wins(tmp_path, monkeypatch):
    env_file = os.path.join(str(tmp_path), "x.env")
    with open(env_file, "w", encoding="utf-8") as file_handle:
        file_handle.write("MY_TOKEN=from_file\n")
    panel = {"name": "p", "token_env": "MY_TOKEN", "env_file": "x.env", "_base_dir": str(tmp_path)}
    monkeypatch.setenv("MY_TOKEN", "from_env")
    assert statusboard_tools.resolve_secret(panel, "token_env") == "from_env"
    monkeypatch.delenv("MY_TOKEN")
    assert statusboard_tools.resolve_secret(panel, "token_env") == "from_file"


def test_resolve_secret_missing_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("MY_TOKEN", raising=False)
    panel = {"name": "p", "token_env": "MY_TOKEN", "_base_dir": str(tmp_path)}
    with pytest.raises(ValueError, match="MY_TOKEN is not set"):
        statusboard_tools.resolve_secret(panel, "token_env")


# %%
# Fetch dispatch #


def test_fetch_panel_never_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("NOPE_TOKEN", raising=False)
    panel = {"name": "p", "type": "github_prs", "token_env": "NOPE_TOKEN", "_base_dir": str(tmp_path)}
    result = statusboard_tools.fetch_panel(panel, str(tmp_path))
    assert result.ok is False
    assert "NOPE_TOKEN" in result.body


# %%
# Browser launch argv #


def test_browser_open_argv():
    from src.status_board import browser_open_argv

    url = "https://github.com/x/y/pull/1"
    assert browser_open_argv(None, url) is None
    assert browser_open_argv("edge", url, system="Darwin") == ["open", "-a", "Microsoft Edge", url]
    assert browser_open_argv("Edge", url, system="Windows") == ["cmd", "/c", "start", "", "msedge", url]
    assert browser_open_argv("chrome", url, system="Linux") == ["google-chrome", url]
    # unknown names pass through as the app/binary name
    assert browser_open_argv("Brave Browser", url, system="Darwin") == ["open", "-a", "Brave Browser", url]


# %%
# Log-link row marking #


def test_mark_log_links_marks_job_tokens():
    from rich.text import Text
    from src.status_board import mark_log_links

    board = (
        "cron job status  (2026-07-22)\n"
        "● FAIL  git_pull      5m ago\n"
        "● ok    hme_ingest    2h ago\n"
        "3 ok · 1 failed\n"
    )
    text = mark_log_links(Text(board), {"pattern": r"^● \S+ +(\S+)", "command": "tail -F {job}"}, "vm_jobs")
    clicks = [
        (text.plain[span.start:span.end], span.style.meta["@click"])
        for span in text.spans
        if getattr(span.style, "meta", {}).get("@click")
    ]
    assert clicks == [
        ("git_pull", "app.view_log('vm_jobs', 'git_pull')"),
        ("hme_ingest", "app.view_log('vm_jobs', 'hme_ingest')"),
    ]
    # header and summary lines stay plain
    assert all(job in ("git_pull", "hme_ingest") for job, _ in clicks)


# %%

# %%
# GitHub PR classification #


def gh_item(repo, number, author="alice"):
    return {
        "html_url": f"https://github.com/{repo}/pull/{number}",
        "repository_url": f"https://api.github.com/repos/{repo}",
        "number": number,
        "title": f"PR {number}",
        "user": {"login": author},
        "updated_at": "2026-07-15T12:00:00Z",
    }


def test_classify_github_prs_buckets_and_order():
    fresh = gh_item("acme/app", 1)                # requested, no review from me -> needs review
    blocked = gh_item("acme/app", 2)              # requested again, but my latest review = CR -> on author
    reviewed_cr = gh_item("acme/app", 3)          # not requested anymore, my review = CR -> on author
    soft = gh_item("acme/app", 4)                 # only commented -> soft bucket
    approved = gh_item("acme/app", 5)             # I approved, nothing pending -> dropped
    my_open = gh_item("acme/app", 6, author="me")
    states = {
        blocked["html_url"]: {"me": "CHANGES_REQUESTED"},
        reviewed_cr["html_url"]: {"me": "CHANGES_REQUESTED"},
        soft["html_url"]: {"me": "COMMENTED"},
        approved["html_url"]: {"me": "APPROVED"},
        my_open["html_url"]: {"bob": "APPROVED"},
    }
    rows, summary = statusboard_tools.classify_github_prs(
        "me", [fresh, blocked], [reviewed_cr, soft, approved], [my_open], states
    )
    assert [(r["badge"], r["url"]) for r in rows] == [
        ("●", fresh["html_url"]),
        ("✋", blocked["html_url"]),
        ("✋", reviewed_cr["html_url"]),
        ("💬", soft["html_url"]),
        ("⬆", my_open["html_url"]),
    ]
    assert summary == "1 to review · 2 on author · 1 yours"
    assert "your PR · ✓ approved" in rows[-1]["meta"]


def test_classify_github_prs_own_pr_verdicts():
    pr = gh_item("acme/app", 7, author="me")
    for others, verdict in [
        ({"bob": "CHANGES_REQUESTED", "eve": "APPROVED"}, "✗ changes requested"),
        ({"bob": "APPROVED"}, "✓ approved"),
        ({}, "⧗ awaiting review"),
        ({"me": "COMMENTED"}, "⧗ awaiting review"),  # my own comments don't count
    ]:
        rows, _ = statusboard_tools.classify_github_prs("me", [], [], [pr], {pr["html_url"]: others})
        assert verdict in rows[0]["meta"]


def test_classify_github_prs_dedups_requested_and_reviewed():
    pr = gh_item("acme/app", 8)
    rows, summary = statusboard_tools.classify_github_prs("me", [pr], [pr], [], {})
    assert len(rows) == 1
    assert summary == "1 to review · 0 on author · 0 yours"


# %%

def test_classify_github_prs_flags_unsubmitted_draft_first():
    draft = gh_item("acme/app", 9)
    fresh = gh_item("acme/app", 10)
    states = {draft["html_url"]: {"me": "PENDING"}}
    rows, summary = statusboard_tools.classify_github_prs("me", [fresh, draft], [], [], states)
    assert [(r["badge"], r["url"]) for r in rows] == [("✏", draft["html_url"]), ("●", fresh["html_url"])]
    assert summary.startswith("1 UNSUBMITTED · 1 to review")
    assert "author can't see it" in rows[0]["meta"]


def test_classify_github_prs_parks_all_drafts_last():
    my_draft = dict(gh_item("acme/app", 11, author="me"), draft=True)
    their_draft = dict(gh_item("acme/app", 12), draft=True)  # even with my review requested
    fresh = gh_item("acme/app", 13)
    rows, summary = statusboard_tools.classify_github_prs("me", [their_draft, fresh], [], [my_draft], {})
    assert [(r["badge"], r["url"]) for r in rows] == [
        ("●", fresh["html_url"]),
        ("◌", their_draft["html_url"]),
        ("◌", my_draft["html_url"]),
    ]
    assert all(r["dim"] for r in rows if r["badge"] == "◌")
    assert summary == "1 to review · 0 on author · 0 yours · 2 parked"


def test_classify_github_prs_rerequest_returns_to_needs_review():
    pr = gh_item("acme/app", 14)
    states = {pr["html_url"]: {"me": "CHANGES_REQUESTED"}}
    # not personally re-requested (e.g. team request) -> still waiting on author
    rows, _ = statusboard_tools.classify_github_prs("me", [pr], [], [], states)
    assert rows[0]["badge"] == "✋"
    # author explicitly re-requested me -> back to needs review, round two
    rows, summary = statusboard_tools.classify_github_prs("me", [pr], [], [], states, {pr["html_url"]})
    assert rows[0]["badge"] == "●"
    assert "re-requested after your changes" in rows[0]["meta"]
    assert summary == "1 to review · 0 on author · 0 yours"


def test_classify_github_prs_pushed_since_returns_to_needs_review():
    pr = gh_item("acme/app", 15)
    states = {pr["html_url"]: {"me": "CHANGES_REQUESTED"}}
    # head moved past the sha my review was submitted against -> back to needs review
    rows, summary = statusboard_tools.classify_github_prs(
        "me", [], [pr], [], states, updated_since={pr["html_url"]}
    )
    assert rows[0]["badge"] == "●"
    assert "updated since your changes" in rows[0]["meta"]
    assert summary == "1 to review · 0 on author · 0 yours"
    # an explicit re-request wins over the pushed-since signal
    rows, _ = statusboard_tools.classify_github_prs(
        "me", [pr], [], [], states, {pr["html_url"]}, {pr["html_url"]}
    )
    assert "re-requested after your changes" in rows[0]["meta"]


def test_pr_review_states_tracks_commit_ids(monkeypatch):
    reviews = [
        {"user": {"login": "me"}, "state": "CHANGES_REQUESTED", "commit_id": "aaa111"},
        {"user": {"login": "bob"}, "state": "APPROVED", "commit_id": "bbb222"},
        {"user": {"login": "eve"}, "state": "COMMENTED", "commit_id": "ccc333"},
        {"user": {"login": "eve"}, "state": "DISMISSED", "commit_id": "ddd444"},
    ]

    class FakeResponse:
        status_code = 200

        def json(self):
            return reviews

    monkeypatch.setattr(statusboard_tools.requests, "get", lambda *a, **k: FakeResponse())
    states, commits = statusboard_tools._pr_review_states("https://api.github.com", {}, gh_item("acme/app", 16))
    assert states == {"me": "CHANGES_REQUESTED", "bob": "APPROVED"}
    assert commits == {"me": "aaa111", "bob": "bbb222"}


# %%
# Bitbucket PR classification #


def bb_pr(number, author_uuid="{alice}", participants=(), **extra):
    return dict(
        {
            "id": number,
            "title": f"PR {number}",
            "author": {"uuid": author_uuid, "display_name": "Alice"},
            "updated_on": "2026-07-15T12:00:00+00:00",
            "links": {"html": {"href": f"https://bitbucket.org/ws/repo/pull-requests/{number}"}},
            "participants": list(participants),
        },
        **extra,
    )


def test_classify_bitbucket_prs_buckets_and_order():
    me = "{me}"
    fresh = bb_pr(1)                                                              # reviewer, no vote -> needs review
    blocked = bb_pr(2, participants=[{"user": {"uuid": me}, "state": "changes_requested"}])
    approved = bb_pr(3, participants=[{"user": {"uuid": me}, "state": "approved"}])  # dropped
    my_open = bb_pr(4, author_uuid=me, participants=[{"user": {"uuid": "{bob}"}, "state": "approved"}])
    rows, summary = statusboard_tools.classify_bitbucket_prs(
        me, [("repo", fresh), ("repo", blocked), ("repo", approved), ("repo", my_open)]
    )
    assert [(r["badge"], r["url"]) for r in rows] == [
        ("●", fresh["links"]["html"]["href"]),
        ("✋", blocked["links"]["html"]["href"]),
        ("⬆", my_open["links"]["html"]["href"]),
    ]
    assert summary == "1 to review · 1 on author · 1 yours"
    assert "your PR · ✓ approved" in rows[-1]["meta"]
    assert rows[0]["text"] == "repo#1  PR 1"


def test_classify_bitbucket_prs_own_pr_verdicts():
    me = "{me}"
    for participants, verdict in [
        ([{"user": {"uuid": "{bob}"}, "state": "changes_requested"},
          {"user": {"uuid": "{eve}"}, "state": "approved"}], "✗ changes requested"),
        ([{"user": {"uuid": "{bob}"}, "state": "approved"}], "✓ approved"),
        ([], "⧗ awaiting review"),
        ([{"user": {"uuid": me}, "state": "approved"}], "⧗ awaiting review"),  # my own vote doesn't count
    ]:
        rows, _ = statusboard_tools.classify_bitbucket_prs(
            me, [("repo", bb_pr(5, author_uuid=me, participants=participants))]
        )
        assert verdict in rows[0]["meta"]


def test_classify_bitbucket_prs_parks_all_drafts_last():
    me = "{me}"
    my_draft = bb_pr(6, author_uuid=me, draft=True)
    their_draft = bb_pr(7, draft=True)
    fresh = bb_pr(8)
    rows, summary = statusboard_tools.classify_bitbucket_prs(
        me, [("repo", my_draft), ("repo", their_draft), ("repo", fresh)]
    )
    assert [(r["badge"], r["url"]) for r in rows] == [
        ("●", fresh["links"]["html"]["href"]),
        ("◌", my_draft["links"]["html"]["href"]),
        ("◌", their_draft["links"]["html"]["href"]),
    ]
    assert all(r["dim"] for r in rows if r["badge"] == "◌")
    assert summary == "1 to review · 0 on author · 0 yours · 2 parked"


def test_fetch_bitbucket_prs_queries_authored_and_reviewed(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def fake_get(url, **kwargs):
        calls.append((url, kwargs.get("params") or {}))
        if url.endswith("/user"):
            return FakeResponse({"uuid": "{me}"})
        return FakeResponse({"values": [bb_pr(9, author_uuid="{me}")]})

    monkeypatch.setattr(statusboard_tools.requests, "get", fake_get)
    monkeypatch.setattr(statusboard_tools, "resolve_secret", lambda panel, key: "x")
    result = statusboard_tools.fetch_bitbucket_prs(
        {"name": "bb", "type": "bitbucket_prs", "workspace": "ws", "repos": ["repo"],
         "username_env": "U", "app_password_env": "P"}
    )
    query = calls[-1][1]["q"]
    assert 'reviewers.uuid="{me}"' in query and 'author.uuid="{me}"' in query
    assert "participants" in calls[-1][1]["fields"]
    assert [row["badge"] for row in result.body] == ["⬆"]
    assert result.summary == "0 to review · 0 on author · 1 yours (ws)"


# %%
