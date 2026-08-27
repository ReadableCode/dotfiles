# %%
# Imports #

import argparse
import json
import os
import sys

from config import grandparent_dir, parent_dir, templates_dir
from readable_utils.host_tools import get_uppercase_hostname
from utils.inventory_tools import (
    CREDENTIALS_SUFFIX,
    find_credentials_dirs,
    find_inventory_paths,
    find_overlay_dirs,
    overlay_context,
)

# %%
# Variables #

REPO_ROOT = parent_dir

# The map is a picture of every machine, so it never belongs in a client repo;
# it is written to the personal credentials repo (and only when that repo is
# cloned here), where Jason commits it by hand.
OUTPUT_REPO = f"personal{CREDENTIALS_SUFFIX}"
# Only one machine may regenerate the map: every other clone of the personal
# credentials repo writing these files leaves that checkout dirty, and the next
# gitpullall aborts on the uncommitted deploy_map.{html,json}.
MAP_HOST = "envy"
OUTPUT_BASENAME = "deploy_map"
TEMPLATE_PATH = os.path.join(templates_dir, "deploy_map.html")
DATA_PLACEHOLDER = "__DATA__"

# Only these platforms have manifest dest blocks; everything else in the
# inventories (phones, TVs, switches, routers) receives no configs at all.
DEPLOY_PLATFORMS = ("darwin", "linux", "windows")
PLATFORM_ALIASES = {"macos": "darwin", "mac": "darwin", "osx": "darwin"}
PLATFORM_ORDER = {name: index for index, name in enumerate(DEPLOY_PLATFORMS)}

# The dotfiles repo itself is always the first (shared) cluster; every other
# context takes the next palette slot in alphabetical order, so the colors of a
# generated map are stable across machines and across runs.
SHARED_CONTEXT = "dotfiles"
PALETTE = [
    "#5b9dff",  # dotfiles / shared
    "#f5b13d",
    "#a78bfa",
    "#2ad4b4",
    "#ff8fa3",
    "#7ee787",
    "#ffd166",
    "#8be9fd",
]

DISK_AREAS = [
    ("home", "HOME", "shell · editors · ssh"),
    ("user_claude", "~/.claude", "user-level claude config"),
    ("repo_claude", "IN A CHECKOUT · CLAUDE", "CLAUDE.md · settings.local · mcp"),
    ("repo_secrets", "IN A CHECKOUT · SECRETS", ".env · configuration"),
    ("repo_other", "IN A CHECKOUT · OTHER", "workspaces · git excludes"),
]

# The disk map answers "where does this file come from", so it keeps {host}
# symbolic: one ~/GitHub/{host}.code-workspace beats the same file drawn once
# per machine.
HOST_PLACEHOLDER = "{host}"

ACTIONS = ["apply", "none", "skip_host", "skip_platform", "skip_variant", "skip_requires"]
ACTION_CODE = {name: index for index, name in enumerate(ACTIONS)}

CATEGORY_LABELS = {
    "ai": "claude / ai",
    "secrets": ".env / secrets",
    "editor": "editors",
    "shell": "shell",
    "ssh": "ssh",
    "git": "git",
    "automation": "automation",
    "manual": "manual (no link)",
    "other": "other",
}


# %%
# Path helpers #


def portable_path(path):
    """
    Rewrite an expanded destination into the form the map displays: forward
    slashes, and this machine's home directory folded back to ``~``.

    Destinations are expanded against the machine that happens to run the
    deploy, so a raw path would read ``/Users/jason/...`` on one machine and
    ``C:\\Users\\jason\\...`` on the next. Folding both back to ``~`` keeps the
    committed map a function of the manifests rather than of the machine that
    regenerated it.
    """
    if not path:
        return path
    path = path.replace("\\", "/")
    home = os.path.expanduser("~").replace("\\", "/").rstrip("/")
    if home and path.startswith(home):
        path = "~" + path[len(home):]
    return path


def categorize(dest, method):
    """Bucket a destination into a kind of config, used for color and filtering."""
    if method == "none":
        return "manual"
    dest = dest or ""
    base = dest.rsplit("/", 1)[-1]
    if "/.ssh/" in dest:
        return "ssh"
    if base.endswith(".env") or base == "configuration.json" or "providers.local" in base:
        return "secrets"
    if "/.claude" in dest or base in ("CLAUDE.md", ".mcp.json"):
        return "ai"
    if "code-workspace" in base or "/Code/User/" in dest or "/zed/" in dest or "/nvim/" in dest:
        return "editor"
    if "/.git/info/exclude" in dest or base == "ignore":
        return "git"
    if base in (".zshrc", ".zshrc.local", ".bashrc", ".bash_aliases", ".shared_aliases", ".tmux.conf"):
        return "shell"
    if base.endswith(".ahk") or "/.hammerspoon/" in dest:
        return "automation"
    return "other"


