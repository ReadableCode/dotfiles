"""Unit tests for src/ssh_aliases.py — the one ssh alias generator both shells eval."""

import json
import os

import config_test_utils  # noqa F401
import pytest
from src import ssh_aliases

# ---------------------------------------------------------------- helpers


def write_inventory(root, context, hosts, filename=None):
    """Create <root>/<context>_credentials/<context>_hosts.json holding hosts."""
    credentials_dir = os.path.join(str(root), "{}_credentials".format(context))
    os.makedirs(credentials_dir, exist_ok=True)
    path = os.path.join(credentials_dir, filename or "{}_hosts.json".format(context))
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump({"hosts": hosts}, file_handle)
    return path


def aliases(root, local_hostname="somewhere-else", include_vnc=False):
    """The generated alias set as a dict, the way a shell would end up with it."""
    return dict(ssh_aliases.collect_aliases(str(root), ssh_aliases.short_name(local_hostname), include_vnc))


# ---------------------------------------------------------------- ssh commands


def test_plain_host_builds_a_bare_ssh_alias(tmp_path):
    host = {"name": "box", "hostname": "10.0.0.5", "user": "jason", "aliases": ["sshbox"]}
    write_inventory(tmp_path, "personal", [host])
    assert aliases(tmp_path) == {"sshbox": "ssh jason@10.0.0.5"}


def test_port_is_carried_into_the_alias(tmp_path):
    host = {"name": "box", "hostname": "10.0.0.5", "user": "jason", "port": 2222, "aliases": ["sshbox"]}
    write_inventory(tmp_path, "personal", [host])
    assert aliases(tmp_path)["sshbox"] == "ssh -p 2222 jason@10.0.0.5"


def test_ssh_user_wins_over_user_and_name_stands_in_for_hostname(tmp_path):
    host = {"name": "box.local", "user": "generic", "ssh_user": "svc", "aliases": ["sshbox"]}
    write_inventory(tmp_path, "personal", [host])
    assert aliases(tmp_path)["sshbox"] == "ssh svc@box.local"


def test_host_with_no_user_makes_no_ssh_alias(tmp_path):
    write_inventory(tmp_path, "personal", [{"name": "box", "hostname": "10.0.0.5", "aliases": ["sshbox"]}])
    assert aliases(tmp_path) == {}


def test_every_alias_of_a_host_gets_its_own_definition(tmp_path):
    write_inventory(tmp_path, "personal", [{"name": "box", "user": "jason", "aliases": ["sshbox", "b"]}])
    assert sorted(aliases(tmp_path)) == ["b", "sshbox"]


# ---------------------------------------------------------------- jump hosts


JUMP_INVENTORY = [
    {"name": "gateway", "hostname": "192.168.1.9", "user": "jason", "port": 2222, "aliases": ["sshgw"]},
    {"name": "vm", "hostname": "172.20.10.101", "user": "svc", "aliases": ["sshvm"], "jump": "gateway"},
]


def test_jump_hop_is_baked_into_the_alias(tmp_path):
    write_inventory(tmp_path, "acme", JUMP_INVENTORY)
    assert aliases(tmp_path)["sshvm"] == "ssh -J jason@192.168.1.9:2222 svc@172.20.10.101"


def test_jump_can_name_the_hop_by_alias_instead_of_name(tmp_path):
    hosts = [dict(JUMP_INVENTORY[0]), dict(JUMP_INVENTORY[1], jump="SSHGW")]
    write_inventory(tmp_path, "acme", hosts)
    assert aliases(tmp_path)["sshvm"] == "ssh -J jason@192.168.1.9:2222 svc@172.20.10.101"


def test_jump_hop_is_dropped_when_generated_on_the_jump_machine(tmp_path):
    write_inventory(tmp_path, "acme", JUMP_INVENTORY)
    # The jump host holds the VPN, so from there the target is direct. The
    # local name is matched on its short, case-insensitive form.
    assert aliases(tmp_path, local_hostname="GATEWAY.corp.example")["sshvm"] == "ssh svc@172.20.10.101"


def test_portless_jump_host_yields_a_hop_without_a_port(tmp_path):
    hosts = [{"name": "gateway", "hostname": "192.168.1.9", "user": "jason", "aliases": ["sshgw"]}, JUMP_INVENTORY[1]]
    write_inventory(tmp_path, "acme", hosts)
    assert aliases(tmp_path)["sshvm"] == "ssh -J jason@192.168.1.9 svc@172.20.10.101"


def test_unresolvable_jump_token_is_ignored(tmp_path):
    write_inventory(tmp_path, "acme", [dict(JUMP_INVENTORY[1], jump="nowhere")])
    assert aliases(tmp_path)["sshvm"] == "ssh svc@172.20.10.101"


def test_jump_is_resolved_within_one_inventory_only(tmp_path):
    write_inventory(tmp_path, "acme", [JUMP_INVENTORY[1]])
    write_inventory(tmp_path, "personal", [JUMP_INVENTORY[0]])
    # The gateway lives in the OTHER context's inventory, so there is no hop to make.
    assert aliases(tmp_path)["sshvm"] == "ssh svc@172.20.10.101"


