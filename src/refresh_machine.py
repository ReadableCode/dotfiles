#!/usr/bin/env python3
"""Pull every repo, then bring this machine's configs up to date.

The one implementation of pullrepos, gitpullall and myupdater on every
platform. ``.shared_aliases`` and ``powershell_aliases.ps1`` only launch it, so
the steps and their order exist once instead of once per shell language, and
``--help`` (HELP_PAGE below) is the only description of what they do.

Every step runs even when an earlier one fails, the way the shell chains always
behaved: a repo that would not pull must not stop the deploy of the configs
that did. Ctrl+C stops the whole run. The exit code is 1 when any step failed.

Stdlib-only on purpose, like ``src/ssh_aliases.py``: a bare ``python3`` runs it,
so a machine without uv can still pull (the uv steps then say uv is missing).

The steps stream to the terminal as they run; the page at the end comes from
the report file every step appends to (``refresh_report.py`` has the format).
"""

import argparse
import functools
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import refresh_report
import terminal_style

HELP_PAGE = """# refresh_machine

> pull every repo, then bring this machine's configs up to date.
> gitpullall, myupdater and pullrepos all run this, from any directory, against `$gitDir`.
> every step runs even when an earlier one fails, and the exit code is 1 when any did. ctrl+c stops the run.
> the steps stream as they run; a status page follows: what pulled, upgraded (`old -> new`), deployed, installed.
> `--check` is the read-only twin: it reports what the steps below would change and writes nothing.

## what happens

1. pull every repo under `$gitDir` at the same time
   a repo it cannot pull is tagged `WIP PROTECTED`, `FAILED` or `AUTH REQUIRED`, left as it is, and counted in a warning
   runs `go_apps/git_puller -path $gitDir -r`
   when the pull moves dotfiles, the run starts again from the code it just pulled, so a fix applies on this run
2. with `--packages` only: upgrade os packages, before the deploy so a config an upgrade clobbers is linked again
   runs `scripts/my_updater.sh` on macos and linux, `scripts/my_updater.ps1` on windows
   on windows winget upgrades only what a winget app list names and chocolatey only what it installed,
   neither to a version already there, nor an app `app_upgrade_holds.yaml` names; each upgrade is one quiet line,
   its output goes to `~/logs/updater`, and the ones that failed are listed in the summary with the reason
   a step whose tool is missing offers to install it with `scripts/bootstrap.sh --only <tool>` first
   once an os release upgrade is downloaded, steps 7 and 7b wait for its reboot: any package change would undo it
3. offer to clone repos this machine should have but is missing, asking [y/N/q] first
   the lists are each context's `<context>_repos.yaml`, which the pull just refreshed
   runs `src/clone_repos.py`
4. sync every uv project's environment to its lock, so each repo's own linters and formatters are installed
   runs `src/sync_python_envs.py`
5. deploy configs from the manifests, for this host and platform
   runs `src/deploy_configs.py`
6. prune config paths a removals file names and no manifest entry still wants
   runs `src/deploy_configs.py prune --apply`
7. with `--packages` only: offer to uninstall apps an app removals file retired, asking [y/N/q] per app
   the app lists win: a package one of them still names is never offered
   on windows, also offer the extra copy of an app an app list installs, found by winget, not declared
   runs `src/app_removals.py`
7b. with `--packages` only: offer the app list entries this machine does not have
   the dotfiles `app_lists/` plus each member context's `<context>_app_lists.yaml`
   asks once per package manager whether to go through them, then about each app: yes, not now, or ignore here
   an ignored app is never offered on this machine again, via `~/.dotfiles_ignored_apps`
   every question for every manager comes first, then everything chosen installs in one go
   runs the `scripts/install_*` for this machine's package managers, once to ask and once to install
   `installmissing` is the same offer with the ignored apps in it, and a yes takes the app out of the ignore file
   a choco app already installed by hand or by winget is listed, not offered: choco would install a second copy
   on windows, the duplicate check of step 7 then runs again, so a second copy an install made is offered for removal
   runs `src/app_removals.py --duplicates`
8. on windows only: bring autohotkey in line with the repo's v2 scripts
   runs `scripts/ensure_autohotkey_v2.ps1 -AutoFix -Full`
9. with `--packages` only: list every app the lists name that is still not installed, in the summary
   so a package an installer could not find is read at the end, not lost mid-run
   runs `src/app_lists.py --missing`

## examples

- pull and refresh everything:

`gitpullall`

- the same, with os package updates and an offer of the listed apps this machine lacks (`--packages`):

`myupdater`

- only pull every repo (`--pull-only`):

`pullrepos`

- gitpullall plus the app offer with this machine's ignored apps in it, un-ignoring each yes (`--install-missing`):

`installmissing`

- report what is behind, stale or undeployed, changing nothing (`--check`):

`gitpullall --check`

- run it without the shell commands:

`python3 $gitDir/dotfiles/src/refresh_machine.py --packages`
"""

