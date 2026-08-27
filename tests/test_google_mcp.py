# %%
# Imports #

from datetime import datetime, timezone

import config_test_utils  # noqa F401
import pytest
import google_mcp

# %%
# Helpers #


def utc(*parts):
    return datetime(*parts, tzinfo=timezone.utc)


TIMED_EVENT = {
    "title": "Revenue sync",
    "calendar": "primary",
    "start": utc(2026, 8, 27, 15, 0),
    "end": utc(2026, 8, 27, 15, 30),
    "all_day": False,
    "response": "accepted",
    "details": {"organizer": "owner@x.com", "attendees": [("Me", "accepted")]},
}

ALL_DAY_EVENT = {
    "title": "Sabbatical",
    "calendar": "Finance PTO",
    "start": utc(2026, 8, 27),
    "end": utc(2026, 8, 29),
    "all_day": True,
    "response": "organizer",
    "details": {},
}


# %%
# Event serialization #


def test_serialize_event_emits_timed_events_in_local_time():
    serialized = google_mcp._serialize_event(TIMED_EVENT)
    # same instant, but carrying the local offset rather than a bare UTC wall clock
    assert datetime.fromisoformat(serialized["start"]) == TIMED_EVENT["start"]
    assert datetime.fromisoformat(serialized["end"]) == TIMED_EVENT["end"]
    assert datetime.fromisoformat(serialized["start"]).utcoffset() == TIMED_EVENT["start"].astimezone().utcoffset()


def test_serialize_event_reads_as_the_local_wall_clock():
    serialized = google_mcp._serialize_event(TIMED_EVENT)
    expected = TIMED_EVENT["start"].astimezone()
    assert serialized["start"].startswith(f"{expected:%Y-%m-%dT%H:%M}")


def test_serialize_event_keeps_all_day_events_as_plain_dates():
    serialized = google_mcp._serialize_event(ALL_DAY_EVENT)
    assert serialized["start"] == "2026-08-27"
    assert serialized["end"] == "2026-08-29"
    assert serialized["end_is_exclusive"] is True


def test_serialize_event_does_not_mutate_the_source_event():
    before = TIMED_EVENT["start"]
    google_mcp._serialize_event(TIMED_EVENT)
    assert TIMED_EVENT["start"] is before and isinstance(TIMED_EVENT["start"], datetime)


def test_serialize_event_keeps_the_nested_details():
    serialized = google_mcp._serialize_event(TIMED_EVENT)
    assert serialized["details"]["organizer"] == "owner@x.com"
    assert serialized["title"] == "Revenue sync" and serialized["response"] == "accepted"


def test_jsonable_walks_nested_datetimes():
    payload = {"when": [utc(2026, 1, 1)], "nested": {"then": utc(2026, 1, 2)}}
    assert google_mcp._jsonable(payload) == {
        "when": ["2026-01-01T00:00:00+00:00"],
        "nested": {"then": "2026-01-02T00:00:00+00:00"},
    }


# %%
# Time field shape #


def test_time_field_treats_a_bare_date_as_all_day():
    assert google_mcp._time_field("2026-08-27") == {"date": "2026-08-27"}


def test_time_field_treats_a_timestamp_as_timed():
    assert google_mcp._time_field("2026-08-27T10:00:00-05:00") == {
        "dateTime": "2026-08-27T10:00:00-05:00"
    }


# %%
# Account resolution #


def test_resolve_defaults_to_the_only_configured_entry():
    only = {"name": "solo"}
    assert google_mcp._resolve([only], "", "mailbox") is only


def test_resolve_picks_the_named_entry():
    entries = [{"name": "a"}, {"name": "b"}]
    assert google_mcp._resolve(entries, "b", "mailbox")["name"] == "b"


def test_resolve_refuses_to_guess_between_several():
    entries = [{"name": "a"}, {"name": "b"}]
    with pytest.raises(ValueError, match="several mailboxes configured"):
        google_mcp._resolve(entries, "", "mailbox")


def test_resolve_points_at_the_setup_doc_when_nothing_is_configured():
    with pytest.raises(ValueError, match="no mailboxes configured"):
        google_mcp._resolve([], "", "mailbox")


def test_resolve_reports_an_unknown_name():
    with pytest.raises(ValueError, match="unknown source 'nope'"):
        google_mcp._resolve([{"name": "a"}], "nope", "source")


# %%
# Server wiring #


def test_every_tool_is_registered_once():
    names = [tool.name for tool in google_mcp.server._tool_manager.list_tools()]
    assert len(names) == len(set(names))
    for expected in ("calendar_agenda", "calendar_get_event", "gmail_search", "gmail_send_message"):
        assert expected in names


# %%


# %%
# Context pinning #


def _write_empty(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")


def test_context_pins_calendar_discovery_to_that_repos_config(monkeypatch, tmp_path):
    config = tmp_path / "acme_credentials" / "acme_calendarboard.yaml"
    _write_empty(config)
    captured = {}

    def fake_load(root, repo_root=None, config_path=None):
        captured["config_path"] = config_path
        return [], [config_path]

    monkeypatch.setattr(google_mcp, "load_sources", fake_load)
    monkeypatch.setattr(google_mcp, "CREDENTIALS_ROOT", str(tmp_path))
    monkeypatch.setattr(google_mcp, "_context", "acme")
    assert google_mcp._calendar_sources() == []
    assert captured["config_path"] == str(config)


def test_context_pins_mailbox_discovery_to_that_repos_config(monkeypatch, tmp_path):
    config = tmp_path / "acme_credentials" / "acme_googlemail.yaml"
    _write_empty(config)
    captured = {}

    def fake_load(root, repo_root=None, config_path=None):
        captured["config_path"] = config_path
        return [], [config_path]

    monkeypatch.setattr(google_mcp.gtools, "load_mailboxes", fake_load)
    monkeypatch.setattr(google_mcp, "CREDENTIALS_ROOT", str(tmp_path))
    monkeypatch.setattr(google_mcp, "_context", "acme")
    assert google_mcp._mailboxes() == []
    assert captured["config_path"] == str(config)


def test_pinned_context_without_a_config_reports_no_accounts_not_everyones(monkeypatch, tmp_path):
    (tmp_path / "acme_credentials").mkdir()

    def explode(*_args, **_kwargs):
        raise AssertionError("discovery must not run for a pinned context with no config")

    monkeypatch.setattr(google_mcp, "load_sources", explode)
    monkeypatch.setattr(google_mcp.gtools, "load_mailboxes", explode)
    monkeypatch.setattr(google_mcp, "CREDENTIALS_ROOT", str(tmp_path))
    monkeypatch.setattr(google_mcp, "_context", "acme")
    assert google_mcp._calendar_sources() == []
    assert google_mcp._mailboxes() == []


def test_parse_args_context_defaults_to_unpinned():
    assert google_mcp.parse_args([]).context == ""
    assert google_mcp.parse_args(["--context", "acme"]).context == "acme"
