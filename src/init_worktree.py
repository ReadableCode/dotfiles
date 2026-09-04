#!/usr/bin/env python3
"""Bring a fresh git worktree up to parity with its main checkout.

T3 Code (and ``git worktree add`` by hand) gives every thread its own checkout
under ``~/.t3/worktrees/<repo>/<id>``. A worktree shares the repo's git dir -
hooks, ``.git/info/exclude``, stashes - but NOT the gitignored files that make a
checkout usable, and those are exactly the ones ``deploy_configs.py`` links into
the main checkout only (``.env``, ``.mcp.json``, ``.claude/settings.local.json``,
``configuration.json``, ...). This script closes that gap for one worktree:

    python3 ~/GitHub/dotfiles/src/init_worktree.py                 # from inside the worktree
    python3 ~/GitHub/dotfiles/src/init_worktree.py --label ACME-1234
    python3 ~/GitHub/dotfiles/src/init_worktree.py --remove        # leaving: drop the workspace entry

1. **Local-only links.** Every symlink at the top level and under ``.claude/`` of
   the MAIN checkout that git ignores is re-created in the worktree, pointing
   at the same ABSOLUTE target (the main checkout's ``.env`` is a relative link
   into the sibling credentials repo, which would dangle from a worktree two
   directories away). A plain-file ``.env`` is copied instead. Nothing in the
   worktree is ever overwritten: a path that already exists with different
   content or a different target is reported as a conflict and left alone.
   Other gitignored files in the main checkout (tokens, keys, reports) are
   listed so you know they were NOT carried over - they are deliberately not
   copied around by a script.
2. **VS Code workspace.** The host's ``<repo_parent>/<host>.code-workspace``
   (the manifest-deployed link next to the checkouts, see docs/setup_vscode.md)
   gets a folder entry for the worktree right after the main checkout's own
   entry, named ``│ <repo> · <label>`` to match the hand-kept layout. VS Code
   watches the workspace file, so the folder appears in the open window with
   no reload. The file is JSONC with trailing commas, so this is a text
   insertion, not a JSON round-trip. Idempotent by path; a re-run with a new
   label renames the entry in place - T3 Code cuts worktrees from master on a
   placeholder branch and the ticket is created later from inside, so the
   usual sequence is init now, re-run once the ticket exists.
3. **``uv sync``** when the worktree has a ``uv.lock`` and ``uv`` is on PATH -
   a worktree gets its own ``.venv`` (``--no-sync`` to skip).

Stdlib-only on purpose (like ``ticket_pr.py``): it runs with a bare
``python3`` from any repo in any context before that repo's venv exists.
Wrapped by the ``/init_worktree`` Claude command
(``application_configs/claude/commands/init_worktree.md``).
"""

import argparse
import os
import re
import shutil
import socket
import subprocess
import sys

TICKET_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
# Where deploy-managed links live in a checkout: the root, and .claude/ for settings.local.json.
LINK_SCAN_DIRS = ("", ".claude")
# Ignored files that are noise, not config: never worth a "not mirrored" line.
REPORT_SKIP = {".DS_Store", "desktop.ini"}
WORKSPACE_LABEL = "│ {repo} · {label}"
WORKSPACE_ENTRY = '{indent}{{\n{indent}  "name": "{name}",\n{indent}  "path": "{path}",\n{indent}}},\n'


# ---------------------------------------------------------------- git


def git(args, cwd):
    """Run a git command in cwd and return stripped stdout; raises on failure."""
    return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()


def worktree_root(path):
    """Top level of the checkout containing path."""
    return os.path.realpath(git(["rev-parse", "--show-toplevel"], path))


def main_checkout(path):
    """The repo's main working tree - first entry of `git worktree list`."""
    for line in git(["worktree", "list", "--porcelain"], path).splitlines():
        if line.startswith("worktree "):
            return os.path.realpath(line[len("worktree "):])
    raise RuntimeError("git worktree list returned no worktrees")


