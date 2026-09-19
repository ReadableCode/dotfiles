"""Unit tests for src/sweep_worktrees.py — classifying T3 thread worktrees and picking candidates."""

import os
import sqlite3

import config_test_utils  # noqa F401
import pytest

from src import sweep_worktrees

# ---------------------------------------------------------------- helpers

SCHEMA = """
CREATE TABLE projection_threads (
  thread_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, branch TEXT, worktree_path TEXT,
  created_at TEXT, updated_at TEXT, deleted_at TEXT, settled_override TEXT, settled_at TEXT);
CREATE TABLE projection_thread_sessions (
  thread_id TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT);
"""


def make_db(path, threads):
    """threads: list of (thread_id, title, branch, worktree_path, deleted_at, settled_at, override, status)."""
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    for thread_id, title, branch, worktree, deleted, settled, override, status in threads:
        connection.execute(
            "INSERT INTO projection_threads (thread_id, title, branch, worktree_path, deleted_at,"
            " settled_at, settled_override) VALUES (?,?,?,?,?,?,?)",
            (thread_id, title, branch, worktree, deleted, settled, override),
        )
        if status:
            connection.execute(
                "INSERT INTO projection_thread_sessions (thread_id, status) VALUES (?,?)", (thread_id, status)
            )
    connection.commit()
    connection.close()
    return path


# ---------------------------------------------------------------- thread_state


@pytest.mark.parametrize(
    "deleted, settled, override, status, expected",
    [
        (None, None, None, "stopped", "unsettled"),
        (None, "2026-09-11T00:00:00Z", None, "stopped", "settled"),
        (None, None, "settled", "stopped", "settled"),
        ("2026-09-11T00:00:00Z", None, None, "stopped", "deleted"),
        (None, "2026-09-11T00:00:00Z", None, "running", "active"),
        (None, None, None, "ready", "active"),
        ("2026-09-11T00:00:00Z", None, None, "running", "active"),
        (None, "2026-09-11T00:00:00Z", "unsettled", "stopped", "unsettled"),
    ],
)
def test_thread_state_precedence(deleted, settled, override, status, expected):
    """A live session outranks everything; a re-opened thread beats its own stale settled_at."""
    assert sweep_worktrees.thread_state(deleted, settled, override, status) == expected


# ---------------------------------------------------------------- thread_states


def test_thread_states_reads_the_projection(tmp_path):
    db = make_db(
        str(tmp_path / "state.sqlite"),
        [("abcdef1234", "a title", "t3code/x", str(tmp_path / "wt"), None, None, None, "stopped")],
    )
    states = sweep_worktrees.thread_states(db)
    entry = states[os.path.realpath(str(tmp_path / "wt"))]
    assert entry == {"thread": "abcdef12", "title": "a title", "branch": "t3code/x", "state": "unsettled"}


def test_thread_states_is_none_without_a_database(tmp_path):
    """No T3 on this machine means no verdicts at all, which is what makes everything `unknown`."""
    assert sweep_worktrees.thread_states(str(tmp_path / "nope.sqlite")) is None


def test_thread_states_ignores_threads_with_no_worktree(tmp_path):
    db = make_db(str(tmp_path / "state.sqlite"), [("a", "no worktree", None, None, None, None, None, "stopped")])
    assert sweep_worktrees.thread_states(db) == {}


# ---------------------------------------------------------------- discover


def test_discover_finds_repo_slash_id_only(tmp_path):
    for relpath in ("repo_a/t3code-1", "repo_a/t3code-2", "repo_b/t3code-3"):
        os.makedirs(tmp_path / relpath)
    (tmp_path / "loose_file").write_text("", encoding="utf-8")
    found = sweep_worktrees.discover(str(tmp_path))
    assert [os.path.relpath(path, tmp_path) for path in found] == [
        "repo_a/t3code-1",
        "repo_a/t3code-2",
        "repo_b/t3code-3",
    ]


def test_discover_tolerates_a_missing_root(tmp_path):
    assert sweep_worktrees.discover(str(tmp_path / "gone")) == []


# ---------------------------------------------------------------- survey


@pytest.fixture
def stub_git(monkeypatch):
    """main_checkout always resolves; unpushed_work is controlled per test."""
    monkeypatch.setattr(sweep_worktrees.init_worktree, "main_checkout", lambda path: "/main")
    monkeypatch.setattr(sweep_worktrees.init_worktree, "unpushed_work", lambda path: [])


