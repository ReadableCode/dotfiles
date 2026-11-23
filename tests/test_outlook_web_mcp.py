# %%
# Imports #

import base64
import json
from datetime import datetime, timezone

import config_test_utils  # noqa F401
import pytest

import outlook_web_mcp
from utils import outlookweb_tools as otools

# %%
# Helpers #

ACCOUNT = {
    "name": "acme",
    "address": "jason@acme.test",
    "sign_in": "jason@acme-corp.test",
    "browser": "Microsoft Edge",
    "profile": "Profile 1",
}


def write_config(tmp_path, text):
    path = tmp_path / "acme_outlookweb.yaml"
    path.write_text(text)
    return str(path)


# %%
# Server wiring #


def test_every_tool_is_registered_once():
    names = [tool.name for tool in outlook_web_mcp.server._tool_manager.list_tools()]
    assert len(names) == len(set(names))
    for expected in (
        "list_accounts",
        "mail_search",
        "mail_get_message",
        "mail_download_attachment",
        "calendar_list_calendars",
        "calendar_agenda",
        "calendar_create_event",
        "calendar_delete_event",
    ):
        assert expected in names


# %%
# Config #


def test_load_accounts_reads_every_field(tmp_path):
    path = write_config(
        tmp_path,
        "- name: acme\n  address: jason@acme.test\n  sign_in: jason@acme-corp.test\n"
        "  browser: Microsoft Edge\n  profile: Profile 1\n",
    )
    (account,) = otools.load_accounts(path)
    assert {key: account[key] for key in ACCOUNT} == ACCOUNT


@pytest.mark.parametrize(
    ("text", "complaint"),
    [
        ("- name: acme\n  address: jason@acme.test\n", "needs name, address, sign_in"),
        ("name: acme\n", "expected a list"),
    ],
)
def test_load_accounts_refuses_an_incomplete_entry(tmp_path, text, complaint):
    with pytest.raises(ValueError, match=complaint):
        otools.load_accounts(write_config(tmp_path, text))


# %%
# Session #


def test_a_tab_signed_in_as_someone_else_is_refused(monkeypatch):
    monkeypatch.setattr(otools, "require_macos", lambda: None)
    state = {"state": "ok", "user": "someone@other.test", "expires": 2000, "now": 1000}
    monkeypatch.setattr(otools, "_token_state", lambda account: state)
    with pytest.raises(PermissionError, match="signed in as someone@other.test"):
        otools.ensure_session(ACCOUNT)


def test_a_live_token_for_the_sign_in_is_accepted(monkeypatch):
    monkeypatch.setattr(otools, "require_macos", lambda: None)
    state = {"state": "ok", "user": "jason@acme-corp.test", "expires": 5000, "now": 1000}
    monkeypatch.setattr(otools, "_token_state", lambda account: state)
    assert otools.ensure_session(ACCOUNT) == state


def test_the_tab_that_answered_is_remembered_and_a_sleeping_one_skipped(monkeypatch):
    monkeypatch.setattr(otools, "_tab", {"id": "", "hung": set()})
    scripts = []

    def osascript(script):
        scripts.append(script)
        return "OK\nT7\nT3\nfirst line\nsecond line"

    monkeypatch.setattr(otools, "_osascript", osascript)
    assert otools.run_js(ACCOUNT, "1") == "first line\nsecond line"
    otools.run_js(ACCOUNT, "1")
    assert 'set preferred to "T7"' in scripts[1] and 'set hung to {"T3"}' in scripts[1]


def test_no_tab_awake_is_unavailable(monkeypatch):
    monkeypatch.setattr(otools, "_tab", {"id": "T7", "hung": set()})
    monkeypatch.setattr(otools, "_osascript", lambda script: "NONE\nT3,T7")
    assert otools._on_tab(ACCOUNT, "1") == otools.UNAVAILABLE
    assert otools._tab == {"id": "", "hung": {"T3", "T7"}}
    with pytest.raises(RuntimeError, match="open and awake"):
        otools.run_js(ACCOUNT, "1")


def test_a_fresh_tab_is_opened_when_none_is_awake(monkeypatch):
    monkeypatch.setattr(otools, "require_macos", lambda: None)
    monkeypatch.setattr(otools.time, "sleep", lambda seconds: None)
    states = [None, None, {"state": "ok", "user": "jason@acme-corp.test", "expires": 5000, "now": 1000}]
    monkeypatch.setattr(otools, "_token_state", lambda account: states.pop(0))
    opened = []
    monkeypatch.setattr(otools, "open_tab", lambda account: opened.append(account["profile"]))
    assert otools.ensure_session(ACCOUNT)["state"] == "ok"
    assert opened == ["Profile 1"]


def fake_tab(monkeypatch, status=200, text='{"value": [1]}', lose_first=0):
    """A tab that starts each request and answers its poll; the first `lose_first` polls find another tab."""
    monkeypatch.setattr(otools, "ensure_session", lambda account: {})
    monkeypatch.setattr(otools, "POLL_SECONDS", 0)
    monkeypatch.setattr(otools, "_tab", {"id": "T1", "hung": set()})
    calls = {"started": 0, "lost": lose_first}

    def on_tab(account, expression):
        if "fetch(" in expression:
            calls["started"] += 1
            otools._tab["id"] = "T1"
            return "started"
        if "JSON.stringify" in expression:
            if calls["lost"]:
                calls["lost"] -= 1
                otools._tab["id"] = "T2"
                return "null"
            return json.dumps({"done": True, "status": status, "text": text})
        return "ok"

    monkeypatch.setattr(otools, "_on_tab", on_tab)
    return calls


