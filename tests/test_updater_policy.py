"""Unit tests for src/updater_policy.py — the per-host updater policy lookup my_updater.sh calls."""

import json
import os

import config_test_utils  # noqa F401
from src import updater_policy

# ---------------------------------------------------------------- helpers


def write_inventory(root, context, hosts, filename=None):
    """Create <root>/<context>_credentials/<context>_hosts.json holding hosts."""
    credentials_dir = os.path.join(str(root), "{}_credentials".format(context))
    os.makedirs(credentials_dir, exist_ok=True)
    path = os.path.join(credentials_dir, filename or "{}_hosts.json".format(context))
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump({"hosts": hosts}, file_handle)
    return path


def lookup(root, hostname, key):
    """The rendered value my_updater.sh would capture for this host and key."""
    host = updater_policy.find_host_entry(str(root), updater_policy.short_name(hostname))
    if host is None:
        return ""
    return updater_policy.render(updater_policy.resolve(host, key))


WORKSTATION = {
    "name": "Workstation-1",
    "aliases": ["sshwork"],
    "updater": {
        "release_ceiling": {"ubuntu": "26.04"},
        "ubuntu_prompt": "normal",
        "post_update_check": ["work-repo/scripts/check_a.sh", "work-repo/scripts/check_b.sh"],
    },
}


# ---------------------------------------------------------------- lookups


def test_dotted_key_resolves_inside_the_updater_block(tmp_path):
    write_inventory(tmp_path, "acme", [WORKSTATION])
    assert lookup(tmp_path, "Workstation-1", "release_ceiling.ubuntu") == "26.04"
    assert lookup(tmp_path, "Workstation-1", "ubuntu_prompt") == "normal"


def test_lists_render_comma_joined_for_the_shell(tmp_path):
    write_inventory(tmp_path, "acme", [WORKSTATION])
    assert lookup(tmp_path, "Workstation-1", "post_update_check") == (
        "work-repo/scripts/check_a.sh,work-repo/scripts/check_b.sh"
    )


def test_host_matches_by_alias_and_case_insensitive_short_name(tmp_path):
    write_inventory(tmp_path, "acme", [WORKSTATION])
    assert lookup(tmp_path, "WORKSTATION-1.local", "release_ceiling.ubuntu") == "26.04"
    assert lookup(tmp_path, "sshwork", "release_ceiling.ubuntu") == "26.04"


def test_unlisted_host_gets_nothing_even_when_other_hosts_are_governed(tmp_path):
    """The host-gating contract: cloning a repo must not govern machines it does not name."""
    write_inventory(tmp_path, "acme", [WORKSTATION])
    assert lookup(tmp_path, "personal-box", "release_ceiling.ubuntu") == ""


def test_host_without_updater_block_and_missing_keys_render_empty(tmp_path):
    write_inventory(tmp_path, "acme", [{"name": "plain-box"}, WORKSTATION])
    assert lookup(tmp_path, "plain-box", "release_ceiling.ubuntu") == ""
    assert lookup(tmp_path, "Workstation-1", "release_ceiling.fedora") == ""
    assert lookup(tmp_path, "Workstation-1", "no_such.key") == ""


def test_hosts_are_found_across_all_sibling_inventories(tmp_path):
    write_inventory(tmp_path, "acme", [WORKSTATION])
    write_inventory(
        tmp_path,
        "personal",
        [{"name": "home-box", "updater": {"release_ceiling": {"ubuntu": "26.04"}}}],
        filename="hosts.json",
    )
    assert lookup(tmp_path, "home-box", "release_ceiling.ubuntu") == "26.04"
    assert lookup(tmp_path, "Workstation-1", "release_ceiling.ubuntu") == "26.04"


# ---------------------------------------------------------------- cli


def test_main_prints_value_and_where_lists_inventories(tmp_path, capsys):
    inventory_path = write_inventory(tmp_path, "acme", [WORKSTATION])
    assert (
        updater_policy.main(
            ["--root", str(tmp_path), "--local-hostname", "workstation-1", "release_ceiling.ubuntu"]
        )
        == 0
    )
    assert capsys.readouterr().out.strip() == "26.04"
    assert updater_policy.main(["--root", str(tmp_path), "--where"]) == 0
    assert capsys.readouterr().out.strip() == inventory_path


def test_main_is_silent_and_zero_for_an_unlisted_host(tmp_path, capsys):
    write_inventory(tmp_path, "acme", [WORKSTATION])
    assert updater_policy.main(["--root", str(tmp_path), "--local-hostname", "nobody", "ubuntu_prompt"]) == 0
    assert capsys.readouterr().out == ""