def test_survey_marks_settled_deleted_and_orphan_as_candidates(tmp_path, monkeypatch, stub_git):
    monkeypatch.setattr(sweep_worktrees, "WORKTREES_ROOT", str(tmp_path))
    paths = {name: os.path.realpath(str(tmp_path / "repo" / name)) for name in ("s", "d", "o", "u", "a")}
    states = {
        paths["s"]: {"thread": "1", "title": "", "branch": "", "state": "settled"},
        paths["d"]: {"thread": "2", "title": "", "branch": "", "state": "deleted"},
        paths["u"]: {"thread": "3", "title": "", "branch": "", "state": "unsettled"},
        paths["a"]: {"thread": "4", "title": "", "branch": "", "state": "active"},
    }
    rows = {row["path"]: row for row in sweep_worktrees.survey(list(paths.values()), states)}
    assert rows[paths["s"]]["candidate"] is True
    assert rows[paths["d"]]["candidate"] is True
    assert rows[paths["o"]]["state"] == "orphan" and rows[paths["o"]]["candidate"] is True
    assert rows[paths["u"]]["candidate"] is False
    assert rows[paths["a"]]["candidate"] is False


def test_survey_without_a_database_makes_nothing_a_candidate(tmp_path, monkeypatch, stub_git):
    """`unknown` is deliberately not sweepable: with no thread state, only a named path may go."""
    monkeypatch.setattr(sweep_worktrees, "WORKTREES_ROOT", str(tmp_path))
    rows = sweep_worktrees.survey([os.path.realpath(str(tmp_path / "repo" / "x"))], None)
    assert rows[0]["state"] == "unknown"
    assert rows[0]["candidate"] is False


def test_survey_flags_a_candidate_holding_unpushed_work(tmp_path, monkeypatch, stub_git):
    monkeypatch.setattr(sweep_worktrees, "WORKTREES_ROOT", str(tmp_path))
    monkeypatch.setattr(sweep_worktrees.init_worktree, "unpushed_work", lambda path: ["2 uncommitted change(s)"])
    path = os.path.realpath(str(tmp_path / "repo" / "s"))
    states = {path: {"thread": "1", "title": "", "branch": "", "state": "settled"}}
    row = sweep_worktrees.survey([path], states)[0]
    assert row["candidate"] is True and row["blocked"] == ["2 uncommitted change(s)"]


def test_survey_marks_a_non_worktree_directory_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep_worktrees, "WORKTREES_ROOT", str(tmp_path))

    def explode(path):
        raise RuntimeError("not a git worktree")

    monkeypatch.setattr(sweep_worktrees.init_worktree, "main_checkout", explode)
    row = sweep_worktrees.survey([os.path.realpath(str(tmp_path / "repo" / "x"))], {})[0]
    assert row["state"] == "unknown" and row["candidate"] is False


# ---------------------------------------------------------------- output


def test_render_names_every_worktree_and_its_verdict(tmp_path, monkeypatch, stub_git):
    monkeypatch.setattr(sweep_worktrees, "WORKTREES_ROOT", str(tmp_path))
    path = os.path.realpath(str(tmp_path / "repo" / "t3code-1"))
    states = {path: {"thread": "1", "title": "a thread", "branch": "", "state": "unsettled"}}
    text = sweep_worktrees.render(sweep_worktrees.survey([path], states), color=False)
    assert "repo/t3code-1" in text and "unsettled" in text and "a thread" in text


def test_advice_sends_an_unsettled_thread_back_to_its_own_thread(tmp_path, monkeypatch, stub_git):
    monkeypatch.setattr(sweep_worktrees, "WORKTREES_ROOT", str(tmp_path))
    path = os.path.realpath(str(tmp_path / "repo" / "t3code-1"))
    states = {path: {"thread": "1", "title": "", "branch": "", "state": "unsettled"}}
    text = sweep_worktrees.advice(sweep_worktrees.survey([path], states), color=False)
    assert "/remove_worktree" in text and "not swept" in text


def test_advice_is_empty_when_every_worktree_is_a_clean_candidate(tmp_path, monkeypatch, stub_git):
    monkeypatch.setattr(sweep_worktrees, "WORKTREES_ROOT", str(tmp_path))
    path = os.path.realpath(str(tmp_path / "repo" / "t3code-1"))
    states = {path: {"thread": "1", "title": "", "branch": "", "state": "settled"}}
    assert sweep_worktrees.advice(sweep_worktrees.survey([path], states), color=False) == ""
