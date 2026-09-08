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
- Commit messages are plain lowercase descriptions matching the repo's log.
  No scope or tool-name prefixes, no attribution trailers, no session links.
- Ticket, PR and commit text: my wording is the spec. No extra sentences, no
  templated checkbox or "Summary / Test plan" scaffolding. Short plain prose.
- Never push a tool-minted temporary branch (`t3code/<hash>`); rename it to
  the ticket branch first.

## Answering versus acting

- A question wants an answer, not an edit. Change code only when asked
  ("fix", "change", "do it").
- Explain what and why before any permission prompt, especially on sensitive
  paths or state-changing commands. Reading my credentials repos is fine; an
  unexplained grep of them is not.
- A change to configuration or capability is not permission to run it
  against real data. Dry-run into a throwaway target, show what a real run
  would do, and stop.
- Verify claims in the code before they shape a decision; a repo's own
  trap-notes are hypotheses. Say plainly when something is unverified.
- Never claim a chain works past the hop you could test. Name the hops you
  verified and instrument the one only I can trigger.
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

## Code and design

- One method per job. Match the transport or tool the repo already uses;
  never add a second mechanism or a fallback path.
- No interim compatibility layers when things move: ship the clean end state
  everywhere at once and let me sequence the pushes.
- Never disable or suppress a failing check; fix the code it points at, and
  confirm the fix is a fixed point for the formatter.
- Fix the code, not the editor: no `.vscode` workarounds for bad structure.
- Tests run real from any machine. An unreachable dependency is red, never a
  silent skip, deselect or stale-cache green.
- Database bootstrap is the application's job, at startup, additive and
  idempotent only. Never `DROP`, `TRUNCATE` or an unfiltered `DELETE` in a
  startup path, and never destructive DB operations without confirmation.
  Shared databases are production.
- An app never names, imports from, or bind-mounts another of my apps; shared
  identity and data go through shared infrastructure.
- Credentials, not sign-ins: no `gh` CLI or signed-in machine state in
  scripts. Use the token pinned by the repo's `.env` through `ticket_pr.py`
  or raw REST.
- Nothing client-specific in a public repo: no client names, repo slugs,
  ticket prefixes or hostnames. Use the `acme` placeholder.
- Contexts never reference each other: a client's name, repo, ticket key or
  hostname never appears in another client's repos, docs, configs, commands
  or deployed files, and never in an example. Describe a mirrored pattern
  generically. Before finishing, grep every edited file for every other
  context's identifiers.
- Findings outside the current task become tracked backlog entries in the
  repo that owns the fix (the repo-backlog skill), never chat-only notes;
  closed entries are deleted in the same commit as the fix.
- A "map" of a codebase means one self-contained interactive HTML plus a
  diffable JSON, never a pile of cross-referenced markdown.
- Public-facing writing is plain and terse: no em-dashes, no emojis, no
  marketing phrases.