def disk_area(dest, repo_parent):
    """
    The cluster a destination sits in on the disk map: the home-directory areas
    a config can land in, and - for anything inside a checkout - what kind of
    file it is, since "every CLAUDE.md" is the question being asked there, not
    "every file in this one repo".
    """
    if not dest.startswith(repo_parent.rstrip("/") + "/"):
        return "user_claude" if dest.startswith("~/.claude") else "home"
    category = categorize(dest, "symlink")
    return {"ai": "repo_claude", "secrets": "repo_secrets"}.get(category, "repo_other")


def list_directory(path, limit=40):
    """
    A current listing of a directory the manifest links whole, so the map can
    show what actually rides along with the link (the point of linking a folder
    rather than its files one by one).
    """
    found = []
    for root, dir_names, file_names in os.walk(path):
        dir_names[:] = sorted(name for name in dir_names if name != ".git")
        for name in sorted(file_names):
            if name == ".DS_Store":
                continue
            found.append(os.path.relpath(os.path.join(root, name), path).replace("\\", "/"))
            if len(found) > limit:
                return found[:limit], True
    return found, False


def dest_zone(dest, repo_parent):
    """
    The folder a destination is grouped under in the Destinations view: the
    checkout it lands in for anything under the repo parent, the first path
    segment otherwise, and a single ``~`` bucket for dotfiles dropped straight
    into the home directory.
    """
    prefix = repo_parent.rstrip("/") + "/"
    if dest.startswith(prefix):
        rest = dest[len(prefix):]
        return repo_parent if "/" not in rest else f"{repo_parent}/{rest.split('/')[0]}"
    parts = dest.split("/")
    if len(parts) == 2:
        return parts[0]
    if len(parts) > 2:
        return "/".join(parts[:2])
    return dest


# %%
# Contexts #


def map_context(base_dir, repo_root, overlay_dirs):
    """
    The cluster an entry belongs to: ``dotfiles`` for the main manifest, and
    otherwise the overlay repo's context token.

    An opt-in overlay named ``<context>_<gate>`` (the pattern for config that
    must reach a narrower set of clones than the credentials repo itself - see
    docs/deploy_configs.md) folds into ``<context>`` whenever that credentials
    repo is also cloned here, so one context is one cluster on the map.
    """
    if os.path.normpath(base_dir) == os.path.normpath(repo_root):
        return SHARED_CONTEXT
    context = overlay_context(base_dir)
    credential_contexts = {
        overlay_context(path) for path in overlay_dirs if path.endswith(CREDENTIALS_SUFFIX)
    }
    for known in sorted(credential_contexts, key=len, reverse=True):
        if context.startswith(f"{known}_"):
            return known
    return context


def build_contexts(entries):
    """Ordered cluster metadata: dotfiles first, then every other context alphabetically."""
    seen = {}
    for entry in entries:
        seen.setdefault(entry["ctx"], {"repos": set(), "manifests": set()})
        seen[entry["ctx"]]["repos"].add(entry["repo"])
        seen[entry["ctx"]]["manifests"].add(os.path.basename(entry["manifest"]))
    order = ([SHARED_CONTEXT] if SHARED_CONTEXT in seen else []) + sorted(
        key for key in seen if key != SHARED_CONTEXT
    )
    contexts = []
    for index, key in enumerate(order):
        manifests = sorted(seen[key]["manifests"])
        contexts.append(
            {
                "key": key,
                "label": key.replace("_", " ").upper() + (" · SHARED" if key == SHARED_CONTEXT else ""),
                "color": PALETTE[index % len(PALETTE)],
                "sub": manifests[0] if len(manifests) == 1 else f"{len(manifests)} manifests",
                "repos": sorted(seen[key]["repos"]),
            }
        )
    return contexts


# %%
# Inventory #


