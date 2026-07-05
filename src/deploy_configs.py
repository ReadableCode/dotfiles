# %%
# Imports #

import argparse
import hashlib
import os
import platform
import shutil
import sys
import time

import yaml
from config import grandparent_dir, parent_dir
from dotenv import load_dotenv
from utils.host_tools import get_uppercase_hostname

# %%
# Variables #

dotenv_path = os.path.join(grandparent_dir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

system = platform.system()

REPO_ROOT = parent_dir
MANIFEST_PATH = os.path.join(REPO_ROOT, "deploy_manifest.yaml")
BACKUP_ROOT = os.path.join(REPO_ROOT, "data", "config_backups")

PLATFORM_KEYS = {"Darwin": "darwin", "Linux": "linux", "Windows": "windows"}

# Statuses that mean "this entry needs no attention"
HEALTHY_STATUSES = {"OK"}
# Rows that are informational only and never affect the exit code
INFO_ACTIONS = {"none", "skip_host", "skip_platform"}


# %%
# Helpers #


def get_platform_key(system_name=None):
    """Map platform.system() to the keys used in deploy_manifest.yaml dest blocks."""
    system_name = system_name or system
    return PLATFORM_KEYS.get(system_name, system_name.lower())


def _file_hash(path):
    hasher = hashlib.sha256()
    with open(path, "rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def create_link(repo_path, system_path, method="symlink"):
    """
    Create a symlink (or copy) at system_path pointing back at repo_path.

    On Windows, os.symlink works without admin when Developer Mode is enabled; if it
    is denied we fall back to a copy - never a hard link, because git replaces files
    with new inodes on checkout/pull, which silently orphans hard links.
    """
    parent = os.path.dirname(system_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if method == "copy":
        shutil.copy2(repo_path, system_path)
        return "copied"
    try:
        os.symlink(repo_path, system_path)
        return "symlinked"
    except OSError:
        if system == "Windows":
            print(f"Symlink not permitted for {system_path}, falling back to copy (enable Developer Mode for links)")
            shutil.copy2(repo_path, system_path)
            return "copied"
        raise


def is_deployed(repo_path, system_path, method="symlink"):
    """True when system_path is already a correct deployment of repo_path."""
    if os.path.islink(system_path):
        return os.path.exists(system_path) and os.path.realpath(system_path) == os.path.realpath(repo_path)
    if method == "copy" and os.path.isfile(system_path) and os.path.isfile(repo_path):
        return _file_hash(system_path) == _file_hash(repo_path)
    return False


def backup_system_file(system_path, repo_path, backup_root=None, repo_root=None):
    """
    Copy system_path to <backup_root>/<repo-relative path>.<timestamp>.

    Backups live under data/config_backups (data/ is gitignored) so they never
    appear as clutter next to tracked configs.
    """
    backup_root = backup_root or BACKUP_ROOT
    repo_root = repo_root or REPO_ROOT
    relative_path = os.path.relpath(os.path.abspath(repo_path), repo_root)
    if relative_path.startswith(".."):
        relative_path = os.path.basename(repo_path)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = os.path.join(backup_root, f"{relative_path}.{timestamp}")
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    shutil.copy2(system_path, backup_path)
    return backup_path


# %%
# Deploy #


def deploy_config(
    repo_path,
    system_path,
    ingest_system_if_exists=False,
    backup_into_repo=True,
    method="symlink",
    backup_root=None,
    repo_root=None,
):
    """
    Keep the real file in the repo and place a symlink (or, as a Windows fallback,
    a copy) at system_path. Optionally ingest an existing system file into the repo
    and back up the existing system file before replacing it.

    Idempotent: a destination that is already a correct link (or matching copy)
    is a no-op.
    """
    repo_path = os.path.abspath(os.path.expanduser(repo_path))
    system_path = os.path.abspath(os.path.expanduser(system_path))

    if is_deployed(repo_path, system_path, method=method):
        print(f"Already deployed: {system_path} -> {repo_path} (no action)")
        return "noop"

    # A wrong-target or dangling link at the destination is just a pointer - drop it
    if os.path.islink(system_path):
        os.remove(system_path)
        print(f"Removed stale link at {system_path}")

    repo_exists = os.path.exists(repo_path)
    system_exists = os.path.exists(system_path)

    if repo_exists and not system_exists:
        action = create_link(repo_path, system_path, method=method)
        print(f"Case 1: {action} {system_path} -> {repo_path}")
        return action
    if not repo_exists and system_exists:
        return _ingest_system_file(repo_path, system_path, ingest_system_if_exists, method)
    if repo_exists and system_exists:
        return _replace_system_file(repo_path, system_path, backup_into_repo, method, backup_root, repo_root)
    print("Case 4: Neither repo nor system file exists. No action taken.")
    return "missing"


def _ingest_system_file(repo_path, system_path, ingest_system_if_exists, method):
    print("Case 2: Repo file does not exist, system file exists")
    if not ingest_system_if_exists:
        print(f"Skipping ingestion of existing system file {system_path} into repo")
        return "skipped"
    os.makedirs(os.path.dirname(repo_path), exist_ok=True)
    shutil.move(system_path, repo_path)
    print(f"Moved {system_path} into repo at {repo_path}")
    action = create_link(repo_path, system_path, method=method)
    print(f"{action} {system_path} -> {repo_path}")
    return "ingested"


def _replace_system_file(repo_path, system_path, backup_into_repo, method, backup_root, repo_root):
    print("Case 3: Both repo and system file exist")
    if not backup_into_repo:
        print(f"Skipping backup of existing system file {system_path}. No changes made.")
        return "skipped"
    backup_path = backup_system_file(system_path, repo_path, backup_root=backup_root, repo_root=repo_root)
    print(f"Backed up {system_path} to {backup_path}")
    if method == "copy":
        # With copies the repo is the source of truth - refresh the destination
        shutil.copy2(repo_path, system_path)
        print(f"Copied {repo_path} over {system_path}")
        return "copied"
    shutil.move(system_path, repo_path)
    print(f"Moved {system_path} into repo at {repo_path} (system version kept; git diff shows what changed)")
    action = create_link(repo_path, system_path, method=method)
    print(f"{action} {system_path} -> {repo_path}")
    return "ingested"


# %%
# Manifest #


def load_manifest(manifest_path=None):
    """Load and validate deploy_manifest.yaml, returning a list of entry dicts."""
    manifest_path = manifest_path or MANIFEST_PATH
    with open(manifest_path, "r", encoding="utf-8") as file_handle:
        entries = yaml.safe_load(file_handle) or []
    if not isinstance(entries, list):
        raise ValueError(f"Manifest {manifest_path} must be a YAML list of entries")
    for entry in entries:
        if not isinstance(entry, dict) or "name" not in entry or "repo" not in entry:
            raise ValueError(f"Manifest entry must be a mapping with 'name' and 'repo' keys: {entry}")
        method = entry.get("method", "symlink")
        if method not in ("symlink", "copy", "none"):
            raise ValueError(f"Manifest entry {entry['name']} has invalid method: {method}")
    return entries


def resolve_dest(entry, platform_key):
    """Return the expanded destination path for this platform, or None if not applicable."""
    dest = entry.get("dest") or {}
    raw_dest = dest.get(platform_key)
    return os.path.expanduser(raw_dest) if raw_dest else None


def host_allowed(entry, hostname):
    """Apply the optional hosts filter, matching full or short (pre-dot) hostname."""
    hosts = entry.get("hosts")
    if not hosts:
        return True
    hostname = (hostname or "").upper()
    short_hostname = hostname.split(".")[0]
    return any(str(host).upper() in (hostname, short_hostname) for host in hosts)


def build_plan(entries, platform_key, hostname, repo_root=None):
    """Turn manifest entries into plan rows: apply / none / skip_host / skip_platform."""
    repo_root = repo_root or REPO_ROOT
    plan = []
    for entry in entries:
        row = {
            "name": entry["name"],
            "repo": os.path.join(repo_root, entry["repo"]),
            "method": entry.get("method", "symlink"),
            "note": entry.get("note", ""),
            "dest": None,
            "action": "apply",
        }
        if row["method"] == "none":
            row["action"] = "none"
        elif not host_allowed(entry, hostname):
            row["action"] = "skip_host"
        else:
            row["dest"] = resolve_dest(entry, platform_key)
            if row["dest"] is None:
                row["action"] = "skip_platform"
        plan.append(row)
    return plan


# %%
# Status #


def classify_entry(repo_path, system_path, method="symlink"):
    """Classify the deployment health of one destination. Returns (status, detail)."""
    if not os.path.exists(repo_path):
        return "REPO_MISSING", f"repo file {repo_path} does not exist"
    if not os.path.lexists(system_path):
        return "NOT_DEPLOYED", "destination missing"
    if os.path.islink(system_path):
        if not os.path.exists(system_path):
            return "BROKEN_LINK", f"dangling link -> {os.readlink(system_path)}"
        if os.path.realpath(system_path) == os.path.realpath(repo_path):
            return "OK", "link resolves to repo file"
        return "WRONG_TARGET", f"link resolves to {os.path.realpath(system_path)}"
    if os.path.isdir(system_path):
        return "NOT_A_LINK", "destination is a directory, expected a file link"
    if method == "copy":
        if _file_hash(system_path) == _file_hash(repo_path):
            return "OK", "copy content matches repo file"
        return "DIVERGED", "copy content differs from repo file"
    if _file_hash(system_path) == _file_hash(repo_path):
        return "NOT_A_LINK", "regular file; content matches repo (candidate for ingest)"
    return "NOT_A_LINK", "regular file; content diverges from repo"


def planned_action(status, method):
    """Human description of what deploy would do for a given status."""
    descriptions = {
        "OK": "no action (already deployed)",
        "NOT_DEPLOYED": f"would create {method} at destination",
        "BROKEN_LINK": f"would remove stale link and create {method}",
        "WRONG_TARGET": f"would remove stale link and create {method}",
        "NOT_A_LINK": "would back up system file to data/config_backups, ingest it into the repo, then link",
        "DIVERGED": "would back up system file to data/config_backups and re-copy the repo version",
        "REPO_MISSING": "nothing to deploy (repo file missing)",
    }
    return descriptions.get(status, "unknown")


def _print_info_row(row, platform_key):
    if row["action"] == "none":
        print(f"NONE          {row['name']:<22} no link by design. {row['note']}")
    elif row["action"] == "skip_host":
        print(f"SKIP_HOST     {row['name']:<22} not for this host")
    else:
        print(f"SKIP_PLATFORM {row['name']:<22} no dest for {platform_key}")


def run_dry_run(plan, platform_key):
    """Print the planned action for every manifest entry without touching anything."""
    for row in plan:
        if row["action"] != "apply":
            _print_info_row(row, platform_key)
            continue
        status, detail = classify_entry(row["repo"], row["dest"], method=row["method"])
        print(f"{status:<13} {row['name']:<22} {row['dest']}: {planned_action(status, row['method'])} ({detail})")
    print("Dry run complete. No changes made.")
    return 0


def run_deploy(plan, platform_key):
    """Deploy every applicable manifest entry; correct deployments are no-ops."""
    counts = {"changed": 0, "noop": 0, "skipped": 0}
    for row in plan:
        if row["action"] != "apply":
            _print_info_row(row, platform_key)
            continue
        print(f"--- {row['name']} ---")
        result = deploy_config(row["repo"], row["dest"], method=row["method"])
        if result == "noop":
            counts["noop"] += 1
        elif result in ("skipped", "missing"):
            counts["skipped"] += 1
        else:
            counts["changed"] += 1
    print(f"Deploy complete: {counts['changed']} changed, {counts['noop']} already deployed, "
          f"{counts['skipped']} skipped")
    return 0


def run_status(plan, platform_key):
    """Print a health report for every applicable entry; non-zero exit on any drift."""
    status_counts: dict = {}
    for row in plan:
        if row["action"] != "apply":
            _print_info_row(row, platform_key)
            continue
        status, detail = classify_entry(row["repo"], row["dest"], method=row["method"])
        status_counts[status] = status_counts.get(status, 0) + 1
        print(f"{status:<13} {row['name']:<22} {row['dest']} ({detail})")
    summary = ", ".join(f"{count} {status.lower()}" for status, count in sorted(status_counts.items()))
    print(summary if summary else "no applicable entries")
    unhealthy = sum(count for status, count in status_counts.items() if status not in HEALTHY_STATUSES)
    return 1 if unhealthy else 0


# %%
# Main #


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Deploy the configs in deploy_manifest.yaml for the current machine."
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["deploy", "status"],
        default="deploy",
        help="deploy (default) creates the links; status reports drift without changing anything",
    )
    parser.add_argument("--dry-run", action="store_true", help="print planned actions without touching the filesystem")
    parser.add_argument("--status", action="store_true", help="same as the status command; non-zero exit on drift")
    parser.add_argument("--manifest", default=None, help="path to an alternate manifest file (for testing)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    entries = load_manifest(args.manifest)
    platform_key = get_platform_key()
    hostname = get_uppercase_hostname()
    print(f"platform: {platform_key}, hostname: {hostname}")
    plan = build_plan(entries, platform_key, hostname)
    if args.status or args.command == "status":
        return run_status(plan, platform_key)
    if args.dry_run:
        return run_dry_run(plan, platform_key)
    return run_deploy(plan, platform_key)


if __name__ == "__main__":
    sys.exit(main())


# %%