UNPULLED = re.compile(r"^\[(WIP PROTECTED|FAILED|AUTH REQUIRED)\]")
# git_puller's per-repo tags, each followed by the repo's absolute path
PULL_TAG = re.compile(r"^\[(PULLED|NO CHANGES|UPDATED|WIP PROTECTED|FAILED|AUTH REQUIRED|DIRTY)\] (.*?)(?::| \(|$)")
FAST_FORWARD = re.compile(r"^Updating ([0-9a-f]+)\.\.([0-9a-f]+)")
FILES_CHANGED = re.compile(r"^\s*(\d+) files? changed")
DIRTY_COUNT = re.compile(r"\((\d+) uncommitted\)")


@dataclass
class Step:
    title: str
    argv: list
    needs: str = ""  # an executable that must be on PATH before the step can run
    pull: bool = False  # stream the output and count the repos git_puller could not pull
    action: object = None  # python-implemented step: action(out) -> exit code
    family: str = ""  # which report lines the closing page sums up for this step (refresh_report.py)


def resolve_git_dir(environ, script_path=__file__):
    """The repos directory: the shell's exported gitDir, else the one holding this checkout.

    Either way it must hold a dotfiles checkout, or the run stops: a guessed
    root once pointed the repo puller at a whole home directory. A copy of this
    script in a worktree outside gitDir therefore refuses instead of pulling
    from the wrong place.
    """
    candidate = environ.get("gitDir") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(script_path))))
    candidate = candidate.rstrip("/\\") or candidate
    if not os.path.exists(os.path.join(candidate, "dotfiles", ".git")):
        return None
    return candidate


def git_puller_binary(git_dir, system, machine):
    """The committed git_puller build for this OS and CPU."""
    base = os.path.join(git_dir, "dotfiles", "go_apps", "git_puller", "git_puller")
    arm = machine.lower() in ("arm64", "aarch64")
    if system == "Windows":
        return base + ".exe"
    if system == "Darwin":
        return base + ("_mac_arm" if arm else "_mac_x86")
    return base + ("_arm" if arm else "")


def repo_dirs(git_dir):
    """Every checkout directly under the repos directory, by name."""
    names = sorted(os.listdir(git_dir)) if os.path.isdir(git_dir) else []
    paths = ((name, os.path.join(git_dir, name)) for name in names)
    return [(name, path) for name, path in paths if os.path.exists(os.path.join(path, ".git"))]


def fetch_behind(entry):
    """Fetch one repo and report how far behind upstream it is. Never writes to the worktree."""
    name, path = entry
    fetched = subprocess.run(["git", "-C", path, "fetch", "--quiet"], capture_output=True, text=True)
    if fetched.returncode:
        return name, 0, "fetch failed (offline or no remote)"
    counted = subprocess.run(["git", "-C", path, "rev-list", "--count", "HEAD..@{u}"], capture_output=True, text=True)
    if counted.returncode:
        return name, 0, "no upstream branch"
    return name, int(counted.stdout.strip() or 0), ""


