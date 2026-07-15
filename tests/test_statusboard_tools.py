# %%
# Imports #

import json
import os

import config_test_utils  # noqa F401
import pytest
import yaml
from utils import statusboard_tools

# %%
# Helpers #


def write_yaml(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        yaml.safe_dump(payload, file_handle)
    return path


def make_credentials_repo(root, context, panels=None, hosts=None):
    """Create a fake <context>_credentials repo with optional statusboard config and inventory."""
    repo = os.path.join(str(root), f"{context}_credentials")
    os.makedirs(repo, exist_ok=True)
    if panels is not None:
        write_yaml(os.path.join(repo, f"{context}_statusboard.yaml"), panels)
    if hosts is not None:
        with open(os.path.join(repo, f"{context}_hosts.json"), "w", encoding="utf-8") as file_handle:
            json.dump({"hosts": hosts}, file_handle)
    return repo


SSH_PANEL = {"name": "vm_jobs", "type": "ssh_command", "host": "sshvm", "jump": "LAPTOP-1", "command": "bash x.sh"}
FF_HOSTS = [
    {"name": "LAPTOP-1", "hostname": "192.168.86.126", "user": "jason.c", "port": 2222, "aliases": ["jump1"]},
    {"name": "vm-01", "hostname": "172.20.10.101", "user": "svc_linux", "aliases": ["sshvm"]},
]


# %%
# Discovery / loading #


def test_discover_finds_overlays_and_repo_root_config(tmp_path):
    make_credentials_repo(tmp_path, "acme", panels=[])
    make_credentials_repo(tmp_path, "empty")  # no config -> contributes nothing
    repo_root = os.path.join(str(tmp_path), "dotfiles")
    write_yaml(os.path.join(repo_root, "statusboard.yaml"), [])
    configs = statusboard_tools.discover_statusboard_configs(str(tmp_path), repo_root)
    assert [os.path.basename(path) for path, _ in configs] == ["statusboard.yaml", "acme_statusboard.yaml"]


def test_load_panels_stamps_base_dir_and_defaults_interval(tmp_path):
    repo = make_credentials_repo(tmp_path, "acme", panels=[SSH_PANEL])
    panels, config_paths = statusboard_tools.load_panels(str(tmp_path))
    assert len(panels) == 1 and len(config_paths) == 1
    assert panels[0]["_base_dir"] == repo
    assert panels[0]["interval"] == statusboard_tools.DEFAULT_INTERVALS["ssh_command"]


def test_load_panels_rejects_duplicate_names(tmp_path):
    github_panel = {"name": "vm_jobs", "type": "github_prs", "token_env": "T"}
    make_credentials_repo(tmp_path, "aaa", panels=[SSH_PANEL])
    make_credentials_repo(tmp_path, "bbb", panels=[github_panel])
    with pytest.raises(ValueError, match="Duplicate statusboard panel name 'vm_jobs'"):
        statusboard_tools.load_panels(str(tmp_path))


@pytest.mark.parametrize(
    "panel, match",
    [
        ({"name": "x", "type": "nope"}, "unknown type"),
        ({"name": "x", "type": "ssh_command", "host": "h"}, "missing required keys: command"),
        ({"name": "x", "type": "github_prs"}, "missing required keys: token_env"),
        ({"name": "x", "type": "bitbucket_prs", "workspace": "w"}, "missing required keys"),
        ({"type": "ssh_command"}, "'name' and 'type'"),
    ],
)
def test_panel_validation(tmp_path, panel, match):
    make_credentials_repo(tmp_path, "acme", panels=[panel])
    with pytest.raises(ValueError, match=match):
        statusboard_tools.load_panels(str(tmp_path))


def test_load_panels_single_config_escape_hatch(tmp_path):
    config_path = write_yaml(os.path.join(str(tmp_path), "solo.yaml"), [SSH_PANEL])
    panels, config_paths = statusboard_tools.load_panels("/nonexistent", config_path=config_path)
    assert config_paths == [config_path]
    assert panels[0]["_base_dir"] == str(tmp_path)


# %%
# Host resolution / ssh argv #


def test_find_host_matches_name_and_alias_case_insensitive(tmp_path):
    repo = make_credentials_repo(tmp_path, "acme", hosts=FF_HOSTS)
    assert statusboard_tools.find_host("SSHVM", repo, str(tmp_path))["hostname"] == "172.20.10.101"
    assert statusboard_tools.find_host("laptop-1", repo, str(tmp_path))["port"] == 2222


def test_find_host_searches_other_inventories(tmp_path):
    make_credentials_repo(tmp_path, "aaa", hosts=FF_HOSTS)
    other = make_credentials_repo(tmp_path, "bbb", hosts=[])
    assert statusboard_tools.find_host("sshvm", other, str(tmp_path))["user"] == "svc_linux"


def test_find_host_unknown_raises(tmp_path):
    repo = make_credentials_repo(tmp_path, "acme", hosts=FF_HOSTS)
    with pytest.raises(ValueError, match="Host 'ghost' not found"):
        statusboard_tools.find_host("ghost", repo, str(tmp_path))


def test_build_ssh_argv_with_jump_and_ports(tmp_path):
    repo = make_credentials_repo(tmp_path, "acme", hosts=FF_HOSTS)
    panel = dict(SSH_PANEL, _base_dir=repo)
    argv = statusboard_tools.build_ssh_argv(panel, str(tmp_path), local_hostname="ENVY")
    assert argv[0] == "ssh"
    assert argv[argv.index("-J") + 1] == "jason.c@192.168.86.126:2222"
    assert argv[-2:] == ["svc_linux@172.20.10.101", "bash x.sh"]


def test_build_ssh_argv_skips_jump_when_running_on_jump_host(tmp_path):
    repo = make_credentials_repo(tmp_path, "acme", hosts=FF_HOSTS)
    panel = dict(SSH_PANEL, _base_dir=repo)
    argv = statusboard_tools.build_ssh_argv(panel, str(tmp_path), local_hostname="LAPTOP-1.local")
    assert "-J" not in argv


def test_build_ssh_argv_target_port(tmp_path):
    hosts = [{"name": "boxy", "hostname": "10.0.0.5", "user": "me", "port": 2200}]
    repo = make_credentials_repo(tmp_path, "acme", hosts=hosts)
    panel = {"name": "p", "type": "ssh_command", "host": "boxy", "command": "uptime", "_base_dir": repo}
    argv = statusboard_tools.build_ssh_argv(panel, str(tmp_path))
    assert argv[argv.index("-p") + 1] == "2200"
    assert "-J" not in argv


# %%
# Secrets #


def test_resolve_secret_environment_wins(tmp_path, monkeypatch):
    env_file = os.path.join(str(tmp_path), "x.env")
    with open(env_file, "w", encoding="utf-8") as file_handle:
        file_handle.write("MY_TOKEN=from_file\n")
    panel = {"name": "p", "token_env": "MY_TOKEN", "env_file": "x.env", "_base_dir": str(tmp_path)}
    monkeypatch.setenv("MY_TOKEN", "from_env")
    assert statusboard_tools.resolve_secret(panel, "token_env") == "from_env"
    monkeypatch.delenv("MY_TOKEN")
    assert statusboard_tools.resolve_secret(panel, "token_env") == "from_file"


def test_resolve_secret_missing_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("MY_TOKEN", raising=False)
    panel = {"name": "p", "token_env": "MY_TOKEN", "_base_dir": str(tmp_path)}
    with pytest.raises(ValueError, match="MY_TOKEN is not set"):
        statusboard_tools.resolve_secret(panel, "token_env")


# %%
# Fetch dispatch #


def test_fetch_panel_never_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("NOPE_TOKEN", raising=False)
    panel = {"name": "p", "type": "github_prs", "token_env": "NOPE_TOKEN", "_base_dir": str(tmp_path)}
    result = statusboard_tools.fetch_panel(panel, str(tmp_path))
    assert result.ok is False
    assert "NOPE_TOKEN" in result.body


# %%
