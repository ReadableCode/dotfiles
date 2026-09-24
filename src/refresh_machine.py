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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import terminal_style

HELP_PAGE = """# refresh_machine

> pull every repo, then bring this machine's configs up to date.
> gitpullall, myupdater and pullrepos all run this, from any directory, against `$gitDir`.
> every step runs even when an earlier one fails, and the exit code is 1 when any did. ctrl+c stops the run.
> `--check` is the read-only twin: it reports what the steps below would change and writes nothing.

## what happens

1. pull every repo under `$gitDir` at the same time
   a repo it cannot pull is tagged `WIP PROTECTED`, `FAILED` or `AUTH REQUIRED`, left as it is, and counted in a warning
   runs `go_apps/git_puller -path $gitDir -r`
2. with `--packages` only: upgrade os packages, before the deploy so a config an upgrade clobbers is linked again
   runs `scripts/my_updater.sh` on macos and linux, `scripts/my_updater.ps1` on windows
   a step whose tool is missing offers to install it with `scripts/bootstrap.sh --only <tool>` first
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
7b. `installmissing` only: offer to install app list entries this machine does not have
   the dotfiles `app_lists/` plus each member context's `<context>_app_lists.yaml`
   answer with numbers (or `i`) to ignore apps on this machine for good, in `~/.dotfiles_ignored_apps`
   deliberately NOT part of a plain pull or update - installing apps is a thing you ask for
   runs the `scripts/install_*` for this machine's package managers
8. on windows only: bring autohotkey in line with the repo's v2 scripts
   runs `scripts/ensure_autohotkey_v2.ps1 -AutoFix -Full`
9. with `--packages` or `installmissing`: list every app the lists name that is still not installed, in the summary
   so a package an installer could not find is read at the end, not lost mid-run
   runs `src/app_lists.py --missing`

## examples

- pull and refresh everything:

`gitpullall`

- the same, with os package updates (`--packages`):

`myupdater`

- only pull every repo (`--pull-only`):

`pullrepos`

- gitpullall plus an offer of every app_lists entry this machine is missing:

`installmissing`

- report what is behind, stale or undeployed, changing nothing (`--check`):

`gitpullall --check`

- run it without the shell commands:

`python3 $gitDir/dotfiles/src/refresh_machine.py --packages`
"""

UNPULLED = re.compile(r"^\[(WIP PROTECTED|FAILED|AUTH REQUIRED)\]")


@dataclass
class Step:
    title: str
    argv: list
    needs: str = ""  # an executable that must be on PATH before the step can run
    pull: bool = False  # stream the output and count the repos git_puller could not pull
    action: object = None  # python-implemented step: action(out) -> exit code


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
        elif count:
            behind += 1
            out.write("   " + name + ": " + str(count) + " commit(s) behind\n")
    out.write("   checked " + str(len(results)) + " repos: " + str(behind) + " behind\n")
    return 1 if behind else 0


def uv_python(dotfiles, script, *args):
    return ["uv", "run", "--project", dotfiles, "python", os.path.join(dotfiles, "src", script), *args]


def check_steps(git_dir, dotfiles, windows, powershell, packages, pull_only):
    """What each step would change, asked read-only. Every tool owns its own check."""
    steps = [
        Step("checking every repo for upstream commits", [], action=functools.partial(fetch_check, git_dir)),
    ]
    if pull_only:
        return steps
    updater = os.path.join(dotfiles, "scripts", "my_updater.ps1" if windows else "my_updater.sh")
    if packages and windows:
        steps.append(Step("checking os packages", powershell + ["-File", updater, "--check"]))
    elif packages:
        steps.append(Step("checking os packages", ["bash", updater, "--check"]))
    steps += [
        Step("checking for repos to clone", uv_python(dotfiles, "clone_repos.py", "--list"), needs="uv"),
        Step("checking python environments", uv_python(dotfiles, "sync_python_envs.py", "--check"), needs="uv"),
        Step("checking deployed configs", uv_python(dotfiles, "deploy_configs.py", "status", "--problems"), needs="uv"),
        Step("checking for configs to prune", uv_python(dotfiles, "deploy_configs.py", "prune"), needs="uv"),
    ]
    if packages:
        steps.append(Step("checking for apps to remove", uv_python(dotfiles, "app_removals.py", "--list"), needs="uv"))
    ensure_ahk = os.path.join(dotfiles, "scripts", "ensure_autohotkey_v2.ps1")
    if windows and os.path.exists(ensure_ahk):
        steps.append(Step("checking autohotkey", powershell + ["-File", ensure_ahk, "-Check"]))
    return steps


