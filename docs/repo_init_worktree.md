# Initialising a git worktree

T3 Code checks every thread out into its own git worktree under
`~/.t3/worktrees/<repo>/<id>`; `git worktree add` by hand produces the same
thing. A worktree shares the repository's git dir with the main checkout, so
hooks, `.git/info/exclude` and the stash stack carry over. What does **not**
carry over is every gitignored file, and those are exactly the ones
`deploy_configs.py` links into the main checkout to make it usable:

| Main checkout          | Comes from                                        |
|------------------------|---------------------------------------------------|
| `.env`                 | `<context>_credentials/<repo>.env` (relative link) |
| `.mcp.json`            | generated `dotfiles/data/mcp/<context>.mcp.json`  |
| `.claude/settings.local.json` | `<context>_credentials/<repo>_claude_settings.json` |
| `configuration.json`   | a per-host variant in a sibling working repo  |

`src/init_worktree.py` mirrors them into a worktree, and `/init_worktree`
(deployed to `~/.claude/commands` by the personal and dev overlays, never by
the main manifest, so a client machine that must carry no Claude-named path
never receives it; a machine that already had the link from the old
unfiltered entry cleans it up by hand, since a removals line may not name a
dest that is live elsewhere) wraps it:

```bash
cd ~/.t3/worktrees/acme-app/<id>
python3 ~/GitHub/dotfiles/src/init_worktree.py --label ACME-1234
python3 ~/GitHub/dotfiles/src/init_worktree.py --dry-run     # report only
python3 ~/GitHub/dotfiles/src/init_worktree.py --remove      # teardown; see below
```

It is stdlib-only so it runs with a bare `python3` before the worktree has a
venv, from any repo in any context.

## What it does

1. **Local-only links.** Every gitignored symlink at the top level and under
   `.claude/` of the main checkout is re-created in the worktree with an
   **absolute** target. The main checkout's `.env` is a *relative* link
   (`../acme_credentials/acme_app.env`) that would dangle from a
   worktree two directories away, which is why the link is resolved rather
   than copied verbatim. A plain-file `.env` is copied. Nothing existing is
   overwritten: a different file or target is reported as a `conflict`, left
   alone, and makes the script exit 1. Other gitignored top-level files (OAuth
   tokens, `.pem` keys, reports) are listed as `not mirrored` on purpose —
   copying secrets around by script is not the pattern; carry them by hand
   when a task needs them.
2. **VS Code workspace.** Adds `│ <repo> · <label>` right after the main
   checkout's own folder entry in `<repo_parent>/<host>.code-workspace` — the
   manifest-deployed link next to the checkouts (see `setup_vscode.md`). VS
   Code watches the workspace file, so the folder appears in the open window
   without a reload. The label defaults to the ticket key in the branch name,
   else in the subjects of commits the branch adds on top of master (never
   master's own tip, which carries whichever ticket merged last), else the
   directory name with a warning. T3 Code cuts worktrees from master on a
   placeholder branch and the ticket is created from inside the worktree
   later, so the normal sequence is: init with a short description, then
   re-run once the ticket exists and the entry is relabeled in place. The file is
   JSONC with trailing commas, so the entry is inserted as text, not via a
   JSON round-trip, and the edit is idempotent by path. That file is tracked
   in the credentials repo that owns it, so the repo is left dirty — the entry
   is temporary and `--remove` takes it out again.
3. **`uv sync`** when the worktree has a `uv.lock` — each worktree gets its own
   `.venv`; `--no-sync` skips it.

## Leaving: `--remove` and `/remove_worktree`

T3 Code creates a worktree per thread but has no teardown of its own —
settling never deletes a directory — so without a teardown the directories
accumulate, one per thread, each with its own `.venv`. `--remove` is that
teardown, wrapped by **`/remove_worktree`**, the sibling command deployed from
the same two overlays for the same reason as `/init_worktree`.

A thread runs it on itself, from inside its worktree, as the **last** command
of the turn: the script steps out of the directory before deleting it. It
drops the worktree's workspace entry (returning the credentials repo that owns
the file to clean), then runs `git worktree remove --force` on that exact path
from the main checkout, which takes the directory and everything that
accumulated in it — the `.venv`, the mirrored links, caches, anything placed
by hand. There is no list of files to keep current: the directory is the only
place a worktree accumulates anything, and the directory goes.