def is_ignored(repo, relpath):
    """True when git ignores relpath in repo (so it is local-only, never tracked)."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", relpath],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def default_branch(repo):
    """The integration branch this worktree was cut from: origin/HEAD, else a local master/main."""
    try:
        ref = git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], repo)
        if ref:
            return ref
    except subprocess.CalledProcessError:
        pass
    for name in ("master", "main"):
        probe = subprocess.run(["git", "rev-parse", "--verify", "-q", name], cwd=repo, stdout=subprocess.DEVNULL)
        if probe.returncode == 0:
            return name
    return None


def derive_label(worktree):
    """
    Ticket key from the branch name, else from the subjects of commits this
    branch adds on top of the default branch, else None.

    T3 Code cuts worktrees from master on a placeholder branch (t3code/<hash>),
    and the ticket is created later from inside the worktree - so a fresh one
    usually has no ticket anywhere yet. Only commits AHEAD of the default
    branch are consulted: master's own tip carries whichever ticket merged
    last, which is not this worktree's.
    """
    try:
        branch = git(["branch", "--show-current"], worktree)
    except subprocess.CalledProcessError:
        branch = ""
    match = TICKET_RE.search(branch)
    if match:
        return match.group(0)
    base = default_branch(worktree)
    if base:
        try:
            subjects = git(["log", "--pretty=%s", f"{base}..HEAD"], worktree)
        except subprocess.CalledProcessError:
            subjects = ""
        match = TICKET_RE.search(subjects)
        if match:
            return match.group(0)
    return None


# ---------------------------------------------------------------- local-only files


def absolute_link_target(link_path):
    """Where a symlink points, made absolute relative to the link's own directory."""
    target = os.readlink(link_path)
    if os.path.isabs(target):
        return os.path.normpath(target)
    return os.path.normpath(os.path.join(os.path.dirname(link_path), target))


def local_only_entries(main):
    """
    Gitignored things in the main checkout worth knowing about, as
    (relpath, kind, target) with kind in {"link", "env", "other"}.

    "link" is any ignored symlink in LINK_SCAN_DIRS (target = absolute), "env" is
    a plain-file .env (target = its absolute path), "other" is every remaining
    ignored top-level file - reported, never mirrored.
    """
    entries = []
    for scan_dir in LINK_SCAN_DIRS:
        directory = os.path.join(main, scan_dir)
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            relpath = os.path.join(scan_dir, name) if scan_dir else name
            full = os.path.join(directory, name)
            if name in REPORT_SKIP or not is_ignored(main, relpath):
                continue
            if os.path.islink(full):
                entries.append((relpath, "link", absolute_link_target(full)))
            elif relpath == ".env" and os.path.isfile(full):
                entries.append((relpath, "env", full))
            elif os.path.isfile(full):
                entries.append((relpath, "other", full))
    return entries


def _same_file_content(path_a, path_b):
    with open(path_a, "rb") as file_a, open(path_b, "rb") as file_b:
        return file_a.read() == file_b.read()


def mirror_entry(entry, worktree, dry_run=False):
    """Re-create one local-only entry in the worktree. Returns a status word; never overwrites."""
    relpath, kind, target = entry
    if kind == "other":
        return "not mirrored"
    dest = os.path.join(worktree, relpath)
    if os.path.lexists(dest):
        if kind == "link":
            if os.path.islink(dest) and absolute_link_target(dest) == target:
                return "ok"
            return "conflict"
        if os.path.isfile(dest) and not os.path.islink(dest) and _same_file_content(dest, target):
            return "ok"
        return "conflict"
    if dry_run:
        return "would link" if kind == "link" else "would copy"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if kind == "env":
        shutil.copy2(target, dest)
        return "copied"
    try:
        os.symlink(target, dest, target_is_directory=os.path.isdir(target))
        return "linked"
    except OSError:
        # Windows without Developer Mode cannot symlink; fall back to a copy so
        # the worktree still works (same fallback deploy_configs.py makes).
        if os.path.isfile(target):
            shutil.copy2(target, dest)
            return "copied (no symlink support)"
        raise


# ---------------------------------------------------------------- vs code workspace


def short_host_token(hostname):
    """Lowercase short (pre-dot) hostname - the token deploy_configs.py uses for {host}."""
    return (hostname or "").split(".")[0].lower()


def workspace_file(repo_parent, hostname=None):
    """<repo_parent>/<host>.code-workspace - the link deploy_configs.py puts next to the checkouts."""
    token = short_host_token(hostname or socket.gethostname())
    return os.path.join(repo_parent, f"{token}.code-workspace")


def _folder_block_re(path):
    """Regex for one `{ "name": ..., "path": "<path>", },` block in the JSONC folders list."""
    return re.compile(
        r'(?P<indent>[ \t]*)\{\s*"name":\s*"[^"\n]*",\s*"path":\s*"' + re.escape(path) + r'",?\s*\},?[ \t]*\n',
    )


def add_workspace_folder(text, anchor_path, name, path):
    """
    Insert a folder entry for `path` right after the entry whose path is
    `anchor_path`. Returns (new_text, status): "present" when `path` is already
    listed under this name, "relabeled" when it is listed under another name
    (the ticket arrived after the first run), "no anchor" when the main
    checkout is not in the file, else "added".
    """
    existing = re.search(r'"name":\s*"(?P<name>[^"\n]*)",\s*"path":\s*"' + re.escape(path) + r'"', text)
    if existing:
        if existing.group("name") == name:
            return text, "present"
        return text[: existing.start("name")] + name + text[existing.end("name"):], "relabeled"
    match = _folder_block_re(anchor_path).search(text)
    if not match:
        return text, "no anchor"
    block = WORKSPACE_ENTRY.format(indent=match.group("indent"), name=name, path=path)
    return text[: match.end()] + block + text[match.end():], "added"


