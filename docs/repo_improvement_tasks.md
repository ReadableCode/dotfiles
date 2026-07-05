# Repo improvement tasks

Backlog of deployment/tracking improvements and repo splits, from the July 2026
repo analysis. Each task below is written as a self-contained brief for a
subagent: run one task per agent, in a fresh session, when we're ready to do it.

## How to use this file

- **Spawn one subagent per task.** Give it the full task section verbatim plus
  the "Ground rules" section. Tasks are independent unless a dependency is
  called out (Task 2 requires Task 1).
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

## Task 1 — Manifest-driven config deployment

**Problem.** `src/deploy_configs.py` defines a solid `deploy_config()` function
(handles repo-only / system-only / both / neither cases, with ingest and backup
options) but its `__main__` block only prints a message — nothing calls the
function. The real repo-path → system-path mappings live as copy-paste shell
commands scattered through `docs/setup_mac_workstation.md`,
`docs/setup_vscode.md`, `docs/setup_zed.md`, `docs/setup_neovim.md`,
`docs/setup_windows_workstation_personal.md`, and `docs/powershell.md`. There is
no single command to deploy a machine and no single source of truth for what
should be deployed where.

**Goal.** One manifest file + one command deploys (or dry-runs) every config
for the current machine.

**Steps.**

1. Create `deploy_manifest.yaml` at the repo root. Suggested entry schema:

   ```yaml
   - name: zshrc
     repo: application_configs/bash/.zshrc
     dest:
       darwin: ~/.zshrc
       linux: ~/.zshrc
     # optional keys:
     # dest.windows: path (only if the app is deployed on Windows)
     # hosts: [ENVY, ELITEDESK]   # limit to specific hostnames (uppercase)
     # method: symlink | copy      # default symlink
     # note: free text (e.g. "nvim on Windows uses XDG_CONFIG_HOME instead")
   ```

2. Harvest every existing mapping by grepping the docs:
   `grep -rn "ln -s\|mklink\|New-Item" docs/` — each hit that points into
   `application_configs/` or `scripts/` becomes a manifest entry. Include the
   AHK startup entries currently hardcoded in
   `scripts/create_sym_links_startup.ps1` (`app_jumping.ahk`, `sheets.ahk` →
   Windows Startup folder).
3. Apps that intentionally do NOT use links (nvim on Windows via
   `XDG_CONFIG_HOME`, per `docs/setup_neovim.md`) get an entry with
   `method: none` and a `note`, so the manifest is a complete inventory, not
   just a link list.
4. Rewrite the `__main__` block of `src/deploy_configs.py` with `argparse`:
   `deploy` (default) and a `--dry-run` flag that prints planned actions
   without touching the filesystem. Resolve `~`, pick the `dest` for the
   current platform, apply `hosts` filters using
   `utils.host_tools.get_uppercase_hostname()`.
5. Idempotency: an entry whose destination is already a correct link is a
   no-op, and a second run right after a first run must report zero changes.
6. Update each setup doc: replace the per-app `ln -s`/`mklink` blocks with a
   pointer to `uv run python src/deploy_configs.py --dry-run` / `deploy`,
   keeping any app-specific caveats as prose.

**Acceptance criteria.**

- `uv run python src/deploy_configs.py --dry-run` on any machine lists every
  applicable entry with its planned action and exits 0.
- Running deploy twice in a row: second run reports all no-ops.
- No mapping exists only in a doc; `grep -rn "ln -s.*application_configs"
  docs/` hits only prose examples that also exist in the manifest.
- Unit tests in `tests/` for manifest parsing and per-platform dest resolution
  (no filesystem side effects; use tmp_path).

---

## Task 2 — `--status` drift detection (requires Task 1)

**Problem.** There is no way to ask a machine "are your deployed configs
current and healthy?" Drift is discovered by accident (see Completed: a
deploy script referenced a file deleted months earlier).