def load_hosts(credentials_root=None):
    """
    Every machine declared by every credentials inventory, tagged with the
    platform key its manifest dest blocks use. Non-deploy devices are returned
    too, flagged, so the map can say how many were skipped.
    """
    credentials_root = credentials_root or grandparent_dir
    hosts = []
    for path in find_inventory_paths(credentials_root):
        inventory_repo = os.path.basename(os.path.dirname(path))
        with open(path, "r", encoding="utf-8") as file_handle:
            inventory = json.load(file_handle)
        for host in inventory.get("hosts", []):
            name = str(host["name"])
            os_name = str(host.get("os", "")).lower()
            platform_key = PLATFORM_ALIASES.get(os_name, os_name)
            hosts.append(
                {
                    "id": name.split(".")[0],
                    "name": name,
                    "os": platform_key,
                    "inventory": inventory_repo,
                    "groups": host.get("groups", []),
                    "deployable": platform_key in DEPLOY_PLATFORMS,
                }
            )
    hosts.sort(key=lambda host: (PLATFORM_ORDER.get(host["os"], 9), host["id"].lower()))
    return hosts


# %%
# Dataset #


def build_map_data(entries, repo_root=None, credentials_root=None):
    """
    Run the real planner once per machine and roll the results into the dataset
    the map renders.

    ``requires`` preconditions are treated as satisfied on purpose: the map is a
    picture of the whole fleet, so it must not change depending on which repos
    the machine that regenerated it happens to have cloned. Platform filters,
    ``hosts:`` filters and per-host variant files are all evaluated for real.
    """
    import deploy_configs  # imported here: deploy_configs calls back into this module

    repo_root = repo_root or REPO_ROOT
    credentials_root = credentials_root or grandparent_dir
    repo_parent = portable_path(credentials_root)
    overlay_dirs = find_overlay_dirs(credentials_root)

    mapped = _map_entries(entries, repo_root, credentials_root, overlay_dirs)
    entry_index = {entry["id"]: index for index, entry in enumerate(mapped)}

    inventory = load_hosts(credentials_root)
    hosts = [dict(host) for host in inventory if host["deployable"]]
    non_targets = [
        {"name": host["name"], "os": host["os"] or "unknown", "inventory": host["inventory"]}
        for host in inventory
        if not host["deployable"]
    ]

    dest_table: list = []
    dest_lookup: dict = {}

    def dest_id(path):
        if path is None:
            return -1
        if path not in dest_lookup:
            dest_lookup[path] = len(dest_table)
            dest_table.append(path)
        return dest_lookup[path]

    matrix = [[[ACTION_CODE["none"], -1] for _ in hosts] for _ in mapped]
    variants = [["" for _ in hosts] for _ in mapped]
    for column, host in enumerate(hosts):
        plan = deploy_configs.build_plan(
            entries, host["os"], host["name"], repo_root, assume_requires=True
        )
        for row in plan:
            index = entry_index[row["name"]]
            matrix[index][column] = [ACTION_CODE[row["action"]], dest_id(portable_path(row["dest"]))]
            variants[index][column] = os.path.basename(row["repo"])
        host["prune"] = [
            portable_path(dest)
            for dest, _, _ in deploy_configs.build_prune_candidates(
                entries, host["os"], host["name"], repo_root, assume_requires=True
            )
        ]

    _roll_up_entries(mapped, hosts, matrix, variants, dest_table)
    _roll_up_hosts(mapped, hosts, matrix, dest_table, repo_parent)
    _add_disk_view(mapped, entries, repo_root, credentials_root, repo_parent)

    return {
        "meta": {
            "repoParent": repo_parent,
            "manifests": sorted({entry["manifest"] for entry in mapped}),
            "actions": ACTIONS,
            "categories": CATEGORY_LABELS,
            "platforms": [key for key in DEPLOY_PLATFORMS if any(h["os"] == key for h in hosts)],
            "entryCount": len(mapped),
            "hostCount": len(hosts),
            "linkCount": sum(1 for row in matrix for cell in row if cell[0] == ACTION_CODE["apply"]),
            "destCount": len(dest_table),
            "nonTargets": sorted(non_targets, key=lambda device: device["name"].lower()),
        },
        "contexts": build_contexts(mapped),
        "areas": [{"key": key, "label": label, "sub": sub} for key, label, sub in DISK_AREAS],
        "hosts": hosts,
        "entries": mapped,
        "dests": dest_table,
        "matrix": matrix,
        "paths": _build_path_tree(mapped, hosts, matrix, dest_table, repo_parent),
        "disk": _build_disk_nodes(mapped, repo_parent),
    }


