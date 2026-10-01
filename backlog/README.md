# backlog

Known issues in this repo that are real, understood, and deliberately not
fixed yet. One file per issue, this file is the index.

An entry earns its place by being actionable: it says how to re-check that the
problem still exists, what the fix is, and what the fix would disturb. If it
can't answer those, it's a note, not a backlog item — put it in the relevant
doc instead.

Re-run an entry's `verify:` command before acting on it. These describe the
system on the day they were written, and infrastructure moves on its own.

| Issue | Found | Status |
|-------|-------|--------|
| [pi0's SD card is failing](pi0-failing-sd-card.md) | 2026-09-19 | open |
| [pi4a is on the 2023 Foundation kernel](pi4a-old-foundation-kernel.md) | 2026-09-20 | open |
| [stale local branches after squash merges](stale-local-branches-after-squash-merge.md) | 2026-09-19 | open |
| [pasting into the RyzenWhite VNC session does nothing](vnc-paste-into-ryzenwhite.md) | 2026-09-24 | open |
| [google_mcp hides the reason for anticipated errors](google-mcp-hides-error-reasons.md) | 2026-09-26 | open |
| [mac_mcp has no Windows or Linux equivalent](mac-mcp-windows-linux.md) | 2026-09-26 | open |
| [the drive pulled from behemoth's disk5 may be good, and is untested](behemoth-old-disk5-untested.md) | 2026-09-28 | open |
| [mac_mcp: a macOS-only server lives in the repo every machine clones](mac-mcp-belongs-in-personal-dev.md) | 2026-09-30 | open |
| [chrome_bookmarks: a personal-only tool and its alias ship to every machine](chrome-bookmarks-is-personal-only.md) | 2026-09-30 | open |
| [gmail_filters: written for any context, used by one](gmail-filters-is-personal-only.md) | 2026-09-30 | open |
| [ssh_devices: dead script, described wrongly in CLAUDE.md](ssh-devices-has-no-callers.md) | 2026-09-30 | open |
| [go_apps: syncthing_artifact_cleanup has no callers and hard-codes personal folders](syncthing-artifact-cleanup-unused.md) | 2026-09-30 | open |
| [context_leak_check: a public repo may name the user's home town, and nothing refuses it](leak-check-has-no-private-places.md) | 2026-09-30 | open |
| [google_mcp: no tool saves a Gmail attachment to a local path](google-mcp-no-attachment-to-local-path.md) | 2026-10-01 | open |
