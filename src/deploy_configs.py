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
from readable_utils.host_tools import get_uppercase_hostname
from utils.inventory_tools import (
    find_overlay_dirs,
    load_inventory_hostnames,
    load_union_inventory_hostnames,
    overlay_context,
)

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


def _term_width():
    try:
        return min(shutil.get_terminal_size().columns, 100)
    except (OSError, ValueError):
        return 80


def print_section(title, count, color):
    """Section divider: a colored '-- Title (n) ----' rule across the terminal.

    ASCII only: Windows consoles default to cp1252, which cannot encode box
    drawing characters, and printing one raised UnicodeEncodeError before the
    report finished. Keep every character written to stdout in this file ASCII.
    """
    prefix = f"-- {title} ({count}) "
    print(paint(prefix + "-" * max(1, _term_width() - len(prefix)), color))


def fit_text(text, width):
    """Truncate prose to width with an ellipsis (paths are never passed through this)."""
    if width < 10 or len(text) <= width:
        return text
    return text[: width - 3].rstrip() + "..."


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
        # os.link cannot hard-link directories, so the Windows fallback is files-only
        if system == "Windows" and not os.path.isdir(repo_path):
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
    Copy system_path (file or directory) to <backup_root>/<repo-relative path>.<timestamp>.

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
    if os.path.isdir(system_path):
        shutil.copytree(system_path, backup_path, symlinks=True)
    else:
        shutil.copy2(system_path, backup_path)
    return backup_path


# %%
# Removals #


def discover_removals():
    """
    Locate every removals file: an optional deploy_removals.yaml in dotfiles plus,
    for each sibling overlay repo, an optional ``<context>_removals.yaml``
    (see find_overlay_dirs - every ``*_credentials`` repo, plus any sibling that
    opts in by declaring one of these files).

    A removals file is the committed list of destinations that must NOT exist any
    more. It is deliberately shared state, not machine state: the machine that
    deletes a manifest entry is almost never the only machine holding the link it
    created, so the list has to travel with the repo for every other machine to
    clean itself up on its next prune.
    """
    files = []
    base = os.path.join(REPO_ROOT, "deploy_removals.yaml")
    if os.path.exists(base):
        files.append(base)
    for overlay_dir in find_overlay_dirs(grandparent_dir):
        overlay = os.path.join(overlay_dir, f"{overlay_context(overlay_dir)}_removals.yaml")
        if os.path.exists(overlay):
            files.append(overlay)
    return files


def load_removals():
    """Parse every discovered removals file into entries with 'name' and 'dest' (no 'repo' - the source is gone)."""
    entries = []
    seen: dict = {}
    for path in discover_removals():
        with open(path, "r", encoding="utf-8") as handle:
            parsed = yaml.safe_load(handle) or []
        if not isinstance(parsed, list):
            raise ValueError(f"Removals file {path} must be a YAML list of entries")
        for entry in parsed:
            if not isinstance(entry, dict) or "name" not in entry or "dest" not in entry:
                raise ValueError(f"Removal entry must be a mapping with 'name' and 'dest' keys: {entry}")
            if entry["name"] in seen:
                raise ValueError(
                    f"Duplicate removal entry name '{entry['name']}' in {path} "
                    f"(already defined in {seen[entry['name']]})"
                )
            seen[entry["name"]] = path
            entries.append(entry)
    return entries


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
        print(f"  {action} {system_path}\n         -> {repo_path}")
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
    print(f"  {action} {system_path}\n         -> {repo_path}")
    return "ingested"


def _replace_system_file(repo_path, system_path, replace_system_if_exists, backup_root, repo_root):
    if not replace_system_if_exists:
        print(f"  both versions exist; skipping replacement of {system_path} - no changes made")
        return "skipped"
    backup_path = backup_system_file(system_path, repo_path, backup_root=backup_root, repo_root=repo_root)
    print(f"  backed up {system_path}\n         -> {backup_path}")
    if os.path.isdir(system_path):
        shutil.rmtree(system_path)
    else:
        os.remove(system_path)
    print("  replaced system version with the repo version (local edits live only in the backup)")
    action = create_link(repo_path, system_path)
    print(f"  {action} {system_path}\n         -> {repo_path}")
    return "replaced"