def fetch_check(git_dir, out, fetch=fetch_behind, workers=8):
    """The read-only twin of the pull: fetch every repo at once and report the ones behind."""
    repos = repo_dirs(git_dir)
    if not repos:
        out.write("   no repos found under " + git_dir + "\n")
        return 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(fetch, repos))
    behind = 0
    for name, count, problem in results:
        if problem:
            out.write("   " + name + ": " + problem + "\n")
            refresh_report.record("pull.problem", name, problem)
        elif count:
            behind += 1
            out.write("   " + name + ": " + str(count) + " commit(s) behind\n")
            refresh_report.record("pull.behind", name, refresh_report.plural(count, "commit") + " behind")
    out.write("   checked " + str(len(results)) + " repos: " + str(behind) + " behind\n")
    return 1 if behind else 0


def uv_python(dotfiles, script, *args):
    return ["uv", "run", "--project", dotfiles, "python", os.path.join(dotfiles, "src", script), *args]


def check_steps(git_dir, dotfiles, windows, powershell, packages, pull_only):
    """What each step would change, asked read-only. Every tool owns its own check."""
    steps = [
        Step(
            "checking every repo for upstream commits",
            [],
            action=functools.partial(fetch_check, git_dir),
            family="pull",
        ),
    ]
    if pull_only:
        return steps
    updater = os.path.join(dotfiles, "scripts", "my_updater.ps1" if windows else "my_updater.sh")
    if packages and windows:
        steps.append(Step("checking os packages", powershell + ["-File", updater, "--check"], family="package"))
    elif packages:
        steps.append(Step("checking os packages", ["bash", updater, "--check"], family="package"))
    steps += [
        Step(
            "checking for repos to clone", uv_python(dotfiles, "clone_repos.py", "--list"), needs="uv", family="clone"
        ),
        Step(
            "checking python environments",
            uv_python(dotfiles, "sync_python_envs.py", "--check"),
            needs="uv",
            family="env",
        ),
        Step(
            "checking deployed configs",
            uv_python(dotfiles, "deploy_configs.py", "status", "--problems"),
            needs="uv",
            family="deploy",
        ),
        Step(
            "checking for configs to prune",
            uv_python(dotfiles, "deploy_configs.py", "prune"),
            needs="uv",
            family="prune",
        ),
    ]
    if packages:
        steps.append(Step("checking for apps to remove", uv_python(dotfiles, "app_removals.py", "--list"), needs="uv"))
    ensure_ahk = os.path.join(dotfiles, "scripts", "ensure_autohotkey_v2.ps1")
    if windows and os.path.exists(ensure_ahk):
        steps.append(Step("checking autohotkey", powershell + ["-File", ensure_ahk, "-Check"]))
    return steps


