---
description: Sweep the T3 Code thread worktrees nobody is using any more — one row per worktree under ~/.t3/worktrees matched against T3's own thread state, then remove only the finished ones, one agreed path at a time. An unsettled thread is sent back to its own thread.
argument-hint: none
---

# Sweep worktrees

T3 Code makes a worktree per thread and never deletes one. `/remove_worktree`
is the teardown a thread runs on **itself**. This is the cleanup for the
leftovers: threads that ended without running it.

Everything mechanical is `dotfiles/src/sweep_worktrees.py` (stdlib-only). This
command is the thin wrapper: run the report, read it back, then go through the
candidates with Jason.

## Step 1 — report

```bash
python3 ~/GitHub/dotfiles/src/sweep_worktrees.py
```

Changes nothing and prompts for nothing. Every worktree on disk is matched
against T3's thread state (`~/.t3/userdata/state.sqlite`, opened read-only
while the app is running) and gets one verdict:

| Verdict | Meaning | Swept? |
|---------|---------|--------|
| `active` | a thread is running or ready in it | never |
| `unsettled` | a live thread still owns it | **no** — see Step 2 |
| `settled` | the thread is settled | candidate |
| `deleted` | the thread is gone from T3 | candidate |
| `orphan` | no thread references the path at all | candidate |
| `unknown` | no state database on this machine | never |

A candidate still gets held back when it holds work that exists nowhere else
(uncommitted tracked changes, untracked non-ignored files, a detached HEAD, or
commits neither on the upstream nor on the default branch). Those show as
`holds work that exists nowhere else` and are not offered.

A **squash-merged** branch is not one of them. Several of these repos land PRs
as a squash merge, which deletes the remote branch and rewrites the commits, so
a fully merged branch looks identical to one that was never pushed. The tool
probes for that per branch — it never assumes a repo squashes — and clears it.
So do not tell Jason to commit and push a held-back worktree without checking
what it actually holds:

```bash
git -C <worktree> status --porcelain --untracked-files=all
git -C <worktree> log --oneline origin/master..HEAD
```

## Step 2 — an unsettled thread is not yours to clean up

Do **not** sweep an `unsettled` row and do not offer to. Tell Jason which
thread it is, by title, and that the fix is in that thread: settle it, or open
it and run `/remove_worktree` there. The thread that knows the work decides
whether the work is finished — this command only cleans up after threads that
already said they were done.

Same for `active`: a thread is running in it right now. Leave it.

## Step 3 — go through the candidates

Report what the table says first and **ask Jason which candidates may go** —
by name, not "all of them". Then pass back exactly the paths he agreed to:

```bash
python3 ~/GitHub/dotfiles/src/sweep_worktrees.py --remove \
  --worktree ~/.t3/worktrees/<repo>/<id> --worktree ~/.t3/worktrees/<repo>/<id>
```

`--worktree` is repeatable and is the only way to sweep from a tool call: bare
`--remove` prompts per candidate and so needs a terminal, which a command run
does not have. Naming the paths is the same agreement the prompt is, just
gathered in the conversation instead. Any path that is not a candidate cancels
the whole run before anything is removed, so one wrong path never takes the
others with it.

Each removal is the same
`init_worktree.teardown` `/remove_worktree` uses — workspace entry dropped,
worktree removed, a spent `t3code/` placeholder branch retired, a ticket
branch left alone — so there is no second delete path to reason about.

Add `--dry-run` to walk the prompts and print what each removal would do.

Never reach past this into `git worktree remove`, `rm -rf`, or a loop over the
table. The prompt per path is the agreement, and a worktree the tool did not
offer is one it decided must not go.

## Step 4 — report back

Name what was removed, what was left, and why each thing was left. If anything
was blocked by unpushed work, say which worktree and what it holds — that is
the one case that needs Jason to go and deal with the work itself.
