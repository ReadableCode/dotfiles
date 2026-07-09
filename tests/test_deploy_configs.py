# %%
# Imports #

import os

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
        '{"hosts": [{"name": "Envy"}, {"name": "envy.asusrouter"}, {"name": "FFLAP-2229"}]}\n',
    )
    hostnames = load_inventory_hostnames(inventory_path)
    assert hostnames == {"ENVY", "FFLAP-2229"}


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
        str(overlay_tree / "dotfiles" / "deploy_manifest.yaml"),
        [{"name": "a", "repo": "f1", "dest": {"darwin": "~/.f1"}, "hosts": ["ENVY", "ACMEBOX"]}],
    )
    entries, _ = deploy_configs.load_manifests()  # hosts from different inventories both resolve
    assert entries[0]["hosts"] == ["ENVY", "ACMEBOX"]

    write_manifest_at(
        str(overlay_tree / "dotfiles" / "deploy_manifest.yaml"),
        [{"name": "a", "repo": "f1", "dest": {"darwin": "~/.f1"}, "hosts": ["NOSUCHBOX"]}],
    )
    with pytest.raises(ValueError, match="NOSUCHBOX"):
        deploy_configs.load_manifests()


def test_hosts_validation_skipped_when_no_inventory_exists(overlay_tree):
    # no *_credentials repo declares an inventory -> machine without credentials repos
    write_manifest_at(
        str(overlay_tree / "dotfiles" / "deploy_manifest.yaml"),
        [{"name": "a", "repo": "f1", "dest": {"darwin": "~/.f1"}, "hosts": ["GHOSTBOX"]}],
    )
    entries, _ = deploy_configs.load_manifests()
    assert entries[0]["hosts"] == ["GHOSTBOX"]


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
        # a repo path may exist as-is, or only as <base>.<host-or-platform>.<ext> variants
        assert os.path.exists(repo_path) or deploy_configs._any_variant_exists(repo_path), (
            f"manifest entry {entry['name']} points at missing repo path {repo_path} (no variants either)"
        )
        if entry.get("method", "symlink") != "none":
            dests = entry.get("dest") or {}
            assert dests, f"manifest entry {entry['name']} has no dest and is not method: none"
            assert set(dests) <= {"darwin", "linux", "windows"}


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
    assert deploy_configs.host_allowed(entry, "ENVY.ASUSROUTER")
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
    assert plan[0]["repo"] == os.path.join("/repo", "f1")
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
    assert deploy_configs.short_host_token("ENVY.ASUSROUTER") == "envy"
    assert deploy_configs.short_host_token("MACBOOKPROM5") == "macbookprom5"
    assert deploy_configs.short_host_token(None) == ""


def test_resolve_repo_variant_prefers_host_then_platform_then_bare(tmp_path):
    bare = write_file(str(tmp_path / "settings.json"), "bare")
    mac = write_file(str(tmp_path / "settings.mac.json"), "mac")
    host = write_file(str(tmp_path / "settings.envy.json"), "host")
    assert deploy_configs.resolve_repo_variant(bare, "ENVY.ASUSROUTER", "darwin") == (host, True)
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
    dest = deploy_configs.resolve_dest(entry, "darwin", "ENVY.ASUSROUTER", repo_root="/parent/dotfiles")
    assert dest == "/parent/envy.code-workspace"


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
    plan = deploy_configs.build_plan(entries, "darwin", "ENVY.ASUSROUTER", repo_root=repo_root)
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
    monkeypatch.setattr(deploy_configs, "get_uppercase_hostname", lambda: "ENVY.ASUSROUTER")
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
    # for backup_system_file (backups are copies by design), which lives outside
    # the Deploy section
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
