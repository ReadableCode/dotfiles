---
description: Bring a fresh git worktree (T3 Code thread checkout) up to parity with its main checkout — re-create the deploy-managed gitignored links (.env, .mcp.json, .claude/settings.local.json, ...), add the worktree to this machine's open VS Code workspace, run uv sync. Never overwrites, never commits.
argument-hint: [label — optional; defaults to the ticket key in the branch name or last commit]
---

# Init worktree

Run this once in every new worktree (T3 Code creates one per thread under
`~/.t3/worktrees/<repo>/<id>`, `git worktree add` by hand makes the same
thing). A worktree shares the repo's git dir — hooks, `.git/info/exclude`,
stashes all carry over — but none of the gitignored files that make a checkout
usable, because `deploy_configs.py` links those into the **main** checkout only.

Everything mechanical is `dotfiles/src/init_worktree.py` (stdlib-only, runs
with bare `python3` before the worktree has a venv). This command is the thin
wrapper: pick the label, run it, read the report back.

## Step 1 — where am I

```bash
git rev-parse --show-toplevel
git worktree list
```

The first line of `git worktree list` is the main checkout. If the current
directory IS the main checkout, stop and say so — there is nothing to init.

## Step 2 — pick the workspace label

The worktree appears in VS Code as `│ <repo> · <label>`, directly under the
main checkout's folder (matches the hand-kept layout of the host
`<host>.code-workspace` files in the credentials repos).

The usual case: T3 Code cut this worktree from master on a placeholder branch
(`t3code/<hash>`) and **the ticket does not exist yet** — it gets created from
inside the worktree later (the context's create-ticket command). So:

- `$ARGUMENTS` given → that is the label, verbatim.
- Otherwise the script looks for a ticket key (`ABC-123`) in the branch name,
  then in the subjects of commits this branch adds on top of master (never
  master's own tip — that is whichever ticket merged last, not ours).
- No ticket anywhere → pass a **two-to-four-word description of the task** from
  the thread's opening message as `--label` (e.g. `highjump snapshot compare`).
  Only if the thread has not said what it is for yet, ask. Do not fall back to
  the bare directory name; `t3code-ff3b06a8` in the sidebar helps nobody.

Re-running later is safe and expected: once the ticket exists, run the command
again (or `--label ACME-1234`) and the entry is **relabeled in place**.

## Step 3 — run it

`dotfiles` is a sibling of the main checkout, so resolve it from there rather
than assuming `~/GitHub`:

```bash
MAIN=$(git worktree list --porcelain | head -1 | cut -d' ' -f2-)
python3 "$(dirname "$MAIN")/dotfiles/src/init_worktree.py" --label "<label>"
```

Add `--dry-run` first if anything about the worktree looks unusual (files
already present, unexpected main checkout). Flags: `--no-workspace`,
`--no-sync`, `--remove` (see Step 5).

What it does, in order (every step is idempotent, so re-running after the
ticket is created only relabels the workspace entry):

1. **Local-only links** — every gitignored symlink at the top level and under
   `.claude/` of the main checkout is re-created in the worktree with an
   **absolute** target (the main checkout's `.env` is a relative link into the
   sibling credentials repo, which would dangle from two directories away). A
   plain-file `.env` is copied. Existing paths are never overwritten: a
   different file or target is reported as `conflict` and left alone (exit 1).
   Remaining gitignored top-level files (OAuth tokens, `.pem` keys, reports)
   are printed as `not mirrored` — carry those by hand if the task needs them.
2. **VS Code workspace** — inserts the folder entry into
   `<repo_parent>/<host>.code-workspace`, the deploy-managed link next to the
   checkouts. VS Code watches that file, so the folder shows up in the open
   window immediately with no reload. Idempotent by path. The file lives in
   a **tracked** credentials-repo file (`personal_credentials/vscode/...` or the
   client's), so this leaves that repo dirty on purpose.
3. **`uv sync`** — when the worktree has a `uv.lock`; each worktree gets its own
   `.venv`.

## Step 4 — report

Print the script's table back compactly: what was linked/copied, what was
`not mirrored`, the workspace status, the uv result. Call out any `conflict`
line explicitly — that is the one case that needs a human decision.

If the workspace line says `no workspace file`, this host has no
`<host>.code-workspace` variant deployed yet — see `dotfiles/docs/setup_vscode.md`.
If it says `no anchor`, the main checkout itself is not in the workspace; add
it by hand first.

## Step 5 — do NOT commit; leaving a worktree

- Never commit the workspace-file change. It is Jason's credentials repo; the
  entry is meant to be dropped again when the worktree goes.
- When a thread is done: `python3 .../init_worktree.py --remove` from inside the
  worktree removes its workspace entry, then `git worktree remove <path>` as
  usual. Nothing else was created outside the worktree directory.
