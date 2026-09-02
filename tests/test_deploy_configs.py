# %%
# Imports #

import glob
import json
import os
import subprocess

import config_test_utils  # noqa F401
import pytest
import yaml
from src import deploy_configs
from utils.inventory_tools import (
    find_inventory_paths,
    load_inventory_hostnames,
    load_union_inventory_hostnames,
)

# %%
# Helpers #


def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        file_handle.write(content)
    return path


def write_manifest(tmp_path, entries):
    manifest_path = os.path.join(str(tmp_path), "manifest.yaml")
    with open(manifest_path, "w", encoding="utf-8") as file_handle:
        yaml.safe_dump(entries, file_handle)
    return manifest_path


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


# %%
# Manifest parsing #


def test_load_manifest_parses_entries(tmp_path):
    manifest_path = write_manifest(
        tmp_path,
        [
            {"name": "zshrc", "repo": "application_configs/bash/.zshrc", "dest": {"darwin": "~/.zshrc"}},
            {"name": "inventory_only", "repo": "application_configs/nvim/init.lua", "method": "none", "note": "x"},
        ],
    )
    entries = deploy_configs.load_manifest(manifest_path)
    assert len(entries) == 2
    assert entries[0]["name"] == "zshrc"
    assert entries[0].get("method", "symlink") == "symlink"
    assert entries[1]["method"] == "none"


def test_load_manifest_rejects_non_list(tmp_path):
    manifest_path = write_file(os.path.join(str(tmp_path), "bad.yaml"), "name: not_a_list\n")
    with pytest.raises(ValueError):
        deploy_configs.load_manifest(manifest_path)


def test_load_manifest_rejects_missing_keys(tmp_path):
    manifest_path = write_manifest(tmp_path, [{"name": "no_repo_key"}])
    with pytest.raises(ValueError):
        deploy_configs.load_manifest(manifest_path)


def test_load_manifest_rejects_bad_method(tmp_path):
    manifest_path = write_manifest(tmp_path, [{"name": "x", "repo": "y", "method": "hardlink"}])
    with pytest.raises(ValueError):
        deploy_configs.load_manifest(manifest_path)


def test_load_manifest_rejects_bad_on_drift(tmp_path):
    manifest_path = write_manifest(tmp_path, [{"name": "x", "repo": "y", "on_drift": "merge"}])
    with pytest.raises(ValueError, match="on_drift"):
        deploy_configs.load_manifest(manifest_path)


def test_load_manifest_rejects_copy_method(tmp_path):
    # copies silently drift - there is deliberately no copy method
    manifest_path = write_manifest(tmp_path, [{"name": "x", "repo": "y", "method": "copy"}])
    with pytest.raises(ValueError):
        deploy_configs.load_manifest(manifest_path)


def test_load_manifest_rejects_invalid_requires(tmp_path):
    for bad in ("  ", [], ["~/ok", "  "], [5], {"path": "~/x"}):
        manifest_path = write_manifest(tmp_path, [{"name": "x", "repo": "y", "requires": bad}])
        with pytest.raises(ValueError, match="requires"):
            deploy_configs.load_manifest(manifest_path)


def test_load_manifest_accepts_requires_list(tmp_path):
    manifest_path = write_manifest(
        tmp_path, [{"name": "x", "repo": "y", "requires": ["{repo_parent}/a", "{repo_parent}/b"]}]
    )
    entries = deploy_configs.load_manifest(manifest_path, inventory_path=str(tmp_path / "no_inventory.json"))
    assert entries[0]["requires"] == ["{repo_parent}/a", "{repo_parent}/b"]


def test_load_manifest_rejects_hosts_missing_from_inventory(tmp_path):
    inventory_path = write_file(
        str(tmp_path / "hosts.json"),
        '{"hosts": [{"name": "Envy", "user": "jason"}]}\n',
    )
    manifest_path = write_manifest(
        tmp_path,
        [{"name": "a", "repo": "f1", "dest": {"darwin": "~/.f1"}, "hosts": ["ENVY", "NOSUCHBOX"]}],
    )
    with pytest.raises(ValueError, match="NOSUCHBOX"):
        deploy_configs.load_manifest(manifest_path, inventory_path=inventory_path)


def test_load_inventory_hostnames_uppercases_short_names(tmp_path):
    inventory_path = write_file(
        str(tmp_path / "hosts.json"),
        '{"hosts": [{"name": "Envy"}, {"name": "envy.local"}, {"name": "ACME-LAP-01"}]}\n',
    )
    hostnames = load_inventory_hostnames(inventory_path)
    assert hostnames == {"ENVY", "ACME-LAP-01"}


# %%
# Overlay manifests from sibling *_credentials repos #


def write_manifest_at(path, entries):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        yaml.safe_dump(entries, file_handle)
    return path


@pytest.fixture
def overlay_tree(tmp_path, monkeypatch):
    """Fake ~/GitHub with a dotfiles checkout and one sibling acme_credentials overlay repo."""
    github = tmp_path / "GitHub"
    repo_root = github / "dotfiles"
    os.makedirs(str(repo_root))
    monkeypatch.setattr(deploy_configs, "REPO_ROOT", str(repo_root))
    monkeypatch.setattr(deploy_configs, "grandparent_dir", str(github))
    write_manifest_at(
        str(repo_root / "deploy_manifest.yaml"),
        [{"name": "main_conf", "repo": "application_configs/app/conf", "dest": {"darwin": "~/.conf"}}],
    )
    write_manifest_at(
        str(github / "acme_credentials" / "acme_manifest.yaml"),
        [
            {
                "name": "acme_conf",
                "repo": "configs/acme.json",
                "dest": {"darwin": "{repo_parent}/some-repo/acme.json"},
            }
        ],
    )
    return github


def test_load_manifests_discovers_overlays_and_resolves_repo_against_overlay_root(overlay_tree):
    entries, manifest_paths = deploy_configs.load_manifests()
    assert [os.path.basename(path) for path in manifest_paths] == ["deploy_manifest.yaml", "acme_manifest.yaml"]
    assert [entry["name"] for entry in entries] == ["main_conf", "acme_conf"]

    plan = deploy_configs.build_plan(entries, "darwin", "ENVY")
    rows = {row["name"]: row for row in plan}
    # main entry resolves against the dotfiles root, overlay entry against ITS repo root
    assert rows["main_conf"]["repo"] == os.path.join(str(overlay_tree), "dotfiles", "application_configs",
                                                     "app", "conf")
    assert rows["acme_conf"]["repo"] == os.path.join(str(overlay_tree), "acme_credentials", "configs", "acme.json")
    # {repo_parent} still expands against the DOTFILES parent, not the overlay repo
    assert rows["acme_conf"]["dest"] == os.path.join(str(overlay_tree), "some-repo", "acme.json")


def test_load_manifests_with_explicit_manifest_skips_overlay_discovery(overlay_tree, tmp_path):
    manifest_path = write_manifest_at(
        str(tmp_path / "solo.yaml"), [{"name": "solo", "repo": "f1", "dest": {"darwin": "~/.f1"}}]
    )
    entries, manifest_paths = deploy_configs.load_manifests(manifest_path)
    assert manifest_paths == [manifest_path]
    assert [entry["name"] for entry in entries] == ["solo"]
    # repo paths of an explicit manifest resolve against the dotfiles REPO_ROOT
    plan = deploy_configs.build_plan(entries, "darwin", "ENVY")
    assert plan[0]["repo"] == os.path.join(str(overlay_tree), "dotfiles", "f1")


def test_credentials_repo_without_manifest_contributes_nothing(overlay_tree):
    os.makedirs(str(overlay_tree / "empty_credentials"))
    _, manifest_paths = deploy_configs.load_manifests()
    assert [os.path.basename(path) for path in manifest_paths] == ["deploy_manifest.yaml", "acme_manifest.yaml"]


def test_non_credentials_repo_opts_in_as_overlay_by_declaring_its_own_manifest(overlay_tree):
    # a sibling repo that is NOT *_credentials contributes an overlay named after
    # its own directory, so config it carries follows THAT clone rather than the
    # credentials clone (context token keeps the full dirname - no suffix to drop)
    write_manifest_at(
        str(overlay_tree / "acme_dev" / "acme_dev_manifest.yaml"),
        [{"name": "acme_dev_conf", "repo": "configs/dev.json", "dest": {"darwin": "~/.dev"}}],
    )
    entries, manifest_paths = deploy_configs.load_manifests()
    assert [os.path.basename(path) for path in manifest_paths] == [
        "deploy_manifest.yaml",
        "acme_manifest.yaml",
        "acme_dev_manifest.yaml",
    ]
    plan = deploy_configs.build_plan(entries, "darwin", "ENVY")
    rows = {row["name"]: row for row in plan}
    assert rows["acme_dev_conf"]["repo"] == os.path.join(str(overlay_tree), "acme_dev", "configs", "dev.json")


def test_sibling_repo_without_a_matching_manifest_name_is_not_an_overlay(overlay_tree):
    # only <dirname>_manifest.yaml opts a plain repo in; an unrelated yaml does not
    write_manifest_at(
        str(overlay_tree / "acme_dev" / "some_manifest.yaml"),
        [{"name": "ignored", "repo": "f1", "dest": {"darwin": "~/.f1"}}],
    )
    _, manifest_paths = deploy_configs.load_manifests()
    assert [os.path.basename(path) for path in manifest_paths] == ["deploy_manifest.yaml", "acme_manifest.yaml"]