# %%
# Manifest #


def discover_manifests():
    """
    Locate every manifest to load: the main deploy_manifest.yaml (repo paths
    relative to REPO_ROOT) plus, for each sibling overlay repo, an optional
    overlay manifest named ``<context>_manifest.yaml`` whose repo paths are
    relative to that overlay repo's root. Overlay repos are every
    ``*_credentials`` repo plus any sibling that opts in by declaring such a
    file (see find_overlay_dirs). Returns a list of (manifest_path, base_dir)
    pairs, overlays sorted for determinism.
    """
    manifests = [(os.path.join(REPO_ROOT, "deploy_manifest.yaml"), REPO_ROOT)]
    for overlay_dir in find_overlay_dirs(grandparent_dir):
        overlay = os.path.join(overlay_dir, f"{overlay_context(overlay_dir)}_manifest.yaml")
        if os.path.exists(overlay):
            manifests.append((overlay, overlay_dir))
    return manifests


def load_manifests(manifest_path=None, inventory_path=None):
    """
    Load the main manifest plus every discovered overlay manifest, returning
    (entries, manifest_paths). Each entry is stamped with the internal keys
    ``_base_dir`` (its manifest's repo root, which build_plan joins ``repo``
    against) and ``_manifest`` (for error messages). Entry names must be
    unique across ALL loaded manifests.

    Passing manifest_path (the --manifest test escape hatch) loads only that
    single file, repo paths relative to the dotfiles REPO_ROOT, skipping
    overlay discovery.

    ``hosts`` filters are only allowed in overlay manifests: only an overlay
    travels with the inventory that knows its names, so a filter in the main
    manifest would fail host validation on any machine that clones a
    different subset of credentials repos.
    """
    located = [(manifest_path, REPO_ROOT)] if manifest_path else discover_manifests()
    main_manifest = None if manifest_path else located[0][0]
    entries = []
    seen: dict = {}
    for path, base_dir in located:
        for entry in _parse_manifest_file(path):
            if path == main_manifest and entry.get("hosts"):
                raise ValueError(
                    f"Manifest entry '{entry['name']}' in {path} uses a hosts filter; hosts "
                    "filters are only allowed in overlay manifests (move the entry to the "
                    "relevant <context>_manifest.yaml, which travels with the clones that "
                    "know those machine names)"
                )
            if entry["name"] in seen:
                raise ValueError(
                    f"Duplicate manifest entry name '{entry['name']}' in {path} "
                    f"(already defined in {seen[entry['name']]})"
                )
            seen[entry["name"]] = path
            entry["_base_dir"] = base_dir
            entry["_manifest"] = path
            entries.append(entry)
    validate_manifest_hosts(entries, inventory_path)
    return entries, [path for path, _ in located]


def load_manifest(manifest_path=None, inventory_path=None):
    """Load and validate a single manifest file (no overlay discovery), returning its entry dicts."""
    entries = _parse_manifest_file(manifest_path or MANIFEST_PATH)
    validate_manifest_hosts(entries, inventory_path)
    return entries


def _parse_manifest_file(manifest_path):
    """Parse one manifest file and validate the entry schema, returning a list of entry dicts."""
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
        if requires is not None:
            paths = requires if isinstance(requires, list) else [requires]
            if not paths or any(not isinstance(path, str) or not path.strip() for path in paths):
                raise ValueError(
                    f"Manifest entry {entry['name']} has invalid requires "
                    f"(must be a non-empty path or list of paths): {requires}"
                )
    return entries


