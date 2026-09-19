#!/usr/bin/env python3
"""Sweep the T3 Code thread worktrees nobody is using any more.

T3 Code checks every thread out into its own worktree under
``~/.t3/worktrees/<repo>/<id>`` and has no teardown of its own - settling never
deletes a directory - so they accumulate, one per thread, each with its own
``.venv``. ``init_worktree.py --remove`` (``/remove_worktree``) is the teardown
for *one* worktree, run by the thread that owns it. This is the other case: the
leftovers from threads that ended without running it.

    python3 ~/GitHub/dotfiles/src/sweep_worktrees.py            # report, change nothing
    python3 ~/GitHub/dotfiles/src/sweep_worktrees.py --remove   # prompt per candidate

Every worktree found on disk is matched against T3's own thread state
(``~/.t3/userdata/state.sqlite``, opened read-only while the app runs) and gets
one verdict:

``active``     a thread is running or ready in it - never a candidate.
``unsettled``  a live thread still owns it. NOT swept: settle that thread, or
               open it and run ``/remove_worktree`` there, so the thread that
               knows the work decides. The sweep only ever cleans up after
               threads that are finished.
``settled``    the thread is settled - a candidate.
``deleted``    the thread is gone from T3 entirely - a candidate.
``orphan``     no thread references this path at all - a candidate.
``unknown``    no state database on this machine (no T3, or a fresh install) -
               never a candidate; remove those by name with ``/remove_worktree``.

A candidate is still refused when the worktree holds work that exists nowhere
else (``init_worktree.unpushed_work``): uncommitted tracked changes, untracked
files git does not ignore, a detached HEAD, or commits that are neither on the
branch's upstream nor already on the default branch.

Nothing is ever removed without being printed first and agreed to one at a
time, and the removal itself is ``init_worktree.teardown`` - the same single
implementation ``/remove_worktree`` uses, called once per agreed path, so this
tool has no delete of its own.

Stdlib-only (``sqlite3`` included), like its siblings: a bare ``python3`` runs
it before any venv exists.
"""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import init_worktree  # noqa: E402
import terminal_style  # noqa: E402

WORKTREES_ROOT = os.path.expanduser("~/.t3/worktrees")
STATE_DB = os.path.expanduser("~/.t3/userdata/state.sqlite")
# Session statuses that mean a thread is live in its worktree right now.
LIVE_SESSION = {"running", "ready"}
SWEEPABLE = {"settled", "deleted", "orphan"}
VERDICT_ROLE = {"settled": "green", "deleted": "green", "orphan": "green", "unsettled": "amber", "active": "red"}

HELP_PAGE = """
// sweep_worktrees

Sweep the T3 Code thread worktrees nobody is using any more. One row per
worktree found under ~/.t3/worktrees, each matched against T3's own thread
state and given a verdict.

1. `sweep_worktrees.py`
   Report only. Changes nothing, prompts for nothing.
2. `sweep_worktrees.py --remove`
   Prompt once per candidate, then hand that one path to the same teardown
   /remove_worktree uses.
3. `sweep_worktrees.py --remove --dry-run`
   Walk the prompts and print what each removal would do.

An `unsettled` thread is never swept: settle it, or open that thread and run
/remove_worktree there. The thread that knows the work decides.
"""


# ---------------------------------------------------------------- t3 state


def thread_states(db_path=STATE_DB):
    """Map realpath(worktree) -> {thread, title, branch, state} from T3's projection tables.

    Opened read-only through a file: URI so a running T3 is never disturbed. Returns None when
    there is no database on this machine, which is what makes every worktree `unknown`.
    """
    if not os.path.isfile(db_path):
        return None
    uri = "file:" + db_path.replace("?", "%3f").replace("#", "%23") + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        rows = connection.execute(
            """
            SELECT t.worktree_path, t.thread_id, t.title, t.branch, t.deleted_at,
                   t.settled_at, t.settled_override, s.status
            FROM projection_threads t
            LEFT JOIN projection_thread_sessions s ON s.thread_id = t.thread_id
            WHERE t.worktree_path IS NOT NULL
            """
        ).fetchall()
    finally:
        connection.close()
    states = {}
    for path, thread_id, title, branch, deleted_at, settled_at, override, status in rows:
        states[os.path.realpath(path)] = {
            "thread": (thread_id or "")[:8],
            "title": title or "",
            "branch": branch or "",
            "state": thread_state(deleted_at, settled_at, override, status),
        }
    return states


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


# ---------------------------------------------------------------- discovery


def discover(root=WORKTREES_ROOT):
    """Every ``<root>/<repo>/<id>`` directory on disk, realpath'd and sorted."""
    if not os.path.isdir(root):
        return []
    found = []
    for repo in sorted(os.listdir(root)):
        repo_dir = os.path.join(root, repo)
        if not os.path.isdir(repo_dir):
            continue
        for entry in sorted(os.listdir(repo_dir)):
            path = os.path.join(repo_dir, entry)
            if os.path.isdir(path):
                found.append(os.path.realpath(path))
    return found