**Goal.** `uv run python src/deploy_configs.py --status` prints a per-entry
health report and exits non-zero if anything is wrong, so it can run from cron.

**Steps.**

1. Add a `status` mode that walks the manifest and classifies each applicable
   entry:
   - `OK` — destination is a link resolving to the repo file (or, for
     `method: copy`, content hash matches the repo file).
   - `NOT_DEPLOYED` — destination missing.
   - `BROKEN_LINK` — destination is a dangling symlink.
   - `NOT_A_LINK` — destination is a regular file where a link was expected;
     also report whether its content matches the repo copy (candidate for
     ingest) or diverges.
   - `DIVERGED` — `method: copy` and hashes differ (this is the Windows
     hard-link failure mode from Task 3 being caught).
2. Exit code 0 only if everything is `OK`; print a one-line summary last
   (`12 ok, 1 broken_link, 2 not_deployed`).
3. Add a `--status` invocation to `scripts/my_updater.sh` so every manual
   update run surfaces drift, and document a cron line for it (do not install
   cron entries yourself — see homelab deploy doc for how jobs are managed).

**Acceptance criteria.**

- On the machine where it runs, `--status` output covers every applicable
  manifest entry, and a deliberately broken link (create one in a temp HOME
  during tests) is reported as `BROKEN_LINK` with non-zero exit.
- Unit tests cover each classification using `tmp_path` fixtures.

---

## Task 3 — Fix silent Windows hard-link breakage

**Problem.** `deploy_config()` uses `os.link()` (hard links) on Windows
(`src/deploy_configs.py` — the three `os.link` call sites). Git replaces files
with new inodes on checkout/pull, so after the next `git pull` the deployed
hard link still points at the *old* content and silently stops updating. This
is the worst kind of drift: everything looks deployed.

**Goal.** Windows deployments either use real symlinks or copies that Task 2's
`--status` can verify.

**Steps.**

1. In `deploy_config()`, on Windows try `os.symlink()` first — it works
   without admin when Windows Developer Mode is enabled. Catch `OSError`
   (privilege error) and fall back to **copy** (never hard link), so the
   worst case is a copy that `--status` can hash-compare, not a stale inode.
2. Remove all `os.link()` usage.
3. Update `docs/sym_linking_and_hard_linking.md` with a "why not hard links
   for git-tracked files" section explaining the inode-replacement hazard, and
   update its `New-Item -ItemType HardLink` examples to symlink/copy
   equivalents.
4. Where an app supports config-path indirection instead of links, prefer
   documenting that (the repo already does this well: nvim via
   `XDG_CONFIG_HOME` set in `application_configs/powershell/powershell_aliases.ps1`,
   git via `include.path`). Note candidates in the manifest `note` field —
   don't migrate apps in this task.

**Acceptance criteria.**

- `grep -n "os.link" src/` returns nothing.
- Behavior table (symlink success / symlink denied → copy) covered by unit
  tests with monkeypatched `os.symlink`.
- Doc updated.

---

## Task 4 — Keep deploy backups out of the repo tree

**Problem.** `deploy_config()`'s backup path writes
`<repo_file>.backup.<timestamp>` right next to the tracked config inside the
repo, and `.gitignore` has no matching rule — the first real backup becomes
untracked clutter (or worse, gets committed).

**Steps.**

1. Change the backup destination to `data/config_backups/<original relative
   path>.<timestamp>` (`data/` is already gitignored). Create parent dirs as
   needed.
2. Also add `*.backup.*` to `.gitignore` as belt-and-braces against old
   behavior.

**Acceptance criteria.** Unit test proves a Case-3 deploy (both sides exist,
`backup_into_repo=True`) writes under `data/config_backups/` and leaves the
config's directory clean; `git status` unaffected.

---

## Task 5 — One naming convention for host/platform-specific configs

