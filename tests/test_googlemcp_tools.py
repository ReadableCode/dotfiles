# %%
# Imports #

import base64
import json
import os

import config_test_utils  # noqa F401
import pytest
import yaml
from utils import google_oauth_tools, googlemcp_tools

# %%
# Helpers #

MAILBOX = {
    "name": "personal_gmail",
    "type": "gmail",
    "oauth_env": "M_OAUTH",
    "token_env": "M_TOKEN",
}

CALENDAR_SOURCE = {
    "name": "personal_google",
    "type": "google_calendar",
    "client_id_env": "G_ID",
    "client_secret_env": "G_SECRET",
    "refresh_token_env": "G_REFRESH",
}


def write_yaml(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        yaml.safe_dump(payload, file_handle)
    return path


def make_credentials_repo(root, context, mailboxes=None):
    """Create a fake <context>_credentials repo with an optional googlemail config."""
    repo = os.path.join(str(root), f"{context}_credentials")
    os.makedirs(repo, exist_ok=True)
    if mailboxes is not None:
        write_yaml(os.path.join(repo, f"{context}_googlemail.yaml"), mailboxes)
    return repo


def b64(text):
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("utf-8")


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)
        self.content = self.text.encode("utf-8")

    def json(self):
        return self.payload


def stub_requests(monkeypatch, handler, module=googlemcp_tools):
    """Route module-level requests.request through ``handler(method, url, params, payload)``."""
    calls = []

    def fake_request(method, url, headers=None, params=None, json=None, timeout=None):
        calls.append({"method": method, "url": url, "params": params, "payload": json})
        return handler(method, url, params, json)

    monkeypatch.setattr(module.requests, "request", fake_request)
    return calls


@pytest.fixture(autouse=True)
def clear_tokens():
    google_oauth_tools.clear_token_cache()
    yield
    google_oauth_tools.clear_token_cache()


# %%
# Mailbox config discovery #


def test_load_mailboxes_reads_credentials_overlays(tmp_path):
    make_credentials_repo(tmp_path, "acme", [MAILBOX])
    mailboxes, paths = googlemcp_tools.load_mailboxes(str(tmp_path))
    assert [mailbox["name"] for mailbox in mailboxes] == ["personal_gmail"]
    assert mailboxes[0]["_base_dir"].endswith("acme_credentials")
    assert len(paths) == 1


def test_load_mailboxes_skips_repos_without_a_config(tmp_path):
    make_credentials_repo(tmp_path, "acme", [MAILBOX])
    make_credentials_repo(tmp_path, "beta")
    mailboxes, paths = googlemcp_tools.load_mailboxes(str(tmp_path))
    assert len(mailboxes) == 1 and len(paths) == 1


def test_load_mailboxes_rejects_duplicate_names_across_configs(tmp_path):
    make_credentials_repo(tmp_path, "acme", [MAILBOX])
    make_credentials_repo(tmp_path, "beta", [MAILBOX])
    with pytest.raises(ValueError, match="Duplicate googlemail mailbox name"):
        googlemcp_tools.load_mailboxes(str(tmp_path))


def test_load_mailboxes_rejects_missing_keys(tmp_path):
    broken = {key: value for key, value in MAILBOX.items() if key != "token_env"}
    make_credentials_repo(tmp_path, "acme", [broken])
    with pytest.raises(ValueError, match="is missing"):
        googlemcp_tools.load_mailboxes(str(tmp_path))


def test_load_mailboxes_rejects_unknown_type(tmp_path):
    make_credentials_repo(tmp_path, "acme", [dict(MAILBOX, type="imap")])
    with pytest.raises(ValueError, match="unknown type"):
        googlemcp_tools.load_mailboxes(str(tmp_path))


def test_load_mailboxes_rejects_a_mapping_instead_of_a_list(tmp_path):
    repo = make_credentials_repo(tmp_path, "acme")
    write_yaml(os.path.join(repo, "acme_googlemail.yaml"), {"name": "oops"})
    with pytest.raises(ValueError, match="expected a list of mailboxes"):
        googlemcp_tools.load_mailboxes(str(tmp_path))


def test_find_by_name_lists_the_valid_names_when_it_misses():
    with pytest.raises(ValueError, match="configured mailboxes: personal_gmail"):
        googlemcp_tools.find_by_name([MAILBOX], "nope", "mailbox")