def test_non_credentials_repo_can_contribute_removals(overlay_tree):
    write_manifest_at(
        str(overlay_tree / "acme_dev" / "acme_dev_removals.yaml"),
        [{"name": "dead_dev_conf", "dest": {"darwin": "~/.dev"}}],
    )
    assert [entry["name"] for entry in deploy_configs.load_removals()] == ["dead_dev_conf"]


def write_inventory_at(path, names):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump({"hosts": [{"name": name} for name in names]}, file_handle)
    return path


def test_hosts_filter_in_main_manifest_is_rejected(overlay_tree):
    # rejected even when an inventory KNOWS the name - the rule is structural:
    # other machines clone other inventories, so validation there would fail
    write_inventory_at(str(overlay_tree / "acme_credentials" / "acme_hosts.json"), ["ENVY"])
    write_manifest_at(
        str(overlay_tree / "dotfiles" / "deploy_manifest.yaml"),
        [{"name": "main_conf", "repo": "f1", "dest": {"darwin": "~/.f1"}, "hosts": ["ENVY"]}],
    )
    with pytest.raises(ValueError, match="only allowed in overlay manifests"):
        deploy_configs.load_manifests()


def test_hosts_filter_in_overlay_validates_against_the_only_inventory_present(overlay_tree):
    # the work-laptop case: ONE client repo cloned, nothing else - the
    # overlay's hosts filter validates against its own inventory
    write_inventory_at(str(overlay_tree / "acme_credentials" / "acme_hosts.json"), ["ACMEBOX"])
    write_manifest_at(
        str(overlay_tree / "acme_credentials" / "acme_manifest.yaml"),
        [{"name": "acme_conf", "repo": "configs/acme.json", "dest": {"darwin": "~/.acme"}, "hosts": ["ACMEBOX"]}],
    )
    entries, _ = deploy_configs.load_manifests()
    assert [entry["name"] for entry in entries] == ["main_conf", "acme_conf"]


def test_explicit_manifest_flag_still_allows_hosts_filters(overlay_tree, tmp_path):
    write_inventory_at(str(overlay_tree / "acme_credentials" / "acme_hosts.json"), ["ENVY"])
    manifest_path = write_manifest_at(
        str(tmp_path / "solo.yaml"),
        [{"name": "solo", "repo": "f1", "dest": {"darwin": "~/.f1"}, "hosts": ["ENVY"]}],
    )
    entries, _ = deploy_configs.load_manifests(manifest_path)
    assert [entry["name"] for entry in entries] == ["solo"]


def test_duplicate_entry_names_across_manifests_raise(overlay_tree):
    write_manifest_at(
        str(overlay_tree / "acme_credentials" / "acme_manifest.yaml"),
        [{"name": "main_conf", "repo": "configs/clash.json", "dest": {"darwin": "~/.clash"}}],
    )
    with pytest.raises(ValueError) as excinfo:
        deploy_configs.load_manifests()
    message = str(excinfo.value)
    assert "main_conf" in message
    assert "deploy_manifest.yaml" in message and "acme_manifest.yaml" in message


# %%
# Host inventory union across *_credentials repos #


def test_find_inventory_paths_prefers_prefixed_name_over_legacy_fallback(tmp_path):
    write_file(str(tmp_path / "acme_credentials" / "acme_hosts.json"), '{"hosts": [{"name": "ACMEBOX"}]}')
    write_file(str(tmp_path / "acme_credentials" / "hosts.json"), '{"hosts": [{"name": "DECOY"}]}')
    write_file(str(tmp_path / "personal_credentials" / "hosts.json"), '{"hosts": [{"name": "Envy"}]}')
    os.makedirs(str(tmp_path / "no_inventory_credentials"))
    paths = find_inventory_paths(str(tmp_path))
    assert paths == [
        os.path.join(str(tmp_path), "acme_credentials", "acme_hosts.json"),
        os.path.join(str(tmp_path), "personal_credentials", "hosts.json"),
    ]
    hostnames, inventory_paths = load_union_inventory_hostnames(str(tmp_path))
    assert hostnames == {"ACMEBOX", "ENVY"}
    assert inventory_paths == paths


def test_manifest_hosts_validate_against_union_of_inventories(overlay_tree):
    write_file(str(overlay_tree / "acme_credentials" / "acme_hosts.json"), '{"hosts": [{"name": "ACMEBOX"}]}')
    write_file(str(overlay_tree / "personal_credentials" / "hosts.json"), '{"hosts": [{"name": "Envy"}]}')
    write_manifest_at(
        str(overlay_tree / "acme_credentials" / "acme_manifest.yaml"),
        [{"name": "acme_conf", "repo": "f1", "dest": {"darwin": "~/.f1"}, "hosts": ["ENVY", "ACMEBOX"]}],
    )
    entries, _ = deploy_configs.load_manifests()  # hosts from different inventories both resolve
    assert entries[-1]["hosts"] == ["ENVY", "ACMEBOX"]

    write_manifest_at(
        str(overlay_tree / "acme_credentials" / "acme_manifest.yaml"),
        [{"name": "acme_conf", "repo": "f1", "dest": {"darwin": "~/.f1"}, "hosts": ["NOSUCHBOX"]}],
    )
    with pytest.raises(ValueError, match="NOSUCHBOX"):
        deploy_configs.load_manifests()


def test_hosts_validation_skipped_when_no_inventory_exists(overlay_tree):
    # no *_credentials repo declares an inventory -> machine without credentials repos
    write_manifest_at(
        str(overlay_tree / "acme_credentials" / "acme_manifest.yaml"),
        [{"name": "acme_conf", "repo": "f1", "dest": {"darwin": "~/.f1"}, "hosts": ["GHOSTBOX"]}],
    )
    entries, _ = deploy_configs.load_manifests()
    assert entries[-1]["hosts"] == ["GHOSTBOX"]


def test_real_manifest_hosts_all_exist_in_union_inventory():
    # host targeting must use inventory names - load_manifests enforces it
    # against the union of every *_credentials repo's inventory
    known_hosts, inventory_paths = load_union_inventory_hostnames(deploy_configs.grandparent_dir)
    if not inventory_paths:
        pytest.skip("no *_credentials host inventory present on this machine")
    entries, _ = deploy_configs.load_manifests()
    for entry in entries:
        for host in entry.get("hosts") or []:
            assert str(host).split(".")[0].upper() in known_hosts, \
                f"{entry['name']} targets unknown host {host}"


def test_real_manifests_are_valid_and_repo_paths_exist():
    # loads the real deploy_manifest.yaml plus any overlay manifests present;
    # load_manifests itself enforces name uniqueness across all of them
    entries, manifest_paths = deploy_configs.load_manifests()
    assert manifest_paths[0] == os.path.join(deploy_configs.REPO_ROOT, "deploy_manifest.yaml")
    for entry in entries:
        repo_path = os.path.join(entry["_base_dir"], entry["repo"])
        # a repo path may exist as-is, or only as <base>.<host-or-platform>.<ext> variants;
        # a `generated: true` source is produced by the deploy itself and may not exist yet
        assert entry.get("generated") or os.path.exists(repo_path) or deploy_configs._any_variant_exists(repo_path), (
            f"manifest entry {entry['name']} points at missing repo path {repo_path} (no variants either)"
        )
        if entry.get("method", "symlink") != "none":
            dests = entry.get("dest") or {}
            assert dests, f"manifest entry {entry['name']} has no dest and is not method: none"
            assert set(dests) <= {"darwin", "linux", "windows"}


# %%
# Per-repo expansion #


def write_repos_file(path, names):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        yaml.safe_dump({"defaults": {"provider": "github", "org": "acme"}, "repos": [{"name": n} for n in names]},
                       file_handle)


def per_repo_entry(**overrides):
    entry = {
        "name": "acme_repo_mcp",
        "repo": "generated/acme.mcp.json",
        "dest": {"darwin": "{repo_parent}/{context_repo}/.mcp.json", "linux": "{repo_parent}/{context_repo}/.mcp.json"},
        "per_context_repo": True,
    }
    entry.update(overrides)
    return entry


def test_per_context_repo_expands_into_one_entry_per_declared_repo(overlay_tree):
    write_repos_file(str(overlay_tree / "acme_credentials" / "acme_repos.yaml"), ["svc-a", "svc-b"])
    write_manifest_at(str(overlay_tree / "acme_credentials" / "acme_manifest.yaml"), [per_repo_entry()])

    entries, _ = deploy_configs.load_manifests()
    names = [entry["name"] for entry in entries if entry.get("_expanded_from")]

    assert names == ["acme_repo_mcp__svc-a", "acme_repo_mcp__svc-b"]
    first = next(entry for entry in entries if entry["name"] == "acme_repo_mcp__svc-a")
    assert first["dest"] == {"darwin": "{repo_parent}/svc-a/.mcp.json", "linux": "{repo_parent}/svc-a/.mcp.json"}
    # each expansion gates on its checkout existing, so an uncloned repo is a skip
    assert first["requires"] == ["{repo_parent}/svc-a"]
    assert first["_context_repo"] == "svc-a"
    assert "per_context_repo" not in first
    plan = {row["name"]: row for row in deploy_configs.build_plan(entries, "darwin", "ENVY")}
    assert plan["acme_repo_mcp__svc-a"]["action"] == "skip_requires"
    os.makedirs(str(overlay_tree / "svc-a"))
    plan = {row["name"]: row for row in deploy_configs.build_plan(entries, "darwin", "ENVY")}
    assert plan["acme_repo_mcp__svc-a"]["action"] == "apply"
    assert plan["acme_repo_mcp__svc-a"]["dest"] == os.path.join(str(overlay_tree), "svc-a", ".mcp.json")