def _map_entries(entries, repo_root, credentials_root, overlay_dirs):
    """Static per-entry facts, ordered by context then source repo then name."""
    mapped = []
    for entry in entries:
        base_dir = entry.get("_base_dir") or repo_root
        mapped.append(
            {
                "id": entry["name"],
                "ctx": map_context(base_dir, repo_root, overlay_dirs),
                "repo": os.path.relpath(base_dir, credentials_root).replace("\\", "/"),
                "manifest": entry["_manifest"],
                "src": str(entry["repo"]).replace("\\", "/"),
                "method": entry.get("method", "symlink"),
                "note": " ".join((entry.get("note") or "").split()),
                "hostsFilter": list(entry.get("hosts") or []),
                "platforms": sorted((entry.get("dest") or {}).keys()),
                "requires": entry.get("requires"),
            }
        )
    contexts = [context["key"] for context in build_contexts(mapped)]
    mapped.sort(key=lambda entry: (contexts.index(entry["ctx"]), entry["repo"], entry["id"]))
    for entry in mapped:
        entry["manifest"] = os.path.relpath(entry["manifest"], credentials_root).replace("\\", "/")
    return mapped


def _roll_up_entries(entries, hosts, matrix, variants, dest_table):
    """Per-entry rollups: which machines it reaches, which paths, which variants."""
    for index, entry in enumerate(entries):
        cells = matrix[index]
        applied = [column for column, cell in enumerate(cells) if cell[0] == ACTION_CODE["apply"]]
        entry["hosts"] = [hosts[column]["id"] for column in applied]
        entry["dests"] = sorted({dest_table[cells[column][1]] for column in applied if cells[column][1] >= 0})
        entry["variantsUsed"] = sorted({variants[index][column] for column in applied})
        entry["cat"] = categorize(entry["dests"][0] if entry["dests"] else "", entry["method"])


def _roll_up_hosts(entries, hosts, matrix, dest_table, repo_parent):
    """Per-machine rollups: which entries land, how they are grouped, what was skipped."""
    for column, host in enumerate(hosts):
        received, counts, zones = [], {}, {}
        for index, entry in enumerate(entries):
            code, dest = matrix[index][column]
            action = ACTIONS[code]
            counts[action] = counts.get(action, 0) + 1
            if action != "apply":
                continue
            received.append(entry["id"])
            if dest >= 0:
                path = dest_table[dest]
                zones.setdefault(dest_zone(path, repo_parent), []).append([entry["id"], path])
        host["entries"] = received
        host["counts"] = counts
        host["zones"] = dict(sorted(zones.items()))


def _add_disk_view(mapped, entries, repo_root, credentials_root, repo_parent):
    """
    Per-entry facts the disk map needs: the destination *templates* (``{host}``
    left symbolic, one per platform block) and, when the source is a directory
    the manifest links whole, what is currently inside it.
    """
    import deploy_configs

    raw = {entry["name"]: entry for entry in entries}
    for entry in mapped:
        source = raw[entry["id"]]
        dest_block = source.get("dest") or {}
        templates: dict = {}
        for platform_key in sorted(dest_block):
            path = portable_path(
                deploy_configs.expand_path(dest_block[platform_key], HOST_PLACEHOLDER, repo_root)
            )
            templates.setdefault(path, []).append(platform_key)
        entry["diskDests"] = [
            {"path": path, "platforms": platforms, "area": disk_area(path, repo_parent)}
            for path, platforms in templates.items()
        ]

        # the file the entry actually points at, with any ../ traversal resolved:
        # two manifests in different repos can name one file (an overlay reusing a
        # dotfiles script), and on the disk map that is one source, not two
        repo_path = os.path.normpath(os.path.join(source.get("_base_dir") or repo_root, source["repo"]))
        entry["srcPath"] = os.path.relpath(repo_path, credentials_root).replace("\\", "/")
        entry["srcRepo"] = entry["srcPath"].split("/")[0]
        entry["isDir"] = os.path.isdir(repo_path)
        if entry["isDir"]:
            contents, truncated = list_directory(repo_path)
            entry["contents"] = contents
            entry["contentsTruncated"] = truncated


def _build_disk_nodes(mapped, repo_parent):
    """
    One node per destination template, carrying every entry that writes there.

    Grouped by path rather than by entry so a location with more than one owner
    reads as one place on disk, which is how it behaves.
    """
    nodes: dict = {}
    for entry in mapped:
        for dest in entry["diskDests"]:
            node = nodes.setdefault(
                dest["path"],
                {"path": dest["path"], "area": dest["area"], "zone": dest_zone(dest["path"], repo_parent),
                 "entries": [], "platforms": []},
            )
            node["entries"].append(entry["id"])
            node["platforms"] = sorted(set(node["platforms"]) | set(dest["platforms"]))
    return sorted(nodes.values(), key=lambda node: node["path"])