# %%
# Gmail credentials #


def test_gmail_credentials_prefers_the_token_files_own_client(monkeypatch):
    monkeypatch.setenv("M_TOKEN", json.dumps({"refresh_token": "r", "client_id": "i", "client_secret": "s"}))
    assert googlemcp_tools._gmail_credentials(MAILBOX) == ("i", "s", "r")


def test_gmail_credentials_falls_back_to_the_oauth_client_json(monkeypatch):
    monkeypatch.setenv("M_TOKEN", json.dumps({"refresh_token": "r"}))
    monkeypatch.setenv("M_OAUTH", json.dumps({"installed": {"client_id": "i", "client_secret": "s"}}))
    assert googlemcp_tools._gmail_credentials(MAILBOX) == ("i", "s", "r")


def test_gmail_credentials_without_a_refresh_token_is_an_error(monkeypatch):
    monkeypatch.setenv("M_TOKEN", json.dumps({"client_id": "i"}))
    with pytest.raises(ValueError, match="has no refresh_token"):
        googlemcp_tools._gmail_credentials(MAILBOX)


def test_gmail_credentials_without_any_client_is_an_error(monkeypatch):
    monkeypatch.setenv("M_TOKEN", json.dumps({"refresh_token": "r"}))
    monkeypatch.setenv("M_OAUTH", json.dumps({"installed": {}}))
    with pytest.raises(ValueError, match="no client_id/client_secret"):
        googlemcp_tools._gmail_credentials(MAILBOX)


# %%
# Access token caching #


def test_cached_access_token_reuses_a_live_token(monkeypatch):
    refreshes = []

    def fake_post(url, data=None, timeout=None):
        refreshes.append(data["refresh_token"])
        return FakeResponse({"access_token": "tok", "expires_in": 3600})

    monkeypatch.setattr(google_oauth_tools.requests, "post", fake_post)
    assert google_oauth_tools.cached_access_token("i", "s", "r") == "tok"
    assert google_oauth_tools.cached_access_token("i", "s", "r") == "tok"
    assert refreshes == ["r"]  # second call served from cache


def test_cached_access_token_refetches_once_expired(monkeypatch):
    refreshes = []

    def fake_post(url, data=None, timeout=None):
        refreshes.append(data["refresh_token"])
        # expires_in below the margin, so the entry is already stale when stored
        return FakeResponse({"access_token": f"tok{len(refreshes)}", "expires_in": 1})

    monkeypatch.setattr(google_oauth_tools.requests, "post", fake_post)
    assert google_oauth_tools.cached_access_token("i", "s", "r") == "tok1"
    assert google_oauth_tools.cached_access_token("i", "s", "r") == "tok2"


def test_refresh_access_token_names_the_source_on_failure(monkeypatch):
    monkeypatch.setattr(
        google_oauth_tools.requests, "post", lambda url, data=None, timeout=None: FakeResponse({}, status_code=400)
    )
    with pytest.raises(ValueError, match="re-run --auth personal_google"):
        google_oauth_tools.refresh_access_token("i", "s", "r", context="personal_google")


# %%
# Gmail reads #


def gmail_env(monkeypatch):
    monkeypatch.setenv("M_TOKEN", json.dumps({"refresh_token": "r", "client_id": "i", "client_secret": "s"}))
    monkeypatch.setattr(googlemcp_tools, "gmail_headers", lambda mailbox: {"Authorization": "Bearer tok"})


def test_gmail_search_returns_summaries_from_metadata(monkeypatch):
    gmail_env(monkeypatch)

    def handler(method, url, params, payload):
        if url.endswith("/messages"):
            return FakeResponse({"messages": [{"id": "m1"}, {"id": "m2"}]})
        return FakeResponse({
            "id": "m1",
            "threadId": "t1",
            "snippet": "hi",
            "labelIds": ["INBOX", "UNREAD"],
            "payload": {"headers": [
                {"name": "From", "value": "a@b.com"},
                {"name": "Subject", "value": "Hello"},
            ]},
        })

    calls = stub_requests(monkeypatch, handler)
    results = googlemcp_tools.gmail_search(MAILBOX, query="is:unread", max_results=2)
    assert [item["subject"] for item in results] == ["Hello", "Hello"]
    assert results[0]["from"] == "a@b.com" and results[0]["unread"] is True
    assert calls[0]["params"]["q"] == "is:unread"
    assert calls[1]["params"]["format"] == "metadata"


