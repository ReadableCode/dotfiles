# %%
# Imports #

import glob
import json
import os

# %%
# Variables #

CREDENTIALS_SUFFIX = "_credentials"

# %%
# Functions #


def find_credentials_dirs(credentials_root):
    """
    Return every sibling credentials repo under credentials_root: directories
    named ``<context>_credentials`` (e.g. ``personal_credentials``,
    ``acme_credentials``). Sorted for determinism.
    """
    pattern = os.path.join(glob.escape(credentials_root), f"*{CREDENTIALS_SUFFIX}")
    return [path for path in sorted(glob.glob(pattern)) if os.path.isdir(path)]


def credentials_context(credentials_dir):
    """Context token of a credentials repo: its directory name minus the ``_credentials`` suffix."""
    return os.path.basename(os.path.normpath(credentials_dir))[: -len(CREDENTIALS_SUFFIX)]


def overlay_context(overlay_dir):
    """
    Context token of any overlay repo: a ``*_credentials`` repo drops the
    suffix (``acme_credentials`` -> ``acme``), any other repo is its own
    directory name (``acme_dev`` -> ``acme_dev``).
    """
    name = os.path.basename(os.path.normpath(overlay_dir))
    return name[: -len(CREDENTIALS_SUFFIX)] if name.endswith(CREDENTIALS_SUFFIX) else name


def find_overlay_dirs(overlay_root):
    """
    Return every sibling repo that may contribute deploy overlays: all the
    ``*_credentials`` repos, plus any other sibling that opts in by declaring a
    ``<dirname>_manifest.yaml``, ``<dirname>_removals.yaml``,
    ``<dirname>_repos.yaml`` or ``<dirname>_mcp_servers.yaml`` at its root.

    The opt-in form exists so an overlay can live in a repo that is NOT cloned
    everywhere its credentials repo is. A credentials repo travels to the
    machines that need that context's secrets; an overlay carrying config which
    must NOT reach those machines has to be gated by a different clone, and the
    only reliable gate is the repo it lives in. Sorted for determinism.
    """
    dirs = list(find_credentials_dirs(overlay_root))
    seen = set(dirs)
    for path in sorted(glob.glob(os.path.join(glob.escape(overlay_root), "*"))):
        if path in seen or not os.path.isdir(path):
            continue
        context = overlay_context(path)
        if any(
            os.path.exists(os.path.join(path, f"{context}_{kind}.yaml"))
            for kind in ("manifest", "removals", "repos", "mcp_servers")
        ):
            dirs.append(path)
            seen.add(path)
    return sorted(dirs)


def find_inventory_paths(credentials_root):
    """
    Locate the host inventory file of every ``*_credentials`` repo under
    credentials_root. Each repo may declare ``<context>_hosts.json``; repos
    without one contribute nothing.
    """
    paths = []
    for credentials_dir in find_credentials_dirs(credentials_root):
        context = credentials_context(credentials_dir)
        path = os.path.join(credentials_dir, f"{context}_hosts.json")
        if os.path.exists(path):
            paths.append(path)
    return paths


def load_inventory_hostnames(inventory_path):
    """
    Parse one hosts.json-style inventory and return the set of uppercase short
    hostnames it declares.

    Each entry's "name" contributes its first dot-separated token, uppercased,
    matching how deploy_configs compares manifest hosts entries.
    """
    with open(inventory_path, "r", encoding="utf-8") as file_handle:
        inventory = json.load(file_handle)
    return {
        str(host["name"]).split(".")[0].upper()
        for host in inventory.get("hosts", [])
    }


def load_union_inventory_hostnames(credentials_root):
    """
    Union of hostnames across every ``*_credentials`` inventory under
    credentials_root. Returns ``(hostnames, inventory_paths)``; an empty path
    list means no credentials repo on this machine declares an inventory.
    """
    inventory_paths = find_inventory_paths(credentials_root)
    hostnames: set = set()
    for path in inventory_paths:
        hostnames |= load_inventory_hostnames(path)
    return hostnames, inventory_paths


def find_host_record(hostname, credentials_root):
    """
    The inventory record for hostname: ``(context, record)`` from the first
    ``*_credentials`` inventory under credentials_root that lists it (short
    name, case-insensitive), or ``(None, None)`` when none does.
    """
    short = str(hostname).split(".")[0].upper()
    for path in find_inventory_paths(credentials_root):
        with open(path, "r", encoding="utf-8") as file_handle:
            inventory = json.load(file_handle)
        for host in inventory.get("hosts", []):
            if str(host["name"]).split(".")[0].upper() == short:
                return credentials_context(os.path.dirname(path)), host
    return None, None


def record_contexts(context, record):
    """
    The contexts a machine is in, read from its inventory record alone: the
    context whose inventory lists it plus any it names under ``contexts`` (a
    dev box that also works in a client's context). This is the single
    membership declaration - the deploy loads a context's overlays, the clone
    offers its repos and the map draws them on a machine only when its record
    says so. A checkout that sits on a box for another reason (the git hub of
    a credentials repo) does not make that box a member.
    """
    ordered = []
    for found in [context] + [str(extra) for extra in (record or {}).get("contexts") or []]:
        if found not in ordered:
            ordered.append(found)
    return ordered


def host_member_contexts(hostname, credentials_root):
    """
    record_contexts for hostname, or ``None`` when no inventory under
    credentials_root lists it: nothing to gate on, so every cloned overlay
    loads there.
    """
    context, record = find_host_record(hostname, credentials_root)
    return None if context is None else record_contexts(context, record)


# %%
