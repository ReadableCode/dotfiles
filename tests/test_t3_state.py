"""Unit tests for src/t3_state.py — reading T3's v2 thread projection."""

import json
import os
import sqlite3

import config_test_utils  # noqa F401
import pytest

from src import t3_state

# ---------------------------------------------------------------- helpers

SCHEMA = """
CREATE TABLE orchestration_v2_projection_threads (
  thread_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, created_at TEXT, updated_at TEXT,
  archived_at TEXT, deleted_at TEXT, payload_json TEXT NOT NULL);
CREATE TABLE orchestration_v2_projection_provider_sessions (
  provider_session_id TEXT PRIMARY KEY, thread_id TEXT, provider TEXT, status TEXT, updated_at TEXT,
  payload_json TEXT);
"""


def make_db(path, threads, sessions=()):
    """threads: (thread_id, title, deleted_at, payload); sessions: (thread_id, status)."""
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    for thread_id, title, deleted, payload in threads:
        connection.execute(
            "INSERT INTO orchestration_v2_projection_threads (thread_id, title, deleted_at, payload_json)"
            " VALUES (?,?,?,?)",
            (thread_id, title, deleted, json.dumps(payload)),
        )
    for number, (thread_id, status) in enumerate(sessions):
        connection.execute(
            "INSERT INTO orchestration_v2_projection_provider_sessions (provider_session_id, thread_id, status)"
            " VALUES (?,?,?)",
            (f"session-{number}", thread_id, status),
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
        (None, None, None, None, "unsettled"),
    ],
)
def test_thread_state_precedence(deleted, settled, override, status, expected):
    """A live session outranks everything; a re-opened thread beats its own stale settled_at."""
    assert t3_state.thread_state(deleted, settled, override, status) == expected


# ---------------------------------------------------------------- thread_states


def test_thread_states_reads_the_v2_projection(tmp_path):
    db = make_db(
        str(tmp_path / "statev2.sqlite"),
        [("abcdef1234", "a title", None, {"worktreePath": str(tmp_path / "wt"), "branch": "t3code/x"})],
        sessions=[("abcdef1234", "stopped")],
    )
    states = t3_state.thread_states(db)
    entry = states[os.path.realpath(str(tmp_path / "wt"))]
    assert entry == {"thread": "abcdef12", "title": "a title", "branch": "t3code/x", "state": "unsettled"}


def test_thread_states_reads_settled_from_the_payload(tmp_path):
    db = make_db(
        str(tmp_path / "statev2.sqlite"),
        [("a", "done", None, {"worktreePath": str(tmp_path / "wt"), "settledAt": "2026-10-16T00:00:00Z"})],
    )
    assert t3_state.thread_states(db)[os.path.realpath(str(tmp_path / "wt"))]["state"] == "settled"


def test_thread_states_is_none_without_a_database(tmp_path):
    """No T3 on this machine means no verdicts at all, which is what makes everything `unknown`."""
    assert t3_state.thread_states(str(tmp_path / "nope.sqlite")) is None


def test_thread_states_ignores_threads_with_no_worktree(tmp_path):
    db = make_db(str(tmp_path / "statev2.sqlite"), [("a", "no worktree", None, {"worktreePath": None})])
    assert t3_state.thread_states(db) == {}


def test_a_thread_with_any_live_session_is_active(tmp_path):
    """Several sessions per thread: one running is enough, whatever order the join returns them in."""
    db = make_db(
        str(tmp_path / "statev2.sqlite"),
        [("a", "busy", None, {"worktreePath": str(tmp_path / "wt"), "settledAt": "2026-10-16T00:00:00Z"})],
        sessions=[("a", "running"), ("a", "stopped")],
    )
    assert t3_state.thread_states(db)[os.path.realpath(str(tmp_path / "wt"))]["state"] == "active"
