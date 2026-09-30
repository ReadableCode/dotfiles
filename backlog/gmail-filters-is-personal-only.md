# gmail_filters: written for any context, used by one

    found:  2026-09-30
    status: open
    verify: ls ../*_credentials/*_gmail_filters.yaml

On 2026-09-30 the verify line printed one file,
`../personal_credentials/personal_gmail_filters.yaml`.

## Evidence

- Only the personal context declares a `<context>_gmail_filters.yaml`.
- No alias, command or scheduled job calls `src/gmail_filters.py`. It is run
  by hand, and its only mentions are docs: `CLAUDE.md`, `docs/README.md`,
  `docs/repo_gmail_filters.md` and `docs/setup_google_mcp.md`.
- Its open follow-ups live in `personal_credentials`, not here.

## fix

1. Move `src/gmail_filters.py`, its test and `docs/repo_gmail_filters.md` to
   `personal_dev`.
2. It imports `utils/googlemcp_tools.py`, which `google_mcp.py` also uses and
   which stays here. Either reach it the way `personal_dev` reaches the other
   dotfiles servers, or move the filter half of `googlemcp_tools` with it;
   check which functions `gmail_filters.py` actually calls first.
3. Update the four docs that mention it.

## blast radius

None at run time: nothing schedules it. The docs change.

## not doing yet

Step 2 needs a look at the shared Google helpers first. If a work context
ever declares a filters file, the tool stays here and this entry is deleted.
