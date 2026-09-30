# chrome_bookmarks: a personal-only tool and its alias ship to every machine

    found:  2026-09-30
    status: open
    verify: git grep -n '^BASE_NAME\|default="personal"' src/chrome_bookmarks.py; ls ../*_credentials/bookmarks

On 2026-09-30 the verify line printed `BASE_NAME = "personal_bookmarks"`,
`default="personal"`, and one bookmarks folder, in `personal_credentials`.

## Evidence

- `src/chrome_bookmarks.py:17` hard-codes `BASE_NAME = "personal_bookmarks"`,
  and `--context` defaults to `personal` (line 287).
- Only `personal_credentials/bookmarks/` exists.
- Its one workflow is `personal_dev/claude/commands/personal_chrome_bookmarks.md`.
- The `bookmarks` alias in `application_configs/bash/.shared_aliases`
  (line 188 on) and the PowerShell aliases deploy to every machine, work
  machines included.

`docs/repo_philosophy.md` cites it as the worked example of a tool that
earned its place by taking `--context`. No second context ever used it.

## fix

1. `git mv` is not possible across repos: copy `src/chrome_bookmarks.py` and
   its test to `personal_dev/src/` and `personal_dev/tests/`, then delete them
   here.
2. Point `personal_chrome_bookmarks.md` at
   `uv run --project ~/GitHub/personal_dev python ~/GitHub/personal_dev/src/chrome_bookmarks.py`.
3. Remove the `bookmarks` alias from `.shared_aliases` and
   `powershell_aliases.ps1`.
4. Replace the worked example in `docs/repo_philosophy.md` with a tool that
   really serves more than one context.

## blast radius

The `bookmarks` alias disappears everywhere; the command keeps working. No
data moves: the exports already live in `personal_credentials`.

## not doing yet

Batched with the other moves out of dotfiles so the aliases and the doc
change once.