def app_list_installers(dotfiles, system, which=shutil.which, offer_ignored=False):
    """
    The app-list installer(s) this machine's package managers call for, as
    (name, argv) pairs.

    ``offer_ignored`` is what `installmissing` adds: the apps this machine
    ignores are asked about too, and a yes takes the app out of the ignore
    file. The bash installers take it from the environment, the PowerShell
    ones as a switch.

    These are the same scripts bootstrap runs, not a second install path: the
    app_lists files are the one record of what a machine should have. Each one
    reports installed vs pending and asks about each pending app itself, so
    this does not reimplement the questions.

    Linux can legitimately answer to several - an apt box with flatpak - so this
    returns every manager present rather than the first.
    """
    scripts = os.path.join(dotfiles, "scripts")

    def script(name):
        return os.path.join(scripts, name)

    def bash(name):
        return (["env", "OFFER_IGNORED=1"] if offer_ignored else []) + ["bash", script(name)]

    if system == "Darwin":
        return [("mac apps", bash("install_mac_apps.sh"))]
    if system == "Windows":
        shell = which("pwsh") or which("powershell") or "powershell"
        prefix = [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
        switches = ["-OfferIgnored"] if offer_ignored else []
        return [
            ("choco apps", prefix + [script("install_windows_apps_with_chocolatey.ps1")] + switches),
            ("winget apps", prefix + [script("install_windows_apps_with_winget.ps1")] + switches),
        ]
    found = []
    if which("apt-get"):
        found.append(("apt apps", bash("install_linux_apps.sh")))
    if which("dnf"):
        found.append(("dnf apps", bash("install_linux_apps_dnf.sh")))
    if which("flatpak"):
        found.append(("flatpaks", bash("install_linux_apps_flatpak.sh")))
    return found


def app_plan_path():
    """The file the installers' ask phase writes and their install phase reads, one per run."""
    return os.path.join(tempfile.gettempdir(), f"refresh_machine_apps_{os.getpid()}.tsv")


def report_path(environ=None):
    """
    The report file this run's steps append to (refresh_report.py). The restart
    after a pull that moved dotfiles inherits the parent's, so the pull it
    already did is on the page; otherwise it is one new file per run.
    """
    environ = os.environ if environ is None else environ
    return environ.get(refresh_report.REPORT_ENV) or os.path.join(
        tempfile.gettempdir(), f"refresh_machine_report_{os.getpid()}.tsv"
    )


def pending_release(dotfiles, system, capture=subprocess.run):
    """
    The OS release a downloaded upgrade is waiting to install, or "". Asked of
    my_updater.sh, which owns what a pending download looks like (Fedora only
    for now). Any package transaction before its reboot can throw the
    download away, so while one waits the package steps below stand down.
    """
    if system != "Linux":
        return ""
    updater = os.path.join(dotfiles, "scripts", "my_updater.sh")
    try:
        done = capture(["bash", updater, "--pending-release"], capture_output=True, text=True)
    except OSError:
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def unless_release_pending(dotfiles, system, action, out, pending=pending_release):
    """Run a package step's action, or skip it while a downloaded release upgrade waits for its reboot."""
    target = pending(dotfiles, system)
    if target:
        out.write(f"   release {target} is downloaded and waiting for its reboot; no package changes until then\n")
        out.write("   run myupdater again after the reboot to be offered this\n")
        return 0
    return action(out)


def run_argv(argv, out):
    """A plain step as an action, so it can be wrapped."""
    return run_plain(argv)


def run_app_phase(argv, phase, plan, out, run=subprocess.run):
    """One installer in one phase (scripts/app_install_lib.sh describes APP_PHASE and APP_PLAN)."""
    return run(argv, env={**os.environ, "APP_PHASE": phase, "APP_PLAN": plan}).returncode


def app_install_steps(dotfiles, system, which=shutil.which, offer_ignored=False):
    """
    Every installer asks, then every installer installs: all the questions for
    every package manager come before the first install, so the person at the
    terminal answers once and can walk away while it all installs.
    """
    installers = app_list_installers(dotfiles, system, which, offer_ignored)
    plan = app_plan_path()

    def step(title, argv, phase):
        phase_action = functools.partial(run_app_phase, argv, phase, plan)
        return Step(title, argv, action=functools.partial(unless_release_pending, dotfiles, system, phase_action))

    asks = [step(f"choosing missing {name}", argv, "ask") for name, argv in installers]
    installs = [step(f"installing chosen {name}", argv, "install") for name, argv in installers]
    for install in installs:
        install.family = "install"
    return asks + installs


def build_steps(
    git_dir, system, machine, packages=False, pull_only=False, check=False, install_missing=False, which=shutil.which
):
    """The steps this run takes, in order."""
    dotfiles = os.path.join(git_dir, "dotfiles")
    windows = system == "Windows"
    powershell = [which("pwsh") or which("powershell") or "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass"]

    if check:
        return check_steps(git_dir, dotfiles, windows, powershell, packages, pull_only)

    puller = git_puller_binary(git_dir, system, machine)
    steps = [Step("pulling every repo", [puller, "-path", git_dir, "-r"], pull=True, family="pull")]
    if pull_only:
        return steps

    if packages and windows:
        updater = os.path.join(dotfiles, "scripts", "my_updater.ps1")
        steps.append(Step("updating os packages", powershell + ["-File", updater], family="package"))
    elif packages:
        updater = os.path.join(dotfiles, "scripts", "my_updater.sh")
        steps.append(Step("updating os packages", ["bash", updater], family="package"))
    steps += [
        Step("checking for repos to clone", uv_python(dotfiles, "clone_repos.py"), needs="uv", family="clone"),
        Step("syncing python environments", uv_python(dotfiles, "sync_python_envs.py"), needs="uv", family="env"),
        Step("deploying configs", uv_python(dotfiles, "deploy_configs.py"), needs="uv", family="deploy"),
        Step(
            "pruning removed configs",
            uv_python(dotfiles, "deploy_configs.py", "prune", "--apply"),
            needs="uv",
            family="prune",
        ),
    ]
    # packages only: these are package-manager operations and they prompt, so
    # they ride with myupdater rather than every gitpullall. Nothing installs
    # without a yes for that app at the terminal.
    if packages:
        removals = uv_python(dotfiles, "app_removals.py")
        remove_action = functools.partial(run_argv, removals)
        steps.append(
            Step(
                "checking for apps to remove",
                removals,
                needs="uv",
                action=functools.partial(unless_release_pending, dotfiles, system, remove_action),
                family="remove",
            )
        )
        steps += app_install_steps(dotfiles, system, which)
    # installmissing: the same offer without the package upgrades or removals,
    # with this machine's ignored apps asked about too.
    elif install_missing:
        steps += app_install_steps(dotfiles, system, which, offer_ignored=True)
    if packages and windows:
        # Again, after the installs: a copy one of them just put beside an
        # existing install is offered for removal on this run, not the next.
        twice = uv_python(dotfiles, "app_removals.py", "--duplicates")
        steps.append(Step("checking for apps installed twice", twice, needs="uv", family="remove"))
    ensure_ahk = os.path.join(dotfiles, "scripts", "ensure_autohotkey_v2.ps1")
    if windows and os.path.exists(ensure_ahk):
        steps.append(Step("checking autohotkey", powershell + ["-File", ensure_ahk, "-AutoFix", "-Full"]))
    return steps


def make_executable(path):
    """A checkout on a filesystem that dropped the exec bit still runs git_puller."""
    if os.name != "nt" and os.path.isfile(path) and not os.access(path, os.X_OK):
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def remove_if_exists(path):
    if os.path.exists(path):
        os.remove(path)


def run_plain(argv):
    """A step with the real terminal: its prompts and colours reach the person running it."""
    return subprocess.run(argv).returncode


def dotfiles_head(dotfiles, capture=subprocess.run):
    """The dotfiles commit checked out, or None when git cannot say."""
    try:
        done = capture(["git", "-C", dotfiles, "rev-parse", "HEAD"], capture_output=True, text=True)
    except OSError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def restart_argv(argv, script_path=__file__):
    """
    This run again from the file on disk, without the pull it already did.
    The process running now holds the code from before the pull, so every fix
    to this file would otherwise only reach the run after the one that pulled it.
    The pull's result reaches the restart through the report file it inherits.
    """
    return [sys.executable, os.path.abspath(script_path), *argv, "--after-pull"]


def commits_between(path, old, new, capture=subprocess.run):
    """How many commits a fast-forward covered, or 0 when git cannot say."""
    try:
        done = capture(["git", "-C", path, "rev-list", "--count", f"{old}..{new}"], capture_output=True, text=True)
    except OSError:
        return 0
    return int(done.stdout.strip() or 0) if done.returncode == 0 else 0


class PullLog:
    """
    What git_puller said about each repo, read from its stream as it passes
    through to the terminal, and recorded for the closing page once the pull
    is over. A repo is named by its directory; the paths git_puller prints are
    absolute.
    """

    def __init__(self, commits=commits_between):
        self.repos = {}  # path -> {"status": tag, "old": sha, "new": sha, "files": n, "detail": text}
        self.current = None  # the [UPDATED] block whose git output is streaming now
        self.commits = commits

    def feed(self, line):
        text = line.rstrip("\r\n")
        tag = PULL_TAG.match(text)
        if tag:
            status, path = tag.group(1), tag.group(2).strip()
            repo = self.repos.setdefault(path, {})
            # the lines after [UPDATED], [WIP PROTECTED] and [FAILED] belong to that repo
            self.current = repo if status in ("UPDATED", "WIP PROTECTED", "FAILED") else None
            if status == "UPDATED":
                return
            if status == "DIRTY":
                found = DIRTY_COUNT.search(text)
                repo["dirty"] = found.group(1) if found else "some"
                return
            repo["status"] = status
            if status in ("FAILED", "AUTH REQUIRED", "WIP PROTECTED"):
                repo["detail"] = text.partition(path)[2].strip(" :()").replace("Skipping", "").strip()
            return
        if self.current is None:
            return
        if text.startswith("["):
            self.current = None
            return
        moved = FAST_FORWARD.match(text)
        if moved:
            self.current["old"], self.current["new"] = moved.group(1), moved.group(2)
        changed = FILES_CHANGED.match(text)
        if changed:
            self.current["files"] = int(changed.group(1))
        if text.startswith("\t") and "detail" in self.current:
            # git's own prose is above in the log; the page wants the file names
            note = text.strip()
            if note and not note.startswith(("error:", "Please", "Aborting", "hint:")):
                self.current["detail"] = (self.current["detail"] + " " + note).strip()

    def record(self, record=None):
        record = refresh_report.record if record is None else record
        for path in sorted(self.repos):
            repo = self.repos[path]
            name = os.path.basename(path.rstrip("/\\")) or path
            status = repo.get("status")
            if "dirty" in repo:
                record("pull.dirty", name, f"{repo['dirty']} uncommitted")
            if status == "PULLED":
                parts = []
                if "old" in repo:
                    commits = self.commits(path, repo["old"], repo["new"])
                    parts.append(f"{repo['old'][:7]}{refresh_report.ARROW}{repo['new'][:7]}")
                    if commits:
                        parts.append(refresh_report.plural(commits, "commit"))
                if "files" in repo:
                    parts.append(refresh_report.plural(repo["files"], "file"))
                record("pull.pulled", name, "  ".join(parts))
            elif status == "NO CHANGES":
                record("pull.current", name, "")
            elif status == "WIP PROTECTED":
                record("pull.wip", name, repo.get("detail", ""))
            elif status == "AUTH REQUIRED":
                record("pull.auth", name, "")
            elif status == "FAILED":
                record("pull.failed", name, repo.get("detail", ""))


def run_pull(argv, out, log=None):
    """Stream git_puller's output as it arrives and count the repos it could not pull."""
    unpulled = 0
    log = PullLog() if log is None else log
    with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace") as proc:
        for line in proc.stdout:
            out.write(line)
            out.flush()
            log.feed(line)
            if UNPULLED.match(line):
                unpulled += 1
    log.record()
    return proc.returncode, unpulled


def bootstrap_argv(dotfiles, need):
    """The repo's own installer asked for one tool, so a tool has one install path and not two."""
    return ["bash", os.path.join(dotfiles, "scripts", "bootstrap.sh"), "--only", need, "--yes"]


def ask_yes_no(question):
    """True only for an explicit yes. EOF or a bare Enter means no."""
    try:
        return input(question).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def offer_dependency(need, dotfiles, out, color, run=run_plain, which=shutil.which, ask=None):
    """
    Offer to install a missing tool and report whether it is now on PATH.

    Only the person at a terminal is asked. A cron or ssh run reports and fails
    exactly as it did before this existed, so nothing ever installs itself
    unattended - the elitedesk crontab must keep behaving the same.

    The install is bootstrap's, never a copy of it: the reason a Pi could not
    deploy was that it had no uv and nothing offered to fetch it, not that the
    command was hard to write.
    """
    paint = terminal_style.paint
    # resolved here rather than as a default argument, so the prompt stays
    # substitutable from a test without the real input() ever being bound
    ask = ask or ask_yes_no
    if dotfiles is None or not sys.stdin.isatty():
        return False
    out.write(paint(f"   {need} is missing; scripts/bootstrap.sh can install it", "amber", color) + "\n")
    out.flush()
    if not ask(f"   install {need} now? [y/N] "):
        return False
    if run(bootstrap_argv(dotfiles, need)):
        out.write(paint(f"   bootstrap could not install {need}", "red", color) + "\n")
        return False
    return bool(which(need))


def execute(steps, out, color, run=run_plain, pull=run_pull, which=shutil.which, dotfiles=None, record=None):
    """
    Run every step, even after a failure. Returns the titles of the steps that
    failed, and records each step's outcome and time for the closing page.
    """
    paint = terminal_style.paint
    record = refresh_report.record if record is None else record
    failed = []
    for index, step in enumerate(steps):
        out.write(("\n" if index else "") + terminal_style.section(step.title, color) + "\n")
        out.flush()
        started = time.monotonic()
        if step.needs and not which(step.needs):
            if not offer_dependency(step.needs, dotfiles, out, color, run=run, which=which):
                out.write(paint(f"   {step.needs} is not installed, so this step cannot run", "red", color) + "\n")
                failed.append(step.title)
                record("step", step.title, refresh_report.step_detail("failed", 0, step.family))
                continue
        try:
            if step.action is not None:
                code = step.action(out)
            elif step.pull:
                make_executable(step.argv[0])
                code, unpulled = pull(step.argv, out)
                if unpulled:
                    warning = (
                        f"   {unpulled} repo(s) could not be pulled (tagged above); "
                        "later steps run from their current, possibly stale, checkouts"
                    )
                    out.write(paint(warning, "amber", color, bold=True) + "\n")
            else:
                code = run(step.argv)
        except OSError as error:
            out.write(paint(f"   could not run {step.argv[0]}: {error.strerror}", "red", color) + "\n")
            code = 1
        if code:
            out.write(paint(f"   failed with exit code {code}", "red", color) + "\n")
            failed.append(step.title)
        status = "failed" if code else "ok"
        record("step", step.title, refresh_report.step_detail(status, time.monotonic() - started, step.family))
        out.flush()
    return failed


def missing_apps(dotfiles, capture=subprocess.run, which=shutil.which):
    """
    ``{"missing": [...], "elsewhere": [...], "ignored": [...], "ignore-file":
    [path]}`` of ``manager:package`` for the apps this machine's lists name
    that their manager has not installed, or None when that could not be
    worked out. Asked once, after every step, so
    an app an installer could not find is said where it is read - in the
    summary - and not somewhere in the middle of a long run.
    """
    if not which("uv"):
        return None
    try:
        done = capture(
            uv_python(dotfiles, "app_lists.py", "--missing"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return None
    if done.returncode:
        return None
    found: dict = {"missing": [], "elsewhere": [], "ignored": [], "ignore-file": []}
    for line in done.stdout.splitlines():
        kind, _, name = line.strip().partition(" ")
        if kind in found and name:
            found[kind].append(name)
    return found


def page(report, command, host, started, seconds, color, check=False, missing=None, asked_missing=False, size=None):
    """The closing status page: every step's outcome, then what was pulled, upgraded, deployed and installed."""
    lines = refresh_report.read(report)
    return refresh_report.render(lines, command, host, started, seconds, color, check, missing, asked_missing, size)


def command_name(args):
    """The shell command this run answers to, for the page title."""
    if args.pull_only:
        name = "pullrepos"
    elif args.packages:
        name = "myupdater"
    elif args.install_missing:
        name = "installmissing"
    else:
        name = "gitpullall"
    return name + (" --check" if args.check else "")


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="refresh_machine.py", add_help=False)
    terminal_style.add_help_page(parser, HELP_PAGE)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--packages", action="store_true", help="upgrade os packages between the pull and the deploy")
    mode.add_argument("--pull-only", action="store_true", help="pull every repo and stop")
    mode.add_argument(
        "--install-missing",
        action="store_true",
        help="what `installmissing` runs: offer the app list entries this machine lacks, ignored ones included",
    )
    parser.add_argument("--check", action="store_true", help="report what would change, write nothing")
    # internal: the restart after a pull that moved dotfiles (restart_argv)
    parser.add_argument("--after-pull", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv=None, environ=None, run=subprocess.run, head=dotfiles_head, clock=time.time):
    argv = sys.argv[1:] if argv is None else argv
    args = parse_args(argv)
    environ = os.environ if environ is None else environ
    git_dir = resolve_git_dir(environ)
    if git_dir is None:
        print(
            "refresh_machine: no dotfiles checkout under $gitDir or next to this script. "
            "Open a shell that sources the shared aliases so gitDir is exported.",
            file=sys.stderr,
        )
        return 1
    out = sys.stdout
    if hasattr(out, "reconfigure"):
        # A legacy Windows console has no glyph for the page's dots and arrows; never crash on it.
        out.reconfigure(errors="replace")
    color = terminal_style.use_color(out, environ)
    dotfiles = os.path.join(git_dir, "dotfiles")
    steps = build_steps(
        git_dir,
        platform.system(),
        platform.machine(),
        args.packages,
        args.pull_only,
        args.check,
        args.install_missing,
    )
    # Every step appends what it did here (refresh_report.py); the page at the
    # end is drawn from it. The restart after a pull inherits the parent's file.
    inherited = refresh_report.REPORT_ENV in os.environ
    report = report_path()
    os.environ[refresh_report.REPORT_ENV] = report
    started = clock()
    if args.after_pull:
        steps = steps[1:]
        started -= sum(seconds for _, _, seconds, _ in refresh_report.steps_of(refresh_report.read(report)))
    try:
        if not (args.after_pull or args.check or args.pull_only):
            before = head(dotfiles)
            execute(steps[:1], out, color, dotfiles=dotfiles)
            if head(dotfiles) != before:
                out.write(
                    terminal_style.paint("   dotfiles moved; continuing with the code just pulled", "muted", color)
                )
                out.write("\n\n")
                out.flush()
                # the restart draws the page and removes the report it inherited
                return run(restart_argv(argv)).returncode
            steps = steps[1:]
            out.write("\n")
        execute(steps, out, color, dotfiles=dotfiles)
    except KeyboardInterrupt:
        out.write("\n" + terminal_style.paint("interrupted: the remaining steps did not run", "red", color) + "\n")
        remove_if_exists(report)
        return 130
    finally:
        remove_if_exists(app_plan_path())
    # Package runs only: listing what is installed costs a winget list, which
    # a plain pull should not pay for.
    asked_missing = (args.packages or args.install_missing) and not args.pull_only
    missing = missing_apps(dotfiles) if asked_missing else None
    recorded = refresh_report.steps_of(refresh_report.read(report))
    failed = [title for title, status, _, _ in recorded if status != "ok"]
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(started))
    host = platform.node().split(".")[0].lower()
    text = page(report, command_name(args), host, when, clock() - started, color, args.check, missing, asked_missing)
    out.write("\n" + text)
    remove_if_exists(report)
    if not inherited:
        del os.environ[refresh_report.REPORT_ENV]
    return 1 if failed or (asked_missing and missing is None) else 0


if __name__ == "__main__":
    sys.exit(main())