def validate_manifest_hosts(entries, inventory_path=None):
    """
    Raise if any manifest hosts entry names a machine missing from the host
    inventories - the single source of truth for machine names - so a typo or
    invented hostname fails loudly instead of silently deploying to (or
    skipping) the wrong machines.

    By default the check runs against the UNION of every sibling
    ``*_credentials`` repo's inventory (``<context>_hosts.json``, legacy
    fallback ``hosts.json``); machines with no inventory at all (no
    credentials repos cloned) skip it. Passing inventory_path validates
    against that single file instead (tests).
    """
    if inventory_path is not None:
        if not os.path.exists(inventory_path):
            return
        known_hosts = load_inventory_hostnames(inventory_path)
        source = inventory_path
    else:
        known_hosts, inventory_paths = load_union_inventory_hostnames(grandparent_dir)
        if not inventory_paths:
            return
        source = ", ".join(inventory_paths)
    unknown = [
        f"{entry['name']}: {host}"
        for entry in entries
        for host in entry.get("hosts") or []
        if str(host).split(".")[0].upper() not in known_hosts
    ]
    if unknown:
        raise ValueError(
            f"Manifest hosts not found in inventory {source} "
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
    directory containing the DOTFILES checkout (e.g. ~/GitHub) - always, even
    for entries loaded from an overlay manifest.

    Returns a path in the platform's native separators. Manifest dest strings
    are written with forward slashes, so on Windows an expanded ~ produced
    mixed separators ("C:\\Users\\jason\\GitHub/load-log/.env") that leaked into
    the status report. normpath is a no-op on POSIX.
    """
    raw_path = raw_path.replace("{host}", short_host_token(hostname))
    raw_path = raw_path.replace("{repo_parent}", os.path.dirname(repo_root or REPO_ROOT))
    return os.path.normpath(os.path.expanduser(raw_path))


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
            # each entry's repo path resolves against its own manifest's repo root
            # (overlay entries live in their *_credentials repo, not in dotfiles).
            # normpath because manifest repo values use forward slashes, which
            # os.path.join leaves untouched inside the joined segment.
            "repo": os.path.normpath(os.path.join(entry.get("_base_dir") or repo_root, entry["repo"])),
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
    Apply the optional requires precondition: a path or list of paths
    (placeholder-expanded) that must ALL already exist for the entry to
    deploy on this machine.

    Use it for dests inside sibling repo checkouts: without it, deploying on a
    machine that never cloned the repo would silently create the repo's folder
    (and break a later git clone into it). List both the dest repo and the
    source (credentials) repo so the entry follows the clones, not a host
    whitelist. Configs that OWN their destination dir (~/.config/nvim,
    ~/.claude, ...) should NOT set requires - creating those dirs is wanted.
    """
    requires = entry.get("requires")
    if not requires:
        return True
    paths = requires if isinstance(requires, list) else [requires]
    expanded = [expand_path(path, hostname, repo_root) for path in paths]
    missing = [path for path in expanded if not os.path.exists(path)]
    row["requires"] = ", ".join(missing or expanded)
    return not missing


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
        return "NOT_A_LINK", "destination is a real directory; deploy would back it up and replace it with a link"
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


def run_status(plan, platform_key, prune_candidates=None):
    """
    Combined health report + dry run, grouped into sections (least interesting
    first, problems last so they stay on screen): not applicable -> healthy ->
    needs attention. Read-only; exits non-zero when anything needs attention
    (cron-able drift check).
    """
    name_width = max([len(row["name"]) for row in plan] + [4])
    info, healthy, unhealthy = [], [], []
    for row in plan:
        if row["action"] != "apply":
            info.append((row["action"].upper(), row, _info_detail(row, platform_key)))
            continue
        status, detail = classify_entry(row["repo"], row["dest"])
        (healthy if status in HEALTHY_STATUSES else unhealthy).append((status, row, detail))

    if info:
        detail_width = _term_width() - 18 - name_width
        print_section("Not applicable on this machine", len(info), "dim")
        for status, row, detail in info:
            print("  " + status_line(status, row["name"], fit_text(detail, detail_width), name_width))
        print()
    if healthy:
        print_section("Healthy", len(healthy), "green")
        for status, row, _ in healthy:
            print("  " + status_line(status, row["name"], row["dest"], name_width))
        print()
    if unhealthy:
        print_section("Needs attention", len(unhealthy), "red")
        for status, row, detail in unhealthy:
            print("  " + status_line(status, row["name"], row["dest"], name_width))
            print(paint(f"      {detail}", "dim"))
            print(paint(f"      -> {planned_action(status)}", "dim"))
        print()

    orphans = [(dest, reason) for dest, reason in (prune_candidates or []) if os.path.lexists(dest)]
    if orphans:
        print_section("Orphaned - no manifest entry wants these", len(orphans), "yellow")
        for dest, reason in orphans:
            print(f"  {dest}")
            print(paint(f"      {reason}", "dim"))
            print(paint("      -> run 'deploy_configs.py prune --apply' to remove", "dim"))
        print()

    status_counts: dict = {}
    for status, _, _ in healthy + unhealthy:
        status_counts[status] = status_counts.get(status, 0) + 1
    summary = ", ".join(f"{count} {status.lower()}" for status, count in sorted(status_counts.items()))
    if not summary:
        print("no applicable entries")
    elif unhealthy:
        print(paint(f"drift detected: {summary} - run deploy to fix", "red"))
    elif orphans:
        print(paint(f"{summary}; {len(orphans)} orphaned - run prune to remove", "yellow"))
    else:
        print(paint(f"all healthy: {summary}", "green"))
    return 1 if (unhealthy or orphans) else 0


def run_deploy(plan, platform_key):
    """
    Deploy every applicable manifest entry; correct deployments are no-ops.

    Output is grouped into sections ordered least interesting first, so what
    changed is still on screen when done: not applicable -> already deployed
    -> changes. Already-correct entries (classify_entry "OK" - the same check
    deploy_config no-ops on) are listed without redundant per-entry chatter;
    everything else deploys last, printing what it does as it goes.
    """
    name_width = max([len(row["name"]) for row in plan] + [4])
    info = [row for row in plan if row["action"] != "apply"]
    apply_rows = [row for row in plan if row["action"] == "apply"]
    healthy = [row for row in apply_rows if classify_entry(row["repo"], row["dest"])[0] == "OK"]
    work = [row for row in apply_rows if row not in healthy]
    counts = {"changed": 0, "noop": len(healthy), "skipped": 0}

    if info:
        detail_width = _term_width() - 18 - name_width
        print_section("Not applicable on this machine", len(info), "dim")
        for row in info:
            detail = fit_text(_info_detail(row, platform_key), detail_width)
            print("  " + status_line(row["action"].upper(), row["name"], detail, name_width))
        print()
    if healthy:
        print_section("Already deployed - nothing to do", len(healthy), "green")
        for row in healthy:
            name = paint(f"{row['name']:<{name_width}}", "green")
            print(f"  {name}  {row['dest']}")
        print()
    if work:
        print_section("Changes", len(work), "cyan")
        for row in work:
            print("  " + paint(row["name"], "bold"))
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
        "green" if not counts["skipped"] else "yellow",
    ))
    return 0