**Problem.** Three conventions coexist for "this file is for machine/platform
X": hostname embedded mid-name (`barrier_config_ryzenwhite.sgc`), platform
suffix (`vscode/settings_mac.json`), and bare-hostname filename
(`elitedesk.code-workspace`). A manifest can't auto-resolve host overrides
against three patterns.

**Goal.** Single convention: `<base>.<HOST-or-platform>.<ext>` suffix, e.g.
`settings.mac.json`, `barrier_config.ryzenwhite.sgc`,
`workspace.elitedesk.code-workspace` — resolution order: exact hostname →
platform → bare default.

**Steps.**

1. Enumerate the affected files: `application_configs/barrier/*`,
   `application_configs/vscode/*` (both `settings_mac.json` and all
   `*.code-workspace`), `application_configs/claude/settings_hf*.json`.
   Decide and document the final scheme in `CLAUDE.md`'s conventions section
   before renaming.
2. Rename with `git mv` only. Update every reference:
   `grep -rn "<oldname>" docs/ scripts/ src/ application_configs/`.
3. **Caution — existing symlinks on other machines point at the old names**
   (e.g. `~/GitHub/envy.code-workspace` →
   `dotfiles/application_configs/vscode/envy.code-workspace`). Renames break
   them on every machine at next pull. Add each renamed file to the Task 1
   manifest so redeploying fixes the links, and list the affected
   machines/paths in the PR description.
4. Teach the Task 1 manifest resolver the hostname → platform → default
   fallback so future host variants need no new manifest entries.

**Acceptance criteria.** No references to old names anywhere in the repo;
manifest resolves the right variant per host in unit tests; PR description
lists the re-link step per machine.

---

## Task 6 — Collect crontabs from all hosts (ansible)

**Problem.** `triggers/` is supposed to snapshot scheduled jobs per host but
contains only elitedesk. Cron jobs on every other machine are untracked.

**Steps.**

1. Write `ansible_playbooks/collect_crontabs.yml`: for each host in
   `inventory/hosts`, run `crontab -l` (and `sudo crontab -l` for root where
   sudo is available), and `fetch` results back to
   `triggers/crontab_extraction_<hostname>.txt`, matching the existing
   elitedesk file's naming so the `.gitignore` allowlist
   (`!triggers/crontab_extraction*`) keeps them tracked.
2. Handle hosts with no crontab gracefully (empty file with a header line, not
   a failed play).
3. Follow the patterns of the existing playbooks in `ansible_playbooks/`
   (inventory groups, become usage). Document the run command in
   `docs/ansible_playbooks.md`.
4. Do NOT install anything on remote hosts; read-only collection.

**Acceptance criteria.** Playbook is idempotent, `--check`-safe, and a run
against reachable inventory hosts produces one tracked file per host.

---

## Task 7 — Split the Python automation stack into its own repo

**Problem.** The heavy Python code in this repo is not machine configuration:
`src/utils/` (gmail/google/drive/sheets/s3/postgres/display/date/json tools)
plus the jobs that consume it. It's the reason "dotfiles" needs pandas,
matplotlib, jupyterlab, streamlit, impyla, psycopg2, boto3, a 600 MB venv, and
live-credential integration tests.

**Scope to move** (verify with a fresh grep before moving):

- `src/utils/` (all of it, including the `df_*.csv` and yaml data files)
- Jobs: `src/bitwarden.py` + `Dockerfile-bitwarden_backup` + `.dockerignore`,
  `src/pull_home_assistant_configs.py`, `src/pull_router_configs.py`,
  `src/chrome_bookmarks.py`, `src/parse_minecraft_logs.py`,
  `src/ssh_devices.py`
- `tests/` and `integration_tests/` (they test the above), plus
  `conftest.py`
- The matching dependencies out of `pyproject.toml`