# ---------------------------------------------------------------- vnc aliases


VNC_HOST = {
    "name": "envy",
    "hostname": "192.168.1.20",
    "user": "jason",
    "aliases": ["sshenvy"],
    "vnc_aliases": ["vncenvy"],
}


def test_vnc_aliases_are_macos_only(tmp_path):
    write_inventory(tmp_path, "personal", [VNC_HOST])
    assert "vncenvy" not in aliases(tmp_path, include_vnc=False)
    assert aliases(tmp_path, include_vnc=True)["vncenvy"] == "open vnc://jason@192.168.1.20"


def test_vnc_hostname_overrides_the_ssh_target(tmp_path):
    write_inventory(tmp_path, "personal", [dict(VNC_HOST, vnc_hostname="envy.tail1234.ts.net")])
    generated = aliases(tmp_path, include_vnc=True)
    assert generated["vncenvy"] == "open vnc://jason@envy.tail1234.ts.net"
    assert generated["sshenvy"] == "ssh jason@192.168.1.20"


def test_userless_host_still_gets_its_vnc_alias(tmp_path):
    write_inventory(tmp_path, "personal", [{"name": "tv", "hostname": "10.0.0.9", "vnc_aliases": ["vnctv"]}])
    assert aliases(tmp_path, include_vnc=True) == {"vnctv": "open vnc://10.0.0.9"}


# ---------------------------------------------------------------- discovery


def test_legacy_bare_hosts_json_is_still_read(tmp_path):
    host = {"name": "box", "user": "jason", "aliases": ["sshbox"]}
    write_inventory(tmp_path, "personal", [host], filename="hosts.json")
    assert aliases(tmp_path) == {"sshbox": "ssh jason@box"}


def test_every_credentials_repo_contributes(tmp_path):
    write_inventory(tmp_path, "personal", [{"name": "home", "user": "jason", "aliases": ["sshhome"]}])
    write_inventory(tmp_path, "acme", [{"name": "work", "user": "svc", "aliases": ["sshwork"]}])
    assert sorted(aliases(tmp_path)) == ["sshhome", "sshwork"]


def test_last_inventory_wins_a_name_collision(tmp_path):
    # find_inventory_paths sorts by directory, so personal_credentials is read
    # after acme_credentials — the same last-definition-wins a shell applies.
    write_inventory(tmp_path, "acme", [{"name": "a", "user": "svc", "aliases": ["sshbox"]}])
    write_inventory(tmp_path, "personal", [{"name": "b", "user": "jason", "aliases": ["sshbox"]}])
    assert aliases(tmp_path)["sshbox"] == "ssh jason@b"


def test_no_credentials_repos_means_no_aliases(tmp_path):
    assert aliases(tmp_path) == {}


def write_raw_inventory(root, context, text):
    credentials_dir = os.path.join(str(root), "{}_credentials".format(context))
    os.makedirs(credentials_dir, exist_ok=True)
    path = os.path.join(credentials_dir, "{}_hosts.json".format(context))
    with open(path, "w", encoding="utf-8") as file_handle:
        file_handle.write(text)
    return path


def test_unparseable_inventory_is_a_hard_error(tmp_path):
    write_raw_inventory(tmp_path, "broken", "{not json")
    write_inventory(tmp_path, "personal", [{"name": "box", "user": "jason", "aliases": ["sshbox"]}])
    # Same rule as a bad alias name: no partial-success mode. One broken file
    # costs every context its aliases, loudly, until it is fixed.
    with pytest.raises(ValueError) as raised:
        aliases(tmp_path)
    assert "broken_hosts.json" in str(raised.value)
    assert "unreadable host inventory" in str(raised.value)


def test_inventory_that_is_not_an_object_is_a_hard_error(tmp_path):
    write_raw_inventory(tmp_path, "broken", '["box"]')
    with pytest.raises(ValueError) as raised:
        aliases(tmp_path)
    assert "must be an object with a 'hosts' list" in str(raised.value)


def test_inventory_with_no_hosts_key_is_fine(tmp_path):
    # An inventory that parses but declares nothing is not an error - a
    # credentials repo may legitimately carry no hosts yet.
    write_raw_inventory(tmp_path, "empty", "{}")
    assert aliases(tmp_path) == {}


@pytest.mark.parametrize("bad_name", ["ssh box", "ssh;box", "ssh'box", "$(id)", "", "-rf"])
def test_alias_names_that_are_not_bare_words_are_a_hard_error(tmp_path, bad_name):
    # The output is eval'd by the shell, so a hostile or fat-fingered inventory
    # entry must stop the whole run — not quietly lose one alias on one machine.
    write_inventory(tmp_path, "personal", [{"name": "box", "user": "jason", "aliases": [bad_name, "sshbox"]}])
    with pytest.raises(ValueError) as raised:
        aliases(tmp_path)
    assert repr(bad_name) in str(raised.value)
    assert "personal_hosts.json" in str(raised.value)