# %%
# Prune #


def build_prune_candidates(entries, platform_key, hostname, repo_root=None):
    """
    Every destination the removals files say must not exist, as sorted
    (dest, reason).

    A destination that some manifest entry still wants is never a candidate, so
    re-adding an entry silently wins over a stale removals line instead of the
    two fighting each other.
    """
    repo_root = repo_root or REPO_ROOT
    wanted = {
        row["dest"]
        for row in build_plan(entries, platform_key, hostname, repo_root)
        if row["action"] == "apply" and row["dest"]
    }
    candidates: dict = {}
    for entry in load_removals():
        if not host_allowed(entry, hostname):
            continue
        dest = resolve_dest(entry, platform_key, hostname, repo_root)
        # requires gates on the checkout existing, same as a manifest entry: a repo
        # this machine never cloned has no link to prune.
        if not dest or dest in wanted or not requires_satisfied(entry, {}, hostname, repo_root):
            continue
        candidates.setdefault(dest, f"removals:{entry['name']}")
    return sorted(candidates.items())


def classify_prune_target(dest):
    """(removable, description) for a prune candidate that exists on disk."""
    if os.path.islink(dest):
        return True, "symlink"
    if os.path.isdir(dest):
        # never rmtree: a real directory here means something other than a deployed file
        return False, "real directory - left in place"
    if os.path.isfile(dest):
        # A hard link is indistinguishable from a regular file once its source is
        # gone, so the removals list is the authority that it was ours.
        return True, "hard link / regular file"
    return False, "special file - left in place"


