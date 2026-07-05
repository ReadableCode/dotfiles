# %%
# Imports #

import os

import config_test_utils  # noqa F401
import pytest
import yaml
from src import deploy_configs

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


def test_real_manifest_is_valid_and_repo_paths_exist():
    entries = deploy_configs.load_manifest()
    names = [entry["name"] for entry in entries]
    assert len(names) == len(set(names)), "manifest entry names must be unique"
    for entry in entries:
        repo_path = os.path.join(deploy_configs.REPO_ROOT, entry["repo"])
        assert os.path.exists(repo_path), f"manifest entry {entry['name']} points at missing repo path {repo_path}"
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


def test_windows_symlink_denied_falls_back_to_copy(tmp_path, monkeypatch):
    repo_file = write_file(str(tmp_path / "repo" / "conf"), "repo content")
    dest = str(tmp_path / "sys" / "conf")

    def deny_symlink(src, dst, **kwargs):
        raise OSError("A required privilege is not held by the client")

    monkeypatch.setattr(deploy_configs, "system", "Windows")
    monkeypatch.setattr(deploy_configs.os, "symlink", deny_symlink)
    result = deploy_configs.deploy_config(repo_file, dest)
    assert result == "copied"
    assert os.path.isfile(dest) and not os.path.islink(dest)
    with open(dest, encoding="utf-8") as file_handle:
        assert file_handle.read() == "repo content"


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


def test_no_hard_links_in_source():
    source_path = deploy_configs.__file__.replace(".pyc", ".py")
    with open(source_path, encoding="utf-8") as file_handle:
        assert "os.link(" not in file_handle.read()


def test_case3_backup_goes_to_backup_root_not_repo_tree(tmp_path):
    repo_root = str(tmp_path / "repo")
    backup_root = os.path.join(repo_root, "data", "config_backups")
    repo_file = write_file(os.path.join(repo_root, "application_configs", "app", "conf"), "repo version")
    dest = write_file(str(tmp_path / "sys" / "conf"), "system version")

    result = deploy_configs.deploy_config(
        repo_file, dest, backup_into_repo=True, backup_root=backup_root, repo_root=repo_root
    )

    assert result == "ingested"
    assert os.path.islink(dest)
    with open(repo_file, encoding="utf-8") as file_handle:
        assert file_handle.read() == "system version"
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
    result = deploy_configs.deploy_config(repo_file, dest, backup_into_repo=False)
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


def test_copy_method_refreshes_diverged_copy(tmp_path):
    repo_root = str(tmp_path / "repo")
    backup_root = os.path.join(repo_root, "data", "config_backups")
    repo_file = write_file(os.path.join(repo_root, "conf"), "repo version")
    dest = write_file(str(tmp_path / "sys" / "conf"), "stale copy")
    result = deploy_configs.deploy_config(
        repo_file, dest, method="copy", backup_root=backup_root, repo_root=repo_root
    )
    assert result == "copied"
    assert not os.path.islink(dest)
    with open(dest, encoding="utf-8") as file_handle:
        assert file_handle.read() == "repo version"
    # matching copy is a no-op on the next run
    assert deploy_configs.deploy_config(repo_file, dest, method="copy") == "noop"


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


def test_classify_copy_ok_and_diverged(tmp_path):
    repo_file = write_file(str(tmp_path / "repo" / "conf"), "content")
    dest_match = write_file(str(tmp_path / "sys" / "match"), "content")
    dest_diff = write_file(str(tmp_path / "sys" / "diff"), "stale")
    assert deploy_configs.classify_entry(repo_file, dest_match, method="copy")[0] == "OK"
    assert deploy_configs.classify_entry(repo_file, dest_diff, method="copy")[0] == "DIVERGED"


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


def test_dry_run_plans_without_touching_filesystem(tmp_path, fake_home, monkeypatch, capsys):
    manifest_path = _temp_manifest(tmp_path, monkeypatch)
    dest = os.path.join(str(fake_home), "config_dir", "conf")

    exit_code = deploy_configs.main(["--dry-run", "--manifest", manifest_path])
    output = capsys.readouterr().out
    assert exit_code == 0
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