def test_gmail_search_clamps_max_results_to_gmails_page_cap(monkeypatch):
    gmail_env(monkeypatch)
    calls = stub_requests(monkeypatch, lambda *args: FakeResponse({"messages": []}))
    googlemcp_tools.gmail_search(MAILBOX, max_results=10_000)
    assert calls[0]["params"]["maxResults"] == googlemcp_tools.MAX_GMAIL_RESULTS


def test_gmail_search_omits_the_query_when_empty(monkeypatch):
    gmail_env(monkeypatch)
    calls = stub_requests(monkeypatch, lambda *args: FakeResponse({"messages": []}))
    googlemcp_tools.gmail_search(MAILBOX)
    assert "q" not in calls[0]["params"]


def test_gmail_get_message_prefers_the_plain_text_part(monkeypatch):
    gmail_env(monkeypatch)
    payload = {
        "id": "m1",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [{"name": "Subject", "value": "S"}],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": b64("the plain body")}},
                {"mimeType": "text/html", "body": {"data": b64("<p>html body</p>")}},
            ],
        },
    }
    stub_requests(monkeypatch, lambda *args: FakeResponse(payload))
    message = googlemcp_tools.gmail_get_message(MAILBOX, "m1")
    assert message["body"] == "the plain body"


def test_gmail_get_message_falls_back_to_stripped_html(monkeypatch):
    gmail_env(monkeypatch)
    payload = {
        "id": "m1",
        "payload": {"mimeType": "text/html", "body": {"data": b64("<p>hello <b>there</b></p>")}, "headers": []},
    }
    stub_requests(monkeypatch, lambda *args: FakeResponse(payload))
    assert googlemcp_tools.gmail_get_message(MAILBOX, "m1")["body"] == "hello there"


def test_gmail_get_message_truncates_a_long_body(monkeypatch):
    gmail_env(monkeypatch)
    payload = {"id": "m1", "payload": {"mimeType": "text/plain", "body": {"data": b64("x" * 500)}, "headers": []}}
    stub_requests(monkeypatch, lambda *args: FakeResponse(payload))
    body = googlemcp_tools.gmail_get_message(MAILBOX, "m1", body_limit=100)["body"]
    assert len(body) == 100 and body.endswith("…")


def test_gmail_get_message_lists_attachments(monkeypatch):
    gmail_env(monkeypatch)
    payload = {
        "id": "m1",
        "payload": {
            "headers": [],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": b64("body")}},
                {"filename": "book.xlsx", "mimeType": "application/vnd.ms-excel",
                 "body": {"size": 42, "attachmentId": "a1"}},
            ],
        },
    }
    stub_requests(monkeypatch, lambda *args: FakeResponse(payload))
    attachments = googlemcp_tools.gmail_get_message(MAILBOX, "m1")["attachments"]
    assert attachments == [
        {"filename": "book.xlsx", "mime_type": "application/vnd.ms-excel", "size": 42, "attachment_id": "a1"}
    ]


def test_decode_part_tolerates_missing_base64_padding():
    assert googlemcp_tools._decode_part({"body": {"data": base64.urlsafe_b64encode(b"abcde").decode().rstrip("=")}})


# %%
# Gmail writes #


def test_gmail_modify_message_sends_both_label_lists(monkeypatch):
    gmail_env(monkeypatch)
    calls = stub_requests(monkeypatch, lambda *args: FakeResponse({"id": "m1", "labelIds": ["INBOX"]}))
    result = googlemcp_tools.gmail_modify_message(MAILBOX, "m1", add_labels=["A"], remove_labels=["UNREAD"])
    assert calls[0]["payload"] == {"addLabelIds": ["A"], "removeLabelIds": ["UNREAD"]}
    assert result == {"id": "m1", "labels": ["INBOX"]}


def test_gmail_modify_message_without_labels_is_an_error(monkeypatch):
    gmail_env(monkeypatch)
    with pytest.raises(ValueError, match="at least one label"):
        googlemcp_tools.gmail_modify_message(MAILBOX, "m1")