def test_request_starts_in_the_tab_and_polls_for_the_answer(monkeypatch):
    fake_tab(monkeypatch)
    assert otools.request(ACCOUNT, "GET", "https://outlook.office.com/api/v2.0/me/calendars") == {"value": [1]}


def test_the_script_reads_the_token_in_the_page():
    assert "Bearer " in otools.REQUEST_JS and "localStorage" in otools.REQUEST_JS


def test_a_refused_request_raises_with_the_status(monkeypatch):
    fake_tab(monkeypatch, status=403, text="Forbidden")
    with pytest.raises(RuntimeError, match="403 Forbidden"):
        otools.request(ACCOUNT, "GET", "https://outlook.office.com/api/v2.0/me/calendars")


def test_a_read_whose_tab_fell_asleep_runs_again(monkeypatch):
    calls = fake_tab(monkeypatch, lose_first=1)
    assert otools.request(ACCOUNT, "GET", "https://outlook.office.com/api/v2.0/me/calendars") == {"value": [1]}
    assert calls["started"] == 2


def test_a_write_whose_tab_fell_asleep_is_not_repeated(monkeypatch):
    calls = fake_tab(monkeypatch, lose_first=1)
    with pytest.raises(otools.TabLost, match="read it back before retrying"):
        otools.request(ACCOUNT, "POST", "https://outlook.office.com/api/v2.0/me/events", body={})
    assert calls["started"] == 1


# %%
# Calendar #


def test_a_timed_meeting_is_local_with_its_response_and_attendees():
    item = {
        "Id": "E1",
        "Subject": "Planning",
        "Start": {"DateTime": "2026-11-23T15:00:00.0000000", "TimeZone": "UTC"},
        "End": {"DateTime": "2026-11-23T15:30:00.0000000", "TimeZone": "UTC"},
        "IsAllDay": False,
        "ResponseStatus": {"Response": "TentativelyAccepted"},
        "Attendees": [{"EmailAddress": {"Address": "a@acme.test"}}, {"EmailAddress": {"Address": "b@acme.test"}}],
        "Type": "Occurrence",
    }
    event = otools.serialize_event(ACCOUNT, "CAL", item)
    assert datetime.fromisoformat(event["start"]) == datetime(2026, 11, 23, 15, tzinfo=timezone.utc)
    assert (event["response"], event["has_attendees"], event["attendees_listed"]) == ("tentative", True, 2)
    assert event["recurring"] and not event["all_day"]


def test_an_all_day_event_keeps_its_dates():
    item = {
        "Id": "E2",
        "Subject": "Holiday",
        "Start": {"DateTime": "2026-11-26T00:00:00.0000000", "TimeZone": "UTC"},
        "End": {"DateTime": "2026-11-27T00:00:00.0000000", "TimeZone": "UTC"},
        "IsAllDay": True,
        "ResponseStatus": {"Response": "Organizer"},
        "Attendees": [],
        "Type": "SingleInstance",
    }
    event = otools.serialize_event(ACCOUNT, "CAL", item)
    assert (event["start"], event["end"], event["end_is_exclusive"]) == ("2026-11-26", "2026-11-27", True)
    assert (event["response"], event["has_attendees"]) == ("organizer", False)


def test_a_created_event_is_sent_in_utc_busy_with_no_reminder(monkeypatch):
    sent = []

    def request(account, method, url, body=None, headers=None):
        sent.append((method, url, body))
        return {"Id": "E3", "Subject": body["Subject"], "Start": body["Start"], "End": body["End"]}

    monkeypatch.setattr(otools, "request", request)
    otools.calendar_create_event(ACCOUNT, "CAL/1", ".", "2026-11-23T09:00:00-06:00", "2026-11-23T09:30:00-06:00")
    method, url, body = sent[0]
    assert method == "POST" and url.endswith("/calendars/CAL%2F1/events")
    assert body["Start"] == {"DateTime": "2026-11-23T15:00:00", "TimeZone": "UTC"}
    assert (body["ShowAs"], body["IsReminderOn"], "Attendees" in body) == ("Busy", False, False)


def test_update_and_delete_refuse_a_meeting(monkeypatch):
    meeting = {"Attendees": [{"EmailAddress": {"Address": "a@acme.test"}}], "Type": "SingleInstance"}
    monkeypatch.setattr(otools, "request", lambda *args, **kwargs: meeting)
    with pytest.raises(ValueError, match="has attendees"):
        otools.calendar_delete_event(ACCOUNT, "E1")
    with pytest.raises(ValueError, match="has attendees"):
        otools.calendar_update_event(ACCOUNT, "E1", summary="x")


# %%
# Mail #


def test_an_attachment_is_written_byte_for_byte(monkeypatch, tmp_path):
    data = b"%PDF-1.7 remittance"
    attachments = [{"Name": "a.pdf", "ContentBytes": base64.b64encode(data).decode()}, {"Name": "b.pdf"}]
    monkeypatch.setattr(otools, "get_all", lambda account, url: attachments)
    target = tmp_path / "out" / "a.pdf"
    assert otools.mail_download_attachment(ACCOUNT, "M1", "a.pdf", str(target)) == {
        "local_path": str(target),
        "size": len(data),
    }
    assert target.read_bytes() == data
    with pytest.raises(ValueError, match="0 attachments named 'c.pdf'"):
        otools.mail_download_attachment(ACCOUNT, "M1", "c.pdf", str(target))


def test_a_sender_search_goes_to_the_server_search(monkeypatch):
    urls = []

    def get_all(account, url, headers=None, limit=None):
        urls.append(url)
        return []

    monkeypatch.setattr(otools, "get_all", get_all)
    otools.mail_search(ACCOUNT, sender="ap@acme.test", max_results=500)
    assert "$search=%22from%3Aap%40acme.test%22" in urls[0]


# %%
