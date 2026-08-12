# %%
# Imports #

import json
import os
import re

import config_test_utils  # noqa F401
import pytest
import yaml
from src import deploy_configs, deploy_map

# %%
# Helpers #


def write_yaml(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        yaml.safe_dump(payload, file_handle)
    return path


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle)
    return path


def touch(path, content="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        file_handle.write(content)
    return path


@pytest.fixture
def fleet(tmp_path, monkeypatch):
    """
    A fake ~/GitHub: a dotfiles checkout plus acme_credentials (one manifest,
    one inventory of three machines) and personal_credentials (the output repo).
    """
    home = tmp_path / "home"
    github = home / "GitHub"
    repo_root = github / "dotfiles"
    os.makedirs(str(repo_root))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for module in (deploy_configs, deploy_map):
        monkeypatch.setattr(module, "REPO_ROOT", str(repo_root), raising=False)
        monkeypatch.setattr(module, "grandparent_dir", str(github), raising=False)

    touch(str(repo_root / "application_configs" / "app" / "conf"))
    touch(str(repo_root / "application_configs" / "app" / "hostonly.envy.conf"))
    write_yaml(
        str(repo_root / "deploy_manifest.yaml"),
        [
            {
                "name": "shared_conf",
                "repo": "application_configs/app/conf",
                "dest": {"darwin": "~/.conf", "linux": "~/.conf", "windows": "~/AppData/conf"},
            },
            {
                "name": "mac_only_conf",
                "repo": "application_configs/app/conf",
                "dest": {"darwin": "~/Library/conf"},
            },
            {
                "name": "host_variant_conf",
                "repo": "application_configs/app/hostonly.conf",
                "dest": {"darwin": "~/.hostonly", "linux": "~/.hostonly"},
            },
            {"name": "by_hand", "repo": "application_configs/app/conf", "method": "none", "note": "manual"},
        ],
    )
    touch(str(github / "acme_credentials" / "configs" / "acme.env"))
    write_yaml(
        str(github / "acme_credentials" / "acme_manifest.yaml"),
        [
            {
                "name": "acme_env",
                "repo": "configs/acme.env",
                # requires a checkout this machine does NOT have
                "requires": "{repo_parent}/acme-app",
                "dest": {
                    "darwin": "{repo_parent}/acme-app/.env",
                    "linux": "{repo_parent}/acme-app/.env",
                    "windows": "{repo_parent}/acme-app/.env",
                },
            },
            {
                "name": "acme_workspace",
                "repo": "configs/acme.env",
                "hosts": ["ENVY"],
                "dest": {"darwin": "{repo_parent}/{host}-acme.code-workspace"},
            },
        ],
    )
    write_json(
        str(github / "acme_credentials" / "acme_hosts.json"),
        {
            "hosts": [
                {"name": "Envy", "os": "darwin", "groups": ["workstations"]},
                {"name": "Pi", "os": "linux", "groups": ["pis"]},
                {"name": "Tower", "os": "windows", "groups": ["desktops"]},
                {"name": "Doorbell", "os": "other"},
            ]
        },
    )
    os.makedirs(str(github / "personal_credentials"))
    return github


def build(fleet_root):
    entries, _ = deploy_configs.load_manifests()
    return deploy_map.build_map_data(
        entries,
        repo_root=os.path.join(str(fleet_root), "dotfiles"),
        credentials_root=str(fleet_root),
    )


# %%
# Path shaping #


def test_portable_path_folds_home_and_separators(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert deploy_map.portable_path(os.path.join(str(tmp_path), "GitHub", "repo", ".env")) == "~/GitHub/repo/.env"
    assert deploy_map.portable_path("C:\\Program Files\\app.exe") == "C:/Program Files/app.exe"
    assert deploy_map.portable_path(None) is None


def test_dest_zone_groups_home_dotfiles_and_checkouts():
    assert deploy_map.dest_zone("~/.zshrc", "~/GitHub") == "~"
    assert deploy_map.dest_zone("~/.claude/settings.json", "~/GitHub") == "~/.claude"
    assert deploy_map.dest_zone("~/GitHub/repo/.env", "~/GitHub") == "~/GitHub/repo"
    # a file dropped straight into the repo parent stays in the parent's own bucket
    assert deploy_map.dest_zone("~/GitHub/envy.code-workspace", "~/GitHub") == "~/GitHub"


def test_categorize_buckets_by_destination():
    assert deploy_map.categorize("~/GitHub/repo/.env", "symlink") == "secrets"
    assert deploy_map.categorize("~/.claude/settings.json", "symlink") == "ai"
    assert deploy_map.categorize("~/.ssh/config.d/x.conf", "symlink") == "ssh"
    assert deploy_map.categorize("~/.zshrc", "symlink") == "shell"
    # method: none entries never land anywhere, whatever their dest block says
    assert deploy_map.categorize("~/.zshrc", "none") == "manual"


# %%
# Contexts #


def test_map_context_names_the_owning_repo(tmp_path):
    repo_root = str(tmp_path / "dotfiles")
    overlays = [str(tmp_path / "acme_credentials"), str(tmp_path / "acme_dev")]
    assert deploy_map.map_context(repo_root, repo_root, overlays) == "dotfiles"
    assert deploy_map.map_context(overlays[0], repo_root, overlays) == "acme"
    # an opt-in overlay gated by a narrower clone still belongs to its context
    assert deploy_map.map_context(overlays[1], repo_root, overlays) == "acme"


def test_map_context_keeps_standalone_overlay_separate(tmp_path):
    repo_root = str(tmp_path / "dotfiles")
    overlays = [str(tmp_path / "acme_dev")]
    # without the acme credentials repo there is no context to fold into
    assert deploy_map.map_context(overlays[0], repo_root, overlays) == "acme_dev"


def test_contexts_are_ordered_and_coloured_stably(fleet):
    data = build(fleet)
    assert [context["key"] for context in data["contexts"]] == ["dotfiles", "acme"]
    assert data["contexts"][0]["color"] == deploy_map.PALETTE[0]
    assert data["contexts"][1]["color"] == deploy_map.PALETTE[1]


# %%
# Dataset #


def test_build_map_data_counts_machines_and_links(fleet):
    data = build(fleet)
    assert data["meta"]["hostCount"] == 3
    assert [host["id"] for host in data["hosts"]] == ["Envy", "Pi", "Tower"]
    # the non-deploy device is reported, not planned for
    assert [device["name"] for device in data["meta"]["nonTargets"]] == ["Doorbell"]
    assert data["meta"]["entryCount"] == 6


def test_rows_carry_the_reason_an_entry_is_absent(fleet):
    data = build(fleet)
    codes = {entry["id"]: entry for entry in data["entries"]}
    hosts = [host["id"] for host in data["hosts"]]
    cell = lambda name, host: deploy_map.ACTIONS[  # noqa: E731 - table lookup reads better inline
        data["matrix"][data["entries"].index(codes[name])][hosts.index(host)][0]
    ]
    assert cell("shared_conf", "Envy") == "apply"
    assert cell("mac_only_conf", "Pi") == "skip_platform"
    assert cell("acme_workspace", "Pi") == "skip_host"
    # only ENVY has a matching <base>.<host>.<ext> variant of this one
    assert cell("host_variant_conf", "Envy") == "apply"
    assert cell("host_variant_conf", "Pi") == "skip_variant"
    assert cell("by_hand", "Envy") == "none"


def test_requires_is_assumed_so_the_map_is_machine_independent(fleet):
    """The acme-app checkout does not exist here, but the map still draws its link."""
    entries, _ = deploy_configs.load_manifests()
    plan = deploy_configs.build_plan(entries, "darwin", "Envy", os.path.join(str(fleet), "dotfiles"))
    assert {row["name"]: row["action"] for row in plan}["acme_env"] == "skip_requires"

    data = build(fleet)
    entry = next(entry for entry in data["entries"] if entry["id"] == "acme_env")
    assert entry["hosts"] == ["Envy", "Pi", "Tower"]


def test_destinations_are_home_relative(fleet):
    data = build(fleet)
    assert all(dest.startswith("~") for dest in data["dests"]), data["dests"]
    entry = next(entry for entry in data["entries"] if entry["id"] == "acme_workspace")
    # {host} still expands per machine
    assert entry["dests"] == ["~/GitHub/envy-acme.code-workspace"]


def test_paths_view_lists_every_machine_a_file_lands_on(fleet):
    data = build(fleet)
    entries = data["paths"]["~"]
    shared = next(item for item in entries if item["entry"] == "shared_conf")
    assert shared["path"] == "~/.conf"
    assert shared["hosts"] == ["Envy", "Pi"]


def test_build_map_data_is_deterministic(fleet):
    first = json.dumps(build(fleet), sort_keys=False)
    second = json.dumps(build(fleet), sort_keys=False)
    assert first == second
    # nothing machine- or clock-specific leaks into the committed artifact
    assert "stamp" not in first and "generated" not in first


# %%
# Output #


def test_find_output_dir_requires_the_personal_credentials_repo(fleet, tmp_path):
    assert deploy_map.find_output_dir(str(fleet)) == os.path.join(str(fleet), "personal_credentials")
    empty = tmp_path / "elsewhere"
    os.makedirs(str(empty / "acme_credentials"))
    assert deploy_map.find_output_dir(str(empty)) is None


def test_write_map_emits_a_self_contained_page_and_diffable_json(fleet):
    template = touch(
        str(fleet / "dotfiles" / "templates" / "deploy_map.html"),
        '<script id="data" type="application/json">__DATA__</script>',
    )
    entries, _ = deploy_configs.load_manifests()
    paths = deploy_map.write_map(
        entries,
        repo_root=os.path.join(str(fleet), "dotfiles"),
        credentials_root=str(fleet),
        template_path=template,
        hostname="ENVY.LOCAL",
    )
    assert [os.path.basename(path) for path in paths] == ["deploy_map.html", "deploy_map.json"]
    assert all(os.path.dirname(path).endswith("personal_credentials") for path in paths)

    with open(paths[0], "r", encoding="utf-8") as file_handle:
        page = file_handle.read()
    assert deploy_map.DATA_PLACEHOLDER not in page
    assert "</script>" not in page.split('type="application/json">')[1].split("</script>")[0]
    with open(paths[1], "r", encoding="utf-8") as file_handle:
        assert json.load(file_handle)["meta"]["hostCount"] == 3


def test_write_map_skips_machines_without_the_personal_repo(fleet):
    os.rmdir(str(fleet / "personal_credentials"))
    entries, _ = deploy_configs.load_manifests()
    assert deploy_map.write_map(entries, credentials_root=str(fleet), hostname="envy") == []


def test_write_map_only_runs_on_the_map_host(fleet):
    """
    Any other machine writing the map dirties the personal credentials checkout
    and blocks its next pull, so everywhere but MAP_HOST skips before touching
    the output repo - even when that repo is cloned.
    """
    entries, _ = deploy_configs.load_manifests()
    assert deploy_map.write_map(entries, credentials_root=str(fleet), hostname="ULTRAPOCKET") is None
    assert not os.listdir(str(fleet / "personal_credentials"))


def test_shipped_template_names_no_context():
    """
    The page must learn every context from the dataset it is handed.

    A literal ``CTX.<key>`` lookup would both break on any machine whose repos
    differ and put a context name in this public repo; it silently emptied the
    matrix and destinations views once already.
    """
    with open(deploy_map.TEMPLATE_PATH, "r", encoding="utf-8") as file_handle:
        template = file_handle.read()
    assert deploy_map.DATA_PLACEHOLDER in template
    assert re.search(r"CTX\.[A-Za-z_]", template) is None
    assert re.search(r"CTX\[\s*['\"]", template) is None


def test_render_map_html_rejects_a_template_without_the_placeholder(fleet):
    template = touch(str(fleet / "dotfiles" / "templates" / "empty.html"), "<html></html>")
    with pytest.raises(ValueError):
        deploy_map.render_map_html({}, template)


# %%
