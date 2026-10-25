# Working rules

User-level rules for every session on my machines. Deployed to
`~/.claude/rules/working_rules.md` by each context's overlay. Context-free on
purpose: anything that names a client or a private host lives in that
context's own user-level CLAUDE.md.

## Commits, pushes, publishing

- Never `git commit` or `git push` unless the current message asks for it.
  A "commit and push" earlier in the session does not carry forward; each
  batch needs its own instruction. Urgency is not an exception; ask.
- When told to push, run plain `git push`. Every repo has its upstream set;
  naming a remote or branch only guesses wrong.
- Never force push, in any repo, on any branch: no `--force`,
  `--force-with-lease` or `+refspec`. Never amend, rebase, squash or reset a
  commit that has been pushed, and never offer that as an option. A mistake
  in a pushed commit is fixed by a new commit on top.
- Commit messages are plain lowercase descriptions matching the repo's log.
  No scope or tool-name prefixes, no attribution trailers, no session links.
- Ticket, PR, commit, email and chat text sent as me: my wording is the spec.
  State only facts I gave or a source shows, never invented circumstances. No
  extra sentences, no templated checkbox or "Summary / Test plan" scaffolding.
  Short plain prose.
- Never push a tool-minted temporary branch (`t3code/<hash>`); rename it to
  the ticket branch first.
- After a merge I asked for, delete the PR's head branch on the remote and
  locally once the PR shows merged.

## Answering versus acting

- A question wants an answer, not an action. Answer it, run only the
  read-only checks the answer needs, and change nothing until I say "fix",
  "change" or "do it". "Why did you add X?" is not a request to remove X.
- Lead with the answer in one or two sentences, then only what needs my
  decision. Use the names I use: no coined labels, abbreviations, file slugs
  or "same" in a table cell. Never re-ask a settled point or re-propose an
  option I ruled out.
- Before reporting done, restate my original goal in one line and check the
  result against it; a finished sub-step is not the goal. End a finished task
  with its state: committed or not, pushed or not, PR open or merged, deployed
  or not, branches left, thread settled or not.
- After an interruption or "continue", resume the interrupted step; never
  reply "No response requested."
- Explain what and why before any permission prompt, especially on sensitive
  paths or state-changing commands. Reading my credentials repos is fine; an
  unexplained grep of them is not.
- A change to configuration or capability is not permission to run it
  against real data. Dry-run into a throwaway target, show what a real run
  would do, and stop.
- Before stating a cause, a state or a "can't", check it with whatever
  settles it: the code, logs, ssh to a machine I named, the database, the
  attachment, the app's own records. A doc, comment or repo trap-note is a
  hypothesis until checked, and a failure of your own probe is not a finding.
  Call something unverified only when nothing you can reach settles it.
- Never claim a chain works, or fails, past the hop you tested; name the hops
  you verified. For a machine I did not point you at, offer to check it there
  instead of saying it could not be checked. "Check" always means read-only.
  Instrument the hop only I can trigger.
- For a fault, measure what owns it or test one named cause before proposing
  a fix. Never offer a reboot, a purchase, or dropping a feature I use as the
  fix. If I say it started after a change, test that change first.
- A permission denial is about this session, not the task: never write it
  into memory, a command or a doc as a rule. Rerun the read-only parts one per
  call, then say what was blocked and ask once.
- When I state a rule or preference, propose the line for the tracked
  instruction file that owns it. `~/.claude/projects/*/memory` loads in one
  repo on one machine only.
- Before producing an output (a list, PDF, report), find my script or command
  that already makes it and run that.
- Show diffs in unified format (`git diff`, `git diff --no-index`, `diff -u`).

## Machines and deployment

- Machine setup comes from the dotfiles repo only: `docs/setup_*.md`,
  `app_lists/`, `scripts/`, the deploy manifests. Never install or configure
  a device ad hoc, even over ssh with the access to do it. Grep the whole repo
  for an existing install method before adding one; never a second one.
- Deployed configs are symlinks into their source repo. Edit the source; never
  copy over or hand-place a file under `~/.claude` or any deployed path.
- A per-machine config is a class: when one workspace, manifest or settings
  file changes, enumerate every sibling across the credentials repos and apply
  the change to each, then grep-verify.
- Host-specific manifest payloads use `<base>.<host>.<ext>`; variant
  resolution gates per host, never a bespoke filename.
- Code moves between machines through git only. No scp of source into another
  checkout; commit to a branch, push, pull. Compare with `git hash-object`.
- Edit in my existing checkout; never `git worktree add` or clone a copy.
- Never run a recursive name-matched delete over a home folder or repo tree.
  Enumerate, print the full list, agree, delete those exact paths.
- Never validate tmux on the default socket; use `tmux -L cfgtest`.
- Cache and data redirects to an external volume never fall back to the
  internal disk when it is unmounted. Warn and let the tool fail.
- Do not overwrite generated output files (reports, exports, PDFs) when
  testing; gitignored does not mean disposable.
