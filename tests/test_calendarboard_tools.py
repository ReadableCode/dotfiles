# %%
# Imports #

import os
from datetime import date, datetime, timezone

import config_test_utils  # noqa F401
import pytest
import yaml
from utils import calendarboard_tools

# %%
# Helpers #


def write_yaml(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        yaml.safe_dump(payload, file_handle)
    return path


def make_credentials_repo(root, context, sources=None):
    """Create a fake <context>_credentials repo with an optional calendarboard config."""
    repo = os.path.join(str(root), f"{context}_credentials")
    os.makedirs(repo, exist_ok=True)
    if sources is not None:
        write_yaml(os.path.join(repo, f"{context}_calendarboard.yaml"), sources)
    return repo


GOOGLE_SOURCE = {
    "name": "personal_google",
    "type": "google_calendar",
    "client_id_env": "G_ID",
    "client_secret_env": "G_SECRET",
    "refresh_token_env": "G_REFRESH",
}
OUTLOOK_SOURCE = {
    "name": "acme_outlook",
    "type": "outlook_calendar",
    "client_id_env": "MS_ID",
    "refresh_token_env": "MS_REFRESH",
}


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def event(start, end, all_day=False, response="accepted", title="x", calendar="cal"):
    return {
        "title": title,
        "calendar": calendar,
        "start": start,
        "end": end,
        "all_day": all_day,
        "response": response,
        "conflict": False,
    }


# %%
# Discovery / loading #


def test_discover_finds_overlays_and_repo_root_config(tmp_path):
    make_credentials_repo(tmp_path, "acme", sources=[])
    make_credentials_repo(tmp_path, "empty")  # no config -> contributes nothing
    repo_root = os.path.join(str(tmp_path), "dotfiles")
    write_yaml(os.path.join(repo_root, "calendarboard.yaml"), [])
    configs = calendarboard_tools.discover_calendarboard_configs(str(tmp_path), repo_root)
    assert [os.path.basename(path) for path, _ in configs] == ["calendarboard.yaml", "acme_calendarboard.yaml"]


def test_load_sources_stamps_base_dir_and_defaults_interval(tmp_path):
    repo = make_credentials_repo(tmp_path, "acme", sources=[dict(GOOGLE_SOURCE)])
    sources, config_paths = calendarboard_tools.load_sources(str(tmp_path))
    assert len(sources) == 1 and len(config_paths) == 1
    assert sources[0]["_base_dir"] == repo
    assert sources[0]["interval"] == calendarboard_tools.DEFAULT_INTERVAL


def test_load_sources_rejects_duplicate_names(tmp_path):
    make_credentials_repo(tmp_path, "aaa", sources=[dict(GOOGLE_SOURCE)])
    make_credentials_repo(tmp_path, "bbb", sources=[dict(OUTLOOK_SOURCE, name="personal_google")])
    with pytest.raises(ValueError, match="Duplicate calendarboard source name 'personal_google'"):
        calendarboard_tools.load_sources(str(tmp_path))


@pytest.mark.parametrize(
    "source, match",
    [
        ({"name": "x", "type": "nope"}, "unknown type"),
        ({"name": "x", "type": "google_calendar", "client_id_env": "A"}, "missing required keys"),
        ({"name": "x", "type": "outlook_calendar"}, "missing required keys"),
        ({"type": "google_calendar"}, "'name' and 'type'"),
        (dict(OUTLOOK_SOURCE, calendars="Calendar"), "'calendars' must be a list"),
    ],
)
def test_source_validation(tmp_path, source, match):
    make_credentials_repo(tmp_path, "acme", sources=[source])
    with pytest.raises(ValueError, match=match):
        calendarboard_tools.load_sources(str(tmp_path))


def test_load_sources_single_config_escape_hatch(tmp_path):
    config_path = write_yaml(os.path.join(str(tmp_path), "solo.yaml"), [dict(GOOGLE_SOURCE)])
    sources, config_paths = calendarboard_tools.load_sources("/nonexistent", config_path=config_path)
    assert config_paths == [config_path]
    assert sources[0]["_base_dir"] == str(tmp_path)


# %%
# Calendar selection #


def test_calendar_selected_defaults_to_all():
    assert calendarboard_tools.calendar_selected({}, "Anything")


def test_calendar_selected_matches_name_id_and_primary_token():
    source = {"calendars": ["Work", "primary", "abc123@group.calendar.google.com"]}
    assert calendarboard_tools.calendar_selected(source, "work")  # case-insensitive name
    assert calendarboard_tools.calendar_selected(source, "Main", primary=True)
    assert calendarboard_tools.calendar_selected(source, "Other", calendar_id="ABC123@group.calendar.google.com")
    assert not calendarboard_tools.calendar_selected(source, "Family")


# %%
# Time parsing #


def test_parse_iso_datetime_handles_both_apis():
    # Google: offset form
    assert calendarboard_tools.parse_iso_datetime("2026-07-25T09:00:00-05:00") == utc(2026, 7, 25, 14, 0)
    # Google: Z suffix (3.10 fromisoformat rejects it raw)
    assert calendarboard_tools.parse_iso_datetime("2026-07-25T14:00:00Z") == utc(2026, 7, 25, 14, 0)
    # Graph: naive with 7-digit fractional seconds, meaning UTC via the Prefer header
    assert calendarboard_tools.parse_iso_datetime(
        "2026-07-25T14:00:00.0000000", assume_utc=True
    ) == utc(2026, 7, 25, 14, 0)


# %%
# Normalization: Google #


def test_normalize_google_timed_event_maps_self_response():
    raw = {
        "summary": "Standup",
        "start": {"dateTime": "2026-07-25T09:00:00-05:00"},
        "end": {"dateTime": "2026-07-25T09:30:00-05:00"},
        "attendees": [
            {"email": "boss@x.com", "responseStatus": "accepted"},
            {"email": "me@x.com", "self": True, "responseStatus": "needsAction"},
        ],
    }
    normalized = calendarboard_tools.normalize_google_event(raw, "acme main")
    assert normalized["title"] == "Standup"
    assert normalized["calendar"] == "acme main"
    assert normalized["start"] == utc(2026, 7, 25, 14, 0)
    assert normalized["all_day"] is False
    assert normalized["response"] == "needs_action"  # invited, not the other attendee's accepted


def test_normalize_google_organizer_and_solo_events():
    organizer = {"summary": "1:1", "organizer": {"self": True},
                 "start": {"dateTime": "2026-07-25T10:00:00Z"}, "end": {"dateTime": "2026-07-25T11:00:00Z"}}
    solo = {"summary": "focus block",
            "start": {"dateTime": "2026-07-25T10:00:00Z"}, "end": {"dateTime": "2026-07-25T11:00:00Z"}}
    assert calendarboard_tools.normalize_google_event(organizer, "c")["response"] == "organizer"
    assert calendarboard_tools.normalize_google_event(solo, "c")["response"] == "accepted"


def test_normalize_google_all_day_and_cancelled():
    all_day = {"summary": "PTO", "start": {"date": "2026-07-25"}, "end": {"date": "2026-07-27"}}
    normalized = calendarboard_tools.normalize_google_event(all_day, "c")
    assert normalized["all_day"] is True
    assert normalized["start"].date() == date(2026, 7, 25)
    assert normalized["end"].date() == date(2026, 7, 27)  # exclusive end, kept as-is
    assert calendarboard_tools.normalize_google_event({"status": "cancelled"}, "c") is None


# %%
# Normalization: Graph #


def test_normalize_graph_event_maps_response_states():
    def raw(response, organizer=False):
        return {
            "subject": "Sync",
            "isOrganizer": organizer,
            "responseStatus": {"response": response},
            "start": {"dateTime": "2026-07-25T14:00:00.0000000", "timeZone": "UTC"},
            "end": {"dateTime": "2026-07-25T15:00:00.0000000", "timeZone": "UTC"},
        }

    normalize = calendarboard_tools.normalize_graph_event
    assert normalize(raw("notResponded"), "c")["response"] == "needs_action"
    assert normalize(raw("tentativelyAccepted"), "c")["response"] == "tentative"
    assert normalize(raw("declined"), "c")["response"] == "declined"
    assert normalize(raw("none"), "c")["response"] == "accepted"
    assert normalize(raw("accepted", organizer=True), "c")["response"] == "organizer"
    assert normalize(raw("accepted"), "c")["start"] == utc(2026, 7, 25, 14, 0)


def test_normalize_graph_all_day_and_cancelled():
    raw = {
        "subject": "Conference",
        "isAllDay": True,
        "responseStatus": {"response": "accepted"},
        "start": {"dateTime": "2026-07-25T00:00:00.0000000", "timeZone": "UTC"},
        "end": {"dateTime": "2026-07-26T00:00:00.0000000", "timeZone": "UTC"},
    }
    normalized = calendarboard_tools.normalize_graph_event(raw, "c")
    assert normalized["all_day"] is True
    assert calendarboard_tools.normalize_graph_event({"isCancelled": True}, "c") is None


# %%
# Day slicing #


def test_events_for_day_filters_and_sorts():
    tz = timezone.utc
    morning = event(utc(2026, 7, 25, 9), utc(2026, 7, 25, 10), title="morning")
    evening = event(utc(2026, 7, 25, 18), utc(2026, 7, 25, 19), title="evening")
    other_day = event(utc(2026, 7, 26, 9), utc(2026, 7, 26, 10), title="tomorrow")
    pto = event(utc(2026, 7, 24), utc(2026, 7, 27), all_day=True, title="pto")  # 24th-26th inclusive
    selected = calendarboard_tools.events_for_day([evening, other_day, morning, pto], date(2026, 7, 25), tz=tz)
    assert [item["title"] for item in selected] == ["pto", "morning", "evening"]
    # exclusive all-day end: the 27th is outside the PTO block
    assert calendarboard_tools.events_for_day([pto], date(2026, 7, 27), tz=tz) == []


def test_events_for_day_includes_events_crossing_midnight():
    tz = timezone.utc
    overnight = event(utc(2026, 7, 25, 23), utc(2026, 7, 26, 1), title="redeye")
    assert calendarboard_tools.events_for_day([overnight], date(2026, 7, 25), tz=tz)
    assert calendarboard_tools.events_for_day([overnight], date(2026, 7, 26), tz=tz)
    assert calendarboard_tools.events_for_day([overnight], date(2026, 7, 27), tz=tz) == []


# %%
# Conflicts #


def test_mark_conflicts_across_sources():
    a = event(utc(2026, 7, 25, 9), utc(2026, 7, 25, 10), title="client A standup")
    b = event(utc(2026, 7, 25, 9, 30), utc(2026, 7, 25, 10, 30), title="client B sync")
    c = event(utc(2026, 7, 25, 11), utc(2026, 7, 25, 12), title="clear")
    calendarboard_tools.mark_conflicts([a, b, c])
    assert a["conflict"] and b["conflict"] and not c["conflict"]


def test_mark_conflicts_ignores_declined_all_day_and_touching_events():
    declined = event(utc(2026, 7, 25, 9), utc(2026, 7, 25, 10), response="declined")
    overlapping = event(utc(2026, 7, 25, 9), utc(2026, 7, 25, 10))
    pto = event(utc(2026, 7, 25), utc(2026, 7, 26), all_day=True)
    back_to_back = event(utc(2026, 7, 25, 10), utc(2026, 7, 25, 11))
    marked = calendarboard_tools.mark_conflicts([declined, overlapping, pto, back_to_back])
    assert not any(item["conflict"] for item in marked)


def test_mark_conflicts_resets_stale_flags():
    a = event(utc(2026, 7, 25, 9), utc(2026, 7, 25, 10))
    a["conflict"] = True  # left over from a previous render
    calendarboard_tools.mark_conflicts([a])
    assert a["conflict"] is False


# %%
# Fetch dispatch #


def test_fetch_source_never_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("G_ID", raising=False)
    source = dict(GOOGLE_SOURCE, _base_dir=str(tmp_path))
    result = calendarboard_tools.fetch_source(source, utc(2026, 7, 25), utc(2026, 7, 26))
    assert result.ok is False
    assert "G_ID" in result.error


def test_fetch_google_events_selects_calendars_and_normalizes(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self.payload = payload
            self.status_code = status_code
            self.text = ""

        def json(self):
            return self.payload

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append((url, params))
        if url.endswith("/users/me/calendarList"):
            return FakeResponse({"items": [
                {"id": "primary-id", "summary": "Main", "primary": True},
                {"id": "team-id", "summary": "Team"},
                {"id": "junk-id", "summary": "Birthdays"},
            ]})
        return FakeResponse({"items": [{
            "summary": "Standup",
            "start": {"dateTime": "2026-07-25T09:00:00Z"},
            "end": {"dateTime": "2026-07-25T09:30:00Z"},
        }]})

    monkeypatch.setattr(calendarboard_tools.requests, "get", fake_get)
    monkeypatch.setattr(calendarboard_tools, "_google_access_token", lambda source: "tok")
    source = dict(GOOGLE_SOURCE, calendars=["primary", "Team"])
    result = calendarboard_tools.fetch_google_events(source, utc(2026, 7, 25), utc(2026, 7, 26))
    assert result.ok
    event_urls = [url for url, _ in calls if url.endswith("/events")]
    assert len(event_urls) == 2  # Birthdays skipped
    assert all(item["source"] == "personal_google" for item in result.events)
    assert result.summary == "2 cal · 2 events"


def test_fetch_outlook_events_requests_utc_and_pages(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200
        text = ""

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append((url, headers, params))
        if url.endswith("/me/calendars"):
            return FakeResponse({"value": [{"id": "cal1", "name": "Calendar", "isDefaultCalendar": True}]})
        if "page2" in url:
            return FakeResponse({"value": [{
                "subject": "Later",
                "responseStatus": {"response": "accepted"},
                "start": {"dateTime": "2026-07-25T15:00:00.0000000", "timeZone": "UTC"},
                "end": {"dateTime": "2026-07-25T16:00:00.0000000", "timeZone": "UTC"},
            }]})
        return FakeResponse({
            "value": [{
                "subject": "Sync",
                "responseStatus": {"response": "notResponded"},
                "start": {"dateTime": "2026-07-25T14:00:00.0000000", "timeZone": "UTC"},
                "end": {"dateTime": "2026-07-25T15:00:00.0000000", "timeZone": "UTC"},
            }],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/page2",
        })

    monkeypatch.setattr(calendarboard_tools.requests, "get", fake_get)
    monkeypatch.setattr(calendarboard_tools, "_graph_access_token", lambda source: "tok")
    result = calendarboard_tools.fetch_outlook_events(dict(OUTLOOK_SOURCE), utc(2026, 7, 25), utc(2026, 7, 26))
    assert result.ok
    assert [item["title"] for item in result.events] == ["Sync", "Later"]
    assert result.events[0]["response"] == "needs_action"
    view_headers = [headers for url, headers, _ in calls if "calendarView" in url]
    assert all(headers.get("Prefer") == 'outlook.timezone="UTC"' for headers in view_headers)


# %%