def _build_path_tree(entries, hosts, matrix, dest_table, repo_parent):
    """Destination-first view: zone -> every file deployed there, with its machines."""
    grouped: dict = {}
    for index, entry in enumerate(entries):
        for column, (code, dest) in enumerate(matrix[index]):
            if code != ACTION_CODE["apply"] or dest < 0:
                continue
            path = dest_table[dest]
            grouped.setdefault((dest_zone(path, repo_parent), path, entry["id"]), []).append(hosts[column]["id"])
    tree: dict = {}
    for (zone, path, entry_id), host_ids in sorted(grouped.items()):
        entry = next(item for item in entries if item["id"] == entry_id)
        tree.setdefault(zone, []).append(
            {"path": path, "entry": entry_id, "hosts": host_ids, "ctx": entry["ctx"], "cat": entry["cat"]}
        )
    # home-relative zones first, then the checkouts under the repo parent
    return dict(sorted(tree.items(), key=lambda item: (item[0].startswith(repo_parent), item[0].lower())))


# %%
# Render #


def render_map_html(data, template_path=None):
    """Inline the dataset into the template, producing one self-contained page."""
    template_path = template_path or TEMPLATE_PATH
    with open(template_path, "r", encoding="utf-8") as file_handle:
        template = file_handle.read()
    if DATA_PLACEHOLDER not in template:
        raise ValueError(f"Template {template_path} has no {DATA_PLACEHOLDER} placeholder")
    # </ inside a <script> block would close it early; \/ is the same string to JSON
    payload = json.dumps(data, separators=(",", ":"), sort_keys=False).replace("</", "<\\/")
    return template.replace(DATA_PLACEHOLDER, payload)


def find_output_dir(credentials_root=None):
    """The personal credentials repo, or None when it is not cloned on this machine."""
    credentials_root = credentials_root or grandparent_dir
    for path in find_credentials_dirs(credentials_root):
        if os.path.basename(os.path.normpath(path)) == OUTPUT_REPO:
            return path
    return None


def write_map(entries, output_dir=None, repo_root=None, credentials_root=None, template_path=None, hostname=None):
    """
    Write ``deploy_map.html`` (self-contained page) and ``deploy_map.json`` (the
    same data, diffable) into the personal credentials repo.

    Returns the paths written; ``None`` when this machine is not ``MAP_HOST``
    (only that machine may dirty the personal credentials checkout), or an
    empty list when that repo is not cloned here - a work machine holding only
    a client's credentials repo must never grow a file describing every other
    machine.
    """
    hostname = hostname or get_uppercase_hostname()
    if (hostname or "").split(".")[0].lower() != MAP_HOST:
        return None
    credentials_root = credentials_root or grandparent_dir
    output_dir = output_dir or find_output_dir(credentials_root)
    if not output_dir:
        return []
    data = build_map_data(entries, repo_root=repo_root, credentials_root=credentials_root)
    json_path = os.path.join(output_dir, f"{OUTPUT_BASENAME}.json")
    html_path = os.path.join(output_dir, f"{OUTPUT_BASENAME}.html")
    with open(json_path, "w", encoding="utf-8") as file_handle:
        file_handle.write(json.dumps(data, indent=1, sort_keys=False) + "\n")
    with open(html_path, "w", encoding="utf-8") as file_handle:
        file_handle.write(render_map_html(data, template_path))
    return [html_path, json_path]


def report_map(paths, quiet=False):
    """Print where the map went (or why it did not), matching the deploy report's voice."""
    if quiet:
        return
    if paths is None:
        print(f"map: only {MAP_HOST} regenerates the map - skipped")
        return
    if not paths:
        print(f"map: {OUTPUT_REPO} is not cloned here - skipped")
        return
    for path in paths:
        print(f"map: wrote {path}")
    print("map: commit it from that repo when the diff looks right")


# %%
# Main #


def main(argv=None):
    import deploy_configs

    parser = argparse.ArgumentParser(
        description=(
            "Regenerate the deployment map (every manifest entry, every machine) "
            f"into the {OUTPUT_REPO} repo."
        )
    )
    parser.add_argument("--output-dir", default=None, help=f"override the output directory (default: {OUTPUT_REPO})")
    args = parser.parse_args(argv)

    entries, manifest_paths = deploy_configs.load_manifests()
    print(f"manifests: {len(manifest_paths)}, entries: {len(entries)}")
    report_map(write_map(entries, output_dir=args.output_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())


# %%
