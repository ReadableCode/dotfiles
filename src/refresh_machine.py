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
3. offer to clone repos this machine should have but is missing, asking [y/N/q] first
   the lists are each context's `<context>_repos.yaml`, which the pull just refreshed
   runs `src/clone_repos.py`
4. sync every uv project's environment to its lock, so each repo's own linters and formatters are installed
   runs `src/sync_python_envs.py`
5. deploy configs from the manifests, for this host and platform
   runs `src/deploy_configs.py`
6. prune config paths a removals file names and no manifest entry still wants
   runs `src/deploy_configs.py prune --apply`
7. on windows only: bring autohotkey in line with the repo's v2 scripts
   runs `scripts/ensure_autohotkey_v2.ps1 -AutoFix -Full`

## examples

- pull and refresh everything:

`gitpullall`

- the same, with os package updates (`--packages`):

`myupdater`

- only pull every repo (`--pull-only`):

`pullrepos`

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
    counted = subprocess.run(
        ["git", "-C", path, "rev-list", "--count", "HEAD..@{u}"], capture_output=True, text=True
    )
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
    ensure_ahk = os.path.join(dotfiles, "scripts", "ensure_autohotkey_v2.ps1")
    if windows and os.path.exists(ensure_ahk):
        steps.append(Step("checking autohotkey", powershell + ["-File", ensure_ahk, "-Check"]))
    return steps


def build_steps(git_dir, system, machine, packages=False, pull_only=False, check=False, which=shutil.which):
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


def execute(steps, out, color, run=run_plain, pull=run_pull, which=shutil.which):
    """Run every step, even after a failure. Returns the titles of the steps that failed."""
    paint = terminal_style.paint
    failed = []
    for index, step in enumerate(steps):
        out.write(("\n" if index else "") + terminal_style.section(step.title, color) + "\n")
        out.flush()
        if step.needs and not which(step.needs):
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


def summary(failed, total, color, check=False):
    paint = terminal_style.paint
    word = "reported drift" if check else "failed"
    lines = [terminal_style.section("done", color)]
    if failed:
        text = f"   {len(failed)} of {total} steps {word}: " + ", ".join(failed)
        lines.append(paint(text, "amber" if check else "red", color, bold=True))
    else:
        lines.append(paint(f"   all {total} steps ok", "green", color, bold=True))
    return "\n".join(lines) + "\n"


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="refresh_machine.py", add_help=False)
    terminal_style.add_help_page(parser, HELP_PAGE)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--packages", action="store_true", help="upgrade os packages between the pull and the deploy")
    mode.add_argument("--pull-only", action="store_true", help="pull every repo and stop")
    parser.add_argument("--check", action="store_true", help="report what would change, write nothing")
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
        git_dir, platform.system(), platform.machine(), args.packages, args.pull_only, args.check
    )
    try:
        failed = execute(steps, out, color)
    except KeyboardInterrupt:
        out.write("\n" + terminal_style.paint("interrupted: the remaining steps did not run", "red", color) + "\n")
        return 130
    out.write("\n" + summary(failed, len(steps), color, args.check))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
