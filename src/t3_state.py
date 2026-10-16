#!/usr/bin/env python3
"""Read T3 Code's own thread state: which thread owns a worktree, and whether it is finished.

The one reader of ``~/.t3/userdata/statev2.sqlite`` for every tool that acts on T3 threads:
``sweep_worktrees.py`` (which worktrees are leftovers) and ``jupyter_lab.py`` (when a thread's
JupyterLab server should stop). The database is T3's private schema, so every query against it
lives here and nowhere else.

T3 moved its state from ``state.sqlite`` to ``statev2.sqlite`` on 2026-10-16 (server 0.1.0). The
old file stays on disk, frozen at the migration, and the ``projection_threads`` /
``projection_thread_sessions`` tables inside the new one are the import of it, not updated since.
The live projection is ``orchestration_v2_projection_threads`` (settled, deleted and worktree
fields in ``payload_json``) joined to ``orchestration_v2_projection_provider_sessions`` for
whether a session is running right now.

Every connection is read-only through a ``file:`` URI, so a running T3 is never disturbed.
Stdlib-only (``sqlite3`` included), like its callers: a bare ``python3`` runs it before any venv
exists.
"""

import os
import sqlite3

STATE_DB = os.path.expanduser("~/.t3/userdata/statev2.sqlite")
# Session statuses that mean a thread is live in its worktree right now.
LIVE_SESSION = {"running", "ready"}
# Verdicts that mean the thread is done: nothing it started needs to keep running.
FINISHED = {"settled", "deleted"}

THREADS_QUERY = """
SELECT t.thread_id, t.title, t.deleted_at,
       json_extract(t.payload_json, '$.worktreePath'),
       json_extract(t.payload_json, '$.branch'),
       json_extract(t.payload_json, '$.settledAt'),
       json_extract(t.payload_json, '$.settledOverride'),
       s.status
FROM orchestration_v2_projection_threads t
LEFT JOIN orchestration_v2_projection_provider_sessions s ON s.thread_id = t.thread_id
"""


def connect(db_path=STATE_DB):
    """A read-only connection, or None when there is no database on this machine."""
    if not os.path.isfile(db_path):
        return None
    uri = "file:" + db_path.replace("?", "%3f").replace("#", "%23") + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=5)


def thread_state(deleted_at, settled_at, override, status):
    """One thread's verdict, most binding first: live session, then deleted, then settled."""
    if status in LIVE_SESSION:
        return "active"
    if deleted_at:
        return "deleted"
    if override == "unsettled":
        return "unsettled"
    if settled_at or override == "settled":
        return "settled"
    return "unsettled"


def _threads(connection, where="", params=()):
    """thread_id -> {title, worktree, branch, state}; a thread with several sessions is active if any is."""
    threads = {}
    for thread_id, title, deleted_at, worktree, branch, settled_at, override, status in connection.execute(
        THREADS_QUERY + where, params
    ):
        state = thread_state(deleted_at, settled_at, override, status)
        if threads.get(thread_id, {}).get("state") == "active":
            continue
        threads[thread_id] = {"title": title or "", "worktree": worktree, "branch": branch or "", "state": state}
    return threads


def thread_states(db_path=STATE_DB):
    """Map realpath(worktree) -> {thread, title, branch, state} for every thread with a worktree.

    Returns None when there is no database on this machine, which is what makes every worktree
    `unknown` to the sweep.
    """
    connection = connect(db_path)
    if connection is None:
        return None
    try:
        threads = _threads(connection, "WHERE json_extract(t.payload_json, '$.worktreePath') IS NOT NULL")
    finally:
        connection.close()
    return {
        os.path.realpath(entry["worktree"]): {
            "thread": thread_id[:8],
            "title": entry["title"],
            "branch": entry["branch"],
            "state": entry["state"],
        }
        for thread_id, entry in threads.items()
    }


def thread_verdict(thread_id, db_path=STATE_DB):
    """One thread's verdict by id: `deleted` when T3 no longer has it, None when there is no database."""
    connection = connect(db_path)
    if connection is None:
        return None
    try:
        threads = _threads(connection, "WHERE t.thread_id = ?", (thread_id,))
    finally:
        connection.close()
    return threads[thread_id]["state"] if thread_id in threads else "deleted"


def thread_for_session(session_id, db_path=STATE_DB):
    """The T3 thread whose provider thread runs this Claude session (``CLAUDE_CODE_SESSION_ID``), or None.

    T3 records the provider's own session id as ``nativeThreadRef.nativeId`` on the provider
    thread; it is the only link from inside a session back to the thread that owns it.
    """
    if not session_id:
        return None
    connection = connect(db_path)
    if connection is None:
        return None
    try:
        row = connection.execute(
            "SELECT thread_id FROM orchestration_v2_projection_provider_threads"
            " WHERE json_extract(payload_json, '$.nativeThreadRef.nativeId') = ?"
            " ORDER BY updated_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    finally:
        connection.close()
    return row[0] if row else None
