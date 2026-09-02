# %%
# Imports #

import json
import os
import stat
import subprocess

import config_test_utils  # noqa F401
import pytest
import yaml
from src import claude_mcp
from utils import mcpservers_tools as mtools

# %%
# Helpers #


def write_yaml(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        yaml.safe_dump(payload, file_handle)
    return path


def make_credentials_repo(root, context, servers=None, env=None):
    """Create a fake <context>_credentials repo with an optional MCP declaration and env file."""
    repo = os.path.join(str(root), f"{context}_credentials")
    os.makedirs(repo, exist_ok=True)
    if servers is not None:
        write_yaml(os.path.join(repo, f"{context}_{mtools.MCP_CONFIG_NAME}"), servers)
    if env:
        with open(os.path.join(repo, f"{context}.env"), "w", encoding="utf-8") as file_handle:
            file_handle.writelines(f"{key}={value}\n" for key, value in env.items())
    return repo


def make_working_repo(root, name, servers=None):
    """
    A cloned sibling that is NOT a *_credentials repo. It opts into deploy
    discovery by naming its declaration after its own directory, exactly as
    overlay manifests do.
    """
    repo = os.path.join(str(root), name)
    os.makedirs(repo, exist_ok=True)
    if servers is not None:
        write_yaml(os.path.join(repo, f"{name}_{mtools.MCP_CONFIG_NAME}"), servers)
    return repo


def make_repo_root(root, servers=None):
    repo_root = os.path.join(str(root), "dotfiles")
    os.makedirs(repo_root, exist_ok=True)
    if servers is not None:
        write_yaml(os.path.join(repo_root, mtools.MCP_CONFIG_NAME), servers)
    return repo_root


GOOGLE_SERVER = {
    "name": "google",
    "command": "uv",
    "args": ["run", "--project", "{repo_root}", "python", "{repo_root}/src/google_mcp.py"],
}
JIRA_SERVER = {
    "name": "jira",
    "command": "npx",
    "args": ["-y", "mcp-jira-cloud"],
    "env": {"JIRA_BASE_URL": "https://example.atlassian.net"},
    "env_secrets": {"JIRA_API_TOKEN": "JIRA_TOKEN"},
    "env_file": "acme.env",
}


def parse_one(tmp_path, server):
    """Run a single declaration through the real parser, returning the parsed server."""
    repo_root = make_repo_root(tmp_path, servers=[server])
    servers, _ = mtools.load_servers(str(tmp_path), repo_root)
    return servers[0]


# %%
# Discovery #


def test_discover_finds_the_repo_root_config_and_every_credentials_overlay(tmp_path):
    repo_root = make_repo_root(tmp_path, servers=[GOOGLE_SERVER])
    make_credentials_repo(tmp_path, "acme", servers=[])
    make_credentials_repo(tmp_path, "empty")  # no declaration -> contributes nothing

    found = mtools.discover_mcp_configs(str(tmp_path), repo_root)

    assert [os.path.basename(path) for path, _ in found] == ["mcp_servers.yaml", "acme_mcp_servers.yaml"]
    assert [base for _, base in found] == [repo_root, os.path.join(str(tmp_path), "acme_credentials")]


def test_discover_includes_any_cloned_repo_that_declares_servers_not_just_credentials_repos(tmp_path):
    repo_root = make_repo_root(tmp_path, servers=[GOOGLE_SERVER])
    make_credentials_repo(tmp_path, "acme", servers=[JIRA_SERVER], env={"JIRA_TOKEN": "t"})
    make_working_repo(tmp_path, "acme-etl", servers=[{"name": "etl", "command": "acme-etl-mcp"}])
    make_working_repo(tmp_path, "no-opt-in")  # cloned but declares nothing

    found = mtools.discover_mcp_configs(str(tmp_path), repo_root)

    # the machine gets what is cloned on it, whatever kind of repo declared it
    assert [os.path.basename(path) for path, _ in found] == [
        "mcp_servers.yaml",
        "acme-etl_mcp_servers.yaml",
        "acme_mcp_servers.yaml",
    ]


def test_discover_tolerates_a_repo_with_no_declaration_at_all(tmp_path):
    repo_root = make_repo_root(tmp_path)  # dotfiles declares nothing

    assert mtools.discover_mcp_configs(str(tmp_path), repo_root) == []


def test_load_merges_declarations_and_stamps_where_each_came_from(tmp_path):
    repo_root = make_repo_root(tmp_path, servers=[GOOGLE_SERVER])
    credentials = make_credentials_repo(tmp_path, "acme", servers=[JIRA_SERVER], env={"JIRA_TOKEN": "t"})

    servers, config_paths = mtools.load_servers(str(tmp_path), repo_root)

    assert [server["name"] for server in servers] == ["google", "jira"]
    # _base_dir is the DECLARING repo, which is what env_file resolves against
    assert servers[0]["_base_dir"] == repo_root
    assert servers[1]["_base_dir"] == credentials
    assert len(config_paths) == 2


def test_load_rejects_the_same_server_name_declared_by_two_repos(tmp_path):
    repo_root = make_repo_root(tmp_path, servers=[GOOGLE_SERVER])
    make_credentials_repo(tmp_path, "acme", servers=[dict(GOOGLE_SERVER, command="python")])

    with pytest.raises(ValueError, match="Duplicate MCP server name 'google'"):
        mtools.load_servers(str(tmp_path), repo_root)


def test_load_reads_only_the_explicit_config_when_one_is_given(tmp_path):
    repo_root = make_repo_root(tmp_path, servers=[GOOGLE_SERVER])
    make_credentials_repo(tmp_path, "acme", servers=[JIRA_SERVER], env={"JIRA_TOKEN": "t"})
    only = os.path.join(repo_root, mtools.MCP_CONFIG_NAME)

    servers, config_paths = mtools.load_servers(str(tmp_path), repo_root, config_path=only)

    assert [server["name"] for server in servers] == ["google"]
    assert config_paths == [only]


# %%
# Validation #


def test_an_empty_declaration_file_is_valid(tmp_path):
    repo_root = make_repo_root(tmp_path)
    write_yaml(os.path.join(repo_root, mtools.MCP_CONFIG_NAME), [])

    assert mtools.load_servers(str(tmp_path), repo_root)[0] == []


@pytest.mark.parametrize(
    "server, message",
    [
        ({"command": "uv"}, "missing name"),
        ({"name": "google"}, "missing command"),
        ({"name": "google", "command": "uv", "argz": []}, "unknown keys: argz"),
        ({"name": "google", "command": "uv", "args": "run"}, "non-string args"),
        ({"name": "google", "command": "uv", "args": ["run", 3]}, "non-string args"),
        ({"name": "google", "command": "uv", "env": {"PORT": 8080}}, "non-string env map"),
        ({"name": "google", "command": "uv", "env_secrets": {"T": 1}}, "non-string env_secrets map"),
    ],
)
def test_a_malformed_declaration_names_the_problem_and_the_file(tmp_path, server, message):
    repo_root = make_repo_root(tmp_path, servers=[server])

    with pytest.raises(ValueError, match=message):
        mtools.load_servers(str(tmp_path), repo_root)


def test_a_declaration_file_that_is_not_a_list_is_rejected(tmp_path):
    repo_root = make_repo_root(tmp_path)
    write_yaml(os.path.join(repo_root, mtools.MCP_CONFIG_NAME), {"google": GOOGLE_SERVER})

    with pytest.raises(ValueError, match="must be a YAML list"):
        mtools.load_servers(str(tmp_path), repo_root)


def test_env_secrets_without_an_env_file_is_rejected_unless_the_vars_are_already_set(tmp_path, monkeypatch):
    server = {"name": "jira", "command": "npx", "env_secrets": {"JIRA_API_TOKEN": "JIRA_TOKEN"}}
    monkeypatch.delenv("JIRA_TOKEN", raising=False)

    with pytest.raises(ValueError, match="declares env_secrets but no env_file"):
        parse_one(tmp_path, server)

    monkeypatch.setenv("JIRA_TOKEN", "from-environment")
    assert parse_one(tmp_path, server)["name"] == "jira"


# %%
# Token expansion #


def test_expand_tokens_reaches_into_lists_and_dicts_and_leaves_other_types_alone():
    value = {
        "command": "{repo_root}/bin/tool",
        "args": ["--root", "{repo_parent}", "--keep", 7],
        "env": {"HOME_ISH": "{repo_parent}/home"},
    }

    expanded = mtools.expand_tokens(value, "/clones/dotfiles", "/clones")

    assert expanded == {
        "command": "/clones/dotfiles/bin/tool",
        "args": ["--root", "/clones", "--keep", 7],
        "env": {"HOME_ISH": "/clones/home"},
    }


def test_expand_tokens_passes_unknown_braces_through_instead_of_raising():
    # str.replace, not str.format: a command line may legitimately contain braces
    assert mtools.expand_tokens("awk '{print $1}' {repo_root}", "/clones/dotfiles", "/clones") == (
        "awk '{print $1}' /clones/dotfiles"
    )


# %%
# Rendering #


def test_render_expands_tokens_and_omits_keys_the_declaration_did_not_set():
    rendered = mtools.render_server(dict(GOOGLE_SERVER, _base_dir="/clones/dotfiles"), "/clones/dotfiles", "/clones")

    assert rendered == {
        "command": "uv",
        "args": ["run", "--project", "/clones/dotfiles", "python", "/clones/dotfiles/src/google_mcp.py"],
    }
    assert "env" not in rendered


def test_render_resolves_a_secret_out_of_the_declaring_repos_env_file(tmp_path):
    credentials = make_credentials_repo(tmp_path, "acme", servers=[JIRA_SERVER], env={"JIRA_TOKEN": "live-token"})

    rendered = mtools.render_server(dict(JIRA_SERVER, _base_dir=credentials), str(tmp_path / "dotfiles"), str(tmp_path))

    assert rendered["env"] == {"JIRA_BASE_URL": "https://example.atlassian.net", "JIRA_API_TOKEN": "live-token"}


def test_render_prefers_the_real_environment_over_the_env_file(tmp_path, monkeypatch):
    credentials = make_credentials_repo(tmp_path, "acme", servers=[JIRA_SERVER], env={"JIRA_TOKEN": "from-file"})
    monkeypatch.setenv("JIRA_TOKEN", "from-environment")

    rendered = mtools.render_server(dict(JIRA_SERVER, _base_dir=credentials), str(tmp_path / "dotfiles"), str(tmp_path))

    assert rendered["env"]["JIRA_API_TOKEN"] == "from-environment"


def test_redaction_never_resolves_the_secret_it_hides(tmp_path, monkeypatch):
    # no env file, no env var: redaction has to be safe to run with nothing to read
    monkeypatch.delenv("JIRA_TOKEN", raising=False)
    server = dict(JIRA_SERVER, _base_dir=str(tmp_path), env_file=None)

    rendered = mtools.render_server(server, str(tmp_path / "dotfiles"), str(tmp_path), redact=True)

    assert rendered["env"]["JIRA_API_TOKEN"] == mtools.REDACTED
    assert rendered["env"]["JIRA_BASE_URL"] == "https://example.atlassian.net"  # literals stay readable


def test_a_missing_secret_names_the_server_rather_than_writing_an_empty_value(tmp_path, monkeypatch):
    credentials = make_credentials_repo(tmp_path, "acme", servers=[JIRA_SERVER], env={"OTHER": "x"})
    monkeypatch.delenv("JIRA_TOKEN", raising=False)

    with pytest.raises(ValueError, match="'jira': env var JIRA_TOKEN is not set"):
        mtools.render_server(dict(JIRA_SERVER, _base_dir=credentials), str(tmp_path / "dotfiles"), str(tmp_path))


def test_build_document_sorts_servers_so_the_generated_file_diffs_cleanly():
    servers = [
        dict(JIRA_SERVER, _base_dir="/clones/acme_credentials", env_secrets={}),
        dict(GOOGLE_SERVER, _base_dir="/clones/dotfiles"),
    ]

    document = mtools.build_document(servers, "/clones/dotfiles", "/clones")

    assert list(document["mcpServers"]) == ["google", "jira"]


# %%
# Writing #


def test_write_reports_created_then_unchanged_then_updated(tmp_path):
    dest = str(tmp_path / "nested" / mtools.GENERATED_NAME)
    document = {"mcpServers": {"google": {"command": "uv"}}}

    assert mtools.write_document(dest, document) == "created"
    assert mtools.write_document(dest, document) == "unchanged"
    assert mtools.write_document(dest, {"mcpServers": {"google": {"command": "python"}}}) == "updated"
    with open(dest, "r", encoding="utf-8") as file_handle:
        assert json.load(file_handle)["mcpServers"]["google"]["command"] == "python"


def test_the_generated_file_is_owner_only_because_it_can_hold_a_live_token(tmp_path):
    dest = str(tmp_path / mtools.GENERATED_NAME)

    mtools.write_document(dest, {"mcpServers": {}})

    assert stat.S_IMODE(os.stat(dest).st_mode) == 0o600


def test_write_replaces_a_managed_symlink_instead_of_writing_through_it(tmp_path):
    # the dest used to be a symlink into the repo; following it would rewrite a tracked file
    tracked = tmp_path / "tracked.json"
    tracked.write_text('{"mcpServers": {"jira": {"command": "npx"}}}\n', encoding="utf-8")
    dest = str(tmp_path / mtools.GENERATED_NAME)
    os.symlink(str(tracked), dest)

    assert mtools.write_document(dest, {"mcpServers": {"google": {"command": "uv"}}}) == "created"

    assert not os.path.islink(dest)
    assert "google" in open(dest, "r", encoding="utf-8").read()
    assert "jira" in tracked.read_text(encoding="utf-8")  # the repo file is untouched


def test_write_replaces_a_dangling_symlink(tmp_path):
    dest = str(tmp_path / mtools.GENERATED_NAME)
    os.symlink(str(tmp_path / "gone.json"), dest)

    assert mtools.write_document(dest, {"mcpServers": {}}) == "created"
    assert os.path.isfile(dest) and not os.path.islink(dest)


def test_an_update_rewrites_in_place_so_a_hard_link_keeps_seeing_it(tmp_path):
    # Windows deploys fall back to hard links, which share the inode: replacing
    # the file by rename would leave every linked checkout holding old content
    dest = str(tmp_path / mtools.GENERATED_NAME)
    mtools.write_document(dest, {"mcpServers": {"google": {"command": "uv"}}})
    linked = str(tmp_path / "linked.json")
    os.link(dest, linked)

    assert mtools.write_document(dest, {"mcpServers": {"google": {"command": "python"}}}) == "updated"

    assert os.stat(dest).st_ino == os.stat(linked).st_ino
    assert "python" in open(linked, "r", encoding="utf-8").read()
    assert stat.S_IMODE(os.stat(dest).st_mode) == 0o600


def test_no_temporary_file_is_left_behind(tmp_path):
    dest = str(tmp_path / mtools.GENERATED_NAME)

    mtools.write_document(dest, {"mcpServers": {}})

    assert os.listdir(str(tmp_path)) == [mtools.GENERATED_NAME]


# %%
# Entry point #


@pytest.fixture
def clones(tmp_path, monkeypatch):
    """A fake clone root: dotfiles declaring google, one credentials repo declaring jira."""
    repo_root = make_repo_root(tmp_path, servers=[GOOGLE_SERVER])
    make_credentials_repo(tmp_path, "acme", servers=[JIRA_SERVER], env={"JIRA_TOKEN": "live-token"})
    monkeypatch.setattr(claude_mcp, "REPO_ROOT", repo_root)
    monkeypatch.setattr(claude_mcp, "CREDENTIALS_ROOT", str(tmp_path))
    monkeypatch.setattr(claude_mcp, "GENERATED_DIR", os.path.join(repo_root, mtools.GENERATED_DIRNAME))
    monkeypatch.delenv("JIRA_TOKEN", raising=False)
    return tmp_path


def test_generate_writes_one_document_per_declaring_context(clones):
    # a checkout linked to acme.mcp.json must never see another context's
    # servers, so the split is by the repo that declared each server
    documents, target_dir, config_paths = claude_mcp.generate()

    assert target_dir == os.path.join(str(clones), "dotfiles", "data", "mcp")
    assert {context: list(document["mcpServers"]) for context, document in documents.items()} == {
        "dotfiles": ["google"],
        "acme": ["jira"],
    }
    assert len(config_paths) == 2


def test_a_context_that_declares_nothing_gets_no_document(clones):
    make_credentials_repo(clones, "quiet", servers=[])

    documents, _, _ = claude_mcp.generate()

    assert "quiet" not in documents


def test_write_creates_one_file_per_context_and_reports_each(clones, capsys):
    out = str(clones / "out")

    outcomes = claude_mcp.write(output_dir=out)

    assert outcomes == {
        os.path.join(out, "acme.mcp.json"): "created",
        os.path.join(out, "dotfiles.mcp.json"): "created",
    }
    printed = capsys.readouterr().out
    assert "created" in printed and "acme.mcp.json (jira)" in printed and "dotfiles.mcp.json (google)" in printed
    with open(os.path.join(out, "acme.mcp.json"), encoding="utf-8") as handle:
        assert list(json.load(handle)["mcpServers"]) == ["jira"]


def test_write_removes_the_file_of_a_context_no_longer_cloned(clones, capsys):
    out = str(clones / "out")
    gone = os.path.join(out, "old.mcp.json")
    os.makedirs(out)
    with open(gone, "w", encoding="utf-8") as handle:
        handle.write("{}")

    outcomes = claude_mcp.write(output_dir=out)

    assert outcomes[gone] == "removed"
    assert not os.path.exists(gone)
    assert "removed" in capsys.readouterr().out


def test_check_exits_non_zero_while_stale_and_zero_once_written(clones):
    out = str(clones / "out")

    assert claude_mcp.main(["--check", "--output", out]) == 1
    claude_mcp.write(quiet=True, output_dir=out)
    assert claude_mcp.main(["--check", "--output", out]) == 0


def test_check_flags_a_stray_file_for_a_context_that_is_gone(clones):
    out = str(clones / "out")
    claude_mcp.write(quiet=True, output_dir=out)
    with open(os.path.join(out, "old.mcp.json"), "w", encoding="utf-8") as handle:
        handle.write("{}")

    assert claude_mcp.main(["--check", "--output", out]) == 1


def test_print_names_the_repos_that_declared_nothing(clones, capsys):
    make_credentials_repo(clones, "quiet")  # cloned, but declares no MCP server

    claude_mcp.main(["--print", "--output", str(clones / "out")])

    printed = capsys.readouterr().out
    # relative to the clone root, so the line names the repo that declared it
    assert "declared by dotfiles/mcp_servers.yaml" in printed
    assert "declared by acme_credentials/acme_mcp_servers.yaml" in printed
    # the distinction that matters: scanned-and-silent, not simply absent
    assert "scanned, no mcp_servers.yaml of its own: quiet_credentials" in printed
    assert "# acme.mcp.json" in printed and "# dotfiles.mcp.json" in printed


def test_silent_overlay_dirs_ignores_the_repos_that_did_declare(tmp_path):
    make_repo_root(tmp_path, servers=[GOOGLE_SERVER])
    make_credentials_repo(tmp_path, "acme", servers=[JIRA_SERVER], env={"JIRA_TOKEN": "t"})
    make_credentials_repo(tmp_path, "quiet")
    _, config_paths = mtools.load_servers(str(tmp_path), os.path.join(str(tmp_path), "dotfiles"))

    silent = mtools.silent_overlay_dirs(str(tmp_path), config_paths)

    assert [os.path.basename(path) for path in silent] == ["quiet_credentials"]


def test_print_redacts_secrets_and_writes_nothing(clones, capsys):
    out = str(clones / "out")

    assert claude_mcp.main(["--print", "--output", out]) == 0

    printed = capsys.readouterr().out
    assert mtools.REDACTED in printed
    assert "live-token" not in printed
    assert not os.path.exists(out)


# %%


# %%
# Upstream sync warnings #


def _run_git(repo_dir, *args):
    subprocess.run(
        ["git", "-C", repo_dir, "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True, capture_output=True,
    )


def _tracked_clone(tmp_path, name):
    """A clone with an upstream, one pushed commit containing a declaration file."""
    origin = str(tmp_path / f"{name}_origin.git")
    subprocess.run(["git", "init", "-q", "--bare", origin], check=True, capture_output=True)
    clone = str(tmp_path / name)
    subprocess.run(["git", "clone", "-q", origin, clone], check=True, capture_output=True)
    config_path = os.path.join(clone, f"{name}_mcp_servers.yaml")
    with open(config_path, "w", encoding="utf-8") as handle:
        handle.write("[]\n")
    _run_git(clone, "add", ".")
    _run_git(clone, "commit", "-qm", "declare")
    _run_git(clone, "push", "-q", "origin", "HEAD")
    return clone, config_path


def test_sync_warnings_quiet_when_clone_matches_upstream(tmp_path):
    _, config_path = _tracked_clone(tmp_path, "acme_credentials")
    assert mtools.sync_warnings([config_path]) == []


def test_sync_warnings_flag_unpushed_declarations(tmp_path):
    clone, config_path = _tracked_clone(tmp_path, "acme_credentials")
    with open(config_path, "a", encoding="utf-8") as handle:
        handle.write("# changed\n")
    _run_git(clone, "commit", "-aqm", "unpushed declaration change")
    warnings = mtools.sync_warnings([config_path])
    assert len(warnings) == 1
    assert "1 unpushed commit" in warnings[0]
    assert "acme_credentials" in warnings[0]
    assert "invisible to every other machine" in warnings[0]


def test_sync_warnings_flag_a_stale_clone_after_fetch(tmp_path):
    clone, config_path = _tracked_clone(tmp_path, "acme_credentials")
    other = str(tmp_path / "other")
    subprocess.run(["git", "clone", "-q", str(tmp_path / "acme_credentials_origin.git"), other],
                   check=True, capture_output=True)
    with open(os.path.join(other, "acme_credentials_mcp_servers.yaml"), "a", encoding="utf-8") as handle:
        handle.write("# newer\n")
    _run_git(other, "commit", "-aqm", "newer upstream declaration")
    _run_git(other, "push", "-q", "origin", "HEAD")
    _run_git(clone, "fetch", "-q")
    warnings = mtools.sync_warnings([config_path])
    assert len(warnings) == 1
    assert "behind its upstream" in warnings[0]


def test_sync_warnings_skip_repos_with_no_upstream(tmp_path):
    hub = str(tmp_path / "hub_credentials")
    os.makedirs(hub)
    subprocess.run(["git", "-C", hub, "init", "-q"], check=True, capture_output=True)
    config_path = os.path.join(hub, "hub_credentials_mcp_servers.yaml")
    with open(config_path, "w", encoding="utf-8") as handle:
        handle.write("[]\n")
    _run_git(hub, "add", ".")
    _run_git(hub, "commit", "-qm", "hub of record")
    assert mtools.sync_warnings([config_path]) == []
