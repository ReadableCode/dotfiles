# %%
# Imports #

import argparse
import os
import subprocess
import sys

import yaml
from config import grandparent_dir
from readable_utils.host_tools import get_uppercase_hostname
from utils.inventory_tools import (
    find_overlay_dirs,
    load_union_inventory_hostnames,
    overlay_context,
)

# %%
# Variables #

# Where clones land: the directory holding dotfiles and its siblings (gitDir).
GIT_DIR = grandparent_dir

# provider token in <context>_repos.yaml -> ssh clone-URL host
PROVIDER_HOSTS = {
    "github": "github.com",
    "bitbucket": "bitbucket.org",
}

# %%
# Output formatting #

_COLOR_CODES = {
    "green": "32",
    "red": "31",
    "yellow": "33",
    "cyan": "36",
    "dim": "2",
}


def use_color():
    """Color when writing to a real terminal and NO_COLOR is not set."""
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def paint(text, color):
    if not use_color() or color not in _COLOR_CODES:
        return text
    return f"\033[{_COLOR_CODES[color]}m{text}\033[0m"


# %%
# Config discovery #


def discover_repo_configs():
    """
    Locate every ``<context>_repos.yaml`` at the root of a sibling overlay repo
    (every ``*_credentials`` repo plus opt-in siblings - the same discovery
    deploy_configs uses for manifests). These files are read in place and are
    never themselves deployed anywhere. Returns (config_path, context) pairs,
    sorted for determinism.
    """
    configs = []
    for overlay_dir in find_overlay_dirs(GIT_DIR):
        context = overlay_context(overlay_dir)
        path = os.path.join(overlay_dir, f"{context}_repos.yaml")
        if os.path.exists(path):
            configs.append((path, context))
    return configs


def load_repo_entries():
    """
    Load and validate every discovered repos config. A file's optional
    ``defaults`` mapping is merged under every entry (entry keys win), so
    provider/org/ssh_key need not repeat per repo. Each entry is stamped with
    ``_context`` and ``_config`` (for messages). Entry names must be unique
    across all loaded configs - two contexts claiming the same directory under
    gitDir is a mistake worth failing loudly on.
    """
    entries = []
    seen_names = {}
    for path, context in discover_repo_configs():
        with open(path, "r", encoding="utf-8") as file_handle:
            data = yaml.safe_load(file_handle) or {}
        defaults = data.get("defaults") or {}
        for entry in data.get("repos") or []:
            if isinstance(entry, dict):
                entry = {**defaults, **entry}
            validate_entry(entry, path)
            name = entry["name"]
            if name in seen_names:
                raise ValueError(
                    f"Repo '{name}' is declared by both {seen_names[name]} and {path}; "
                    "each clone directory must belong to exactly one context."
                )
            seen_names[name] = path
            entry["_context"] = context
            entry["_config"] = path
            entries.append(entry)
    validate_entry_hosts(entries)
    return entries


def validate_entry(entry, path):
    if not isinstance(entry, dict) or not entry.get("name"):
        raise ValueError(f"Repos entry without a name in {path}: {entry}")
    name = entry["name"]
    provider = entry.get("provider")
    if provider not in PROVIDER_HOSTS:
        raise ValueError(
            f"Repos entry '{name}' in {path} has provider '{provider}' "
            f"(must be one of: {', '.join(sorted(PROVIDER_HOSTS))})"
        )
    if not entry.get("org"):
        raise ValueError(f"Repos entry '{name}' in {path} is missing 'org' (the {provider} org/user)")
    hosts = entry.get("hosts")
    if hosts is not None and (not isinstance(hosts, list) or not all(isinstance(h, str) for h in hosts)):
        raise ValueError(f"Repos entry '{name}' in {path} has an invalid hosts filter (must be a list of names)")


def validate_entry_hosts(entries):
    """
    Same contract as deploy_configs.validate_manifest_hosts: any ``hosts``
    filter must name machines that exist in the union of the sibling
    ``*_credentials`` host inventories, so typos fail loudly. Machines with no
    inventories at all skip the check.
    """
    known_hosts, inventory_paths = load_union_inventory_hostnames(GIT_DIR)
    if not inventory_paths:
        return
    unknown = [
        f"{entry['name']}: {host}"
        for entry in entries
        for host in entry.get("hosts") or []
        if str(host).split(".")[0].upper() not in known_hosts
    ]
    if unknown:
        raise ValueError(
            f"Repos hosts not found in inventories {', '.join(inventory_paths)} "
            f"(fix the config or add the machine to the inventory): {', '.join(unknown)}"
        )


