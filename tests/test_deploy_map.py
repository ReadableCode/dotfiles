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
    # repos files: what clone_repos.py would offer on each machine
    write_yaml(
        str(repo_root / "dotfiles_repos.yaml"),
        {
            "defaults": {"provider": "github", "org": "me"},
            "repos": [{"name": "dotfiles"}, {"name": "status_board"}],
        },
    )
    write_yaml(
        str(github / "acme_credentials" / "acme_repos.yaml"),
        {"defaults": {"provider": "github", "org": "acme"},
         "repos": [{"name": "acme-app", "hosts": ["Envy"]}, {"name": "acme-lib", "exclude_hosts": ["Tower"]},
                   {"name": "upstream-site", "dir": "local-site"}]},
    )
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


def test_matrix_cells_name_the_path_so_a_new_dest_renumbers_nothing(fleet):
    data = build(fleet)
    hosts = [host["id"] for host in data["hosts"]]
    row = data["matrix"][[entry["id"] for entry in data["entries"]].index("shared_conf")]
    assert row[hosts.index("Envy")] == [deploy_map.ACTION_CODE["apply"], "~/.conf"]
    mac_only = data["matrix"][[entry["id"] for entry in data["entries"]].index("mac_only_conf")]
    assert mac_only[hosts.index("Pi")][1] is None
    assert data["dests"] == sorted(data["dests"])


def test_host_counts_follow_the_action_order(fleet):
    data = build(fleet)
    for host in data["hosts"]:
        assert list(host["counts"]) == [action for action in deploy_map.ACTIONS if action in host["counts"]]


def test_format_json_keeps_short_containers_on_one_line(monkeypatch):
    monkeypatch.setattr(deploy_map, "JSON_LINE_WIDTH", 40)
    data = {"repos": [{"name": "a", "hosts": []}, {"name": "b", "hosts": ["x"]}], "long": ["y" * 30, "z" * 30]}
    text = deploy_map.format_json(data)
    assert json.loads(text) == data
    assert text.splitlines() == [
        "{",
        ' "repos": [',
        '  {"name": "a", "hosts": []},',
        '  {"name": "b", "hosts": ["x"]}',
        " ],",
        ' "long": [',
        f'  "{"y" * 30}",',
        f'  "{"z" * 30}"',
        " ]",
        "}",
    ]


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
    assert all(os.path.dirname(path).endswith(os.path.join("personal_credentials", "generated")) for path in paths)

    with open(paths[0], "r", encoding="utf-8") as file_handle:
        page = file_handle.read()
    assert deploy_map.DATA_PLACEHOLDER not in page
    payload = page.split('type="application/json">')[1].split("</script>")[0]
    assert "</script>" not in payload
    with open(paths[1], "r", encoding="utf-8") as file_handle:
        text = file_handle.read()
    assert json.loads(text)["meta"]["hostCount"] == 3
    # the page carries the JSON file's own line-per-record text, never one huge line
    assert payload == text.rstrip("\n").replace("</", "<\\/")
    assert max(len(line) for line in text.splitlines()) < 1000


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


# %%
# Machine view: clone set per host and requires evaluated against it #


def test_machine_view_lists_every_declared_repo_with_its_clone_state(fleet):
    data = build(fleet)
    envy = next(h for h in data["hosts"] if h["id"] == "Envy")
    tower = next(h for h in data["hosts"] if h["id"] == "Tower")

    def state(host, name):
        return next(r["state"] for r in host["repos"] if r["name"] == name)

    # 2 dotfiles + 3 acme + one implicit entry per credentials repo (acme, personal)
    assert data["meta"]["repoCount"] == len(envy["repos"]) == 7
    assert envy["contexts"] == ["dotfiles", "acme"]
    assert state(envy, "personal_credentials") == "other_context"  # Envy is in acme's inventory here, not personal's
    assert state(envy, "acme_credentials") == "credentials"
    assert state(envy, "acme-app") == "cloned"          # hosts allow list names it
    assert state(tower, "acme-app") == "not_listed"     # and not Tower
    assert state(tower, "acme-lib") == "excluded"       # exclude_hosts wins
    assert state(envy, "local-site") == "cloned"        # the checkout dir, not the upstream name
    assert state(envy, "status_board") == "cloned"      # dotfiles' own repos file applies everywhere


def test_machine_view_reports_requires_the_clone_set_cannot_meet(fleet):
    data = build(fleet)
    envy = next(h for h in data["hosts"] if h["id"] == "Envy")
    pi = next(h for h in data["hosts"] if h["id"] == "Pi")
    # acme_env requires {repo_parent}/acme-app: cloned on Envy, never offered to Pi
    assert "acme_env" not in envy["reqMissing"]
    assert pi["reqMissing"] == {"acme_env": ["acme-app"]}


def test_a_host_joins_extra_contexts_through_its_inventory_record(fleet):
    hosts_path = str(fleet / "acme_credentials" / "acme_hosts.json")
    with open(hosts_path, "r", encoding="utf-8") as file_handle:
        inventory = json.load(file_handle)
    inventory["hosts"][1]["contexts"] = ["bravo"]  # Pi also holds bravo's credentials repo by hand
    write_json(hosts_path, inventory)
    write_yaml(str(fleet / "bravo_credentials" / "bravo_repos.yaml"),
               {"defaults": {"provider": "github", "org": "bravo"}, "repos": [{"name": "bravo-tool"}]})
    data = build(fleet)
    pi = next(h for h in data["hosts"] if h["id"] == "Pi")
    envy = next(h for h in data["hosts"] if h["id"] == "Envy")
    assert "bravo" in pi["contexts"] and "bravo" not in envy["contexts"]
    assert next(r["state"] for r in pi["repos"] if r["name"] == "bravo-tool") == "cloned"
    assert next(r["state"] for r in envy["repos"] if r["name"] == "bravo-tool") == "other_context"


def test_an_overlay_entry_only_applies_where_its_repo_is_cloned(fleet):
    # acme_dev opts in with its own manifest and is offered to Envy only; its
    # hosts-less entry must not show up on Pi or Tower even though this machine
    # (which draws the map) has the manifest loaded
    write_yaml(str(fleet / "acme_credentials" / "acme_repos.yaml"),
               {"defaults": {"provider": "github", "org": "acme"}, "repos": [{"name": "acme_dev", "hosts": ["Envy"]}]})
    touch(str(fleet / "acme_dev" / "tool.md"))
    write_yaml(
        str(fleet / "acme_dev" / "acme_dev_manifest.yaml"),
        [{
            "name": "acme_tool",
            "repo": "tool.md",
            "dest": {"darwin": "~/.tool", "linux": "~/.tool", "windows": "~/.tool"},
        }],
    )
    data = build(fleet)
    tool = next(e for e in data["entries"] if e["id"] == "acme_tool")
    assert tool["hosts"] == ["Envy"]

    def code(host_id):
        row = data["matrix"][data["entries"].index(tool)]
        column = next(i for i, h in enumerate(data["hosts"]) if h["id"] == host_id)
        return data["meta"]["actions"][row[column][0]]

    assert code("Envy") == "apply"
    assert code("Pi") == "skip_overlay" and code("Tower") == "skip_overlay"
    # the credentials repo's own entries still reach every machine in its inventory
    shared = next(e for e in data["entries"] if e["id"] == "acme_env")
    assert shared["hosts"] == ["Envy", "Pi", "Tower"]