def test_per_context_repo_can_name_other_contexts_and_add_or_drop_repos(overlay_tree):
    # an opt-in overlay (acme_dev) targeting the credentials context's repo list,
    # plus dotfiles' own list, plus a repo no list declares, minus one
    write_repos_file(str(overlay_tree / "acme_credentials" / "acme_repos.yaml"), ["svc-a", "svc-b"])
    write_repos_file(str(overlay_tree / "dotfiles" / "dotfiles_repos.yaml"), ["dotfiles", "svc-b"])
    write_manifest_at(
        str(overlay_tree / "acme_dev" / "acme_dev_manifest.yaml"),
        [per_repo_entry(per_context_repo=["acme", "dotfiles"], extra_repos=["acme_credentials"],
                        exclude_repos=["svc-b"], requires="{repo_parent}/acme_credentials")],
    )

    entries, _ = deploy_configs.load_manifests()
    expanded = [entry for entry in entries if entry.get("_expanded_from") == "acme_repo_mcp"]

    assert [entry["_context_repo"] for entry in expanded] == ["svc-a", "dotfiles", "acme_credentials"]
    # an explicit requires is kept and the checkout gate is added in front of it, never duplicated
    assert expanded[0]["requires"] == ["{repo_parent}/svc-a", "{repo_parent}/acme_credentials"]
    assert expanded[2]["requires"] == ["{repo_parent}/acme_credentials"]


def test_per_context_repo_keeps_hosts_and_note_and_token_in_requires(overlay_tree):
    write_repos_file(str(overlay_tree / "acme_credentials" / "acme_repos.yaml"), ["svc-a"])
    write_manifest_at(
        str(overlay_tree / "acme_credentials" / "acme_manifest.yaml"),
        [per_repo_entry(hosts=["ENVY"], note="n", requires=["{repo_parent}/{context_repo}/sub"])],
    )
    inventory = str(overlay_tree / "acme_credentials" / "acme_hosts.json")
    write_file(inventory, json.dumps({"hosts": [{"name": "Envy"}]}))

    entries, _ = deploy_configs.load_manifests()
    entry = next(entry for entry in entries if entry["name"] == "acme_repo_mcp__svc-a")

    assert entry["hosts"] == ["ENVY"] and entry["note"] == "n"
    assert entry["requires"] == ["{repo_parent}/svc-a", "{repo_parent}/svc-a/sub"]


def test_excluding_a_repo_no_context_declares_raises(overlay_tree):
    write_repos_file(str(overlay_tree / "acme_credentials" / "acme_repos.yaml"), ["svc-a"])
    write_manifest_at(
        str(overlay_tree / "acme_credentials" / "acme_manifest.yaml"), [per_repo_entry(exclude_repos=["svc-x"])]
    )
    with pytest.raises(ValueError, match="svc-x"):
        deploy_configs.load_manifests()


def test_per_context_repo_without_a_repos_file_raises(overlay_tree):
    write_manifest_at(str(overlay_tree / "acme_credentials" / "acme_manifest.yaml"), [per_repo_entry()])
    with pytest.raises(ValueError, match="acme_repos.yaml"):
        deploy_configs.load_manifests()


@pytest.mark.parametrize(
    "entry",
    [
        per_repo_entry(dest={"darwin": "{repo_parent}/fixed/.mcp.json"}),  # token missing -> one path for all
        per_repo_entry(per_context_repo=None, dest={"darwin": "{repo_parent}/{context_repo}/x"}),  # token, no key
        per_repo_entry(per_context_repo=7),
        per_repo_entry(per_context_repo=[]),
        per_repo_entry(per_context_repo=None, extra_repos=["a"]),
        per_repo_entry(extra_repos="a"),
        per_repo_entry(exclude_repos=[""]),
        {"name": "g", "repo": "x", "dest": {"darwin": "~/x"}, "generated": "yes"},
    ],
)
def test_per_context_repo_schema_errors(tmp_path, entry):
    entry = {key: value for key, value in entry.items() if value is not None}
    with pytest.raises(ValueError):
        deploy_configs.load_manifest(write_manifest(tmp_path, [entry]))


def test_prune_refuses_a_path_inside_a_linked_directory(fake_home):
    # a removals line under a directory the manifest links whole would delete
    # the repo file behind the link, not a deployed copy
    source = fake_home / "repo" / "commands"
    source.mkdir(parents=True)
    (source / "cmd.md").write_text("x", encoding="utf-8")
    linked = fake_home / ".claude" / "commands"
    linked.parent.mkdir()
    os.symlink(str(source), str(linked))

    removable, description = deploy_configs.classify_prune_target(str(linked / "cmd.md"))

    assert removable is False and "linked directory" in description
    assert (source / "cmd.md").exists()
    # the link itself is still a normal prune target
    assert deploy_configs.classify_prune_target(str(linked)) == (True, "symlink")


def test_prune_removes_the_empty_chain_a_pruned_path_leaves_behind(fake_home, monkeypatch):
    # a placeholder taken literally by an older deploy leaves {context_repo}/.claude/
    monkeypatch.setattr(deploy_configs, "grandparent_dir", str(fake_home / "GitHub"))
    junk = fake_home / "GitHub" / "{context_repo}" / ".claude" / "commands"
    junk.parent.mkdir(parents=True)
    junk.write_text("x", encoding="utf-8")
    junk.unlink()

    deploy_configs.remove_empty_parents(str(junk))

    assert not (fake_home / "GitHub" / "{context_repo}").exists()
    assert (fake_home / "GitHub").is_dir()  # the clone root is never removed, even empty


def test_empty_parent_cleanup_stops_at_a_non_empty_directory_and_at_home(fake_home, monkeypatch):
    monkeypatch.setattr(deploy_configs, "grandparent_dir", str(fake_home / "GitHub"))
    skill = fake_home / ".claude" / "skills" / "old-skill" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    (fake_home / ".claude" / "settings.json").write_text("{}", encoding="utf-8")

    deploy_configs.remove_empty_parents(str(skill))

    assert not (fake_home / ".claude" / "skills").exists()
    assert (fake_home / ".claude" / "settings.json").exists()
    os.remove(str(fake_home / ".claude" / "settings.json"))
    deploy_configs.remove_empty_parents(str(fake_home / ".claude" / "x"))
    assert not (fake_home / ".claude").exists() and fake_home.is_dir()


# %%
# Platform / host resolution #


def test_get_platform_key_maps_known_systems():
    assert deploy_configs.get_platform_key("Darwin") == "darwin"
    assert deploy_configs.get_platform_key("Linux") == "linux"
    assert deploy_configs.get_platform_key("Windows") == "windows"


def test_resolve_dest_picks_platform_and_expands_home(fake_home):
    entry = {"dest": {"darwin": "~/.zshrc", "linux": "~/.zshrc_linux", "windows": "~/AppData/x"}}
    assert deploy_configs.resolve_dest(entry, "darwin") == os.path.join(str(fake_home), ".zshrc")
    assert deploy_configs.resolve_dest(entry, "linux") == os.path.join(str(fake_home), ".zshrc_linux")
    assert deploy_configs.resolve_dest({"dest": {"darwin": "~/.x"}}, "windows") is None
    assert deploy_configs.resolve_dest({}, "darwin") is None


def test_host_allowed_matches_short_and_full_hostname():
    entry = {"hosts": ["ENVY", "elitedesk"]}
    assert deploy_configs.host_allowed(entry, "ENVY.LOCAL")
    assert deploy_configs.host_allowed(entry, "ELITEDESK")
    assert not deploy_configs.host_allowed(entry, "YOGA")
    assert deploy_configs.host_allowed({}, "ANY_HOST")


def test_build_plan_classifies_rows(fake_home):
    entries = [
        {"name": "a", "repo": "f1", "dest": {"darwin": "~/.f1"}},
        {"name": "b", "repo": "f2", "dest": {"windows": "~/f2"}},
        {"name": "c", "repo": "f3", "method": "none", "note": "indirection"},
        {"name": "d", "repo": "f4", "dest": {"darwin": "~/.f4"}, "hosts": ["OTHERHOST"]},
    ]
    plan = deploy_configs.build_plan(entries, "darwin", "ENVY", repo_root="/repo")
    actions = {row["name"]: row["action"] for row in plan}
    assert actions == {"a": "apply", "b": "skip_platform", "c": "none", "d": "skip_host"}
    assert plan[0]["repo"] == os.path.normpath(os.path.join("/repo", "f1"))
    assert plan[0]["dest"] == os.path.join(str(fake_home), ".f1")