def test_gmail_trash_message_untrashes_on_undo(monkeypatch):
    gmail_env(monkeypatch)
    calls = stub_requests(monkeypatch, lambda *args: FakeResponse({"id": "m1", "labelIds": []}))
    assert googlemcp_tools.gmail_trash_message(MAILBOX, "m1", undo=True)["action"] == "untrash"
    assert calls[0]["url"].endswith("/untrash")


def test_gmail_send_message_builds_a_raw_mime_payload(monkeypatch):
    gmail_env(monkeypatch)
    calls = stub_requests(monkeypatch, lambda *args: FakeResponse({"id": "m9", "threadId": "t9"}))
    googlemcp_tools.gmail_send_message(MAILBOX, ["a@b.com", "c@d.com"], "Subj", "Body", cc="e@f.com")
    raw = base64.urlsafe_b64decode(calls[0]["payload"]["raw"]).decode("utf-8")
    assert "To: a@b.com, c@d.com" in raw
    assert "Cc: e@f.com" in raw
    assert "Subject: Subj" in raw
    assert "Body" in raw


def test_gmail_send_message_threads_a_reply(monkeypatch):
    gmail_env(monkeypatch)

    def handler(method, url, params, payload):
        if method == "GET":
            return FakeResponse({
                "threadId": "t1",
                "payload": {"headers": [
                    {"name": "Message-ID", "value": "<orig@mail>"},
                    {"name": "References", "value": "<older@mail>"},
                ]},
            })
        return FakeResponse({"id": "m9", "threadId": "t1"})

    calls = stub_requests(monkeypatch, handler)
    googlemcp_tools.gmail_send_message(MAILBOX, "a@b.com", "Re: x", "y", reply_to_message_id="m1")
    sent = calls[-1]["payload"]
    raw = base64.urlsafe_b64decode(sent["raw"]).decode("utf-8")
    assert sent["threadId"] == "t1"
    assert "In-Reply-To: <orig@mail>" in raw
    assert "References: <older@mail> <orig@mail>" in raw


# %%
# Calendar #


def calendar_env(monkeypatch):
    monkeypatch.setattr(googlemcp_tools, "calendar_headers", lambda source: {"Authorization": "Bearer tok"})


RAW_EVENT = {
    "id": "e1",
    "status": "confirmed",
    "summary": "Revenue sync",
    "start": {"dateTime": "2026-08-27T10:00:00-05:00"},
    "end": {"dateTime": "2026-08-27T10:30:00-05:00"},
    "creator": {"email": "maker@x.com"},
    "organizer": {"email": "owner@x.com"},
    "created": "2026-08-26T16:55:18.000Z",
    "updated": "2026-08-27T14:59:11.696Z",
    "attendees": [
        {"email": "owner@x.com", "responseStatus": "accepted", "organizer": True},
        {"email": "me@x.com", "responseStatus": "needsAction", "self": True, "optional": True},
    ],
    "htmlLink": "https://cal/e1",
}


def test_calendar_get_event_keeps_creator_organizer_and_attendees(monkeypatch):
    calendar_env(monkeypatch)
    stub_requests(monkeypatch, lambda *args: FakeResponse(RAW_EVENT))
    event = googlemcp_tools.calendar_get_event(CALENDAR_SOURCE, "e1")
    assert event["creator"] == {"email": "maker@x.com"}
    assert event["organizer"] == {"email": "owner@x.com"}
    assert event["created"] == "2026-08-26T16:55:18.000Z"
    assert event["attendees"][1] == {
        "email": "me@x.com", "name": "", "response": "needsAction",
        "optional": True, "organizer": False, "self": True,
    }


def test_calendar_get_event_url_encodes_the_calendar_id(monkeypatch):
    calendar_env(monkeypatch)
    calls = stub_requests(monkeypatch, lambda *args: FakeResponse(RAW_EVENT))
    googlemcp_tools.calendar_get_event(CALENDAR_SOURCE, "e1", calendar_id="a b@group.calendar.google.com")
    assert "a%20b%40group.calendar.google.com" in calls[0]["url"]


def test_calendar_search_events_passes_the_time_window(monkeypatch):
    calendar_env(monkeypatch)
    calls = stub_requests(monkeypatch, lambda *args: FakeResponse({"items": [RAW_EVENT]}))
    events = googlemcp_tools.calendar_search_events(
        CALENDAR_SOURCE, query="revenue", time_min="2026-08-27T00:00:00Z", time_max="2026-08-28T00:00:00Z"
    )
    assert calls[0]["params"]["q"] == "revenue"
    assert calls[0]["params"]["timeMin"] == "2026-08-27T00:00:00Z"
    assert calls[0]["params"]["singleEvents"] == "true"
    assert events[0]["title"] == "Revenue sync"


