# T3 Code issues

Running notes from daily use: each is either an upstream candidate
([github.com/pingdotgg/t3code](https://github.com/pingdotgg/t3code/issues)) or
a doc/automation task in this repo. Setup, and the workarounds applied on a
machine, are in [setup_t3_code.md](setup_t3_code.md).

- **Snoozing a thread until "Tomorrow" shows the "Snoozed" toast and leaves
  the thread in the inbox, while "In 1 hour" on the same thread works
  (upstream, verified 2026-10-07 on desktop 0.0.45 against the `v0.0.45` tag
  and `main @ 611132c171`)**: it happens only to a thread that was already
  snoozed to that same wake time and then woke early. A snoozed thread whose
  agent finishes a turn on its own (a background command or watcher
  completing, no message from me) "raises its hand":
  `threadRaisedHandWhileSnoozed` in
  `packages/client-runtime/src/state/threadSettled.ts` stops classifying it as
  snoozed once `latestTurn.completedAt > snoozedAt`, and the server keeps
  `snoozedUntil` / `snoozedAt` set (no `thread.unsnoozed` is emitted; only a
  user message clears them). Snoozing again to the same instant then hits the
  duplicate rule in the `thread.snooze` case of
  `apps/server/src/orchestration/decider.ts` (`existingSnoozedAt`): same
  `snoozedUntil` re-emits `thread.snoozed` with the **original** `snoozedAt`,
  so the turn that woke it is still newer than the snooze and the thread stays
  awake. The command succeeds, which is why the toast and the mod+z undo
  appear.
  - **Why only "Tomorrow"**: the calendar presets (`resolveSnoozePresets`:
    "This evening", "Tomorrow", "Next week") resolve to a fixed instant, so a
    repeat sends an identical `snoozedUntil`. "In 1 hour" / "In 3 hours" are
    `now + n`, differ every click, and always stamp a fresh `snoozedAt`.
  - **Evidence**: `orchestration_events` in `~/.t3/userdata/state.sqlite`
    (open with `mode=ro`). A failed attempt is a `thread.snoozed` row whose
    payload `snoozedAt` is older than the row's `occurred_at`. On 2026-10-07
    one thread had five of them in two episodes, each after a background task
    completed and ran a turn while it was snoozed; no earlier day has any.
  - **What changed**: nothing in the snooze logic. The duplicate rule and the
    raised-hand rule both date from the original snooze commit (`202e5609ff`,
    2026-07-23) and are identical in `v0.0.42` through `v0.0.45`; the V2
    orchestrator on `main` carries the same rule
    (`apps/server/src/orchestration-v2/Orchestrator.ts`, `sameWakeTime`). It
    needs a turn that starts without a user message while the thread is
    snoozed, which is what long background watchers now do. Unverified: which
    release first let a background completion run a turn on a snoozed thread.
  - **Workaround**: snooze to any other time first ("In 1 hour"), then
    "Tomorrow"; a different wake time stamps fresh. Sending a message also
    clears the stale snooze.
  - **Upstream fix**: treat a same-time re-snooze as a duplicate only while
    the thread still classifies as snoozed; once it has raised its hand, stamp
    a fresh `snoozedAt`. The file is in the frozen orchestration layer, so this
    is an issue comment, not a PR.

- **The `/` menu shows no provider commands in one project while the same
  commands work in every other project (upstream, verified 2026-09-25 on
  desktop 0.0.42 against `main @ 7a12aff471`; re-checked 2026-09-30 against
  the `v0.0.42` tag and `main @ d2c9281b81`, same code paths)**: typing `/` lists only the
  client built-ins (`/compact`, `/plan`, `/default`, `/usage-limits`) and none
  of the `~/.claude/commands` entries, for every thread whose cwd is one
  particular directory. The agent is unaffected: every session's `system.init`
  message in `~/.t3/userdata/logs/provider/events.<thread>.log` carries the
  full `slash_commands` list, so a command typed out in full still runs.
  The old form of this note (a newly deployed command never appears until the
  server restarts) is the same defect seen from the other side.

  **Mechanism.** Since 0.0.42 (PR 11519, "expose native slash commands across
  clients") the server keeps one command list *per working directory* on top
  of the machine-wide list:

  1. `checkClaudeProviderStatus` (`apps/server/src/provider/Layers/ClaudeProvider.ts:420`,
     the list itself at line 540) builds the machine-wide list every 5 minutes from one SDK `initialize`
     handshake run in the server's own cwd (`probeClaudeCapabilities`, 25 s
     timeout, `settingSources: user,project,local`, no MCP). The result is
     written to `~/.t3/caches/claudeAgent.json` (`slashCommands`, 99 entries
     here on 2026-09-30). The `claude --version` health check that precedes it has a 4 s
     timeout (`providerSnapshot.ts:23`) and takes 1 to 1.8 s on this Mac.
  2. When a thread mounts, `ChatComposer.tsx:1957-2010` asks
     `server.refreshProviders({instanceId, cwd})` for a *workspace snapshot*
     of the thread's cwd (worktree path, else the project root), retrying
     every 10 s until one exists. `ProviderRegistry.refreshWorkspaceSnapshot`
     (`ProviderRegistry.ts:838`) calls `ClaudeDriver.snapshotForCwd`
     (`ClaudeDriver.ts:261`), which is nothing more than
     `{...machineSnapshot, skills: discoverClaudeSkills(cwd)}`: the commands
     are a **copy of the machine list at that instant**. A turn start does the
     same capture (`ProviderCommandReactor.ts:713`).
  3. `upsertProviderWorkspaceSnapshot` (`ProviderRegistry.ts:85`) stores it in
     a ring of **16 entries per provider** (`MAX_WORKSPACE_SNAPSHOTS_PER_PROVIDER`,
     newest wins). The refresh returns early whenever an entry for the cwd
     already exists (`ProviderRegistry.ts:847`), the 5-minute machine refresh
     carries old entries over untouched (`mergeProviderSnapshot`,
     `ProviderRegistry.ts:214`), and only `status === "error"` blocks a capture
     (`ProviderRegistry.ts:863`). So an entry is captured once and **never
     revisited**; it dies only by ring eviction or a server restart.
  4. The client prefers the entry over the machine list
     (`packages/client-runtime/src/providerSkills.ts:121`,
     `resolveProviderSlashCommandsForCwd`), so a bad entry hides a perfectly
     good machine list for that cwd.

  Two windows produce a bad entry, and both leave status `warning`, which
  does not block the capture: (a) the seconds after a server start, when the
  placeholder from `makePendingClaudeProvider` (`ClaudeProvider.ts:605`) has
  `slashCommands: []` and the thread restored at launch asks straight away;
  (b) any 5-minute cycle whose capability probe failed or timed out, when the
  machine list is just `[compact]` (`ClaudeProvider.ts:540-556`). A
  `--version` timeout is a third, softer case: status `error` blocks captures
  and empties the machine list for that cycle, so threads *without* an entry
  show an empty menu until the next successful check.

  **Why one project.** A project whose threads each get a worktree has one cwd
  per ticket thread (16 open ones here), every other project has one. The
  worktree project drives all the churn: its threads are the ones open across
  restarts and the ones creating new cwds, and its root directory is shared by
  every non-worktree thread in it, so one bad root entry blanks most of the
  project at once. A new worktree thread starts on the project root and
  switches to the worktree path after its first turn, which triggers a fresh
  capture: that is the "works after a few turns" behaviour.

  Counted from `~/.t3/userdata/state.sqlite` on 2026-09-30, for the server
  that had been up since 2026-09-23: threads with a turn since that start
  (`projection_turns` joined to `projection_threads` and
  `projection_projects`) ran in 14 distinct working directories across 8
  projects. The worktree project accounts for 7 of them (its root and 6
  worktrees) across 22 threads, 16 of which ran in the shared root; every
  other project has exactly one. 14 is under the 16-entry ring, so turn
  starts alone evicted nothing in that week.

  A settled thread costs nothing by itself. A capture happens only when a
  thread is mounted in the composer or starts a turn, so a settled thread
  matters only if it is opened. Of 201 threads, 196 were settled.

  The last three turns before that restart (13:46 to 13:49 UTC, four minutes
  before it) were in a worktree thread of that project, so the thread
  restored at launch was most likely one of its threads: window (a) above.
  That is one restart, and it points at the project in daily use being the
  one open when T3 restarts.

  The user-level command folder is not the cause: the machine list read from
  it held all 29 deployed commands on 2026-09-30. The per-directory entries
  are in server memory, so an empty one is still inferred, not read back.

  **How it was verified.** Server spans in
  `~/.t3/userdata/logs/server.trace.ndjson*` (rotates every ~35 min at 10 MB
  x 10 files): `refreshWorkspaceSnapshot` under `ensureSessionForThread` on
  every turn start, 0 ms because the entry existed; `checkClaudeProviderStatus`
  1.0-1.8 s every 5 min; the probe replayed by hand (the `initialize` control
  request over `--input-format stream-json` with the probe's flags) answered
  in 0.5-0.8 s with all 95 commands (99 by 2026-09-30). The per-cwd entries themselves are in
  server memory only, reachable through the authenticated `/ws` RPC, so the
  bad capture is inferred from the code paths, not read back.

  **Workarounds.** Quit and reopen T3, and let the Claude provider reach
  `ready` (Settings > Providers) *before* opening a thread, otherwise the
  restored thread's cwd is captured against the placeholder again. Typing the
  full command name still works. Settings > Providers > Refresh does not help:
  `refresh()` merges and keeps the old entries.

  **Upstream state (checked 2026-09-25).** The bug is reported three times:
  [#7111](https://github.com/pingdotgg/t3code/issues/7111) (probe failure
  empties the list, Aug 15), [#11575](https://github.com/pingdotgg/t3code/issues/11575)
  (startup placeholder captured, Sep 13, the exact mechanism above with span
  timings) and [#13635](https://github.com/pingdotgg/t3code/issues/13635)
  (probe stuck on `warning` for hours, Sep 25). Three fix PRs were closed
  unmerged: [#7112](https://github.com/pingdotgg/t3code/pull/7112) and
  [#7175](https://github.com/pingdotgg/t3code/pull/7175) (keep the last good
  list) and [#11576](https://github.com/pingdotgg/t3code/pull/11576) (wait
  for the first probe before capturing). On Sep 19 a maintainer closed
  #11576 with: *"We're not taking changes to the orchestration and provider
  layers right now: that part of the server is being rewritten for V2 ...
  If this is still an issue once V2 lands, please reopen."*
  [#13077](https://github.com/pingdotgg/t3code/pull/13077) (trusted
  contributor, size L, open) re-probes commands per cwd with a 5-minute
  expiry and would also fix this, but it touches the same layers.
  Re-checked 2026-09-30: #7111, #11575 and #13635 are still open, and so is
  #13077, now titled "fix(server): Claude picks up project slash commands",
  with automated review comments unresolved and no maintainer decision.

  **The fix, if we wanted to write it.** Small, all in
  `apps/server/src/provider/Layers/ProviderRegistry.ts`:
  - in `refreshWorkspaceSnapshot`, refuse to capture unless
    `scopedSnapshot.status === "ready"` (today only `"error"` is refused). The
    composer already retries every 10 s and the turn-start path retries per
    turn, so the entry simply arrives once the first probe finishes. This
    alone closes #11575 and the `[compact]` case of #7111.
  - in `upsertProviders` / `mergeProviderSnapshot`, when the machine
    `slashCommands` change, drop (or rewrite) every workspace entry of that
    provider so the next mount recaptures; today a per-cwd entry can never
    learn about a new `~/.claude/commands` file.
  - optional: raise `MAX_WORKSPACE_SNAPSHOTS_PER_PROVIDER` above 16.
  Tests live in `ProviderRegistry.test.ts` ("stores workspace skills and
  commands without changing machine metadata", line 580, is the template);
  the pending-provider case needs a fake instance whose `snapshotForCwd`
  first returns a `warning` snapshot with `slashCommands: []`. Estimate: a
  20-line change plus two tests, an afternoon. The realistic blocker is
  the V2 freeze above, so the useful move is a comment on #11575 with the
  span evidence, and a PR only once V2 lands or the freeze is lifted. See
  [Working on the T3 source](#working-on-the-t3-source) for the checkout and
  PR mechanics.

- **A repo's own `.claude/commands` are never listed in the `/` menu
  (upstream, verified 2026-09-30 on desktop 0.0.42 against the `v0.0.42` tag
  and `main @ d2c9281b81`)**: a command file kept in a project's
  `.claude/commands` does not appear when `/` is typed in a thread of that
  project. It still runs when typed in full, because the agent loads project
  commands itself. Only commands in `~/.claude/commands` are listed, in every
  thread of every project.

  **Mechanism.** T3 is built to hold a command list per working directory:
  each workspace snapshot carries its own `slashCommands`, and the client
  prefers it over the machine list (`resolveProviderSlashCommandsForCwd`,
  `packages/client-runtime/src/providerSkills.ts:121`). The Cursor and
  Antigravity drivers fill it per directory. The Claude driver does not:
  `snapshotForCwd` (`apps/server/src/provider/Drivers/ClaudeDriver.ts:261`)
  returns `{...machineSnapshot, skills}`, where only `skills` is looked up
  for the thread's directory (`discoverClaudeSkills`, `ClaudeSkills.ts`,
  which reads `~/.claude/skills` and `<cwd>/.claude/skills`). The commands
  are the machine list, and the machine list comes from one probe run in the
  server's own working directory (`ServerConfig.cwd`, `ClaudeDriver.ts:119`
  and `:187`): `/` for the desktop app, the home folder under systemd. The
  probe does pass `settingSources: user, project, local`, so a project's
  commands would be listed only if that project were the server's start
  directory.

  **What follows from it.** Project skills are found per thread and project
  commands are not. That is why every slash command here is a flat file
  link in `~/.claude/commands`
  ([repo_deploy_configs.md](repo_deploy_configs.md)), and why every thread
  lists every context's commands. Moving a command into its repo alone takes
  it out of the menu everywhere. Measured 2026-09-30: 31 commands are
  deployed this way by 34 manifest entries, and the T3 cache on the Mac
  lists the 29 that machine has.

  **Upstream state (checked 2026-09-30).**
  [#13077](https://github.com/pingdotgg/t3code/pull/13077), "fix(server):
  Claude picks up project slash commands", is open and is exactly this
  change. It is not in `main @ d2c9281b81`. It touches the provider layers
  that are frozen for the V2 rewrite (see the entry above), so it may wait
  for V2.

  **Workaround.** Keep linking commands into `~/.claude/commands` through
  the overlay manifests. Revisit per-repo commands when #13077 or its V2
  equivalent ships; the check is whether a file placed in a project's
  `.claude/commands` shows in that project's menu and in no other.

- **No verbose transcript view (upstream)**: T3 has no equivalent of Claude
  Code's verbose mode — tool calls render as truncated summaries with no
  setting, keybinding command, or provider option to expand them (confirmed
  against the 0.0.31 schemas: client-settings, server settings, claudeAgent
  provider config, and the keybinding command enum have nothing). The
  `verbose`/`viewMode` keys in `~/.claude/settings.json` only affect the
  Claude Code CLI/desktop TUI; T3 already launches `claude` with
  `--verbose --output-format stream-json` and does its own rendering, so
  the data is there — the UI just never shows it. Also verified absent in
  the latest nightly (`t3@0.0.32-nightly.20260805.1008`: client settings
  gained font options, nothing transcript-related), so upgrading doesn't
  help. Fix: an upstream transcript view-mode toggle (default/verbose) like
  Claude Code's — since threads store the full stream-json, it should apply
  retroactively to existing threads. Interim: click individual tool cards
  to expand them, or run `claude` in T3's terminal panel (`mod+j`) where
  `~/.claude/settings.json` `verbose: true` applies.
- **Background commands can't be watched live, from inside or outside T3
  (upstream)**: when a thread launches a long-running command in the
  background, the thread shows only a collapsed Work Log card
  ("Background command ... ") — there is no live output pane, so the only way
  to see progress is to ask the thread to poll it and wait for the reply. It
  can't be watched from outside either: the background shell belongs to the
  `claude` process T3 spawned for that thread, and `BashOutput` / `/bashes`
  only work inside the owning session, so another Claude Code session (CLI,
  desktop, or a second T3 thread) can't attach. Resuming the session id in a
  new process does not restore background shells — the old process owns them
  until it exits. Fix: stream background-command output into an expandable
  live pane (the data is already in the stream-json). Workarounds, best
  first: (1) have the script write its own log (`./run.sh > /tmp/run.log
  2>&1 &`) so any session, terminal, or machine can `tail -f` it;
  (2) ask the owning thread to check; (3) read the raw transcript — map
  thread → Claude session with
  `sqlite3 -readonly ~/.t3/userdata/state.sqlite "select thread_id, status,
  json_extract(resume_cursor_json,'$.resume') as session_id,
  json_extract(runtime_payload_json,'$.cwd') as cwd from
  provider_session_runtime order by last_seen_at desc limit 5;"`, then
  `tail -f ~/.claude/projects/<cwd-slug>/<session_id>.jsonl` to see the tool
  calls and every polled output the thread has captured.
- **File preview stops at the first 1 MB, with no tail (upstream)**: opening a
  large file in the side pane shows
  "Preview limited to the first 1 MB of a *N* byte file" (seen on a ~120 MB
  run log) and there is no way to seek to the end, follow the tail, or load
  the next chunk — so for a growing log, the one part that matters (the last
  lines) is the one part the viewer can't reach. This makes the file pane
  useless as a substitute for the missing live output above. Fix: a tail/
  follow mode, or at minimum a "jump to end" that loads the final 1 MB.
  Workaround: `tail -f` the file in the terminal panel (`mod+j`) or from any
  shell on that machine.
- **Popped-out browser preview is unreadably blurry (upstream)**: seen on
  0.0.42 (Envy, 2026-09-30). Popping the inline chat thumbnail out gives a
  large window of smeared, unreadable text, while the same page in the side
  pane renders sharp. The pop-out is not a live page: the main process
  `capturePage()`s the preview's web view about 12 times a second
  (`PICTURE_IN_PICTURE_FRAME_INTERVAL_MS`), JPEG-encodes each frame at
  quality 80 and sends it to the picture-in-picture window, which scales it
  up. The capture appears to be taken at the size the web view is drawn on
  screen, so with only the thumbnail showing every frame is thumbnail-sized.
  The viewport setting does not help: `browserDefaultViewport` at a fixed
  1440x900 gave the same blur after a full restart. The page itself renders
  fine; an agent `preview_snapshot` of the same tab came back sharp at
  1280x800. Fix: capture the pop-out frames at the page's viewport size, not
  the drawn size. Workaround: read the page in the side pane, or open the
  URL in the system browser.
- **OAuth account sign-in is broken on Windows — the callback is dropped
  (upstream, OPEN)**: on RyzenWhite (0.0.33), signing in to the T3 account
  with any provider button — Apple, GitHub, Google, Microsoft —
  loops forever. The Clerk modal comes back with a red **"You are signed out"**
  banner, and `~/.t3/userdata/clerk-tokens.json` is never rewritten. GitHub
  itself authenticates fine; the token never gets back into the app.

  Root cause is in the app bundle. The provider flow hands off to the external
  browser and returns via the registered `t3code://` deep link. On Windows a
  deep link to an already-running instance is delivered as **`argv` on
  Electron's `second-instance` event**, and the app's handler — inside
  `desktop.clerk.configure` — is only this:

  ```js
  electronApp.on("second-instance", () => {
    const mainWindow = electronWindow.currentMainOrFirst;
    if (Option.isSome(mainWindow)) electronWindow.reveal(mainWindow.value);
  });
  ```

  It reveals the window and **never reads `argv`**, so the callback URL is
  discarded. There is no `open-url` handler either, i.e. nothing in the app
  consumes a deep link on any platform. Confirming evidence: firing
  `t3code://anything` at the running app focuses the window, spawns no second
  instance, and produces no log line or state change; and Electron's cookie
  store (`%APPDATA%\t3code\Network\Cookies`) is not written during an attempt,
  so Clerk never establishes a session. Ruled out first — system clock (1.1 s
  skew), and the renderer origin (`http://127.0.0.1:3773`, a secure context, so
  `Secure` cookies are fine).

  **Workaround: use a sign-in method that never leaves the app window** —
  *Email address → Continue* and the emailed code, or *Use passkey instead*.
  Both complete in-window and need no deep link. Fix: read the deep link out of
  `argv` in `second-instance` (and add an `open-url` handler for macOS) and
  route it to Clerk.
- **Links in responses aren't clickable (upstream)**: URLs in assistant
  responses render as plain text — no way to open one without selecting and
  copying it by hand (extra painful on the phone apps). Fix: linkify URLs
  (and markdown links) in the transcript renderer and open them in the
  system browser.
- **Bedrock-authed machines: T3 overrides the two things `settings.json`
  can't win (upstream + this repo, handled)**: on a machine where
  Claude Code authenticates through Bedrock
  (`CLAUDE_CODE_USE_BEDROCK=1` in `~/.claude/settings.json`), the interactive
  CLI works but every T3 turn fails. T3 does spawn that CLI and the CLI does
  read its own settings — the problem is the two per-thread values T3 layers
  on top, both of which are first-party-only concepts.
  1. **Permission mode.** T3 maps its Auto runtime mode to SDK
     `permissionMode: "auto"`; Claude Code disables auto mode for
     non-first-party providers ("auto mode disabled: provider bedrock
     requires the `CLAUDE_CODE_ENABLE_AUTO_MODE` opt-in"), so the CLI rejects
     the `setPermissionMode` control request T3 sends at *every turn start*
     and the thread dies with `Provider turn start failed ·
     turn/setPermissionMode failed` before any model call. Interactive use
     never hits it because the TUI doesn't offer Auto. Upstream:
     [#4495](https://github.com/pingdotgg/t3code/issues/4495) (open; PR #4510
     remapping auto→default was closed unmerged, still present in 0.0.31).
     Fix: set the thread's permission dropdown to anything but Auto. Adding
     `"CLAUDE_CODE_ENABLE_AUTO_MODE": "1"` to the settings `env` block is the
     durable version, but a second per-model gate ("auto mode unavailable for
     this model") may still block it for inference-profile model IDs.
  2. **Model.** T3's picker sends first-party slugs (`claude-opus-5`) as
     `--model`, overriding `ANTHROPIC_MODEL` from settings, and Bedrock
     answers `400 The provided model identifier is invalid`. The Claude
     provider config has a `customModels` array for exactly this, but its
     schema marks it `providerSettingsForm: { hidden: true }` and leaves it
     out of the form `order` — **there is no UI for it**, which is what makes
     this look unfixable from inside the app. Set it in `settings.json` and
     the inference profile shows up in the picker. `normalizeCustomModelSlug`
     only trims, so the dots and colons in
     `<region>.anthropic.<model>-v1:0` survive; custom models resolve to
     empty capabilities, so T3 also stops appending the `[1m]` suffix and
     `--effort` for them (and their effort/context-window dropdowns
     disappear — that's the trade).
  Handled here by giving Bedrock machines their own `settings.json` from
  their context manifest rather than the shared one — full procedure in
  [Claude Code on Bedrock](setup_t3_code.md#claude-code-on-bedrock) under Connect
  providers.
- **The server leaks until V8 kills it, ~3 days on a quiet box (upstream,
  OPEN)**: a `t3 serve` left running aborted almost exactly three days after
  start with `FATAL ERROR: Ineffective mark-compacts near heap limit —
  JavaScript heap out of memory`, sitting at V8's default ~4 GB cap. The last
  GCs in the server log show the death spiral before it (`4090.7 → 4089.9 MB`,
  1.17 s per mark-compact, `current mu = 0.019`), so the box is effectively
  unresponsive for a while before the process actually dies. Nothing was
  driving threads at the time; the only steady traffic in the log is the
  relay's own reconnects, so it looks like idle-time growth rather than
  per-thread retention. A Linux `t3code.service` restarts itself out of it
  (`Restart=always`), which is the only supervision that exists for this. To
  confirm a suspected leak on a running box:
  `Get-Process node | Sort-Object WS -Descending | Select-Object -First 3 Id,WS,StartTime`.
- **npm server rejects newer config than its pinned version (this repo,
  handled)**: the headless `t3` server schema-validates managed configs and
  warns on anything a newer build wrote — RyzenWhite's `server.log` spammed
  "ignoring invalid keybinding entry" for `filePicker.toggle` /
  `projectSearch.toggle`, leftovers from the 0.0.32 nightly's default
  keybindings after the downgrade to 0.0.31. Handled by the platform
  variant split in the Settings section of `setup_t3_code.md` (bare files
  stay server-safe);
  deploying to RyzenWhite replaces the stale file and clears the warnings.
- **"Copy update command" starts a second server instead of updating the
  service (upstream)**: for a service-managed Linux environment,
  the remote-environments panel's update command is bare `npx t3@<version>`
  — running it spawns a foreground server that steals the relay tunnel;
  killing it strands the environment on "Relay environment endpoint is
  unavailable" until `systemctl --user restart t3code.service`. The CLI has
  a real updater (`t3 service update`) that the panel should surface when
  the endpoint is service-managed. Full procedure and recovery in
  [Updating a service-managed Linux server](setup_t3_code.md#updating-a-service-managed-linux-server).
  `t3 service update` was the verb through 0.0.42; the 0.0.44 CLI prints a
  deprecation notice for it and performs the update anyway (observed
  2026-09-30 moving a box from 0.0.42 to 0.0.44). `t3 update` itself has not
  been run on a service install yet.
- **Settle button hit area (upstream)**: only part of the Settle button
  registers clicks, not the whole visible button. Fix: extend the click target
  to the full button bounds.
- **Finished threads can refuse to settle (upstream)**: some threads that are
  actually done won't settle because T3 still reports them as working, and the
  settle-error popup offers no way out. Fix: add a **Kill and settle** option
  to that error dialog so a stuck "working" state can be forced closed.
- **Projects don't show their machine (upstream)**: neither the sidebar nor
  the add-project wizard indicates which environment/machine a project runs
  on, so with several environments connected, same-named projects are
  indistinguishable. Fix: badge each project with its environment name in both
  places.
- **Same repo on two environments can't both be added (upstream)**: adding a
  project on a second environment silently does nothing when it matches an
  existing project on another machine — the project is never added. The
  dedup appears to be by repository identity, not (environment, path), so
  there is no workaround via distinct clone paths: the same repo with agents
  on two machines is simply not possible right now. This blocks the core
  multi-machine use case. Fix: key projects per-environment. Possibly related:
  `client-settings.json` has `sidebarProjectGroupingMode: "repository"` —
  worth testing whether a different grouping mode changes the behavior, but
  the add-wizard refusal suggests it's storage-level, not display-level.
  **Working workaround**: add the *parent* workspace folder
  (e.g. `~/GitHub`) as the project instead of the repo — a non-repo
  directory has no repository identity, so the dedup never fires and each
  machine gets its own project over the same repos. Combine with the naming
  convention below.
- **Workaround for the missing environment badges**: prefix project names
  with the machine (`RW-GitHub`, `Envy-GitHub`) when adding/renaming, so
  same-named projects on different environments stay distinguishable in the
  sidebar and in the new-chat picker.
- **iOS app misses new threads until relaunch (upstream)**: a thread created
  from another client on a connected environment didn't appear on the
  iPhone until the app was killed and reopened; after relaunch it showed and
  synced normally (seen on a Tailscale-paired environment). Fix:
  resubscribe/refresh thread lists when the app foregrounds instead of only
  at launch.
- **iPad app auto-settles threads after 3 days and can't be told not to
  (upstream)**: the iPad app settles any thread untouched for about three
  days on its own. Only the iPad app does this - the desktop app leaves
  threads alone - and the iPad app has no settings file or setting to
  turn it off, so there is nothing to deploy for it. A
  thread you come back to on the iPad after a few days is in the settled
  list, not the active one. Fix: make it a setting, or drop the timer to
  match desktop.
- **Slash commands don't auto-suggest on mobile (upstream)**: typing `/` in
  the composer on the phone apps shows no suggestion popup and no
  autocompletion — the full command name must be typed from memory, unlike
  the desktop app. Fix: bring the desktop slash-command picker to the mobile
  composer.
- **New messages yank the scroll position (upstream)**: while scrolled up
  reading a thread's history, an incoming message auto-scrolls the view to
  the bottom. Fix: only auto-scroll when already at (or near) the bottom;
  otherwise keep the reading position and show a "new messages" jump pill.
- **T3 Connect 502s after a reboot when the tunnel ingress port drifts**: the
  cloudflared ingress (`curl 127.0.0.1:20241/config`) was registered against
  port 3774 while a stale instance held 3773; after a clean reboot the server
  binds 3773 (`~/.t3/userdata/server-runtime.json`) and the app does not
  re-register the ingress, so every tunnel request 502s while local use works.
  Diagnose by comparing those two; `cloudflared_tunnel_request_errors ==
  total_requests` in `/metrics` confirms it. Fix: toggle server exposure off
  and on in T3 settings, then wait for `readyConnections: 4` in `/ready`
  (several minutes) before judging.
- **Remote link stops connecting after 30 days**: a paired client's bearer
  session expires 30 days after pairing and is not renewed by use, so the
  environment goes dead while the server, Tailscale Serve and `curl` of the
  tailnet URL all look healthy. The server's boot log shows `Rejected
  authenticated session credential. reason: Session token expired.`, and
  `t3 auth session list` on the server has no entry for that client. Fix:
  `t3 auth pairing create` on the server and re-pair the environment from the
  client inside the token's 5-minute TTL.
- **"OAuth session expired" in T3 while other Claude sessions work**: two
  credential stores exist on a Mac, the keychain item and a leftover
  `~/.claude/.credentials.json` with a rotated-out refresh token, and the
  T3-spawned CLI picks the stale file. Fix both halves: run one headless auth
  as the user (`env -i HOME="$HOME" PATH="$PATH" claude -p "ok"`, which
  cleans the stale file) and kill any T3-spawned `claude --output-format
  stream-json` process started before the cleanup (it caches the dead
  credential; T3 respawns on the next message). Second variant: no file at
  all but the keychain item itself is corrupt (empty tokens, `expiresAt` 0);
  only `/login` fixes that.
- **Duplicate servers on the same state db**: a T3 client on another machine
  in managed SSH-remote mode spawns its own `t3 serve` here
  (`~/.t3/ssh-launch/<hash>/` with `managed`, `pid`, `port`), orphaned to PID 1
  and restarted within seconds if killed, registering the same relay tunnel
  as `t3code.service`. Fix on the client (switch it to T3 Connect or delete
  the connection), never by killing servers; enumerate with
  `pgrep -af '(\.bin/t3|dist/bin\.mjs) serve'` and identify by cgroup.
- **Local Network permission is never requested (upstream)**: the app doesn't
  trigger macOS's Local Network prompt, so LAN connections just fail with
  "Transport error" and no hint that the OS permission is the cause. Fix:
  probe/request Local Network access on first LAN connection attempt and
  surface a pointed error. Workaround until then: the subnet pre-authorization
  in the new-Mac checklist of `setup_t3_code.md`.
- **New SSH connections should offer a T3 connect method (upstream)**: when
  adding a new SSH connection, the wizard should prompt for a T3 connect
  method instead of silently assuming the SSH-tunnel launcher — i.e. offer
  T3 Connect linking at that point.
- **Remote server install is undocumented / manual (upstream + this repo)**:
  what the SSH launcher actually installs and runs on the remote (the
  headless t3 server) isn't documented anywhere, and the prerequisites were
  hand-built here (Node 24 via nvm + `~/.local/bin` symlinks on the Linux dev
  box). Upstream fix: document the server install, or better, have the
  launcher verify/install Node and the server itself. This repo's side is
  handled for Linux by `scripts/setup_t3_server_prereqs_linux.sh`; there is no
  Windows equivalent.
- **T3 Connect: 3 managed tunnels per account, and the CLI hides the error**:
  the mystery relay `403 POST
  /v1/client/environment-links` on RyzenWhite was the account's tunnel cap —
  the desktop's Set up T3 Connect dialog shows the real message ("this
  account already has its maximum of 3 managed tunnels. Unlink an
  environment to free one up"), while the headless CLI logs only a bare 403
  (upstream ask: surface the relay's error body). Which machines hold the
  three slots is the Slot policy in `setup_t3_code.md`. The cap
  counts *published environments*, not the remote-environments list in the
  dashboard — which is why it looks like only two. Workaround while capped:
  `t3 serve --tailscale-serve` + Remote link over the tailnet (no slot
  consumed; see Windows remotes section). Other breadcrumbs: auth codes are
  genuinely issued uppercase (a re-cased code 400s at
  token exchange — enter exactly as displayed); the 0.0.32 nightly never
  attempts the reconcile at all; upstream issue creation is restricted, so
  report via their Discord.
- **File chips resolve relative paths against the workspace root, inventing an
  absolute path that does not exist (upstream, found on 0.0.34)**:
  when an assistant message mentions a file by a repo-relative path — say
  `references/rules.tsv` for a file that actually lives at
  `<repo>/some/deep/dir/references/rules.tsv` — T3 renders it as a file chip
  whose hover tooltip reads `~/GitHub/references/rules.tsv`. That path is
  fabricated: the text fragment is joined to the workspace root with no check
  that anything is there. The tooltip looks authoritative and absolute, so it
  reads as fact. It cost real time here — the invented path pointed at the
  bare `~/GitHub` directory, which looked like an agent had written files
  outside any repo, and only a birth-time sweep of every file created that day
  under `~/GitHub` ruled it out. The failure is one-sided: chips whose path
  *does* resolve open the right file, so the feature works until it silently
  doesn't. Fix: only render a chip when the joined path exists, and otherwise
  leave the text plain rather than showing an absolute path that does not;
  resolving against the thread's cwd instead of the workspace root would fix
  the common case. Workaround: treat chip tooltips as a guess — confirm with
  `ls` before believing a file is somewhere surprising, and ask agents to
  write workspace-relative paths in messages so the join happens to be right.
- **Enumerating a hung FUSE mount wedges the whole server while systemd calls
  it healthy (upstream, OPEN)**: on a work Linux box (0.0.37
  boot service), a thread enumerated into the `google-drive-ocamlfuse` mount
  at `~/GoogleDrive` and the server went dark — clients saw it as a crash.
  Nothing had actually exited. The ocamlfuse daemon had wedged (main thread
  parked normally on `/dev/fuse` — wchan `fuse_dev_do_read` — one worker
  busy-spinning, no open TCP sockets), so every stat/readdir on the
  mountpoint blocked in the kernel forever; even `timeout 5 ls ~/GoogleDrive`
  hung. Inside t3, one worker thread sat in wchan `request_wait_answer` (the
  kernel FUSE wait) and **every HTTP request timed out** — `curl
  127.0.0.1:3773` gave `000` after 15 s — while the process stayed
  `active (running)`, the event loop kept ticking (`PortDiscovery.pollTick`
  spans still landing in `server.trace.ndjson` every 3 s), and the only
  visible symptom was the relay spamming `Incoming request ended abruptly:
  context canceled`. So `Restart=always` never fires (nothing exits) and
  `systemctl --user status` reads healthy — the blind spot to remember: probe
  the port, don't trust the unit state. Diagnosis: `timeout 5 ls
  <mountpoint>` per FUSE mount (`mount | grep fuse`), then per-thread wchan on the serve pid (`for t in
  /proc/<pid>/task/*; do cat $t/wchan; done`) — `request_wait_answer` is the
  tell. Recovery: kill the fuse daemon (SIGTERM was ignored; SIGKILL worked,
  and the mtab entry cleaned itself up), then restart t3 from outside its
  cgroup (`systemd-run --user --collect --unit=t3-restart-manual systemctl
  --user restart t3code.service` — `KillMode=mixed` SIGKILLs a `systemctl`
  run inside it). Server answered in 18 ms immediately after. Remount with
  `google-drive-ocamlfuse ~/GoogleDrive` and note the first listing on a
  fresh mount can take >10 s while the cache repopulates — don't misread
  that as still-hung (it settled to 0.3 s). This machine re-arms the trap by
  design: the mount comes back at every login
  (`~/.config/autostart/google-drive-ocamlfuse.desktop`) and holds a stale
  checkout at `~/GoogleDrive/Projects`, so any file picker or project
  enumeration browsing `$HOME` can walk into it. Upstream fix: filesystem
  walks should skip (or stat with a timeout) FUSE-backed paths so one dead
  network filesystem can't take down every thread on the box; a liveness
  probe of its own HTTP port would also let the service self-restart out of
  this state.
- **Pull request pane fails for client repos on a personal machine (upstream,
  found 2026-09-28 on desktop 0.0.42)**: in a client project, a thread with a
  linked PR opens the side pane to "Could not load pull requests. Pull request
  operation detail failed: GitHub CLI command failed." The link itself comes
  from the `link_pull_request` MCP tool, which only stores the URL, so the
  badge appears and "Open on GitHub" works; everything that needs data fails.
  **Cause.** `gh` is T3's only GitHub credential source. Every lookup runs
  `gh auth token --hostname <host>`, verifies it with `gh api user` and pins
  that token (`captureVerifiedCredential`,
  `apps/server/src/pullRequest/GitHubPullRequestCli.ts:1110`; the pin is
  applied in `sourceControl/GitHubCli.ts:405`). On Envy `gh` holds only the
  personal account, which cannot see the client's private org, so every
  lookup fails. `server.trace.ndjson` shows it for every branch in that
  project: `lookupStatusPr` events "PR lookup failed; keeping last known PR
  state." with `providerOperation: listChangeRequests` and `errorDetail:
  GitHub CLI command failed.` The exact `gh` stderr was not captured: running
  the personal account against the client repo by hand is exactly what we
  don't do. It is probably GitHub's "Could not resolve to a Repository", which
  T3 reports as a generic command failure instead of "no access".
  **No local fix within the rules.** There is no per-project token and no
  per-project PR opt-out: a project's `t3.json` accepts only `vcs.kind`
  (`apps/server/src/vcs/VcsProjectConfig.ts`). Each possible workaround breaks
  a rule. Signing `gh` in to the client account puts a machine-global client
  sign-in on a personal machine. A `gh` wrapper that picks the account from
  the cwd (via `GH_CONFIG_DIR` or `GH_TOKEN`) still uses `gh` for the client,
  and nightly `0.0.43-nightly.20260928.2375` broke that setup anyway by running
  every project's lookups from one directory and batching owners into one
  GraphQL query ([#14123](https://github.com/pingdotgg/t3code/issues/14123),
  triaged and confirmed). A `GH_TOKEN` in the server's environment applies to
  the whole server, so personal repos would then run as the client account.
  Workaround: ignore the pane in client projects. Use "Open on GitHub" or
  `ticket_pr.py pr-status`, which reads the token the repo's `.env` pins.
  **Upstream ask** (none filed as of 2026-09-28): a per-project credential
  source in `t3.json`, such as a token command or an env file plus key, or a
  per-project switch to turn off source control lookups. Also report a repo
  the account can't see as "no access to this repository", not "GitHub CLI
  command failed".
- **No Claude Code update is offered on a Mac that redirects `HOMEBREW_CACHE`
  (upstream, found 2026-09-29 on desktop 0.0.42 against `main @ d2c9281b81`)**:
  Envy ran Claude Code 2.1.280 with 2.1.284 published and T3 showed no update
  prompt, while its own provider message said "Claude Code v2.1.280 is too old
  for Claude Sonnet 5.5. Upgrade to v2.1.284 or newer to access it."
  **Cause.** T3 asks the installer that owns the binary what the latest
  version is, and asks npm only when no installer owns it. Here that is the
  `claude-code@latest` cask, so the server runs
  `brew info --json=v2 claude-code@latest` once an hour
  (`resolvePackageManagedProviderMaintenance`,
  `apps/server/src/provider/providerMaintenance.ts`). `brew info` answers from
  Homebrew's local API cache and refreshes it only past 7 days
  (`DEFAULT_API_STALE_SECONDS`, `Library/Homebrew/api.rb`). Envy has two of
  those caches. Every shell exports `HOMEBREW_CACHE` to the external SSD
  (`application_configs/bash/zshenv_local.envy`), so myupdater's `brew update`
  refreshes that one. The desktop app copies a fixed list of variables from
  the login shell (`LOGIN_SHELL_ENV_NAMES`,
  `apps/desktop/src/shell/DesktopShellEnvironment.ts`) that has
  `HOMEBREW_PREFIX`, `HOMEBREW_CELLAR` and `HOMEBREW_REPOSITORY` but not
  `HOMEBREW_CACHE`, so its brew reads the default `~/Library/Caches/Homebrew`,
  which nothing refreshes.
  **Evidence**, all read 2026-09-29 07:57 CDT. The package file
  `api/internal/packages.arm64_golden_gate.jws.json` under the SSD cache was
  dated Sep 29 07:55 and listed the cask at 2.1.284; the one under
  `~/Library/Caches/Homebrew` was dated Sep 23 15:55 and listed 2.1.280. The
  server process (`ps eww`) carried `PATH` and no `HOMEBREW_CACHE`.
  `~/.t3/caches/claudeAgent.json` held `versionAdvisory` with
  `status: current`, `currentVersion: 2.1.280`, `latestVersion: 2.1.280`, and
  the prompt needs `status: behind_latest` (`isProviderUpdateCandidate`,
  `apps/web/src/components/ProviderUpdateLaunchNotification.logic.ts`). Ruled
  out: the brew probe is healthy (`runHomebrew` span, 456 ms), nothing is
  dismissed (`dismissedProviderUpdateNotificationKeys: []`), and the
  notification settings gate thread notifications only.
  Left alone the prompt works briefly each time T3's cache passes 7 days, then
  goes stale for another week.
  **Second effect.** The update button runs
  `brew upgrade --cask claude-code@latest` in that same environment, so its
  217 MB download lands on the internal disk, which the redirect exists to
  prevent.
  **Upstream fix**: add `HOMEBREW_CACHE` to `LOGIN_SHELL_ENV_NAMES`, one line.
  That file is outside the frozen orchestration and provider layers. Not
  verified against the installed 0.0.42 bundle; the list was read from `main`
  and the server's environment matches it. After a release carrying it,
  confirm with `ps eww -p <server pid> | tr ' ' '\n' | grep HOMEBREW_CACHE`.
  **No local fix.** A LaunchAgent running
  `launchctl setenv HOMEBREW_CACHE ...` would work around it, but no manifest
  deploys a LaunchAgent, it would define the redirect a second time outside
  `zshenv_local.envy`, and it changes brew for every app launched from the
  Dock. Workaround: update Claude Code with myupdater or
  `brew upgrade --cask claude-code@latest` from a shell, both of which use
  the fresh cache. Threads started afterwards get the new binary.

- **Enter in the composer presses the compact button instead of sending
  (upstream, 0.1.0)**: seen 2026-10-16 after the update to 0.1.0 (the server
  on the Linux box reports `serverVersion: "0.1.0"` in
  `~/.t3/userdata/server-runtime.json`). Reported from use, not yet traced in
  the source: which client build, and whether it happens only while the
  compact button is showing, are not recorded. The same day's update also
  moved thread state from `state.sqlite` to `statev2.sqlite` (see
  `src/t3_state.py`).
- **T3 Connect drops off after a suspend when QUIC fails (cloudflared)**:
  QUIC to the edge fails from JasonZephyrus every time (`tls: no application
  protocol`). cloudflared falls back to http2 on a cold start, but on
  2026-10-02 after a suspend it retried QUIC only and never reconnected: the
  service stayed `active` while the machine was gone from T3 Connect. Handled
  by pinning the tunnel to http2 (`30-tunnel-http2.conf`, see Reachability in
  `setup_t3_code.md`).
- **A Windows client drops out of T3 for hours after an update restart**:
  Windows Update restarts just after the end of active hours, and without
  automatic sign-on the box waits at the sign-in screen, so the Startup folder
  never runs: 13 hours on RyzenWhite after the 2026-09-15 and 2026-09-24
  restarts. Even signed in, the Startup folder ran about 8 minutes after
  logon on RyzenWhite, behind every Run-key app. Handled by
  `restart_sign_on`, `preview_updates: false` and `parallel_logon_apps` in
  the host's inventory entry (see "Windows: desktop app only" in
  `setup_t3_code.md`).