# %%
# requires precondition (skip repo-destined entries when the repo is not cloned) #


def test_build_plan_skips_entry_when_requires_path_missing(tmp_path, fake_home):
    repo_root = str(tmp_path / "GitHub" / "dotfiles")
    entries = [
        {
            "name": "into_uncloned_repo",
            "repo": "f1",
            "dest": {"darwin": "{repo_parent}/some-repo/.claude/settings.local.json"},
            "requires": "{repo_parent}/some-repo",
        }
    ]
    plan = deploy_configs.build_plan(entries, "darwin", "ENVY", repo_root=repo_root)
    assert plan[0]["action"] == "skip_requires"
    assert plan[0]["requires"] == os.path.join(str(tmp_path), "GitHub", "some-repo")


def test_build_plan_applies_entry_when_requires_path_exists(tmp_path, fake_home):
    repo_root = str(tmp_path / "GitHub" / "dotfiles")
    os.makedirs(os.path.join(str(tmp_path), "GitHub", "some-repo"))
    entries = [
        {
            "name": "into_cloned_repo",
            "repo": "f1",
            "dest": {"darwin": "{repo_parent}/some-repo/.claude/settings.local.json"},
            "requires": "{repo_parent}/some-repo",
        }
    ]
    plan = deploy_configs.build_plan(entries, "darwin", "ENVY", repo_root=repo_root)
    assert plan[0]["action"] == "apply"


def test_requires_list_needs_every_path(tmp_path, fake_home):
    # repo-specific entries list the dest repo AND the credentials source repo:
    # the entry follows the clones, deploying only where both are checked out
    repo_root = str(tmp_path / "GitHub" / "dotfiles")
    entries = [
        {
            "name": "into_cloned_repo",
            "repo": "f1",
            "dest": {"darwin": "{repo_parent}/some-repo/.mcp.json"},
            "requires": ["{repo_parent}/some-repo", "{repo_parent}/personal_credentials"],
        }
    ]
    os.makedirs(os.path.join(str(tmp_path), "GitHub", "some-repo"))
    plan = deploy_configs.build_plan(entries, "darwin", "ENVY", repo_root=repo_root)
    assert plan[0]["action"] == "skip_requires"
    assert plan[0]["requires"] == os.path.join(str(tmp_path), "GitHub", "personal_credentials")
    os.makedirs(os.path.join(str(tmp_path), "GitHub", "personal_credentials"))
    plan = deploy_configs.build_plan(entries, "darwin", "ENVY", repo_root=repo_root)
    assert plan[0]["action"] == "apply"


def test_requires_expands_home(tmp_path, fake_home):
    entries = [{"name": "x", "repo": "f1", "dest": {"darwin": "~/.x"}, "requires": "~/must_exist"}]
    plan = deploy_configs.build_plan(entries, "darwin", "ENVY", repo_root="/repo")
    assert plan[0]["action"] == "skip_requires"
    os.makedirs(os.path.join(str(fake_home), "must_exist"))
    plan = deploy_configs.build_plan(entries, "darwin", "ENVY", repo_root="/repo")
    assert plan[0]["action"] == "apply"


def test_deploy_never_creates_folder_for_uncloned_repo(tmp_path, fake_home, monkeypatch, capsys):
    repo_root = tmp_path / "GitHub" / "dotfiles"
    monkeypatch.setattr(deploy_configs, "REPO_ROOT", str(repo_root))
    monkeypatch.setattr(deploy_configs, "BACKUP_ROOT", str(repo_root / "data" / "config_backups"))
    monkeypatch.setattr(deploy_configs, "get_uppercase_hostname", lambda: "ENVY")
    write_file(str(repo_root / "allow.json"), "{}")
    dest = "{repo_parent}/some-repo/.claude/settings.local.json"
    manifest_path = write_manifest(
        tmp_path,
        [
            {
                "name": "guarded",
                "repo": "allow.json",
                "dest": {"darwin": dest, "linux": dest, "windows": dest},
                "requires": "{repo_parent}/some-repo",
            }
        ],
    )
    assert deploy_configs.main(["--manifest", manifest_path]) == 0
    output = capsys.readouterr().out
    assert "SKIP_REQUIRES" in output
    # the whole point: the uncloned repo's folder must NOT be created
    assert not os.path.exists(str(tmp_path / "GitHub" / "some-repo"))

    # status treats it as informational, not drift
    assert deploy_configs.main(["--status", "--manifest", manifest_path]) == 0
    assert "SKIP_REQUIRES" in capsys.readouterr().out


# %%
# Variant resolution (exact hostname -> platform -> bare default) #


def test_short_host_token_lowercases_and_strips_domain():
    assert deploy_configs.short_host_token("ENVY.LOCAL") == "envy"
    assert deploy_configs.short_host_token("MACBOOKPROM5") == "macbookprom5"
    assert deploy_configs.short_host_token(None) == ""


def test_resolve_repo_variant_prefers_host_then_platform_then_bare(tmp_path):
    bare = write_file(str(tmp_path / "settings.json"), "bare")
    mac = write_file(str(tmp_path / "settings.mac.json"), "mac")
    host = write_file(str(tmp_path / "settings.envy.json"), "host")
    assert deploy_configs.resolve_repo_variant(bare, "ENVY.LOCAL", "darwin") == (host, True)
    assert deploy_configs.resolve_repo_variant(bare, "YOGA", "darwin") == (mac, True)
    assert deploy_configs.resolve_repo_variant(bare, "YOGA", "linux") == (bare, True)


def test_resolve_repo_variant_host_match_is_case_insensitive(tmp_path):
    variant = write_file(str(tmp_path / "workspace.macbookprom5.code-workspace"), "ws")
    bare = str(tmp_path / "workspace.code-workspace")
    assert deploy_configs.resolve_repo_variant(bare, "MACBOOKPROM5", "darwin") == (variant, True)


def test_resolve_repo_variant_skips_host_without_variant(tmp_path):
    write_file(str(tmp_path / "workspace.envy.code-workspace"), "ws")
    bare = str(tmp_path / "workspace.code-workspace")
    assert deploy_configs.resolve_repo_variant(bare, "RASPBERRYPI", "linux") == (bare, False)


def test_resolve_repo_variant_missing_everything_stays_bare(tmp_path):
    bare = str(tmp_path / "nothing.conf")
    assert deploy_configs.resolve_repo_variant(bare, "ENVY", "darwin") == (bare, True)


def test_resolve_dest_expands_host_and_repo_parent_placeholders():
    entry = {"dest": {"darwin": "{repo_parent}/{host}.code-workspace"}}
    dest = deploy_configs.resolve_dest(entry, "darwin", "ENVY.LOCAL", repo_root="/parent/dotfiles")
    # normpath: expand_path returns native separators, so this is
    # \parent\envy.code-workspace on Windows and /parent/... on POSIX
    assert dest == os.path.normpath("/parent/envy.code-workspace")


def test_build_plan_resolves_variant_and_placeholders(tmp_path):
    repo_root = str(tmp_path / "GitHub" / "dotfiles")
    variant = write_file(
        os.path.join(repo_root, "application_configs", "vscode", "workspace.envy.code-workspace"), "ws"
    )
    entries = [
        {
            "name": "vscode_workspace",
            "repo": "application_configs/vscode/workspace.code-workspace",
            "dest": {
                "darwin": "{repo_parent}/{host}.code-workspace",
                "linux": "{repo_parent}/{host}.code-workspace",
            },
        }
    ]
    plan = deploy_configs.build_plan(entries, "darwin", "ENVY.LOCAL", repo_root=repo_root)
    assert plan[0]["action"] == "apply"
    assert plan[0]["repo"] == variant
    assert plan[0]["dest"] == os.path.join(str(tmp_path), "GitHub", "envy.code-workspace")

    plan = deploy_configs.build_plan(entries, "linux", "PIHOLE", repo_root=repo_root)
    assert plan[0]["action"] == "skip_variant"
    assert plan[0]["dest"] == os.path.join(str(tmp_path), "GitHub", "pihole.code-workspace")


def test_deploy_fixes_dangling_old_name_workspace_link(tmp_path, fake_home, monkeypatch, capsys):
    repo_root = tmp_path / "GitHub" / "dotfiles"
    monkeypatch.setattr(deploy_configs, "REPO_ROOT", str(repo_root))
    monkeypatch.setattr(deploy_configs, "BACKUP_ROOT", str(repo_root / "data" / "config_backups"))
    monkeypatch.setattr(deploy_configs, "get_uppercase_hostname", lambda: "ENVY.LOCAL")
    variant = write_file(
        str(repo_root / "application_configs" / "vscode" / "workspace.envy.code-workspace"), "ws"
    )
    dest_template = "{repo_parent}/{host}.code-workspace"
    manifest_path = write_manifest(
        tmp_path,
        [
            {
                "name": "vscode_workspace",
                "repo": "application_configs/vscode/workspace.code-workspace",
                "dest": {"darwin": dest_template, "linux": dest_template, "windows": dest_template},
            }
        ],
    )
    # dangling link left behind by the Task 5 rename (points at the old filename)
    link = str(tmp_path / "GitHub" / "envy.code-workspace")
    os.symlink(str(repo_root / "application_configs" / "vscode" / "envy.code-workspace"), link)

    assert deploy_configs.main(["--manifest", manifest_path]) == 0
    assert "1 changed" in capsys.readouterr().out
    assert os.path.islink(link)
    assert os.path.realpath(link) == os.path.realpath(variant)


