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
(deployed to `~/.claude/commands` by `deploy_manifest.yaml`) wraps it:

```bash
cd ~/.t3/worktrees/acme-app/<id>
python3 ~/GitHub/dotfiles/src/init_worktree.py --label ACME-1234
python3 ~/GitHub/dotfiles/src/init_worktree.py --dry-run     # report only
python3 ~/GitHub/dotfiles/src/init_worktree.py --remove      # drop the workspace entry when done
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

## Why not teach `deploy_configs.py` about worktrees

The deploy is fleet-wide and idempotent over a fixed manifest; worktrees are
per-thread, short-lived, and machine-local, and their set changes several
times a day. Mirroring what the main checkout *already has* at worktree
creation time needs no manifest knowledge at all and cannot drift from the
deploy, because the deploy is the thing that put the links there.