A `t3code/` placeholder branch whose tip is already on the default branch is
deleted with its worktree, since the name is throwaway and must never be
pushed. A ticket branch is left alone: it is pushed, and it goes when its
remote does.

It **refuses** when the worktree holds work that exists nowhere else —
uncommitted tracked changes, untracked files git does not ignore, a detached
HEAD, or commits that are neither on the branch's upstream nor already on the
default branch. Fix the cause and re-run; never work around the refusal.

### Squash merges

Some of these repos land PRs as a squash merge and some do not, so this is
detected per branch and never configured per repo. A squash merge leaves a
branch indistinguishable from one that was never pushed: the PR lands as one
new commit, so the branch's own commits are not ancestors of the default
branch, and the remote branch is deleted with the PR, so `@{upstream}` is gone.
Both halves of the "unpushed work" test fail on a branch whose work is fully
merged.

`is_squash_merged` settles it with evidence: it builds the synthetic squash of
the branch (`git commit-tree` on the branch's tree, parented on the merge base)
and asks `git cherry` whether that patch is already on the default branch. A
match means the whole branch diff landed and nothing here is unique. The probe
leaves one unreferenced object behind, which gc collects. Two real worktrees
were held back by this before the probe existed, both from squash-merged PRs
with nothing left to lose.

Other worktrees are never listed, inspected or changed: the script only ever
acts on the one path it was given, and refuses anything that is not a
registered non-main worktree of that checkout. A directory left behind by a
thread that never cleaned up is removed the same way, by name, from the main
checkout:

```bash
python3 ~/GitHub/dotfiles/src/init_worktree.py --remove --worktree ~/.t3/worktrees/<repo>/<id>
```

T3 Code re-creates a missing worktree as a fresh, empty checkout of the same
branch when a **new** turn starts in that thread, so a thread spoken to again
after cleaning up simply runs `/init_worktree` then `/remove_worktree` again;
nothing accumulates in between.

## Sweeping the leftovers: `/sweep_worktrees`

`--remove` is what the thread that owns a worktree runs on itself. The threads
that end without running it leave their directory behind, so
`src/sweep_worktrees.py` (`/sweep_worktrees`) is the cleanup for those.

It lists every directory under `~/.t3/worktrees` and matches each against T3's
own thread state in `~/.t3/userdata/state.sqlite`, opened read-only through a
`file:` URI so a running T3 is never disturbed. `projection_threads` carries
`worktree_path`, `branch`, `settled_at`, `settled_override` and `deleted_at`;
`projection_thread_sessions` carries the live `status`. That gives one verdict
per worktree:

| Verdict | Condition | Candidate? |
|---------|-----------|------------|
| `active` | session `running` or `ready` | never |
| `unsettled` | a live thread still owns it | no |
| `settled` | `settled_at` set, or `settled_override: settled` | yes |
| `deleted` | the thread's `deleted_at` is set | yes |
| `orphan` | no thread row references the path | yes |
| `unknown` | no state database on this machine | never |

An **unsettled thread is deliberately not swept**. The fix belongs in that
thread: settle it, or open it and run `/remove_worktree` there. Only the thread
that knows the work can say the work is finished, and a sweep run from
somewhere else cannot. `unknown` is not sweepable for the same reason in the
other direction: with no thread state there is nothing to judge by, so those go
one at a time by name.

A candidate is still held back when `unpushed_work` finds work that exists
nowhere else, and is never offered at the prompt. Everything else is printed
first and agreed to one path at a time (`--remove`), which is the same rule the
rest of the repo follows for a multi-target delete. The removal itself is
`init_worktree.teardown`, the single implementation `/remove_worktree` uses, so
the sweep has no delete of its own and cannot drift from it. Enumeration lives
here and not in `init_worktree.py` on purpose: that script still only ever acts
on the one path it was given.

## Why not teach `deploy_configs.py` about worktrees

The deploy is fleet-wide and idempotent over a fixed manifest; worktrees are
per-thread, short-lived, and machine-local, and their set changes several
times a day. Mirroring what the main checkout *already has* at worktree
creation time needs no manifest knowledge at all and cannot drift from the
deploy, because the deploy is the thing that put the links there.