def remove_workspace_folder(text, path):
    """Drop the folder entry for `path`. Returns (new_text, status) with status "removed" or "absent"."""
    match = _folder_block_re(path).search(text)
    if not match:
        return text, "absent"
    return text[: match.start()] + text[match.end():], "removed"


def workspace_relpath(repo_parent, path):
    """Path as the workspace file wants it: relative to the file's directory, forward slashes."""
    return os.path.relpath(path, repo_parent).replace(os.sep, "/")


def update_workspace(main, worktree, label, remove=False, dry_run=False, hostname=None):
    """Add (or remove) the worktree's folder entry in this host's workspace file. Returns a status."""
    repo_parent = os.path.dirname(main)
    ws_path = workspace_file(repo_parent, hostname)
    if not os.path.isfile(ws_path):
        return f"no workspace file at {ws_path}"
    with open(ws_path, encoding="utf-8") as file_handle:
        text = file_handle.read()
    wt_rel = workspace_relpath(repo_parent, worktree)
    if remove:
        new_text, status = remove_workspace_folder(text, wt_rel)
    else:
        repo_name = os.path.basename(main)
        name = WORKSPACE_LABEL.format(repo=repo_name, label=label)
        new_text, status = add_workspace_folder(text, workspace_relpath(repo_parent, main), name, wt_rel)
    if new_text != text and not dry_run:
        with open(ws_path, "w", encoding="utf-8") as file_handle:
            file_handle.write(new_text)
    elif new_text != text:
        status = f"would be {status}"
    return f"{status} ({os.path.basename(ws_path)}: {wt_rel})"


# ---------------------------------------------------------------- uv


def sync_venv(worktree, dry_run=False):
    """Run `uv sync` in the worktree when it is a uv project. Returns a status."""
    if not os.path.isfile(os.path.join(worktree, "uv.lock")):
        return "skipped (no uv.lock)"
    if shutil.which("uv") is None:
        return "skipped (uv not on PATH)"
    if dry_run:
        return "would run uv sync"
    result = subprocess.run(["uv", "sync"], cwd=worktree)
    return "ok" if result.returncode == 0 else f"FAILED (exit {result.returncode})"


# ---------------------------------------------------------------- main


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--worktree", default=os.getcwd(), help="path inside the worktree (default: cwd)")
    parser.add_argument("--label", help="workspace folder label suffix (default: ticket key from the branch)")
    parser.add_argument("--remove", action="store_true", help="only remove the workspace folder entry")
    parser.add_argument("--no-workspace", action="store_true", help="do not touch the VS Code workspace file")
    parser.add_argument("--no-sync", action="store_true", help="do not run uv sync")
    parser.add_argument("--dry-run", action="store_true", help="report what would happen, change nothing")
    parser.add_argument("--hostname", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    worktree = worktree_root(args.worktree)
    main = main_checkout(worktree)
    if worktree == main:
        print(f"{worktree} is the main checkout, not a worktree - nothing to do")
        return 2
    print(f"worktree: {worktree}\nmain:     {main}")

    if args.remove:
        status = update_workspace(main, worktree, None, remove=True, dry_run=args.dry_run, hostname=args.hostname)
        print("workspace:", status)
        return 0

    conflicts = 0
    print("local-only files:")
    for entry in local_only_entries(main):
        status = mirror_entry(entry, worktree, dry_run=args.dry_run)
        conflicts += status == "conflict"
        target = entry[2] if entry[1] == "link" else ""
        print(f"  {status:<12} {entry[0]}{'  -> ' + target if target else ''}")

    if not args.no_workspace:
        label = args.label or derive_label(worktree) or os.path.basename(worktree)
        if not args.label and label == os.path.basename(worktree):
            print("no ticket in the branch or its commits yet - labelling with the directory name; "
                  "re-run with --label once the ticket exists (or now, with a short description)")
        print("workspace:", update_workspace(main, worktree, label, dry_run=args.dry_run, hostname=args.hostname))
    if not args.no_sync:
        print("uv sync:", sync_venv(worktree, dry_run=args.dry_run))

    print("shared through the common git dir, nothing to do: hooks, .git/info/exclude, stashes")
    if conflicts:
        print(f"{conflicts} conflict(s): the worktree already has a different file there - left untouched")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
