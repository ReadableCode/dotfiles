# setup_t3_code: the "repo commands never show in the / menu" note may be stale on T3 0.1.2

    found:  2026-10-23
    status: open
    verify: git -C ~/GitHub/t3code fetch --tags && git -C ~/GitHub/t3code show v0.1.2:apps/server/src/provider/Drivers/ClaudeDriver.ts | grep -n -A6 "snapshotForCwd"

`docs/setup_t3_code.md` (the bullet starting "A repo's own `.claude/commands`
are never listed in the `/` menu", line 1120) says a command kept only in a
project's `.claude/commands` never appears in T3's `/` menu, because the Claude
driver's `snapshotForCwd` returns the machine command list and looks up only
skills per directory. It was verified on desktop 0.0.42 on 2026-09-30. That
note is the reason every slash command is deployed as a flat link in
`~/.claude/commands`.

## Evidence

On 2026-10-23, on the work Mac, T3 Code (Beta) reported
`CFBundleShortVersionString` 0.1.2. In a thread of a work repo, the `/` menu
listed a command that exists only in that repo's `.claude/commands`, with no
link in `~/.claude/commands` and no deploy manifest entry. That contradicts
the note.

Not yet established: the session's `system.init` `slash_commands` always
carried project commands (the note says so), so the session log is not proof.
What is missing is the T3 source change, or a merged PR or release note, that
makes the menu read the per-thread list. Until that is found the observation
could be something else (a cached list, a different code path).

## fix

1. Run `verify:` and compare `snapshotForCwd` in v0.1.2 (and the latest tag)
   with the 0.0.42 code the note cites (`ClaudeDriver.ts:261`, returning
   `{...machineSnapshot, skills}`). Also check `providerSkills.ts`
   `resolveProviderSlashCommandsForCwd` and the release notes / merged PRs
   between v0.0.42 and v0.1.2 for project slash commands:
   `git -C ~/GitHub/t3code log --oneline v0.0.42..v0.1.2 -- apps/server/src/provider packages/client-runtime/src/providerSkills.ts`
2. If it did change, rewrite the note with the version and commit that changed
   it. Only then decide which `~/.claude/commands` links for repo-tracked
   commands can go.
3. If it did not change, find what made the command appear and correct the
   note's scope instead.

## blast radius

The doc edit disturbs nothing. Removing links later would take commands out of
the `/` menu in threads of other projects, which is why it waits on this.

## not doing yet

Out of scope for the session that saw it. The links stay and new repo
commands keep getting manifest links until the source confirms the change.
