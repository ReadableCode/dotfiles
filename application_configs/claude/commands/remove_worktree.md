---
description: Tear down the git worktree this thread is working in (T3 Code makes one per thread) — drop its VS Code workspace entry, remove the worktree, retire a spent t3code/ placeholder branch. Refuses when the worktree holds work that exists nowhere else.
argument-hint: [path — optional; a leftover worktree to remove instead of this one]
---

# Remove worktree

The other half of `/init_worktree`. Run this when a thread is **done** with its
worktree. Everything mechanical is the same stdlib-only script,
`dotfiles/src/init_worktree.py --remove`; this command is the thin wrapper.

T3 Code creates a worktree per thread under `~/.t3/worktrees/<repo>/` but has
no teardown of its own — settling never deletes a directory — so without this
the directories accumulate, one per thread, each with its own `.venv`.

## Step 1 — where am I

```bash
git rev-parse --show-toplevel
git worktree list
```

The first line of `git worktree list` is the main checkout. If the current
directory **is** the main checkout, stop and say so: there is nothing to
remove, and `$ARGUMENTS` is the only way to act from here (Step 4).

## Step 2 — dry run

```bash
MAIN=$(git worktree list --porcelain | head -1 | cut -d' ' -f2-)
python3 "$(dirname "$MAIN")/dotfiles/src/init_worktree.py" --remove --dry-run
```

Read the plan back before doing it. Three lines matter:

- **workspace** — the folder entry `/init_worktree` added to this host's
  `<host>.code-workspace` is dropped again, which returns that credentials
  repo to clean. `absent` is fine (the entry was never added, or already gone).
- **worktree** — the directory and everything in it (`.venv`, the mirrored
  links, caches, anything placed by hand) goes.
- **branch** — a `t3code/` placeholder whose tip is already on the default
  branch is deleted with the worktree; the name is throwaway and must never be
  pushed. A ticket branch is **left in place** — it is pushed, and it goes when
  its remote does.

## Step 3 — run it, as the LAST tool call of the turn

```bash
python3 "$(dirname "$MAIN")/dotfiles/src/init_worktree.py" --remove
```

The script steps out of the directory before deleting it, so the cwd is gone
when it returns. **Run nothing after it in that turn.** Report the result in
the message, not with another command.

If T3 Code starts a new turn in this thread later, it re-creates the worktree
as a fresh, empty checkout of the same branch — so run `/init_worktree` again
at the start of that turn and this command again at the end. Nothing
accumulates in between.

## Step 4 — a leftover from a thread that never cleaned up

From the main checkout, pass the exact path (this is what `$ARGUMENTS` is for):

```bash
python3 ~/GitHub/dotfiles/src/init_worktree.py --remove --dry-run --worktree ~/.t3/worktrees/<repo>/<id>
```

One path per run, and only a path Jason named. The script refuses anything
that is not a registered non-main worktree of that checkout, and it never
lists, inspects or touches a worktree it was not given. Do not enumerate
`git worktree list` and sweep — show him the list if he asks what is there,
and remove only the ones he names.

## Step 5 — when it refuses

The script refuses whenever the worktree holds work that exists nowhere else:

| Reason | Fix |
|--------|-----|
| uncommitted changes to tracked files | commit them, then push |
| untracked files git does not ignore | commit or delete them deliberately |
| detached HEAD | check out or create a branch and push it |
| commits not on the upstream, and not on the default branch | see below, then `git push` |

**Check for a squash merge before telling Jason to push.** Several of these
repos land PRs as a squash merge, which leaves a branch looking exactly like
one that was never pushed: its commits are not ancestors of the default branch
(the merge rewrote them into one commit) and the remote branch was deleted with
the PR, so `@{upstream}` is gone too. The script already probes for this — it
builds the branch's synthetic squash and asks git whether that patch is
already upstream, per branch, never assuming a repo squashes — so a merged
branch is *not* refused. If it still refuses, the work genuinely did not land:

```bash
git log --oneline origin/master --grep="<TICKET-KEY>"   # the squashed PR, if it merged
```

Empty means push it. A hit means the probe found something the squash did not
cover — say what, and do not remove the worktree.

Fix the cause and re-run. **Never work around the refusal** — no
`git worktree remove --force` by hand, no `git stash` to make the check pass,
no deleting the directory with `rm -rf`. The refusal is the only thing
standing between a finished thread and lost work.
