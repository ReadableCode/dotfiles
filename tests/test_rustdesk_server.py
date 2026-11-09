"""Unit tests for src/rustdesk_server.py - the RustDesk direct IP options a host's record declares."""

import json

import config_test_utils  # noqa F401

from src import rustdesk_server

TOML = """rendezvous_server = 'rs-ny.rustdesk.com:21116'
nat_type = 1
serial = 0

[options]
local-ip-addr = '192.168.86.131'
av1-test = 'Y'
"""


def write_inventory(root, block):
    credentials = root / "personal_credentials"
    credentials.mkdir()
    server = {"name": "Server", "os": "macos"}
    if block is not None:
        server["rustdesk"] = block
    hosts = [server, {"name": "Laptop", "os": "macos"}]
    (credentials / "personal_hosts.json").write_text(json.dumps({"hosts": hosts}))
    return str(root)


def write_config(tmp_path, text=TOML):
    home = tmp_path / "home"
    (home / "Library" / "Preferences" / "com.carriez.RustDesk").mkdir(parents=True)
    path = home / "Library" / "Preferences" / "com.carriez.RustDesk" / "RustDesk2.toml"
    path.write_text(text)
    return home, path


# ---------------------------------------------------------------- the record


def test_a_record_with_no_rustdesk_block_wants_nothing():
    assert rustdesk_server.wanted_options({"name": "Laptop"}) == {}
    assert rustdesk_server.wanted_options(None) == {}


def test_the_block_defaults_to_the_documented_port():
    assert rustdesk_server.wanted_options({"rustdesk": {}}) == {
        "direct-server": "Y",
        "direct-access-port": "21118",
    }


def test_the_block_may_name_another_port():
    options = rustdesk_server.wanted_options({"rustdesk": {"direct_access_port": 21200}})
    assert options["direct-access-port"] == "21200"


# ---------------------------------------------------------------- editing the file


def test_options_are_added_without_touching_the_rest():
    out = rustdesk_server.apply_options(TOML, {"direct-server": "Y", "direct-access-port": "21118"})
    assert "direct-server = 'Y'" in out
    assert "direct-access-port = '21118'" in out
    # every pre-existing key survives, including the app's own runtime state
    assert "local-ip-addr = '192.168.86.131'" in out
    assert "av1-test = 'Y'" in out
    assert "rendezvous_server = 'rs-ny.rustdesk.com:21116'" in out
    assert "nat_type = 1" in out


def test_an_existing_value_is_replaced_not_duplicated():
    once = rustdesk_server.apply_options(TOML, {"direct-access-port": "21118"})
    twice = rustdesk_server.apply_options(once, {"direct-access-port": "21200"})
    assert twice.count("direct-access-port") == 1
    assert "direct-access-port = '21200'" in twice


def test_applying_the_same_options_again_changes_nothing():
    once = rustdesk_server.apply_options(TOML, {"direct-server": "Y", "direct-access-port": "21118"})
    assert rustdesk_server.apply_options(once, {"direct-server": "Y", "direct-access-port": "21118"}) == once


def test_a_file_with_no_options_section_gets_one():
    out = rustdesk_server.apply_options("serial = 0\n", {"direct-server": "Y"})
    assert "[options]" in out
    assert "direct-server = 'Y'" in out
    assert "serial = 0" in out


def test_a_key_outside_the_options_section_is_not_read_as_the_setting():
    text = "direct-access-port = '9999'\n\n[options]\nav1-test = 'Y'\n"
    out = rustdesk_server.apply_options(text, {"direct-access-port": "21118"})
    # the stray top-level key is left alone and the real one is added under [options]
    assert out.startswith("direct-access-port = '9999'")
    assert "[options]\ndirect-access-port = '21118'" in out


# ---------------------------------------------------------------- sync


def test_a_host_with_no_block_writes_nothing(tmp_path):
    root = write_inventory(tmp_path, None)
    home, path = write_config(tmp_path)
    assert rustdesk_server.sync("Server", root, system="Darwin", environ={"HOME": str(home)}) == 0
    assert path.read_text() == TOML


def test_a_declaring_host_gets_the_options(tmp_path):
    root = write_inventory(tmp_path, {"direct_access_port": 21118})
    home, path = write_config(tmp_path)
    assert rustdesk_server.sync("Server", root, system="Darwin", environ={"HOME": str(home)}) == 0
    assert "direct-server = 'Y'" in path.read_text()
    assert "direct-access-port = '21118'" in path.read_text()


def test_check_reports_without_writing(tmp_path):
    root = write_inventory(tmp_path, {"direct_access_port": 21118})
    home, path = write_config(tmp_path)
    assert rustdesk_server.sync("Server", root, check=True, system="Darwin", environ={"HOME": str(home)}) == 0
    assert path.read_text() == TOML


def test_a_missing_config_is_reported_not_created(tmp_path):
    root = write_inventory(tmp_path, {"direct_access_port": 21118})
    home = tmp_path / "home"
    home.mkdir()
    assert rustdesk_server.sync("Server", root, system="Darwin", environ={"HOME": str(home)}) == 0
    assert not (home / "Library").exists()


def test_a_platform_with_no_known_path_writes_nothing(tmp_path):
    root = write_inventory(tmp_path, {"direct_access_port": 21118})
    home, path = write_config(tmp_path)
    assert rustdesk_server.sync("Server", root, system="Windows", environ={"HOME": str(home)}) == 0
    assert path.read_text() == TOML