def test_a_bad_vnc_alias_name_is_a_hard_error_too(tmp_path):
    write_inventory(tmp_path, "personal", [dict(VNC_HOST, vnc_aliases=["vnc envy"])])
    with pytest.raises(ValueError):
        aliases(tmp_path, include_vnc=True)


def test_a_bad_alias_name_stops_the_cli_with_a_nonzero_exit(tmp_path):
    # What the shells actually see: a traceback on stderr and no stdout to eval.
    write_inventory(tmp_path, "personal", [{"name": "box", "user": "jason", "aliases": ["ssh box"]}])
    with pytest.raises(ValueError):
        ssh_aliases.main(["--format", "bash", "--root", str(tmp_path), "--local-hostname", "elsewhere"])


def test_a_bad_alias_name_in_one_context_costs_every_context(tmp_path):
    # Documented blast radius: this is deliberate, not an oversight.
    write_inventory(tmp_path, "acme", [{"name": "vm", "user": "svc", "aliases": ["ssh vm"]}])
    write_inventory(tmp_path, "personal", [{"name": "box", "user": "jason", "aliases": ["sshbox"]}])
    with pytest.raises(ValueError):
        aliases(tmp_path)


# ---------------------------------------------------------------- rendering


def test_bash_rendering_quotes_the_command(tmp_path):
    assert ssh_aliases.render_bash([("sshbox", "ssh jason@box")]) == "alias sshbox='ssh jason@box'"


def test_bash_rendering_escapes_an_embedded_single_quote():
    rendered = ssh_aliases.render_bash([("sshbox", "ssh o'brien@box")])
    assert rendered == r"""alias sshbox='ssh o'\''brien@box'"""


def test_powershell_rendering_defines_a_global_function():
    rendered = ssh_aliases.render_powershell([("sshbox", "ssh jason@box")])
    assert rendered == "Set-Item -Path 'function:global:sshbox' -Value ([scriptblock]::Create('ssh jason@box')) -Force"


def test_powershell_rendering_doubles_an_embedded_single_quote():
    rendered = ssh_aliases.render_powershell([("sshbox", "ssh o'brien@box")])
    assert "'ssh o''brien@box'" in rendered


def test_a_domain_user_backslash_survives_both_renderings():
    # e.g. ssh DOMAIN\1234567@host — a literal backslash in the ssh user.
    definitions = [("sshwin", r"ssh DOMAIN\12345@winbox")]
    assert r"ssh DOMAIN\12345@winbox" in ssh_aliases.render_bash(definitions)
    assert r"ssh DOMAIN\12345@winbox" in ssh_aliases.render_powershell(definitions)


def test_both_shells_are_rendered_from_the_same_alias_set(tmp_path):
    # The point of the whole script: bash and PowerShell can differ in syntax
    # but never in which aliases exist or what they run.
    write_inventory(tmp_path, "acme", JUMP_INVENTORY)
    definitions = ssh_aliases.collect_aliases(str(tmp_path), "somewhere-else", False)
    bash_lines = ssh_aliases.render_bash(definitions).splitlines()
    powershell_lines = ssh_aliases.render_powershell(definitions).splitlines()
    assert len(bash_lines) == len(powershell_lines) == len(definitions)
    for (name, command), bash_line, powershell_line in zip(definitions, bash_lines, powershell_lines):
        assert name in bash_line and name in powershell_line
        assert command in bash_line and command in powershell_line


# ---------------------------------------------------------------- cli


def test_main_prints_the_requested_format(tmp_path, capsys):
    write_inventory(tmp_path, "personal", [{"name": "box", "user": "jason", "aliases": ["sshbox"]}])
    ssh_aliases.main(["--format", "bash", "--root", str(tmp_path), "--local-hostname", "elsewhere"])
    assert capsys.readouterr().out.strip() == "alias sshbox='ssh jason@box'"


def test_main_json_format_is_parseable(tmp_path, capsys):
    write_inventory(tmp_path, "personal", [{"name": "box", "user": "jason", "aliases": ["sshbox"]}])
    ssh_aliases.main(["--format", "json", "--root", str(tmp_path), "--local-hostname", "elsewhere"])
    assert json.loads(capsys.readouterr().out) == [{"alias": "sshbox", "command": "ssh jason@box"}]


def test_main_emits_nothing_when_there_is_nothing_to_emit(tmp_path, capsys):
    assert ssh_aliases.main(["--format", "bash", "--root", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


def test_vnc_gating_follows_the_platform_flag(tmp_path, capsys):
    write_inventory(tmp_path, "personal", [VNC_HOST])
    common = ["--format", "bash", "--root", str(tmp_path), "--local-hostname", "elsewhere"]
    ssh_aliases.main(common + ["--platform", "darwin"])
    assert "vncenvy" in capsys.readouterr().out
    ssh_aliases.main(common + ["--platform", "win32"])
    assert "vncenvy" not in capsys.readouterr().out