# %%
# deploy_config behavior #


def test_case1_creates_symlink(tmp_path):
    repo_file = write_file(str(tmp_path / "repo" / "conf"), "repo content")
    dest = str(tmp_path / "sys" / "conf")
    result = deploy_configs.deploy_config(repo_file, dest)
    assert result == "symlinked"
    assert os.path.islink(dest)
    assert os.path.realpath(dest) == os.path.realpath(repo_file)


def test_deploy_is_idempotent_second_run_is_noop(tmp_path):
    repo_file = write_file(str(tmp_path / "repo" / "conf"), "repo content")
    dest = str(tmp_path / "sys" / "conf")
    assert deploy_configs.deploy_config(repo_file, dest) == "symlinked"
    assert deploy_configs.deploy_config(repo_file, dest) == "noop"
    assert os.path.islink(dest)


def test_windows_symlink_denied_falls_back_to_hard_link_never_copy(tmp_path, monkeypatch, capsys):
    repo_file = write_file(str(tmp_path / "repo" / "conf"), "repo content")
    dest = str(tmp_path / "sys" / "conf")

    def deny_symlink(src, dst, **kwargs):
        raise OSError("A required privilege is not held by the client")

    monkeypatch.setattr(deploy_configs, "system", "Windows")
    monkeypatch.setattr(deploy_configs.os, "symlink", deny_symlink)
    result = deploy_configs.deploy_config(repo_file, dest)
    assert result == "hardlinked"
    assert os.path.isfile(dest) and not os.path.islink(dest)
    assert os.path.samefile(dest, repo_file)
    assert "copied" not in capsys.readouterr().out.lower()


def test_existing_correct_hard_link_is_left_alone(tmp_path):
    repo_file = write_file(str(tmp_path / "repo" / "conf"), "repo content")
    dest = str(tmp_path / "sys" / "conf")
    os.makedirs(os.path.dirname(dest))
    os.link(repo_file, dest)
    assert deploy_configs.deploy_config(repo_file, dest) == "noop"
    assert os.path.samefile(dest, repo_file)


def test_classify_hard_link_is_ok_and_orphaned_hard_link_is_drift(tmp_path):
    repo_file = write_file(str(tmp_path / "repo" / "conf"), "repo content")
    dest = str(tmp_path / "sys" / "conf")
    os.makedirs(os.path.dirname(dest))
    os.link(repo_file, dest)
    assert deploy_configs.classify_entry(repo_file, dest)[0] == "OK"
    # simulate git pull replacing the repo file's inode - the hard link is now orphaned
    os.remove(repo_file)
    write_file(repo_file, "new repo content")
    status, detail = deploy_configs.classify_entry(repo_file, dest)
    assert status == "NOT_A_LINK" and "orphaned hard link" in detail


def test_deploy_section_never_copies_a_config_into_place():
    with open(deploy_configs.__file__.replace(".pyc", ".py"), encoding="utf-8") as file_handle:
        source = file_handle.read()
    # copies as a deployment mechanism are banned; shutil.copy2 is allowed only
    # for backup_system_file and adopt_system_file (backups and worktree
    # adoption are copies by design), which live outside the Deploy section
    deploy_section = source.split("# Deploy #")[1].split("# Manifest #")[0]
    assert "copy2" not in deploy_section