def survey(paths, states):
    """One row per worktree: where it is, what T3 thinks of it, and whether it is a candidate."""
    rows = []
    for path in paths:
        row = {"path": path, "label": os.path.relpath(path, WORKTREES_ROOT), "main": None, "blocked": []}
        row.update({"thread": "", "title": "", "state": "unknown"})
        if states is not None:
            row.update(states.get(path, {"thread": "", "title": "(no thread)", "state": "orphan"}))
        try:
            row["main"] = init_worktree.main_checkout(path)
        except Exception:
            row["state"] = "unknown"
            row["title"] = row["title"] or "(not a git worktree)"
        row["candidate"] = row["state"] in SWEEPABLE and row["main"] is not None
        if row["candidate"]:
            row["blocked"] = init_worktree.unpushed_work(path)
        rows.append(row)
    return rows


# ---------------------------------------------------------------- output


def render(rows, color):
    """One aligned row per worktree, coloured by verdict."""
    if not rows:
        return f"no worktrees under {terminal_style.display_git_dir(WORKTREES_ROOT)}\n"
    label_width = max(len(row["label"]) for row in rows)
    state_width = max(len(row["state"]) for row in rows)
    out = []
    for row in rows:
        note = "holds work that exists nowhere else" if row["blocked"] else row["title"][:40]
        role = "amber" if row["blocked"] else VERDICT_ROLE.get(row["state"], "muted")
        out.append(
            "  {}  {}  {}".format(
                terminal_style.paint(row["label"].ljust(label_width), "ink", color),
                terminal_style.paint(row["state"].ljust(state_width), role, color, bold=True),
                terminal_style.paint(note, "muted", color),
            )
        )
    return "\n".join(out) + "\n"


def advice(rows, color):
    """The one line each non-candidate state earns, printed under the table."""
    out = []
    unsettled = [row for row in rows if row["state"] == "unsettled"]
    active = [row for row in rows if row["state"] == "active"]
    blocked = [row for row in rows if row["blocked"]]
    if active:
        out.append(terminal_style.inline(f"{len(active)} thread(s) running right now - left alone.", "ink2", color))
    if unsettled:
        out.append(
            terminal_style.inline(
                f"{len(unsettled)} unsettled thread(s) - not swept. Settle the thread, or open it "
                f"and run `/remove_worktree` there; the thread that knows the work decides.",
                "ink2",
                color,
            )
        )
    if blocked:
        out.append(
            terminal_style.inline(
                f"{len(blocked)} candidate(s) hold work that exists nowhere else - commit and push "
                f"from that worktree first.",
                "amber",
                color,
            )
        )
    return "\n".join(out) + "\n" if out else ""


# ---------------------------------------------------------------- main


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="sweep_worktrees.py", add_help=False)
    parser.add_argument("--remove", action="store_true", help="prompt once per candidate and remove it")
    parser.add_argument("--dry-run", action="store_true", help="with --remove: walk the prompts, change nothing")
    parser.add_argument("--root", default=WORKTREES_ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--state", default=STATE_DB, help=argparse.SUPPRESS)
    parser.add_argument("--hostname", help=argparse.SUPPRESS)
    terminal_style.add_help_page(parser, HELP_PAGE)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    color = terminal_style.use_color(sys.stdout)
    states = thread_states(args.state)
    rows = survey(discover(args.root), states)
    print(terminal_style.section("worktrees", color))
    print(render(rows, color), end="")
    print(advice(rows, color), end="")
    if states is None:
        print("no T3 state database - every worktree is `unknown` and nothing is a candidate")
        return 0

    candidates = [row for row in rows if row["candidate"] and not row["blocked"]]
    if not args.remove:
        print(f"{len(candidates)} candidate(s) - re-run with --remove to go through them one at a time")
        return 0
    if not sys.stdin.isatty():
        print("--remove needs a terminal: each candidate is agreed to one at a time")
        return 1

    removed = 0
    for row in candidates:
        answer = input(f"remove {row['label']} ({row['state']})? [y/N] ").strip().lower()
        if answer != "y":
            print("  skipped")
            continue
        ok, lines = init_worktree.teardown(row["main"], row["path"], dry_run=args.dry_run, hostname=args.hostname)
        if not ok:
            print("  refused: this worktree holds work that exists nowhere else")
            for reason in lines:
                print("   -", reason)
            continue
        for label, status in lines:
            print(f"  {label + ':':<11}{status}")
        removed += 1
    print(f"{removed} removed, {len(candidates) - removed} left")
    return 0


if __name__ == "__main__":
    sys.exit(main())
