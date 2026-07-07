# %%
# Imports #

import argparse
import glob
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
from utils.inventory_tools import load_inventory_hostnames

# %%
# Variables #

dotenv_path = os.path.join(grandparent_dir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

system = platform.system()

REPO_ROOT = parent_dir
MANIFEST_PATH = os.path.join(REPO_ROOT, "deploy_manifest.yaml")
INVENTORY_PATH = os.path.join(grandparent_dir, "personal_credentials", "hosts.json")
BACKUP_ROOT = os.path.join(REPO_ROOT, "data", "config_backups")

PLATFORM_KEYS = {"Darwin": "darwin", "Linux": "linux", "Windows": "windows"}

# Filename tokens accepted per platform when resolving <base>.<token>.<ext>
# variant files ("mac" is an alias kept for settings.mac.json)
PLATFORM_FILE_TOKENS = {"darwin": ("darwin", "mac"), "linux": ("linux",), "windows": ("windows",)}

# Statuses that mean "this entry needs no attention"
HEALTHY_STATUSES = {"OK"}

# %%
# Output formatting #

_COLOR_CODES = {
    "green": "32",
    "red": "31",
    "yellow": "33",
    "cyan": "36",
    "bold": "1",
    "dim": "2",
}

STATUS_COLORS = {
    "OK": "green",
    "NOT_DEPLOYED": "yellow",
    "BROKEN_LINK": "red",
    "WRONG_TARGET": "red",
    "NOT_A_LINK": "red",
    "REPO_MISSING": "red",
    "NONE": "dim",
    "SKIP_HOST": "dim",
    "SKIP_PLATFORM": "dim",
    "SKIP_VARIANT": "dim",
    "SKIP_REQUIRES": "dim",
}


def use_color():
    """Color when writing to a real terminal and NO_COLOR is not set."""
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def paint(text, color):
    if not use_color() or color not in _COLOR_CODES:
        return text
    return f"\033[{_COLOR_CODES[color]}m{text}\033[0m"


def status_line(status, name, text, name_width=22):
    """One aligned report row: colored STATUS column, entry name, free text."""
    label = paint(f"{status:<14}", STATUS_COLORS.get(status))
    return f"{label}{name:<{name_width}}  {text}".rstrip()


def _info_detail(row, platform_key):
    """Explanation text for rows that are skipped by design."""
    if row["action"] == "none":
        note = " ".join(row["note"].split())
        if len(note) > 90:
            note = note[:90].rstrip() + "... (see manifest note)"
        return f"no link by design{': ' + note if note else ''}"
    if row["action"] == "skip_host":
        return "not for this host"
    if row["action"] == "skip_variant":
        return f"no {os.path.basename(row['repo'])} variant for this host"
    if row["action"] == "skip_requires":
        return f"requires {row['requires']} - not present on this machine (repo not cloned here?)"
    return f"no dest for {platform_key}"


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


def create_link(repo_path, system_path):
    """
    Create a symlink at system_path pointing back at repo_path.

    On Windows, symlinks need admin rights (or Developer Mode); when denied,
    fall back to a HARD link - never a copy (copies have no tie to the repo at
    all and silently drift). The hard-link caveat: git replaces file inodes on
    checkout/pull, orphaning the link; status catches that (the inode no longer
    matches -> NOT_A_LINK) and a re-deploy re-links it.
    """
    parent = os.path.dirname(system_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    try:
        os.symlink(repo_path, system_path)
        return "symlinked"
    except OSError:
        if system == "Windows":
            os.link(repo_path, system_path)
            print("  symlink denied - created a hard link instead; after git pull, "
                  "run status/deploy to catch and fix orphaned hard links")
            return "hardlinked"
        raise


def is_hard_link_to(repo_path, system_path):
    """True when system_path is a regular file sharing repo_path's inode (a hard link)."""
    if os.path.islink(system_path) or not (os.path.isfile(system_path) and os.path.isfile(repo_path)):
        return False
    try:
        return os.path.samefile(system_path, repo_path)
    except OSError:
        return False


def is_deployed(repo_path, system_path):
    """True when system_path is already a correct symlink (or existing hard link) to repo_path."""
    if os.path.islink(system_path):
        return os.path.exists(system_path) and os.path.realpath(system_path) == os.path.realpath(repo_path)
    # an existing correct hard link is left alone - do not churn it
    return is_hard_link_to(repo_path, system_path)


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
    replace_system_if_exists=True,
    backup_root=None,
    repo_root=None,
):
    """
    Keep the real file in the repo and place a symlink at system_path.

    The repo is the source of truth: when both versions exist, the system file
    is backed up (timestamped copy, mtime preserved) and replaced by the link -
    it is never moved into the repo working tree. Ingestion only happens when
    the repo file does not exist yet (first-time capture of a config).

    Idempotent: a destination that is already a correct symlink - or an
    existing hard link sharing the repo file's inode - is a no-op.
    """
    repo_path = os.path.abspath(os.path.expanduser(repo_path))
    system_path = os.path.abspath(os.path.expanduser(system_path))

    if is_deployed(repo_path, system_path):
        print(f"  already deployed: {system_path}")
        return "noop"

    # A wrong-target or dangling link at the destination is just a pointer - drop it
    if os.path.islink(system_path):
        os.remove(system_path)
        print(f"  removed stale link at {system_path}")

    repo_exists = os.path.exists(repo_path)
    system_exists = os.path.exists(system_path)

    if repo_exists and not system_exists:
        action = create_link(repo_path, system_path)
        print(f"  {action} {system_path} -> {repo_path}")
        return action
    if not repo_exists and system_exists:
        return _ingest_system_file(repo_path, system_path, ingest_system_if_exists)
    if repo_exists and system_exists:
        return _replace_system_file(repo_path, system_path, replace_system_if_exists, backup_root, repo_root)
    print(f"  nothing to deploy: neither {repo_path} nor {system_path} exists")
    return "missing"


def _ingest_system_file(repo_path, system_path, ingest_system_if_exists):
    if not ingest_system_if_exists:
        print(f"  repo file missing; skipping ingestion of existing system file {system_path}")
        return "skipped"
    os.makedirs(os.path.dirname(repo_path), exist_ok=True)
    shutil.move(system_path, repo_path)
    print(f"  moved {system_path} into repo at {repo_path}")
    action = create_link(repo_path, system_path)
    print(f"  {action} {system_path} -> {repo_path}")
    return "ingested"


def _replace_system_file(repo_path, system_path, replace_system_if_exists, backup_root, repo_root):
    if not replace_system_if_exists:
        print(f"  both versions exist; skipping replacement of {system_path} - no changes made")
        return "skipped"
    backup_path = backup_system_file(system_path, repo_path, backup_root=backup_root, repo_root=repo_root)
    print(f"  backed up {system_path} to {backup_path}")
    os.remove(system_path)
    print("  replaced system version with the repo version (local edits live only in the backup)")
    action = create_link(repo_path, system_path)
    print(f"  {action} {system_path} -> {repo_path}")
    return "replaced"


# %%
# Manifest #


def load_manifest(manifest_path=None, inventory_path=None):
    """
    Load and validate deploy_manifest.yaml, returning a list of entry dicts.

    Every name in an entry's optional hosts filter must exist in the host
    inventory (personal_credentials/hosts.json) - the single source of truth
    for machine names - so a typo or invented hostname fails loudly instead of
    silently deploying to (or skipping) the wrong machines. Machines without
    the personal_credentials repo skip the check.
    """
    manifest_path = manifest_path or MANIFEST_PATH
    with open(manifest_path, "r", encoding="utf-8") as file_handle:
        entries = yaml.safe_load(file_handle) or []
    if not isinstance(entries, list):
        raise ValueError(f"Manifest {manifest_path} must be a YAML list of entries")
    for entry in entries:
        if not isinstance(entry, dict) or "name" not in entry or "repo" not in entry:
            raise ValueError(f"Manifest entry must be a mapping with 'name' and 'repo' keys: {entry}")
        method = entry.get("method", "symlink")
        if method not in ("symlink", "none"):
            raise ValueError(f"Manifest entry {entry['name']} has invalid method: {method}")
        requires = entry.get("requires")
        if requires is not None and (not isinstance(requires, str) or not requires.strip()):
            raise ValueError(
                f"Manifest entry {entry['name']} has invalid requires (must be a non-empty path): {requires}"
            )
    validate_manifest_hosts(entries, inventory_path)
    return entries


def validate_manifest_hosts(entries, inventory_path=None):
    """Raise if any manifest hosts entry names a machine missing from the inventory."""
    inventory_path = inventory_path or INVENTORY_PATH
    if not os.path.exists(inventory_path):
        return
    known_hosts = load_inventory_hostnames(inventory_path)
    unknown = [
        f"{entry['name']}: {host}"
        for entry in entries
        for host in entry.get("hosts") or []
        if str(host).split(".")[0].upper() not in known_hosts
    ]
    if unknown:
        raise ValueError(
            f"Manifest hosts not found in inventory {inventory_path} "
            f"(fix the manifest name or add the machine to the inventory): {', '.join(unknown)}"
        )


def short_host_token(hostname):
    """Lowercase short (pre-dot) hostname - the token used in variant filenames."""
    return (hostname or "").split(".")[0].lower()


def _variant_path(repo_path, token):
    """<dir>/<base><ext> -> <dir>/<base>.<token><ext> per the variant naming convention."""
    directory, filename = os.path.split(repo_path)
    base, ext = os.path.splitext(filename)
    return os.path.join(directory, f"{base}.{token}{ext}")


def _any_variant_exists(repo_path):
    """True when at least one <base>.<token><ext> sibling of repo_path exists."""
    directory, filename = os.path.split(repo_path)
    base, ext = os.path.splitext(filename)
    pattern = os.path.join(glob.escape(directory), f"{glob.escape(base)}.*{ext}")
    return bool(glob.glob(pattern))


def resolve_repo_variant(repo_path, hostname, platform_key):
    """
    Resolve a manifest repo path to its per-host / per-platform variant file,
    named <base>.<token>.<ext> with a lowercase token (see CLAUDE.md conventions).

    Resolution order: exact hostname (short pre-dot name, case-insensitive) ->
    platform -> bare default. Returns (path, applies):
    - (variant_path, True) when a host or platform variant exists;
    - (repo_path, True) when the bare file exists, or when nothing related
      exists at all (so a bad manifest path still surfaces as REPO_MISSING);
    - (repo_path, False) when only variants for *other* hosts exist - the
      entry simply does not apply to this machine.
    """
    host_token = short_host_token(hostname)
    tokens = ([host_token] if host_token else []) + list(PLATFORM_FILE_TOKENS.get(platform_key, (platform_key,)))
    for token in tokens:
        candidate = _variant_path(repo_path, token)
        if os.path.exists(candidate):
            return candidate, True
    if os.path.exists(repo_path) or not _any_variant_exists(repo_path):
        return repo_path, True
    return repo_path, False


def expand_path(raw_path, hostname="", repo_root=None):
    """
    Expand ~ and the two manifest placeholders: {host} becomes the lowercase
    short hostname (same token as variant filenames) and {repo_parent} the
    directory containing this repo checkout (e.g. ~/GitHub).
    """
    raw_path = raw_path.replace("{host}", short_host_token(hostname))
    raw_path = raw_path.replace("{repo_parent}", os.path.dirname(repo_root or REPO_ROOT))
    return os.path.expanduser(raw_path)


def resolve_dest(entry, platform_key, hostname="", repo_root=None):
    """Return the expanded destination path for this platform, or None if not applicable."""
    dest = entry.get("dest") or {}
    raw_dest = dest.get(platform_key)
    if not raw_dest:
        return None
    return expand_path(raw_dest, hostname, repo_root)


def host_allowed(entry, hostname):
    """Apply the optional hosts filter, matching full or short (pre-dot) hostname."""
    hosts = entry.get("hosts")
    if not hosts:
        return True
    hostname = (hostname or "").upper()
    short_hostname = hostname.split(".")[0]
    return any(str(host).upper() in (hostname, short_hostname) for host in hosts)


def build_plan(entries, platform_key, hostname, repo_root=None):
    """Turn manifest entries into plan rows: apply / none / skip_host / skip_platform / skip_requires / skip_variant."""
    repo_root = repo_root or REPO_ROOT
    plan = []
    for entry in entries:
        row = {
            "name": entry["name"],
            "repo": os.path.join(repo_root, entry["repo"]),
            "method": entry.get("method", "symlink"),
            "note": entry.get("note", ""),
            "requires": None,
            "dest": None,
            "action": "apply",
        }
        if row["method"] == "none":
            row["action"] = "none"
        elif not host_allowed(entry, hostname):
            row["action"] = "skip_host"
        else:
            row["dest"] = resolve_dest(entry, platform_key, hostname, repo_root)
            if row["dest"] is None:
                row["action"] = "skip_platform"
            elif not requires_satisfied(entry, row, hostname, repo_root):
                row["action"] = "skip_requires"
            else:
                row["repo"], applies = resolve_repo_variant(row["repo"], hostname, platform_key)
                if not applies:
                    row["action"] = "skip_variant"
        plan.append(row)
    return plan


def requires_satisfied(entry, row, hostname, repo_root):
    """
    Apply the optional requires precondition: a path (placeholder-expanded)
    that must already exist for the entry to deploy on this machine.

    Use it for dests inside sibling repo checkouts: without it, deploying on a
    machine that never cloned the repo would silently create the repo's folder
    (and break a later git clone into it). Configs that OWN their destination
    dir (~/.config/nvim, ~/.claude, ...) should NOT set requires - creating
    those dirs is wanted.
    """
    requires = entry.get("requires")
    if not requires:
        return True
    row["requires"] = expand_path(requires, hostname, repo_root)
    return os.path.exists(row["requires"])


# %%
# Status #


def classify_entry(repo_path, system_path):
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
    if is_hard_link_to(repo_path, system_path):
        return "OK", "hard link shares the repo file's inode"
    if _file_hash(system_path) == _file_hash(repo_path):
        return "NOT_A_LINK", "regular file; content matches repo (orphaned hard link or not yet linked)"
    return "NOT_A_LINK", "regular file; content diverges from repo (orphaned hard link after git pull?)"


def planned_action(status):
    """Human description of what deploy would do for a given status."""
    descriptions = {
        "OK": "no action needed",
        "NOT_DEPLOYED": "deploy would create symlink at destination",
        "BROKEN_LINK": "deploy would remove the stale link and create symlink",
        "WRONG_TARGET": "deploy would remove the stale link and create symlink",
        "NOT_A_LINK": "deploy would back up the system file to data/config_backups, then replace it with a link "
                      "to the repo version",
        "REPO_MISSING": "nothing to deploy (repo file missing)",
    }
    return descriptions.get(status, "unknown")


def run_status(plan, platform_key):
    """
    Combined health report + dry run: one row per manifest entry showing its
    current state and, when unhealthy, what deploy would do about it. Read-only;
    exits non-zero when anything needs attention (cron-able drift check).
    """
    name_width = max([len(row["name"]) for row in plan] + [4])
    status_counts: dict = {}
    for row in plan:
        if row["action"] != "apply":
            print(status_line(row["action"].upper(), row["name"], _info_detail(row, platform_key), name_width))
            continue
        status, detail = classify_entry(row["repo"], row["dest"])
        status_counts[status] = status_counts.get(status, 0) + 1
        print(status_line(status, row["name"], row["dest"], name_width))
        if status not in HEALTHY_STATUSES:
            follow_up = f"{'':<14}{'':<{name_width}}  -> {detail}; {planned_action(status)}"
            print(paint(follow_up, "dim"))
    unhealthy = sum(count for status, count in status_counts.items() if status not in HEALTHY_STATUSES)
    summary = ", ".join(f"{count} {status.lower()}" for status, count in sorted(status_counts.items()))
    print()
    if not summary:
        print("no applicable entries")
    elif unhealthy:
        print(paint(f"drift detected: {summary} - run deploy to fix", "red"))
    else:
        print(paint(f"all healthy: {summary}", "green"))
    return 1 if unhealthy else 0


def run_deploy(plan, platform_key):
    """Deploy every applicable manifest entry; correct deployments are no-ops."""
    counts = {"changed": 0, "noop": 0, "skipped": 0}
    name_width = max([len(row["name"]) for row in plan] + [4])
    for row in plan:
        if row["action"] != "apply":
            print(status_line(row["action"].upper(), row["name"], _info_detail(row, platform_key), name_width))
            continue
        print(paint(row["name"], "bold"))
        result = deploy_config(row["repo"], row["dest"])
        if result == "noop":
            counts["noop"] += 1
        elif result in ("skipped", "missing"):
            counts["skipped"] += 1
        else:
            counts["changed"] += 1
    print()
    print(paint(
        f"Deploy complete: {counts['changed']} changed, {counts['noop']} already deployed, "
        f"{counts['skipped']} skipped",
        "green",
    ))
    return 0


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
        help="deploy (default) creates the links; status is a read-only combined "
        "drift report + dry run (non-zero exit on drift)",
    )
    parser.add_argument("--status", action="store_true", help="same as the status command")
    parser.add_argument("--dry-run", action="store_true", help="deprecated alias for the status command")
    parser.add_argument("--manifest", default=None, help="path to an alternate manifest file (for testing)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    entries = load_manifest(args.manifest)
    platform_key = get_platform_key()
    hostname = get_uppercase_hostname()
    print(f"platform: {platform_key}, hostname: {hostname}")
    print()
    plan = build_plan(entries, platform_key, hostname)
    if args.status or args.dry_run or args.command == "status":
        return run_status(plan, platform_key)
    return run_deploy(plan, platform_key)


if __name__ == "__main__":
    sys.exit(main())


# %%
