# %%
# Imports #

import config_test_utils  # noqa F401
import pytest

import mac_mcp

# %%
# Server wiring #


def test_every_tool_is_registered_once():
    names = [tool.name for tool in mac_mcp.server._tool_manager.list_tools()]
    assert len(names) == len(set(names))
    for expected in (
        "list_accounts",
        "mail_search",
        "mail_get_message",
        "messages_search",
        "messages_get_chat",
        "calendar_agenda",
        "calendar_create_event",
        "calendar_delete_event",
    ):
        assert expected in names


def test_wrapped_tools_keep_their_argument_schema():
    (search,) = [tool for tool in mac_mcp.server._tool_manager.list_tools() if tool.name == "mail_search"]
    assert {"query", "sender", "since", "account"} <= set(search.parameters["properties"])


def test_anticipated_failures_reach_the_model_with_their_reason(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise ValueError("no messages configured for this context")

    monkeypatch.setattr(mac_mcp, "_scope", refuse)
    with pytest.raises(mac_mcp.ToolError, match="no messages configured"):
        mac_mcp.messages_list_chats()


# %%
# Context pinning #


def _write(path, text=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_context_pins_discovery_to_that_repos_config(monkeypatch, tmp_path):
    config = _write(tmp_path / "acme_credentials" / "acme_macaccounts.yaml")
    _write(tmp_path / "other_credentials" / "other_macaccounts.yaml", "- name: other\n  type: messages\n")
    captured = {}

    def fake_load(root, config_path=None):
        captured["config_path"] = config_path
        return [], [config_path]

    monkeypatch.setattr(mac_mcp.mtools, "load_accounts", fake_load)
    monkeypatch.setattr(mac_mcp, "CREDENTIALS_ROOT", str(tmp_path))
    monkeypatch.setattr(mac_mcp, "_context", "acme")
    assert mac_mcp._configured() == []
    assert captured["config_path"] == str(config)


def test_pinned_context_without_a_config_reports_no_accounts_not_everyones(monkeypatch, tmp_path):
    (tmp_path / "acme_credentials").mkdir()
    _write(tmp_path / "other_credentials" / "other_macaccounts.yaml", "- name: other\n  type: messages\n")
    monkeypatch.setattr(mac_mcp, "CREDENTIALS_ROOT", str(tmp_path))
    monkeypatch.setattr(mac_mcp, "_context", "acme")
    assert mac_mcp._configured() == []


def test_scope_picks_the_named_entry_or_every_entry(monkeypatch):
    entries = [
        {"name": "a", "type": "internet_account", "address": "a@x.test"},
        {"name": "b", "type": "internet_account", "address": "b@x.test"},
        {"name": "texts", "type": "messages"},
    ]
    monkeypatch.setattr(mac_mcp.mtools, "require_macos", lambda: None)
    monkeypatch.setattr(mac_mcp, "_configured", lambda: [dict(entry) for entry in entries])
    monkeypatch.setattr(mac_mcp.mtools, "resolve_scope", lambda accounts: accounts)
    assert [entry["name"] for entry in mac_mcp._scope()] == ["a", "b"]
    assert [entry["name"] for entry in mac_mcp._scope("b")] == ["b"]
    with pytest.raises(ValueError, match="no internet_account named 'c'"):
        mac_mcp._scope("c")


def test_messages_need_a_messages_entry(monkeypatch):
    monkeypatch.setattr(mac_mcp.mtools, "require_macos", lambda: None)
    monkeypatch.setattr(
        mac_mcp, "_configured", lambda: [{"name": "a", "type": "internet_account", "address": "a@x.test"}]
    )
    with pytest.raises(ValueError, match="no messages configured"):
        mac_mcp._require_messages()


# %%
