# Repo improvement tasks

Backlog of deployment/tracking improvements and repo splits, from the July 2026
repo analysis. Each task below is written as a self-contained brief for a
subagent: run one task per agent, in a fresh session, when we're ready to do it.

## How to use this file

- **Spawn one subagent per task.** Give it the full task section verbatim plus
  the "Ground rules" section. Tasks are independent unless a dependency is
  called out.
- Mark a task done by moving it to the "Completed" section at the bottom with
  the date and the commit/PR that landed it.

## Ground rules for every task

1. **Never push to `master`.** Pushing `master` auto-deploys to the homelab via
   a root cron on elitedesk (see `docs/homelab_deployments.md`). Work on a
   feature branch, push the branch, and stop — Jason merges.
2. Before committing Python changes run: `uv run isort .`, `uv run flake8 .`
   (line length 120, max-complexity 15), and `uv run pytest` (unit suite only).
3. No secrets in the repo. `.env` is a symlink to `../personal_credentials/`;
   never inline its values anywhere.
4. Keep platform-specific things in their existing buckets (see `CLAUDE.md`).
5. If a step turns out to require something destructive or outward-facing that
   the task text does not explicitly authorize (history rewrite, force push,
   deleting files on remote machines, publishing a repo), stop and report
   instead of proceeding.

---

## Task 9 (optional, low urgency) — Separate work configs from personal

**Problem.** Employer-specific files are mixed into personal config:
`application_configs/claude/settings.hf.json` and `settings.hf_bedrock.json`,
`application_configs/vscode/workspace.hellofresh.code-workspace`,
`application_configs/barrier/barrier_config.hellofreshwindows.sgc`,
`scripts/aws_credential_extractor*.sh`, `app_lists/windows_apps_aws_choco.txt`.
No secrets are in them today (verified July 2026), but if this repo ever goes
public or the employer changes, the boundary should already exist.

**Steps.** Present Jason two options with a file inventory before moving
anything: (a) a `work/` subtree inside this repo mirroring the existing bucket
structure, or (b) a separate private `work-dotfiles` repo. Whichever is chosen,
move with `git mv` (or plain copy to the new repo), update references, and add
a conventions note to `CLAUDE.md` about where work-specific files go. Fold the
naming into Task 5's convention if that has landed.

---

## Completed

- **2026-07-03 — Drift fixes** (analysis item 5): `scripts/create_sym_links_startup.ps1`
  now deploys `app_jumping.ahk` (was pointing at `key_remaps.ahk`, deleted in
  commit 8732747); renamed `application_configs/claude/setings_hf_bedrock.json`
  → `settings_hf_bedrock.json` (typo, no references existed).
- **2026-07-03 — `design/` extracted** to `~/GitHub/style-terminal-navy`
  (public repo on ReadableCode): SKILL.md, STYLE.md, tokens.css, previews.
  Cross-references updated to point at the new repo; README added.
- **2026-07-05 — Tasks 1+3+4+2 (deploy tooling)**, commit 79a9b43 on the
  `repo-improvements` PR: `deploy_manifest.yaml` (single source of truth,
  harvested from all setup docs) + `src/deploy_configs.py` argparse CLI
  (`deploy` / `--dry-run` / `--status` with OK/NOT_DEPLOYED/BROKEN_LINK/
  WRONG_TARGET/NOT_A_LINK/DIVERGED classification, non-zero exit on drift,
  wired into `scripts/my_updater.sh`); `os.link()` eliminated (Windows:
  symlink → copy fallback, never hard links); backups now go to
  `data/config_backups/`; setup docs point at the one command.
- **2026-07-05 — Task 6 (crontab collection)**, commit 0716eca:
  `ansible_playbooks/collect_crontabs.yml` — read-only, raw-module (works on
  python-less remotes), `--check`-safe, idempotent. Live run captured 15 new
  `triggers/crontab_extraction_*` snapshots (11 hosts + root crontabs on the
  pis); unreachable hosts fail fast. MacBookPro12 and Envy still need
  Jason's SSH key before they can be collected.
- **2026-07-05 — Task 5 (variant naming convention)**, commits 71d58ae +
  fe9a64f: 14 files renamed to `<base>.<token>.<ext>` (lowercase host /
  platform / context token); `deploy_configs.py` auto-resolves exact
  hostname → platform → bare default; convention documented in `CLAUDE.md`.
  Per-machine re-link steps are in the PR description — each machine just
  reruns `uv run python src/deploy_configs.py` after pulling.
- **2026-07-05 — Task 7 (narrowed scope)**, commit 0d87d4d: Jason's rule —
  dotfiles goes on every device he touches (repo pulling + config
  deploy/pull/push stay here); only homelab-only jobs moved to the local,
  unpublished `~/GitHub/personal-automation` repo (`bitwarden.py` +
  `Dockerfile-bitwarden_backup`, `parse_minecraft_logs.py`, the README
  Bitwarden/`bw export` sections; the new repo vendors the small utils it
  imports). `src/utils/` and all pull/deploy tooling stayed; only
  `matplotlib` left `pyproject.toml`. No crontab consumed the movers;
  cutover checklist is in the new repo's README, Jason executes. Repo stays
  local until Jason decides (private if ever pushed).
- **2026-07-05 — Task 8 attempted and REVERTED — do not re-attempt**
  (commit 27af08c, reverted in d527d69): splitting `go_apps/` into a
  separate go-tools repo broke Jason's rule that every host clones ONLY
  dotfiles — `gitpullall` must work from the committed
  `go_apps/git_puller` binaries with no second clone. Committed binaries
  and the `.git` size are an accepted cost; binary paths may move freely
  because the aliases in this repo control them, but the tools themselves
  stay in dotfiles.