**Stays here:** `src/deploy_configs.py`, `src/config.py`, everything in
`scripts/` (verified 2026-07: no `scripts/*.py` imports `src/utils`), with a
slimmed `pyproject.toml` (roughly: python-dotenv, pyyaml, paramiko if still
needed, pytest + lint tooling). `deploy_configs.py` imports
`utils.host_tools.get_uppercase_hostname` — inline that one small function
rather than keeping a dependency.

**Steps.**

1. Create the new repo locally at `~/GitHub/` (suggest name:
   `personal-automation`). Plain copy is fine — do NOT rewrite dotfiles
   history. Set up uv (`pyproject.toml`, `.python-version`, lockfile), carry
   over flake8/isort/mypy configs and the CLAUDE.md sections that describe the
   two test suites.
2. Keep the `.env` pattern: symlink to `../personal_credentials/personal.env`,
   same gitignore rules as here.
3. In dotfiles: remove the moved files, slim `pyproject.toml`, re-lock
   (`uv sync`), fix `README.md` (Bitwarden/docker sections move to the new
   repo), and make sure `uv run pytest` and `uv run python
   src/deploy_configs.py --dry-run` still pass.
4. **Cutover plan for scheduled jobs — do not execute, just document in the
   new repo's README:** elitedesk's cron runs
   `/home/jason/GitHub/dotfiles/.venv/bin/python3 .../scripts/speedtest_logger.py`
   and the homelab push-to-master deploy builds from dotfiles (see
   `triggers/crontab_extraction_elitedesk.txt` and
   `docs/homelab_deployments.md`). List every cron line and deploy reference
   that must be repointed, host by host. Jason executes the cutover.
5. Do not publish the new repo; leave it local until Jason reviews (it
   orbits credentialed services — default private if ever pushed).

**Acceptance criteria.** Both repos lint, type-check, and pass their unit
suites independently; dotfiles has no import of `utils.*` left
(`grep -rn "from utils\|import utils" src/ scripts/`); the cutover checklist
exists and names every affected cron/deploy line.

---

## Task 8 — Move `go_apps/` to its own repo with releases; stop committing binaries

**Problem.** Five ~2.5 MB `git_puller` binaries are committed, and history
shows the Linux and Windows ones recommitted 4× each — the main driver of the
18 MB `.git`. Binaries in git bloat every clone forever.

**Steps.**

1. Before anything: find what consumes the committed binaries —
   `grep -rn "git_puller" docs/ scripts/ triggers/ ansible_playbooks/` and
   check crontab snapshots — record each consumer and its path.
2. New repo at `~/GitHub/` (suggest: `go-tools`) containing
   `git_puller/`, `go_client_server/`, `syncthing_artifact_cleanup/` source +
   READMEs (no binaries). Add a GitHub Actions workflow (or goreleaser) that
   builds the matrix currently represented by the five committed files
   (linux/amd64, linux/arm, windows/amd64, darwin/arm64, darwin/amd64) and
   attaches them to a release on tag push.
3. In dotfiles: `git rm -r go_apps/` (plain removal on a branch — do NOT
   rewrite history; a history purge with `git filter-repo` would force-push
   `master`, break every clone and the elitedesk auto-pull, and is a separate
   decision for Jason).
4. Write the consumer migration list (from step 1) into the new repo's README:
   each cron/script that ran a committed binary gets a "download from
   releases" or `go install` replacement line. Jason executes on-host changes.
5. Publishing the repo (public/private) is Jason's call — leave it local,
   note the decision in the PR description.

**Acceptance criteria.** New repo builds all binaries in CI; dotfiles branch
removes `go_apps/` with no dangling references (`grep -rn "go_apps\|git_puller"`
in docs/scripts is either gone or updated); consumer list is complete.

---

## Task 9 (optional, low urgency) — Separate work configs from personal

**Problem.** Employer-specific files are mixed into personal config:
`application_configs/claude/settings_hf.json` and `settings_hf_bedrock.json`,
`application_configs/vscode/hellofresh.code-workspace`,
`application_configs/barrier/barrier_config_hellofreshwindows.sgc`,
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