def test_non_windows_symlink_failure_raises(tmp_path, monkeypatch):
    repo_file = write_file(str(tmp_path / "repo" / "conf"), "repo content")
    dest = str(tmp_path / "sys" / "conf")

    def deny_symlink(src, dst, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(deploy_configs, "system", "Linux")
    monkeypatch.setattr(deploy_configs.os, "symlink", deny_symlink)
    with pytest.raises(OSError):
        deploy_configs.deploy_config(repo_file, dest)
    assert not os.path.lexists(dest)


def test_case3_backup_goes_to_backup_root_not_repo_tree(tmp_path):
    repo_root = str(tmp_path / "repo")
    backup_root = os.path.join(repo_root, "data", "config_backups")
    repo_file = write_file(os.path.join(repo_root, "application_configs", "app", "conf"), "repo version")
    dest = write_file(str(tmp_path / "sys" / "conf"), "system version")

    result = deploy_configs.deploy_config(
        repo_file, dest, replace_system_if_exists=True, backup_root=backup_root, repo_root=repo_root
    )

    assert result == "replaced"
    assert os.path.islink(dest)
    # repo is the source of truth - the system version is NOT ingested into it
    with open(repo_file, encoding="utf-8") as file_handle:
        assert file_handle.read() == "repo version"
    with open(dest, encoding="utf-8") as file_handle:
        assert file_handle.read() == "repo version"
    backup_dir = os.path.join(backup_root, "application_configs", "app")
    backups = os.listdir(backup_dir)
    assert len(backups) == 1 and backups[0].startswith("conf.")
    with open(os.path.join(backup_dir, backups[0]), encoding="utf-8") as file_handle:
        assert file_handle.read() == "system version"
    # the tracked config's directory stays clean - no *.backup.* clutter next to it
    assert os.listdir(os.path.dirname(repo_file)) == ["conf"]


def test_case3_without_backup_makes_no_changes(tmp_path):
    repo_file = write_file(str(tmp_path / "repo" / "conf"), "repo version")
    dest = write_file(str(tmp_path / "sys" / "conf"), "system version")
    result = deploy_configs.deploy_config(repo_file, dest, replace_system_if_exists=False)
    assert result == "skipped"
    assert not os.path.islink(dest)
    with open(repo_file, encoding="utf-8") as file_handle:
        assert file_handle.read() == "repo version"


# %%
# on_drift: adopt (app atomic-rename saves flow into the repo worktree, not the backup graveyard) #


def _drifted_pair(tmp_path, repo_content, system_content, newer):
    """A diverged repo/system file pair with the given side mtime-newer."""
    repo_file = write_file(str(tmp_path / "repo" / "application_configs" / "app" / "conf"), repo_content)
    dest = write_file(str(tmp_path / "sys" / "conf"), system_content)
    older, newer_path = (repo_file, dest) if newer == "system" else (dest, repo_file)
    os.utime(older, (1000000, 1000000))
    os.utime(newer_path, (2000000, 2000000))
    return repo_file, dest


def test_adopt_copies_newer_system_edit_into_repo_worktree_then_links(tmp_path):
    repo_root = str(tmp_path / "repo")
    repo_file, dest = _drifted_pair(tmp_path, "repo version", "in-app edit", newer="system")
    result = deploy_configs.deploy_config(
        repo_file, dest, backup_root=os.path.join(repo_root, "data", "config_backups"),
        repo_root=repo_root, on_drift="adopt",
    )
    assert result == "adopted"
    assert os.path.islink(dest)
    # the edit landed in the repo file (worktree dirty for the user to commit or revert)...
    with open(repo_file, encoding="utf-8") as file_handle:
        assert file_handle.read() == "in-app edit"
    # ...and a safety-net backup still exists in case the user git-checkouts the file away
    backups = os.listdir(os.path.join(repo_root, "data", "config_backups", "application_configs", "app"))
    assert len(backups) == 1


def test_adopt_still_replaces_when_repo_side_is_newer(tmp_path):
    # the orphaned-hard-link-after-pull case: the system file holds PRE-pull
    # content, so adopting it would resurrect stale config over the pulled update
    repo_root = str(tmp_path / "repo")
    repo_file, dest = _drifted_pair(tmp_path, "pulled update", "stale pre-pull", newer="repo")
    result = deploy_configs.deploy_config(
        repo_file, dest, backup_root=os.path.join(repo_root, "data", "config_backups"),
        repo_root=repo_root, on_drift="adopt",
    )
    assert result == "replaced"
    with open(repo_file, encoding="utf-8") as file_handle:
        assert file_handle.read() == "pulled update"


def test_adopt_with_matching_content_just_relinks(tmp_path):
    repo_root = str(tmp_path / "repo")
    repo_file = write_file(os.path.join(repo_root, "application_configs", "app", "conf"), "same")
    dest = write_file(str(tmp_path / "sys" / "conf"), "same")
    result = deploy_configs.deploy_config(
        repo_file, dest, backup_root=os.path.join(repo_root, "data", "config_backups"),
        repo_root=repo_root, on_drift="adopt",
    )
    assert result == "replaced"
    assert os.path.islink(dest)
    with open(repo_file, encoding="utf-8") as file_handle:
        assert file_handle.read() == "same"


def test_adopt_is_stable_after_adoption(tmp_path):
    # copy2 preserves the edit's mtime, so a second deploy is a plain no-op
    repo_root = str(tmp_path / "repo")
    repo_file, dest = _drifted_pair(tmp_path, "repo version", "in-app edit", newer="system")
    kwargs = {"backup_root": os.path.join(repo_root, "data", "config_backups"),
              "repo_root": repo_root, "on_drift": "adopt"}
    assert deploy_configs.deploy_config(repo_file, dest, **kwargs) == "adopted"
    assert deploy_configs.deploy_config(repo_file, dest, **kwargs) == "noop"


def test_adopt_json_lands_in_canonical_form(tmp_path):
    # the app saves minified with its own key order; the repo copy must come out
    # pretty, key-sorted, newline-terminated - a per-key reviewable diff
    repo_root = str(tmp_path / "repo")
    repo_file = write_file(os.path.join(repo_root, "application_configs", "app", "conf.json"), "{}\n")
    dest = write_file(str(tmp_path / "sys" / "conf.json"), '{"zeta":1,"alpha":{"b":2,"a":[3,1,2]}}')
    os.utime(repo_file, (1000000, 1000000))
    os.utime(dest, (2000000, 2000000))
    result = deploy_configs.deploy_config(
        repo_file, dest, backup_root=os.path.join(repo_root, "data", "config_backups"),
        repo_root=repo_root, on_drift="adopt",
    )
    assert result == "adopted"
    expected = '{\n  "alpha": {\n    "a": [\n      3,\n      1,\n      2\n    ],\n    "b": 2\n  },\n  "zeta": 1\n}\n'
    with open(repo_file, encoding="utf-8") as file_handle:
        assert file_handle.read() == expected


def test_adopt_json_format_only_drift_is_not_an_edit(tmp_path):
    # the app re-minifying UNCHANGED settings over the canonical repo copy must
    # not dirty the worktree - it is the same content in the app's clothing
    repo_root = str(tmp_path / "repo")
    canonical = '{\n  "a": 1,\n  "b": 2\n}\n'
    repo_file = write_file(os.path.join(repo_root, "application_configs", "app", "conf.json"), canonical)
    dest = write_file(str(tmp_path / "sys" / "conf.json"), '{"b":2,"a":1}')
    os.utime(repo_file, (1000000, 1000000))
    os.utime(dest, (2000000, 2000000))
    result = deploy_configs.deploy_config(
        repo_file, dest, backup_root=os.path.join(repo_root, "data", "config_backups"),
        repo_root=repo_root, on_drift="adopt",
    )
    assert result == "replaced"
    with open(repo_file, encoding="utf-8") as file_handle:
        assert file_handle.read() == canonical


def test_adopt_invalid_json_falls_back_to_verbatim_copy(tmp_path):
    repo_root = str(tmp_path / "repo")
    repo_file, dest = _drifted_pair(tmp_path, "{}", "{not json", newer="system")
    repo_file_json = repo_file + ".json"
    os.rename(repo_file, repo_file_json)
    dest_json = dest  # dest extension is irrelevant; adoption keys off the repo path
    result = deploy_configs.deploy_config(
        repo_file_json, dest_json, backup_root=os.path.join(repo_root, "data", "config_backups"),
        repo_root=repo_root, on_drift="adopt",
    )
    assert result == "adopted"
    with open(repo_file_json, encoding="utf-8") as file_handle:
        assert file_handle.read() == "{not json"


def test_status_planned_action_mentions_adoption_for_adopt_entries():
    assert "adopt" in deploy_configs.planned_action("NOT_A_LINK", "adopt")
    assert "adopt" not in deploy_configs.planned_action("NOT_A_LINK")


def test_build_plan_carries_on_drift(fake_home):
    entries = [
        {"name": "a", "repo": "f1", "dest": {"darwin": "~/.f1"}, "on_drift": "adopt"},
        {"name": "b", "repo": "f2", "dest": {"darwin": "~/.f2"}},
    ]
    plan = deploy_configs.build_plan(entries, "darwin", "ENVY", repo_root="/repo")
    assert [row["on_drift"] for row in plan] == ["adopt", "replace"]


def test_case2_ingest_moves_system_file_into_repo(tmp_path):
    repo_file = str(tmp_path / "repo" / "conf")
    dest = write_file(str(tmp_path / "sys" / "conf"), "system version")
    result = deploy_configs.deploy_config(repo_file, dest, ingest_system_if_exists=True)
    assert result == "ingested"
    assert os.path.islink(dest)
    with open(repo_file, encoding="utf-8") as file_handle:
        assert file_handle.read() == "system version"


def test_case2_without_ingest_skips(tmp_path):
    repo_file = str(tmp_path / "repo" / "conf")
    dest = write_file(str(tmp_path / "sys" / "conf"), "system version")
    assert deploy_configs.deploy_config(repo_file, dest) == "skipped"
    assert not os.path.exists(repo_file)
    assert not os.path.islink(dest)


def test_broken_link_at_destination_is_replaced(tmp_path):
    repo_file = write_file(str(tmp_path / "repo" / "conf"), "repo content")
    dest = str(tmp_path / "sys" / "conf")
    os.makedirs(os.path.dirname(dest))
    os.symlink(str(tmp_path / "gone"), dest)
    assert deploy_configs.deploy_config(repo_file, dest) == "symlinked"
    assert os.path.realpath(dest) == os.path.realpath(repo_file)


# %%
# Status classification #


def test_classify_ok_link(tmp_path):
    repo_file = write_file(str(tmp_path / "repo" / "conf"), "content")
    dest = str(tmp_path / "sys" / "conf")
    os.makedirs(os.path.dirname(dest))
    os.symlink(repo_file, dest)
    assert deploy_configs.classify_entry(repo_file, dest)[0] == "OK"


def test_classify_not_deployed(tmp_path):
    repo_file = write_file(str(tmp_path / "repo" / "conf"), "content")
    assert deploy_configs.classify_entry(repo_file, str(tmp_path / "missing"))[0] == "NOT_DEPLOYED"


def test_classify_broken_link(tmp_path):
    repo_file = write_file(str(tmp_path / "repo" / "conf"), "content")
    dest = str(tmp_path / "sys" / "conf")
    os.makedirs(os.path.dirname(dest))
    os.symlink(str(tmp_path / "gone"), dest)
    assert deploy_configs.classify_entry(repo_file, dest)[0] == "BROKEN_LINK"


def test_classify_wrong_target(tmp_path):
    repo_file = write_file(str(tmp_path / "repo" / "conf"), "content")
    other_file = write_file(str(tmp_path / "other" / "conf"), "other")
    dest = str(tmp_path / "sys" / "conf")
    os.makedirs(os.path.dirname(dest))
    os.symlink(other_file, dest)
    assert deploy_configs.classify_entry(repo_file, dest)[0] == "WRONG_TARGET"


def test_classify_not_a_link_matching_and_diverging(tmp_path):
    repo_file = write_file(str(tmp_path / "repo" / "conf"), "content")
    dest_match = write_file(str(tmp_path / "sys" / "match"), "content")
    dest_diff = write_file(str(tmp_path / "sys" / "diff"), "different")
    status, detail = deploy_configs.classify_entry(repo_file, dest_match)
    assert status == "NOT_A_LINK" and "matches" in detail
    status, detail = deploy_configs.classify_entry(repo_file, dest_diff)
    assert status == "NOT_A_LINK" and "diverges" in detail


def test_classify_repo_missing(tmp_path):
    dest = write_file(str(tmp_path / "sys" / "conf"), "content")
    assert deploy_configs.classify_entry(str(tmp_path / "no_repo"), dest)[0] == "REPO_MISSING"


# %%
# End-to-end main() with a temp manifest and temp HOME #


def _temp_manifest(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    monkeypatch.setattr(deploy_configs, "REPO_ROOT", str(repo_root))
    monkeypatch.setattr(deploy_configs, "BACKUP_ROOT", str(repo_root / "data" / "config_backups"))
    write_file(str(repo_root / "application_configs" / "app" / "conf"), "repo content")
    dest = "~/config_dir/conf"
    entries = [
        {
            "name": "app_conf",
            "repo": "application_configs/app/conf",
            "dest": {"darwin": dest, "linux": dest, "windows": dest},
        }
    ]
    return write_manifest(tmp_path, entries)


def test_status_reports_broken_link_and_exits_nonzero(tmp_path, fake_home, monkeypatch, capsys):
    manifest_path = _temp_manifest(tmp_path, monkeypatch)
    dest = os.path.join(str(fake_home), "config_dir", "conf")
    os.makedirs(os.path.dirname(dest))
    os.symlink(os.path.join(str(fake_home), "does_not_exist"), dest)

    exit_code = deploy_configs.main(["--status", "--manifest", manifest_path])
    output = capsys.readouterr().out
    assert exit_code == 1
    assert "BROKEN_LINK" in output
    assert "1 broken_link" in output


def test_status_all_ok_exits_zero(tmp_path, fake_home, monkeypatch, capsys):
    manifest_path = _temp_manifest(tmp_path, monkeypatch)
    repo_file = os.path.join(deploy_configs.REPO_ROOT, "application_configs", "app", "conf")
    dest = os.path.join(str(fake_home), "config_dir", "conf")
    os.makedirs(os.path.dirname(dest))
    os.symlink(repo_file, dest)

    exit_code = deploy_configs.main(["--status", "--manifest", manifest_path])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "1 ok" in output


def test_status_shows_planned_action_without_touching_filesystem(tmp_path, fake_home, monkeypatch, capsys):
    manifest_path = _temp_manifest(tmp_path, monkeypatch)
    dest = os.path.join(str(fake_home), "config_dir", "conf")

    # --dry-run is a deprecated alias for the status command; both are read-only
    for argv in (["status", "--manifest", manifest_path], ["--dry-run", "--manifest", manifest_path]):
        exit_code = deploy_configs.main(argv)
        output = capsys.readouterr().out
        assert exit_code == 1  # not deployed counts as drift
        assert "NOT_DEPLOYED" in output
        assert "would create symlink" in output
        assert not os.path.lexists(dest)


def test_deploy_then_second_run_reports_no_changes(tmp_path, fake_home, monkeypatch, capsys):
    manifest_path = _temp_manifest(tmp_path, monkeypatch)
    dest = os.path.join(str(fake_home), "config_dir", "conf")

    assert deploy_configs.main(["--manifest", manifest_path]) == 0
    first_output = capsys.readouterr().out
    assert "1 changed" in first_output
    assert os.path.islink(dest)

    assert deploy_configs.main(["--manifest", manifest_path]) == 0
    second_output = capsys.readouterr().out
    assert "0 changed, 1 already deployed" in second_output


# %%
# Removals and prune #


def _removals(monkeypatch, entries):
    """Point load_removals at an in-memory removals list."""
    monkeypatch.setattr(deploy_configs, "load_removals", lambda: entries)


def test_prune_candidates_come_from_removals_and_skip_still_wanted_dests(monkeypatch, fake_home):
    """A dest some entry still wants is never pruned, even if a removals line names it."""
    _removals(monkeypatch, [
        {"name": "dead", "dest": {"darwin": "~/.gone"}},
        {"name": "revived", "dest": {"darwin": "~/.keep"}},
    ])
    entries = [{"name": "keep", "repo": "r.txt", "dest": {"darwin": "~/.keep"}}]
    candidates = deploy_configs.build_prune_candidates(entries, "darwin", "ENVY")
    assert [dest for dest, _, _ in candidates] == [os.path.join(str(fake_home), ".gone")]
    assert candidates[0][1] == "removals:dead"


def test_prune_candidates_respect_requires_and_hosts(monkeypatch, fake_home):
    """A repo this machine never cloned has no link to prune; a hosts filter still applies."""
    _removals(monkeypatch, [
        {"name": "uncloned", "dest": {"darwin": "~/.a"}, "requires": "~/never-cloned-repo"},
        {"name": "other_host", "dest": {"darwin": "~/.b"}, "hosts": ["SOMEOTHERBOX"]},
    ])
    assert deploy_configs.build_prune_candidates([], "darwin", "ENVY") == []


def test_prune_removes_orphaned_symlink_only_with_apply(tmp_path, fake_home):
    source = write_file(os.path.join(str(tmp_path), "src.md"), "x")
    dest = os.path.join(str(fake_home), "skills", "old", "SKILL.md")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    os.symlink(source, dest)
    candidates = [(dest, "removals:old", False)]

    deploy_configs.run_prune(candidates, apply_changes=False)
    assert os.path.lexists(dest), "dry run must not delete"

    deploy_configs.run_prune(candidates, apply_changes=True)
    assert not os.path.lexists(dest)
    # the emptied skill-style dir is cleaned up too, and the source is untouched
    assert not os.path.isdir(os.path.dirname(dest))
    assert os.path.exists(source)


def test_prune_removes_dangling_symlink_and_leaves_real_dirs(tmp_path, fake_home):
    dangling = os.path.join(str(fake_home), "dangling.md")
    os.symlink(os.path.join(str(tmp_path), "deleted.md"), dangling)
    real_dir = os.path.join(str(fake_home), "realdir")
    os.makedirs(real_dir, exist_ok=True)

    deploy_configs.run_prune(
        [(dangling, "removals:x", False), (real_dir, "removals:y", False)], apply_changes=True
    )
    assert not os.path.lexists(dangling), "a dangling symlink is still ours to remove"
    assert os.path.isdir(real_dir), "a real directory is never pruned"


def test_prune_removes_hard_link_style_regular_file(fake_home):
    """The Windows fallback: a hard link is a plain file once its source is gone."""
    dest = write_file(os.path.join(str(fake_home), "hardlinked.md"), "stale content")
    deploy_configs.run_prune([(dest, "removals:old", False)], apply_changes=True)
    assert not os.path.exists(dest)


def test_prune_is_idempotent_when_targets_are_already_gone(fake_home, capsys):
    dest = os.path.join(str(fake_home), "never-existed.md")
    assert deploy_configs.run_prune([(dest, "removals:x", False)], apply_changes=True) == 0
    assert "already absent 1" in capsys.readouterr().out


def test_removals_expand_per_context_repo_like_a_manifest(overlay_tree, monkeypatch):
    write_repos_file(str(overlay_tree / "acme_credentials" / "acme_repos.yaml"), ["svc-a", "svc-b"])
    write_manifest_at(
        str(overlay_tree / "acme_credentials" / "acme_removals.yaml"),
        [{"name": "removed_repo_commands", "dest": {"darwin": "{repo_parent}/{context_repo}/.claude/commands"},
          "per_context_repo": True}],
    )

    entries = deploy_configs.load_removals()

    assert [entry["name"] for entry in entries] == ["removed_repo_commands__svc-a", "removed_repo_commands__svc-b"]
    assert entries[0]["dest"] == {"darwin": "{repo_parent}/svc-a/.claude/commands"}
    assert entries[0]["requires"] == ["{repo_parent}/svc-a"]


def test_link_only_removal_ignores_a_real_directory_but_removes_a_link(overlay_tree, fake_home, monkeypatch):
    write_manifest_at(
        str(overlay_tree / "acme_credentials" / "acme_removals.yaml"),
        [{"name": "removed_commands_dir_link", "dest": {"darwin": "~/.claude/commands"}, "link_only": True}],
    )
    entries, _ = deploy_configs.load_manifests()
    target = fake_home / ".claude" / "commands"
    target.mkdir(parents=True)  # the real directory that replaced the link

    assert deploy_configs.build_prune_candidates(entries, "darwin", "ENVY") == []

    target.rmdir()
    os.symlink(str(fake_home), str(target))
    candidates = deploy_configs.build_prune_candidates(entries, "darwin", "ENVY")
    assert [dest for dest, _, _ in candidates] == [str(target)]


def test_load_removals_rejects_entry_without_dest(tmp_path, monkeypatch):
    removals_path = os.path.join(str(tmp_path), "x_removals.yaml")
    with open(removals_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump([{"name": "no_dest"}], handle)
    monkeypatch.setattr(deploy_configs, "discover_removals", lambda: [removals_path])
    with pytest.raises(ValueError, match="'name' and 'dest'"):
        deploy_configs.load_removals()


def test_real_removals_files_parse_and_name_no_still_wanted_dest():
    """The committed seed must stay loadable, and must never target a live entry."""
    removals = deploy_configs.load_removals()
    for entry in removals:
        assert entry.get("name") and entry.get("dest"), entry
    entries, _ = deploy_configs.load_manifests()
    for platform_key in ("darwin", "linux", "windows"):
        wanted = {
            row["dest"]
            for row in deploy_configs.build_plan(entries, platform_key, "ENVY")
            if row["action"] == "apply" and row["dest"]
        }
        targeted = {
            deploy_configs.resolve_dest(entry, platform_key, "ENVY") for entry in removals
        }
        assert not (wanted & targeted), f"removals would delete a live dest on {platform_key}"


# %%
# application_configs/ coverage - keeping the "complete inventory" claim true #

# deploy_manifest.yaml claims to be "a complete inventory of deployed configs,
# not just a link list" - that is what method: none entries are for. The two
# lists below plus the tests under them are what make the claim enforced
# rather than aspirational: a payload added to application_configs/ without a
# manifest entry fails the suite instead of quietly becoming a config no
# machine is ever checked for.

# Payloads no manifest entry deploys, with the reason each is legitimately
# manifest-free. Keep this list short and specific - "nothing deploys it" is
# the drift this whole system exists to catch, so a new line here needs a
# reason that is about the FILE, not about not having gotten to it yet.
MANIFEST_FREE_PAYLOADS = {
    "hammerspoon/window_layout_editor.html": (
        "never installed anywhere: init.lua reads it off disk from this folder (same wl.dir "
        "readlink) and serves it over its localhost HTTP server, so deploying a copy would "
        "only create a second version to drift"
    ),
}

# Payloads whose entry lives in an overlay manifest, by the overlay repo that
# owns it. They need a hosts filter, and those are overlay-only - so a machine
# that has not cloned that repo genuinely cannot see the entry and the payload
# is exempt there. When the overlay IS cloned the second test below insists the
# entry really covers the file, so a stale line here fails on Jason's machines.
OVERLAY_OWNED_PAYLOADS = {
    "autostart/start_x0vncserver.desktop": "personal_credentials",
    "claude/settings.json": "personal_credentials",
    "claude/statusline.sh": "personal_credentials",
    "claude/themes/dark-high-contrast.json": "personal_credentials",
    "ssh/config": "personal_credentials",
    "ssh/config.mac": "personal_credentials",
    "t3code/service.d/10-path.jasonzephyrus.conf": "personal_credentials",
    "t3code/service.d/20-tailscale-serve.jasonzephyrus.conf": "personal_credentials",
    "t3code/settings.json": "personal_credentials",
}

APPLICATION_CONFIGS_DIR = os.path.join(deploy_configs.REPO_ROOT, "application_configs")


def _application_config_payloads():
    """Every TRACKED file under application_configs/, as paths relative to that folder."""
    tracked = subprocess.check_output(
        ["git", "ls-files", "--", "application_configs"],
        cwd=deploy_configs.REPO_ROOT,
        text=True,
    ).split("\n")
    return {path[len("application_configs/"):] for path in tracked if path.strip()}


def _allowed_variant_tokens():
    """
    Tokens a repo path may auto-resolve to: the platform tokens plus every
    hostname in the union inventory. Returns (tokens, inventory_present) -
    without an inventory the caller can only accept any token, since this
    machine cannot tell a hostname from a context tag (settings.acme.json,
    which the resolver never picks up, so it is NOT coverage).
    """
    tokens = {token for tokens in deploy_configs.PLATFORM_FILE_TOKENS.values() for token in tokens}
    hostnames, inventory_paths = load_union_inventory_hostnames(deploy_configs.grandparent_dir)
    return tokens | {name.lower() for name in hostnames}, bool(inventory_paths)


def _covered_payloads(entries):
    """Files under application_configs/ reachable from these entries, same folder-relative form."""
    allowed_tokens, has_inventory = _allowed_variant_tokens()
    covered = set()
    for entry in entries:
        repo_path = os.path.normpath(os.path.join(entry["_base_dir"], entry["repo"]))
        directory, filename = os.path.split(repo_path)
        base, ext = os.path.splitext(filename)
        candidates = [repo_path]
        for variant in glob.glob(os.path.join(glob.escape(directory), f"{glob.escape(base)}.*{ext}")):
            name = os.path.basename(variant)
            token = name[len(base) + 1:len(name) - len(ext) or None]
            if has_inventory and token.lower() not in allowed_tokens:
                continue  # a context tag, which the resolver never picks up
            candidates.append(variant)
        for candidate in candidates:
            if os.path.isdir(candidate):  # folder link: everything inside rides along
                found = [os.path.join(where, name) for where, _, names in os.walk(candidate) for name in names]
            else:
                found = [candidate] if os.path.exists(candidate) else []
            for path in found:
                relative = os.path.relpath(path, APPLICATION_CONFIGS_DIR)
                if not relative.startswith(".."):
                    covered.add(relative.replace(os.sep, "/"))
    return covered


def test_every_application_config_is_reachable_from_a_manifest_entry():
    entries, _ = deploy_configs.load_manifests()
    exempt = set(MANIFEST_FREE_PAYLOADS) | set(OVERLAY_OWNED_PAYLOADS)
    uncovered = _application_config_payloads() - _covered_payloads(entries) - exempt
    assert not uncovered, (
        "application_configs payloads no manifest entry deploys: "
        + ", ".join(sorted(uncovered))
        + " - add an entry (method: none counts, with a note saying how it really gets there), "
        "delete the file, or list it in MANIFEST_FREE_PAYLOADS / OVERLAY_OWNED_PAYLOADS with a reason"
    )


def test_overlay_owned_payloads_are_covered_wherever_their_overlay_is_cloned():
    entries, _ = deploy_configs.load_manifests()
    covered = _covered_payloads(entries)
    for payload, overlay_repo in sorted(OVERLAY_OWNED_PAYLOADS.items()):
        if not os.path.isdir(os.path.join(deploy_configs.grandparent_dir, overlay_repo)):
            continue  # that overlay is not on this machine, so its entries cannot be checked
        assert payload in covered, (
            f"{payload} is listed as owned by {overlay_repo}, which IS cloned here, but no loaded "
            "manifest entry resolves to it - the entry was renamed, retargeted or dropped"
        )


def test_regenerate_mcp_reports_a_failure_loudly_instead_of_aborting_the_deploy(monkeypatch, capsys):
    # imported here, not at module scope: config_test_utils must put src/ on the
    # path first, and isort would sort `import claude_mcp` above it
    import claude_mcp

    def explode(**_kwargs):
        raise ValueError("no declarations parse")

    monkeypatch.setattr(claude_mcp, "write", explode)

    # a deploy that already linked everything must still finish, but say so
    assert deploy_configs.regenerate_mcp() is False
    assert "FAILED to regenerate the MCP files" in capsys.readouterr().out


def test_regenerate_mcp_passes_quiet_through_and_reports_success(monkeypatch):
    import claude_mcp

    seen = {}
    monkeypatch.setattr(claude_mcp, "write", lambda **kwargs: seen.update(kwargs))

    assert deploy_configs.regenerate_mcp(quiet=True) is True
    assert seen == {"quiet": True}


def test_payload_exemption_lists_stay_in_step_with_the_files():
    payloads = _application_config_payloads()
    stale = (set(MANIFEST_FREE_PAYLOADS) | set(OVERLAY_OWNED_PAYLOADS)) - payloads
    assert not stale, f"exemption lists name files that no longer exist: {', '.join(sorted(stale))}"
    entries, _ = deploy_configs.load_manifests()
    now_managed = set(MANIFEST_FREE_PAYLOADS) & _covered_payloads(entries)
    assert not now_managed, (
        "a manifest entry now deploys these, so drop them from MANIFEST_FREE_PAYLOADS: "
        + ", ".join(sorted(now_managed))
    )


def test_deploy_prunes_live_removals_by_default(tmp_path, capsys):
    dead = tmp_path / "dead_link"
    dead.symlink_to(tmp_path / "gone")
    deploy_configs.prune_before_deploy([(str(dead), "removals:test_entry", False)])
    assert not os.path.lexists(dead)
    assert "REMOVED" in capsys.readouterr().out


def test_deploy_prune_prints_nothing_when_no_candidate_is_on_disk(tmp_path, capsys):
    deploy_configs.prune_before_deploy([(str(tmp_path / "absent"), "removals:test_entry", False)])
    assert capsys.readouterr().out == ""


def test_deploy_prune_still_skips_what_run_prune_protects(tmp_path, capsys):
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    deploy_configs.prune_before_deploy([(str(real_dir), "removals:test_entry", False)])
    assert real_dir.is_dir()
    assert "SKIP" in capsys.readouterr().out


def test_no_prune_flag_parses():
    assert deploy_configs.parse_args(["deploy", "--no-prune"]).no_prune is True
    assert deploy_configs.parse_args(["deploy"]).no_prune is False


def _git_repo(path, remote=True):
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "-C", path, "init", "-q"], check=True)
    write_file(os.path.join(path, "f.txt"), "x")
    subprocess.run(["git", "-C", path, "add", "."], check=True)
    subprocess.run(
        ["git", "-C", path, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        check=True,
    )
    if remote:
        subprocess.run(["git", "-C", path, "remote", "add", "origin", "git@example.com:x/y.git"], check=True)
    return path


def test_directory_flag_flows_from_removals_entry(monkeypatch, fake_home):
    _removals(monkeypatch, [
        {"name": "dead_repo", "dest": {"darwin": "~/gone-repo"}, "directory": True},
        {"name": "dead_file", "dest": {"darwin": "~/.gone-file"}},
    ])
    candidates = deploy_configs.build_prune_candidates([], "darwin", "ENVY")
    assert [(os.path.basename(dest), allow) for dest, _, allow in candidates] == [
        (".gone-file", False), ("gone-repo", True),
    ]


def test_prune_directory_removes_only_a_clean_remoted_git_checkout(tmp_path, capsys):
    repo = _git_repo(str(tmp_path / "clean_repo"))
    deploy_configs.run_prune([(repo, "removals:x", True)], apply_changes=True)
    assert not os.path.exists(repo)
    assert "REMOVED" in capsys.readouterr().out


def test_prune_directory_skips_dirty_checkout_and_plain_dirs(tmp_path, capsys):
    dirty = _git_repo(str(tmp_path / "dirty_repo"))
    write_file(os.path.join(dirty, "uncommitted.txt"), "wip")
    plain = str(tmp_path / "plain_dir")
    os.makedirs(plain)
    deploy_configs.run_prune(
        [(dirty, "removals:x", True), (plain, "removals:y", True)], apply_changes=True
    )
    out = capsys.readouterr().out
    assert os.path.isdir(dirty) and "uncommitted changes" in out
    assert os.path.isdir(plain) and "not a git checkout" in out


def test_prune_directory_never_deletes_a_remoteless_origin_hub(tmp_path, capsys):
    hub = _git_repo(str(tmp_path / "hub_repo"), remote=False)
    deploy_configs.run_prune([(hub, "removals:x", True)], apply_changes=True)
    assert os.path.isdir(hub)
    assert "NO remote" in capsys.readouterr().out


def test_prune_directory_without_flag_still_refuses_git_repos(tmp_path, capsys):
    repo = _git_repo(str(tmp_path / "unflagged_repo"))
    deploy_configs.run_prune([(repo, "removals:x", False)], apply_changes=True)
    assert os.path.isdir(repo)
    assert "real directory" in capsys.readouterr().out