# %%
# Clone logic #


def entry_matches_host(entry, hostname):
    hosts = entry.get("hosts")
    if not hosts:
        return True
    short = hostname.split(".")[0].upper()
    return any(str(host).split(".")[0].upper() == short for host in hosts)


def clone_url(entry):
    return f"git@{PROVIDER_HOSTS[entry['provider']]}:{entry['org']}/{entry['name']}.git"


def clone_dest(entry):
    return os.path.join(GIT_DIR, entry.get("dir") or entry["name"])


def ssh_command(entry):
    """The ssh invocation for this repo's key, or None to use the default key/agent."""
    key = entry.get("ssh_key")
    if not key:
        return None
    return f"ssh -i {key} -o IdentitiesOnly=yes"


def clone_repo(entry):
    """Clone one repo, then pin its key and identity in local git config (matching how existing clones are set up)."""
    url = clone_url(entry)
    dest = clone_dest(entry)
    env = dict(os.environ)
    ssh = ssh_command(entry)
    if ssh:
        env["GIT_SSH_COMMAND"] = ssh
    result = subprocess.run(["git", "clone", url, dest], env=env)
    if result.returncode != 0:
        return False
    if ssh:
        subprocess.run(["git", "-C", dest, "config", "core.sshCommand", ssh], check=True)
    if entry.get("git_user_name"):
        subprocess.run(["git", "-C", dest, "config", "user.name", entry["git_user_name"]], check=True)
    if entry.get("git_user_email"):
        subprocess.run(["git", "-C", dest, "config", "user.email", entry["git_user_email"]], check=True)
    return True


def describe(entry):
    key = entry.get("ssh_key") or "default ssh key"
    return f"{entry['provider']}:{entry['org']}/{entry['name']} ({entry['_context']}, {key})"


def prompt_yes_no_quit(question):
    """Return 'y', 'n' or 'q'. EOF or a plain Enter means no."""
    try:
        answer = input(f"{question} [y/N/q] ").strip().lower()
    except EOFError:
        return "q"
    if answer in ("y", "yes"):
        return "y"
    if answer in ("q", "quit"):
        return "q"
    return "n"


def run(list_only=False, assume_yes=False):
    hostname = get_uppercase_hostname()
    entries = load_repo_entries()
    if not entries:
        print(paint("No <context>_repos.yaml found in any sibling overlay repo; nothing to clone.", "dim"))
        return 0

    missing = []
    for entry in entries:
        if not entry_matches_host(entry, hostname):
            continue
        dest = clone_dest(entry)
        if os.path.isdir(dest):
            continue
        missing.append(entry)

    if not missing:
        print(paint(f"All {len(entries)} configured repos for this host are already cloned.", "green"))
        return 0

    print(paint(f"Repos configured for this host but not cloned under {GIT_DIR}:", "cyan"))
    for entry in missing:
        print(f"  {describe(entry)}")
    if list_only:
        return 0
    if not assume_yes and not sys.stdin.isatty():
        print(paint("stdin is not a terminal; skipping clone prompts (run src/clone_repos.py directly).", "yellow"))
        return 0

    failures = 0
    for entry in missing:
        if assume_yes:
            answer = "y"
        else:
            answer = prompt_yes_no_quit(f"Clone {describe(entry)} into {clone_dest(entry)}?")
        if answer == "q":
            print(paint("Stopping; remaining repos left uncloned.", "dim"))
            break
        if answer == "n":
            print(paint(f"  skipped {entry['name']}", "dim"))
            continue
        if clone_repo(entry):
            print(paint(f"  cloned {entry['name']}", "green"))
        else:
            failures += 1
            print(paint(f"  FAILED to clone {entry['name']} (see git output above)", "red"))
    return 1 if failures else 0


# %%
# Main #


def main():
    parser = argparse.ArgumentParser(
        description="Offer to clone repos declared in sibling <context>_repos.yaml configs into gitDir."
    )
    parser.add_argument("--list", action="store_true", help="only report which configured repos are missing")
    parser.add_argument("--yes", action="store_true", help="clone every missing repo without prompting")
    args = parser.parse_args()
    return run(list_only=args.list, assume_yes=args.yes)


if __name__ == "__main__":
    sys.exit(main())

# %%