def run_prune(candidates, apply_changes=False):
    """
    Delete the destinations the removals files list, wherever they still exist.
    Dry run unless apply_changes: deleting files should never be a side effect of
    a normal deploy.
    """
    removed = skipped = absent = 0

    print_section(
        "Prune - removing" if apply_changes else "Prune - dry run (pass --apply to remove)",
        len(candidates),
        "cyan" if apply_changes else "yellow",
    )
    for dest, reason in candidates:
        if not os.path.lexists(dest):
            absent += 1
            continue
        removable, description = classify_prune_target(dest)
        if not removable:
            print(f"  {paint('SKIP', 'yellow')}  {dest}  ({description}; {reason})")
            skipped += 1
            continue
        if apply_changes:
            os.remove(dest)
            try:  # a skill-style dir is left empty behind its removed file
                os.rmdir(os.path.dirname(dest))
            except OSError:
                pass
            print(f"  {paint('REMOVED', 'green')}  {dest}  ({description}; {reason})")
        else:
            print(f"  {paint('WOULD REMOVE', 'yellow')}  {dest}  ({description}; {reason})")
        removed += 1
    print()

    if not candidates:
        print(paint("nothing to prune", "green"))
        return 0
    verb = "removed" if apply_changes else "would remove"
    print(paint(
        f"Prune complete: {verb} {removed}, skipped {skipped}, already absent {absent}",
        "yellow" if skipped else "green",
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
        choices=["deploy", "status", "prune"],
        default="deploy",
        help="deploy (default) creates the links; status is a read-only combined "
        "drift report + dry run (non-zero exit on drift); prune removes managed "
        "links no manifest wants any more (dry run unless --apply)",
    )
    parser.add_argument("--status", action="store_true", help="same as the status command")
    parser.add_argument("--dry-run", action="store_true", help="deprecated alias for the status command")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="prune only: actually remove the orphaned links (default is a dry run)",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="load only this manifest file, repo paths relative to the dotfiles repo root; "
        "skips overlay discovery (for testing)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    entries, manifest_paths = load_manifests(args.manifest)
    platform_key = get_platform_key()
    hostname = get_uppercase_hostname()
    print(f"platform: {platform_key}, hostname: {hostname}")
    manifests_label = os.path.basename(manifest_paths[0])
    if len(manifest_paths) > 1:
        overlays = ", ".join(os.path.basename(path) for path in manifest_paths[1:])
        manifests_label += f" + {len(manifest_paths) - 1} overlays ({overlays})"
    print(f"manifests: {manifests_label}")
    print()
    plan = build_plan(entries, platform_key, hostname)
    # --manifest is the single-file test escape hatch: it skips overlay discovery,
    # so it must skip removals discovery too or an isolated run would
    # report the real machine's orphans.
    candidates = [] if args.manifest else build_prune_candidates(entries, platform_key, hostname)
    if args.command == "prune":
        return run_prune(candidates, apply_changes=args.apply)
    if args.status or args.dry_run or args.command == "status":
        return run_status(plan, platform_key, candidates)
    return run_deploy(plan, platform_key)


if __name__ == "__main__":
    sys.exit(main())


# %%