def test_calendar_create_event_defaults_to_not_emailing_guests(monkeypatch):
    calendar_env(monkeypatch)
    calls = stub_requests(monkeypatch, lambda *args: FakeResponse(RAW_EVENT))
    googlemcp_tools.calendar_create_event(
        CALENDAR_SOURCE, "Sync", {"dateTime": "2026-08-27T10:00:00-05:00"}, {"dateTime": "2026-08-27T10:30:00-05:00"}
    )
    assert calls[0]["params"] == {"sendUpdates": "none"}
    assert calls[0]["payload"]["summary"] == "Sync"
    assert "send_updates" not in calls[0]["payload"]


def test_calendar_create_event_can_notify_guests(monkeypatch):
    calendar_env(monkeypatch)
    calls = stub_requests(monkeypatch, lambda *args: FakeResponse(RAW_EVENT))
    googlemcp_tools.calendar_create_event(
        CALENDAR_SOURCE, "Sync", {"date": "2026-08-27"}, {"date": "2026-08-28"}, send_updates="all"
    )
    assert calls[0]["params"] == {"sendUpdates": "all"}


def test_calendar_update_event_patches_only_what_changed(monkeypatch):
    calendar_env(monkeypatch)
    calls = stub_requests(monkeypatch, lambda *args: FakeResponse(RAW_EVENT))
    googlemcp_tools.calendar_update_event(CALENDAR_SOURCE, "e1", location="Room 2")
    assert calls[0]["method"] == "PATCH"
    assert calls[0]["payload"] == {"location": "Room 2"}


def test_calendar_update_event_without_fields_is_an_error(monkeypatch):
    calendar_env(monkeypatch)
    with pytest.raises(ValueError, match="at least one field"):
        googlemcp_tools.calendar_update_event(CALENDAR_SOURCE, "e1")


def test_calendar_delete_event_reports_what_it_removed(monkeypatch):
    calendar_env(monkeypatch)
    calls = stub_requests(monkeypatch, lambda *args: FakeResponse({}))
    assert googlemcp_tools.calendar_delete_event(CALENDAR_SOURCE, "e1") == {
        "id": "e1", "calendar_id": "primary", "deleted": True
    }
    assert calls[0]["method"] == "DELETE"


def test_calendar_list_calendars_flags_the_primary(monkeypatch):
    calendar_env(monkeypatch)
    stub_requests(monkeypatch, lambda *args: FakeResponse({"items": [
        {"id": "p", "summary": "Mine", "primary": True, "accessRole": "owner"},
        {"id": "t", "summaryOverride": "Renamed", "summary": "Team", "accessRole": "reader"},
    ]}))
    calendars = googlemcp_tools.calendar_list_calendars(CALENDAR_SOURCE)
    assert calendars[0]["primary"] is True
    assert calendars[1]["name"] == "Renamed"  # summaryOverride wins


# %%
# HTTP plumbing #


def test_request_raises_with_the_response_body(monkeypatch):
    stub_requests(monkeypatch, lambda *args: FakeResponse({"error": "nope"}, status_code=403))
    with pytest.raises(ValueError, match="returned 403"):
        googlemcp_tools._request("GET", "https://x/y", {})


def test_paged_follows_next_page_token_until_the_limit(monkeypatch):
    pages = [
        FakeResponse({"items": [1, 2], "nextPageToken": "p2"}),
        FakeResponse({"items": [3, 4], "nextPageToken": "p3"}),
        FakeResponse({"items": [5]}),
    ]
    stub_requests(monkeypatch, lambda *args: pages.pop(0))
    assert googlemcp_tools._paged("https://x/y", {}, {}, "items", limit=3) == [1, 2, 3]


def test_paged_stops_when_a_page_has_no_token(monkeypatch):
    pages = [FakeResponse({"items": [1, 2], "nextPageToken": "p2"}), FakeResponse({"items": [3]})]
    stub_requests(monkeypatch, lambda *args: pages.pop(0))
    assert googlemcp_tools._paged("https://x/y", {}, {}, "items") == [1, 2, 3]


# %%