def app_list_installers(dotfiles, system, which=shutil.which):
    """
    The app-list installer(s) this machine's package managers call for, as
    (title, argv) pairs.

    These are the same scripts bootstrap runs, not a second install path: the
    app_lists files are the one record of what a machine should have. Each one
    reports installed vs pending and prompts once, with numbers to skip, so the
    choice stays per package without this having to reimplement it.

    Linux can legitimately answer to several - an apt box with flatpak - so this
    returns every manager present rather than the first.
    """
    scripts = os.path.join(dotfiles, "scripts")

    def script(name):
        return os.path.join(scripts, name)

    if system == "Darwin":
        return [("installing missing mac apps", ["bash", script("install_mac_apps.sh")])]
    if system == "Windows":
        shell = which("pwsh") or which("powershell") or "powershell"
        prefix = [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
        return [
            ("installing missing choco apps", prefix + [script("install_windows_apps_with_chocolatey.ps1")]),
            ("installing missing winget apps", prefix + [script("install_windows_apps_with_winget.ps1")]),
        ]
    found = []
    if which("apt-get"):
        found.append(("installing missing apt apps", ["bash", script("install_linux_apps.sh")]))
    if which("dnf"):
        found.append(("installing missing dnf apps", ["bash", script("install_linux_apps_dnf.sh")]))
    if which("flatpak"):
        found.append(("installing missing flatpaks", ["bash", script("install_linux_apps_flatpak.sh")]))
    return found


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
    steps = [Step("pulling every repo", [puller, "-path", git_dir, "-r"], pull=True)]
    if pull_only:
        return steps

    if packages and windows:
        updater = os.path.join(dotfiles, "scripts", "my_updater.ps1")
        steps.append(Step("updating os packages", powershell + ["-File", updater]))
    elif packages:
        steps.append(Step("updating os packages", ["bash", os.path.join(dotfiles, "scripts", "my_updater.sh")]))
    steps += [
        Step("checking for repos to clone", uv_python(dotfiles, "clone_repos.py"), needs="uv"),
        Step("syncing python environments", uv_python(dotfiles, "sync_python_envs.py"), needs="uv"),
        Step("deploying configs", uv_python(dotfiles, "deploy_configs.py"), needs="uv"),
        Step("pruning removed configs", uv_python(dotfiles, "deploy_configs.py", "prune", "--apply"), needs="uv"),
    ]
    # packages only: this is a package-manager operation and it prompts, so it
    # rides with myupdater rather than every gitpullall.
    if packages:
        steps.append(Step("checking for apps to remove", uv_python(dotfiles, "app_removals.py"), needs="uv"))
    # Opt-in only. A pull or an update must never start installing software on
    # its own; adding an entry to an app list is not the same as asking for it
    # on this machine.
    if install_missing:
        steps += [Step(title, argv) for title, argv in app_list_installers(dotfiles, system, which)]
    ensure_ahk = os.path.join(dotfiles, "scripts", "ensure_autohotkey_v2.ps1")
    if windows and os.path.exists(ensure_ahk):
        steps.append(Step("checking autohotkey", powershell + ["-File", ensure_ahk, "-AutoFix", "-Full"]))
    return steps


def make_executable(path):
    """A checkout on a filesystem that dropped the exec bit still runs git_puller."""
    if os.name != "nt" and os.path.isfile(path) and not os.access(path, os.X_OK):
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run_plain(argv):
    """A step with the real terminal: its prompts and colours reach the person running it."""
    return subprocess.run(argv).returncode


def run_pull(argv, out):
    """Stream git_puller's output as it arrives and count the repos it could not pull."""
    unpulled = 0
    with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace") as proc:
        for line in proc.stdout:
            out.write(line)
            out.flush()
            if UNPULLED.match(line):
                unpulled += 1
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


def execute(steps, out, color, run=run_plain, pull=run_pull, which=shutil.which, dotfiles=None):
    """Run every step, even after a failure. Returns the titles of the steps that failed."""
    paint = terminal_style.paint
    failed = []
    for index, step in enumerate(steps):
        out.write(("\n" if index else "") + terminal_style.section(step.title, color) + "\n")
        out.flush()
        if step.needs and not which(step.needs):
            if not offer_dependency(step.needs, dotfiles, out, color, run=run, which=which):
                out.write(paint(f"   {step.needs} is not installed, so this step cannot run", "red", color) + "\n")
                failed.append(step.title)
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


def summary(failed, total, color, check=False, missing=None, asked_missing=False):
    paint = terminal_style.paint
    word = "reported drift" if check else "failed"
    lines = [terminal_style.section("done", color)]
    if failed:
        text = f"   {len(failed)} of {total} steps {word}: " + ", ".join(failed)
        lines.append(paint(text, "amber" if check else "red", color, bold=True))
    else:
        lines.append(paint(f"   all {total} steps ok", "green", color, bold=True))
    if asked_missing and missing is None:
        lines.append(
            paint("   could not work out which listed apps are installed (app_lists.py --missing)", "red", color)
        )
    elif missing:
        if missing["missing"]:
            count = len(missing["missing"])
            text = f"   {count} listed app(s) not installed on this machine; `installmissing` offers them:"
            lines.append(paint(text, "amber", color, bold=True))
            lines += [paint(f"     {name}", "amber", color) for name in missing["missing"]]
        if missing["elsewhere"]:
            text = f"   {len(missing['elsewhere'])} listed app(s) installed, but not by the manager their list names:"
            lines.append(paint(text, "amber", color))
            lines += [paint(f"     {name}", "dim", color) for name in missing["elsewhere"]]
        if missing.get("ignored"):
            where = (missing.get("ignore-file") or ["the ignore file"])[0]
            text = f"   {len(missing['ignored'])} listed app(s) not offered, ignored on this machine by {where}"
            lines.append(paint(text + " (delete a line there to be offered it again):", "dim", color))
            lines += [paint(f"     {name}", "dim", color) for name in missing["ignored"]]
    return "\n".join(lines) + "\n"


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="refresh_machine.py", add_help=False)
    terminal_style.add_help_page(parser, HELP_PAGE)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--packages", action="store_true", help="upgrade os packages between the pull and the deploy")
    mode.add_argument("--pull-only", action="store_true", help="pull every repo and stop")
    parser.add_argument("--check", action="store_true", help="report what would change, write nothing")
    parser.add_argument(
        "--install-missing",
        action="store_true",
        help="what `installmissing` runs: also offer the app_lists entries this machine lacks",
    )
    return parser.parse_args(argv)


def main(argv=None, environ=None):
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
    color = terminal_style.use_color(out, environ)
    steps = build_steps(
        git_dir,
        platform.system(),
        platform.machine(),
        args.packages,
        args.pull_only,
        args.check,
        args.install_missing,
    )
    try:
        failed = execute(steps, out, color, dotfiles=os.path.join(git_dir, "dotfiles"))
    except KeyboardInterrupt:
        out.write("\n" + terminal_style.paint("interrupted: the remaining steps did not run", "red", color) + "\n")
        return 130
    # Package runs only: listing what is installed costs a winget list, which
    # a plain pull should not pay for.
    asked_missing = (args.packages or args.install_missing) and not args.pull_only
    missing = missing_apps(os.path.join(git_dir, "dotfiles")) if asked_missing else None
    out.write("\n" + summary(failed, len(steps), color, args.check, missing, asked_missing))
    return 1 if failed or (asked_missing and missing is None) else 0


if __name__ == "__main__":
    sys.exit(main())
