# git: local branches pile up after squash merges, and a safe sweep must not trust git alone

    found:  2026-09-19
    status: open
    verify: for r in ~/GitHub/*/; do git -C "$r" fetch --prune -q 2>/dev/null; printf '%s %s\n' "$(git -C "$r" branch -vv 2>/dev/null | grep -c ': gone]')" "$r"; done | sort -rn | head

Nothing on any machine deletes a local branch. `go_apps/git_puller` runs a
plain `git -C <repo> pull` per repo — no `--prune`, no branch cleanup — and no
step of `refresh_machine.py` touches branches either (its "prune" step is
`deploy_configs.py prune`, which is about config paths).

Squash merging makes this worse than it sounds. A squash-merged branch is not
an ancestor of the default branch, so `git branch -d` refuses it as unmerged,
and the remote branch is deleted with the PR, so it never comes back. The
branches accumulate and the safe delete never applies to any of them. Only
some of these repos squash, which is why this cannot be a per-repo setting.

## Evidence

One working repo, 2026-09-19, after `git fetch --prune`:

    total local branches: 22
    upstream gone:        16

Classifying those 16 with `init_worktree.is_squash_merged` (the probe added
the same day for worktree teardown) gives 14 provably landed on
`origin/master` and 2 that never landed:

    safe    feature/ACME-2169-...    (squash-merged)
    safe    feature/ACME-2389-...    (squash-merged)
    ... 12 more, all squash-merged ...
    UNSURE  feature/ACME-2042-...
    UNSURE  feature/ACME-2324-...

This is not one repo's problem. The `verify:` line on 2026-09-19 returned five
working repos with 20, 16, 15, 13 and 11 such branches each, across more than
one context.

The two UNSURE ones have a deleted remote branch and work that is not on the
default branch — closed without merging, or abandoned. They are exactly what a
blunt sweep would destroy.

## The concern that makes this more than a one-liner

"Delete local branches that are not on the remote" is the obvious rule and it
is wrong. T3 Code cuts every new thread's worktree onto a local-only
placeholder branch (`t3code/<hash>`). Before that thread has committed
anything the branch has no upstream and has not diverged, so every test a
sweep would apply marks it deletable:

    $ git for-each-ref --format='%(refname:short) upstream=[%(upstream)]' refs/heads/t3code/abc123
    t3code/abc123 upstream=[]
    $ git merge-base --is-ancestor t3code/abc123 master && echo TRUE
    TRUE

A live thread's branch would be classified "safe, fully merged" on the very
day it was created.

Git blocks the worst case on its own:

    $ git branch -D t3code/abc123
    error: cannot delete branch 't3code/abc123' used by worktree at '/private/tmp/bt/wt'

So a branch whose worktree still exists cannot be deleted, whatever a sweep
decides. The residual risk is the branch whose **worktree is already gone but
whose thread is not finished** — T3 re-creates a missing worktree as a fresh
checkout of the same branch when a new turn starts in that thread, and it is
**unverified** what it does when that branch no longer exists. Losing a
throwaway placeholder name is cheap; a thread that cannot resume is not.

## fix

A `--branches` mode alongside `src/sweep_worktrees.py`, reusing what is
already there rather than a new rule:

- `git fetch --prune` first, so `: gone]` means something.
- Offer a branch only when `init_worktree.is_squash_merged` or
  `init_worktree.is_ancestor` proves its work is on the default branch. UNSURE
  is never offered.
- Never offer a `t3code/` branch whose thread is not `settled`, `deleted` or
  `orphan` in `~/.t3/userdata/state.sqlite` — `sweep_worktrees.thread_states`
  already reads exactly this, keyed by worktree path, so the branch sweep must
  join through the thread, not judge the branch on git state alone.
- Enumerate, print, agree, delete those exact refs — same rule as the worktree
  sweep, with the same `--worktree`-style named-refs mode so it runs from a
  command as well as a terminal.

## blast radius

Deleting a local branch whose work is on the default branch loses nothing but
the name; the commits are reachable from that branch and the reflog keeps the
old tip for 90 days. The fix touches no deployed config and no other machine.

The risk is entirely in the classification, and is the reason this is not a
`git branch -D` one-liner in `refresh_machine.py`.

## not doing yet

Two things to settle first:

1. What T3 Code does when a thread's branch is missing but the thread is live.
   Until that is known, the `t3code/` rule above is a guess at the right
   guard rather than a verified one.
2. Whether the two UNSURE branches are abandoned or wanted. They are the only
   evidence of what an unlanded branch with a deleted remote means in
   practice, and the answer decides whether UNSURE should be reported, offered
   with a warning, or ignored.