- Prefer home-LAN addresses over Tailscale names in configs; subnet routes
  make them reachable from everywhere.
- Before handing me a command for another machine, run its read-only form
  there (`--help`, `--dry-run`, `ls` of the script), and give it to me as one
  `ssh -t <host> '...'` line.
- Open a page in the browser and profile of the context the work belongs to,
  as that context's user-level CLAUDE.md names it, never in whichever window
  happens to be in front.

## Code and design

- One method per job. Match the transport or tool the repo already uses;
  never add a second mechanism or a fallback path.
- No interim compatibility layers when things move: ship the clean end state
  everywhere at once and let me sequence the pushes.
- Never disable or suppress a failing check; fix the code it points at, and
  confirm the fix is a fixed point for the formatter.
- Never edit a lockfile (`uv.lock`, `package-lock.json`, any `*.lock`): it is
  tool output. Regenerate it with its tool (`uv lock --upgrade-package <name>`,
  or delete and relock) and commit only what the tool wrote.
- Fix the code, not the editor: no `.vscode` workarounds for bad structure.
- Tests run real from any machine. An unreachable dependency is red, never a
  silent skip, deselect or stale-cache green.
- Database bootstrap is the application's job, at startup, additive and
  idempotent only. Never `DROP`, `TRUNCATE` or an unfiltered `DELETE` in a
  startup path, and never destructive DB operations without confirmation.
  Shared databases are production.
- An app never names, imports from, or bind-mounts another of my apps; shared
  identity and data go through shared infrastructure.
- Credentials, not sign-ins: no `gh` CLI, raw GitHub API call or signed-in
  machine state, in scripts or in one-off commands (`gh` may stay installed).
  Use the token pinned by the repo's `.env` through `ticket_pr.py`.
  Reading a ticket means `get-ticket`, which returns every field, comment and
  attachment at once; updating one means `add-comment`. When the harness
  lacks a capability, add it there with a test instead of calling the API
  directly.
- Nothing client-specific in a public repo: no client names, repo slugs,
  ticket prefixes or client hostnames. Use the `acme` placeholder. Public text
  never says or implies how many work contexts I have. My own host names in
  `compose.<host>.yaml` filenames, my repo names and my email in commit
  metadata are not leaks. Fix a leak with a new commit on the branch tip, never
  by rewriting history. Only a real credential justifies touching history, and
  that is my call: tell me so I can rotate it.
- Contexts never reference each other: a context's name, repo, ticket key or
  hostname never appears in another context's repos, docs, configs, commands
  or deployed files, and never in an example. Describe a mirrored pattern
  generically. Before finishing, run
  `python3 ~/GitHub/dotfiles/src/context_leak_check.py --repo <repo>` on every
  repo you edited; never hand-type identifiers into a grep.
- When a run disproves something a doc or note says, fix that line in the
  same change.
- Findings outside the current task become tracked items where that context
  tracks its work (the repo-backlog skill for my repos, a client's ticket
  commands for theirs), never chat-only notes; an item closes when its fix
  lands.
- A "map" of a codebase means one self-contained interactive HTML plus a
  diffable text file, never a pile of cross-referenced markdown.
- Public-facing writing is plain and terse: no em-dashes, no emojis, no
  marketing phrases.

## Threads

- Other threads edit the same checkouts: stage only the paths you changed, by
  name, and leave other uncommitted edits alone.
- When the work moves to a new incident, host or repo, say so and offer a
  handoff note for a new thread.
- Before fanning one task out to many threads, run it on one repo first, put
  the working commands in the shared prompt, and keep repos that share content
  in one thread.
- "Settle this thread" means calling the t3-code `t3_thread_organize` tool
  with action `settle`; never call a thread settled without that call.
- Watch a long job with a background Bash that polls a log on the host and
  exits on the event, never with CronCreate or cloud routines.
- If T3's `preview_snapshot` times out once, take the screenshot with headless
  Chrome (`--headless=new --screenshot=<png> --window-size=W,H`) and a
  throwaway `--user-data-dir`.

## Shell

- The Bash tool runs zsh. Quote every glob and every word starting with `=`
  that a command should receive (`grep --include='*.md'`, `find . -name
  '*x*'`, `echo '==='`). Unquoted, zsh expands them itself and aborts the
  command with "no matches found" or "not found", so its output silently goes
  missing.
- zsh does not word-split an unquoted variable, so `set -- $pair`,
  `for x in $list` and `cmd $args` pass ONE word, not several. Loop over
  literals or an array (`for h in a b c`, `hosts=(a b); for h in
  "${hosts[@]}"`), never over a string. A loop whose first iteration prints
  the whole string as one field has hit this; fix the loop before reading
  anything into the remote's reply.
- `log` is a zsh builtin: run the macOS unified log as `/usr/bin/log show`.
- In a uv project run Python as `uv run python`; bare `python3` lacks the
  project's packages.
- Read a tool's main or `--help` before running it; a run with no arguments
  can rewrite files in place.
