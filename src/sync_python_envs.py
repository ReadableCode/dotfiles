# %%
# Imports #

"""Sync the environment of every uv project under gitDir.

Each repo's own pinned tools (formatters, linters, type checkers) then exist on
this machine, so the editor and the push checks run those versions rather than
a bundled copy. Run by gitpullall and myupdater right after the clone step (a
fresh clone is synced too) and by bootstrap.

A uv project is a directory holding a uv.lock: each repo root, plus its
immediate subdirectories for repos whose Python project lives in one (a
monorepo's backend/). A repo without a uv.lock (Pipenv, requirements files, no
Python at all) is skipped, never given a lock it does not have.

`uv sync --frozen` installs exactly what the lock pins and never rewrites
uv.lock, which is tracked in the repo. A project that fails to sync is reported
and counted but never stops the rest; the exit code is 1 when any failed.

`--check` is the read-only twin behind `cmdr pull --check`: `uv sync --frozen
--check` changes nothing and exits nonzero when the environment differs from
the lock, so a stale project is reported the same way a failed one is. A uv
too old for the flag rejects it and the project is reported as failed, never
skipped.
"""

import argparse
import os
import subprocess
import sys

from config import grandparent_dir

# %%
# Variables #

# Where the repos live: the directory holding dotfiles and its siblings (gitDir).
GIT_DIR = grandparent_dir

SYNC_COMMAND = ["uv", "sync", "--frozen"]
CHECK_COMMAND = SYNC_COMMAND + ["--check"]

# Never searched for a nested project: dependency and cache trees can carry a
# uv.lock that is not a project of ours. Hidden directories (.venv, .git) are
# skipped by name.
SKIP_DIRS = {"node_modules", "__pycache__", "site-packages"}

# The shell step runs this through `uv run --project dotfiles`, which exports
# dotfiles' environment; left in place, uv would warn in every other project
# that the active environment does not match it.
INHERITED_ENV_VARS = ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT")


# %%
# Functions #


def _is_candidate_dir(path, name):
    return os.path.isdir(path) and not name.startswith(".") and name not in SKIP_DIRS


def find_uv_projects(git_dir):
    """Every repo root under git_dir, or immediate subdirectory of one, that holds a uv.lock."""
    projects = []
    for repo in sorted(os.listdir(git_dir)):
        repo_path = os.path.join(git_dir, repo)
        if not _is_candidate_dir(repo_path, repo):
            continue
        if os.path.isfile(os.path.join(repo_path, "uv.lock")):
            projects.append(repo_path)
        for sub in sorted(os.listdir(repo_path)):
            sub_path = os.path.join(repo_path, sub)
            if _is_candidate_dir(sub_path, sub) and os.path.isfile(os.path.join(sub_path, "uv.lock")):
                projects.append(sub_path)
    return projects


def sync_env():
    """This process's environment without the variables that point uv at dotfiles' venv."""
    return {key: value for key, value in os.environ.items() if key not in INHERITED_ENV_VARS}


def sync_project(project, check=False):
    """Run `uv sync --frozen` (or its `--check`) in project and return its exit code."""
    command = CHECK_COMMAND if check else SYNC_COMMAND
    return subprocess.run(command, cwd=project, env=sync_env(), check=False).returncode


def run(git_dir, list_only=False, check=False):
    projects = find_uv_projects(git_dir)
    if not projects:
        print(f"No uv projects under {git_dir}.")
        return 0
    if list_only:
        print(f"uv projects under {git_dir} ({len(projects)}):")
        for project in projects:
            print(f"  {os.path.relpath(project, git_dir)}")
        return 0
    failed = []
    for project in projects:
        name = os.path.relpath(project, git_dir)
        print(f"-- {name}")
        if sync_project(project, check=check) != 0:
            failed.append(name)
    verb = "in sync" if check else "synced"
    if failed:
        what = "out of sync or failed" if check else "failed"
        print(f"{verb}: {len(projects) - len(failed)} of {len(projects)} uv projects; {what}: {', '.join(failed)}")
        return 1
    print(f"{verb}: all {len(projects)} uv projects")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="uv sync --frozen in every uv project under gitDir.")
    parser.add_argument("--list", action="store_true", help="only list the uv projects that would be synced")
    parser.add_argument(
        "--check", action="store_true", help="change nothing; exit 1 if any project's environment differs from its lock"
    )
    args = parser.parse_args(argv)
    return run(GIT_DIR, list_only=args.list, check=args.check)


# %%
# Main #

if __name__ == "__main__":
    sys.exit(main())
