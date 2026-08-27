# %%
# Imports #

import base64
import json
import os
import re
from email.message import EmailMessage
from urllib.parse import quote

import requests
import yaml
from utils.google_oauth_tools import cached_access_token
from utils.inventory_tools import credentials_context, find_credentials_dirs
from utils.secret_tools import resolve_secret

# %%
# Variables #

GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"
DEFAULT_HTTP_TIMEOUT = 30

# Matches the scope the contexts' own mail tooling mints its tokens with -
# gmail.modify covers read, label, trash and send, but never permanent
# deletion.
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.modify"

MAILBOX_TYPES = ("gmail",)
REQUIRED_MAILBOX_KEYS = ("name", "type", "oauth_env", "token_env")

# Gmail caps a single messages.list page at 500.
MAX_GMAIL_RESULTS = 500


# %%
# Mailbox config discovery #


def discover_googlemail_configs(credentials_root, repo_root=None):
    """
    Locate every googlemail config to load: an optional ``googlemail.yaml`` in
    the dotfiles repo root (tracked, so secrets-free mailboxes only) plus, for
    each sibling ``*_credentials`` repo, an optional
    ``<context>_googlemail.yaml`` - the same overlay pattern the status and
    calendar boards use. Returns a list of (config_path, base_dir) pairs.
    """
    configs = []
    if repo_root:
        main_config = os.path.join(repo_root, "googlemail.yaml")
        if os.path.exists(main_config):
            configs.append((main_config, repo_root))
    for credentials_dir in find_credentials_dirs(credentials_root):
        overlay = os.path.join(credentials_dir, f"{credentials_context(credentials_dir)}_googlemail.yaml")
        if os.path.exists(overlay):
            configs.append((overlay, credentials_dir))
    return configs


def load_mailboxes(credentials_root, repo_root=None, config_path=None):
    """
    Load every discovered googlemail config, returning (mailboxes, config_paths).
    Each mailbox is stamped with ``_base_dir`` (its config's repo root, which
    env_file paths resolve against) and ``_config`` (for error messages).
    Mailbox names must be unique across ALL loaded configs.
    """
    if config_path:
        located = [(config_path, os.path.dirname(os.path.abspath(config_path)))]
    else:
        located = discover_googlemail_configs(credentials_root, repo_root)
    mailboxes = []
    seen: dict = {}
    for path, base_dir in located:
        for mailbox in _parse_mailbox_config(path):
            if mailbox["name"] in seen:
                raise ValueError(
                    f"Duplicate googlemail mailbox name '{mailbox['name']}' in {path} "
                    f"(already defined in {seen[mailbox['name']]})"
                )
            seen[mailbox["name"]] = path
            mailbox["_base_dir"] = base_dir
            mailbox["_config"] = path
            mailboxes.append(mailbox)
    return mailboxes, [path for path, _ in located]


def _parse_mailbox_config(config_path):
    """Parse one googlemail config and validate the mailbox schema, returning a list of mailbox dicts."""
    with open(config_path, "r", encoding="utf-8") as file_handle:
        payload = yaml.safe_load(file_handle) or []
    if not isinstance(payload, list):
        raise ValueError(f"{config_path}: expected a list of mailboxes, got {type(payload).__name__}")
    for mailbox in payload:
        if not isinstance(mailbox, dict):
            raise ValueError(f"{config_path}: expected a list of mailbox mappings, got {type(mailbox).__name__}")
        missing = [key for key in REQUIRED_MAILBOX_KEYS if not mailbox.get(key)]
        if missing:
            raise ValueError(f"{config_path}: mailbox {mailbox.get('name', '<unnamed>')} is missing {missing}")
        if mailbox["type"] not in MAILBOX_TYPES:
            raise ValueError(
                f"{config_path}: mailbox '{mailbox['name']}' has unknown type "
                f"'{mailbox['type']}' (expected one of {MAILBOX_TYPES})"
            )
    return payload


def plural(label):
    """Pluralize a config label for error messages - "mailbox" must not become "mailboxs"."""
    return f"{label}es" if label.endswith(("s", "x", "z", "ch", "sh")) else f"{label}s"


def find_by_name(entries, name, label):
    """Pick the one config entry called ``name``, erroring with the valid names when it is not there."""
    for entry in entries:
        if entry["name"] == name:
            return entry
    available = ", ".join(entry["name"] for entry in entries) or "(none configured)"
    raise ValueError(f"unknown {label} '{name}' - configured {plural(label)}: {available}")


# %%
# Gmail auth #


def _gmail_credentials(mailbox):
    """
    (client_id, client_secret, refresh_token) for a mailbox. The token env var
    holds a google-auth "authorized user" JSON, which normally carries the
    client id/secret itself; when it does not, they come from the OAuth client
    JSON in the oauth env var (``installed``/``web`` wrapped).
    """
    token = json.loads(resolve_secret(mailbox, "token_env"))
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise ValueError(f"'{mailbox['name']}': {mailbox['token_env']} has no refresh_token")
    client_id, client_secret = token.get("client_id"), token.get("client_secret")
    if not (client_id and client_secret):
        oauth = json.loads(resolve_secret(mailbox, "oauth_env"))
        installed = oauth.get("installed") or oauth.get("web") or oauth
        client_id = client_id or installed.get("client_id")
        client_secret = client_secret or installed.get("client_secret")
    if not (client_id and client_secret):
        raise ValueError(
            f"'{mailbox['name']}': no client_id/client_secret in either "
            f"{mailbox['token_env']} or {mailbox['oauth_env']}"
        )
    return client_id, client_secret, refresh_token


def gmail_headers(mailbox):
    """Authorization header for a mailbox, off a memoized access token."""
    client_id, client_secret, refresh_token = _gmail_credentials(mailbox)
    token = cached_access_token(client_id, client_secret, refresh_token, context=mailbox["name"])
    return {"Authorization": f"Bearer {token}"}


def calendar_headers(source):
    """Authorization header for a calendarboard google_calendar source, off a memoized access token."""
    token = cached_access_token(
        resolve_secret(source, "client_id_env"),
        resolve_secret(source, "client_secret_env"),
        resolve_secret(source, "refresh_token_env"),
        context=source["name"],
    )
    return {"Authorization": f"Bearer {token}"}


# %%
# HTTP helpers #


def _request(method, url, headers, params=None, payload=None):
    """One Google API call, raising with the response body on anything non-2xx."""
    response = requests.request(
        method, url, headers=headers, params=params, json=payload, timeout=DEFAULT_HTTP_TIMEOUT
    )
    if response.status_code // 100 != 2:
        raise ValueError(f"Google API returned {response.status_code} for {method} {url}: {response.text[:300]}")
    return response.json() if response.content else {}


def _paged(url, headers, params, key, limit=None):
    """Follow nextPageToken, accumulating ``key``, stopping once ``limit`` items are in hand."""
    items: list = []
    params = dict(params or {})
    while True:
        payload = _request("GET", url, headers, params=params)
        items += payload.get(key, [])
        page_token = payload.get("nextPageToken")
        if not page_token or (limit is not None and len(items) >= limit):
            return items[:limit] if limit is not None else items
        params = dict(params, pageToken=page_token)


# %%
# Gmail reads #


def gmail_profile(mailbox):
    """The mailbox's own address and message/thread totals - the cheapest proof the credentials work."""
    return _request("GET", f"{GMAIL_API}/users/me/profile", gmail_headers(mailbox))


def gmail_list_labels(mailbox):
    """Every label, so callers can map names to the ids modify_message needs."""
    payload = _request("GET", f"{GMAIL_API}/users/me/labels", gmail_headers(mailbox))
    return [
        {"id": label.get("id"), "name": label.get("name"), "type": label.get("type")}
        for label in payload.get("labels", [])
    ]


def gmail_search(mailbox, query="", max_results=25, include_spam_trash=False):
    """
    Gmail search (the same query syntax as the web UI's search box), returned
    as a list of summaries: id, threadId, From/To/Subject/Date, snippet and
    labels. Metadata format only - no bodies, so a wide search stays cheap.
    """
    headers = gmail_headers(mailbox)
    max_results = max(1, min(int(max_results), MAX_GMAIL_RESULTS))
    params = {"maxResults": max_results}
    if query:
        params["q"] = query
    if include_spam_trash:
        params["includeSpamTrash"] = "true"
    stubs = _paged(f"{GMAIL_API}/users/me/messages", headers, params, "messages", limit=max_results)
    summaries = []
    for stub in stubs:
        raw = _request(
            "GET",
            f"{GMAIL_API}/users/me/messages/{quote(stub['id'])}",
            headers,
            params={
                "format": "metadata",
                "metadataHeaders": ["From", "To", "Cc", "Subject", "Date"],
            },
        )
        summaries.append(_gmail_summary(raw))
    return summaries


def _gmail_summary(raw):
    """Gmail message (metadata format) -> flat summary dict."""
    headers = _header_map(raw.get("payload") or {})
    return {
        "id": raw.get("id"),
        "thread_id": raw.get("threadId"),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "cc": headers.get("cc", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
        "snippet": raw.get("snippet", ""),
        "labels": raw.get("labelIds", []),
        "unread": "UNREAD" in (raw.get("labelIds") or []),
    }


def _header_map(payload):
    """MIME headers as a lowercased-name -> value dict."""
    return {
        (header.get("name") or "").lower(): header.get("value") or ""
        for header in (payload.get("headers") or [])
    }


def gmail_get_message(mailbox, message_id, body_limit=20000):
    """
    One message in full: the summary fields plus the decoded plain-text body
    (falling back to de-tagged HTML when the sender sent HTML only) and a list
    of attachment names/sizes.
    """
    raw = _request(
        "GET", f"{GMAIL_API}/users/me/messages/{quote(message_id)}", gmail_headers(mailbox), params={"format": "full"}
    )
    payload = raw.get("payload") or {}
    message = _gmail_summary(raw)
    body = _extract_body(payload)
    message["body"] = body[: body_limit - 1] + "…" if len(body) > body_limit else body
    message["attachments"] = _extract_attachments(payload)
    return message


def _walk_parts(payload):
    """Depth-first walk of a MIME tree, yielding every part including the root."""
    yield payload
    for part in payload.get("parts") or []:
        yield from _walk_parts(part)


def _decode_part(part):
    """base64url-decode one part's data to text, tolerating bad padding and stray bytes."""
    data = ((part.get("body") or {}).get("data")) or ""
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8", errors="replace")


def _extract_body(payload):
    """Prefer every text/plain part joined; fall back to HTML with tags stripped."""
    plain = [_decode_part(part) for part in _walk_parts(payload) if part.get("mimeType") == "text/plain"]
    joined = "\n".join(chunk for chunk in plain if chunk).strip()
    if joined:
        return joined
    html = [_decode_part(part) for part in _walk_parts(payload) if part.get("mimeType") == "text/html"]
    text = re.sub(r"<[^>]+>", " ", "\n".join(chunk for chunk in html if chunk))
    return re.sub(r"[ \t]+", " ", text).strip()


def _extract_attachments(payload):
    """Attachment filename/mime/size/id for every part that has a filename."""
    return [
        {
            "filename": part.get("filename"),
            "mime_type": part.get("mimeType"),
            "size": (part.get("body") or {}).get("size"),
            "attachment_id": (part.get("body") or {}).get("attachmentId"),
        }
        for part in _walk_parts(payload)
        if part.get("filename")
    ]


# %%
# Gmail writes #


def gmail_modify_message(mailbox, message_id, add_labels=None, remove_labels=None):
    """
    Add/remove label ids on one message. ``UNREAD`` and ``STARRED`` are label
    ids too, so this covers mark-read/unread and star/unstar; ids come from
    gmail_list_labels.
    """
    payload = {"addLabelIds": list(add_labels or []), "removeLabelIds": list(remove_labels or [])}
    if not (payload["addLabelIds"] or payload["removeLabelIds"]):
        raise ValueError("gmail_modify_message needs at least one label to add or remove")
    raw = _request(
        "POST",
        f"{GMAIL_API}/users/me/messages/{quote(message_id)}/modify",
        gmail_headers(mailbox),
        payload=payload,
    )
    return {"id": raw.get("id"), "labels": raw.get("labelIds", [])}


def gmail_trash_message(mailbox, message_id, undo=False):
    """
    Move a message to Trash, or back out of it with ``undo``. Recoverable on
    purpose - gmail.modify cannot permanently delete, and this deliberately
    does not try to.
    """
    action = "untrash" if undo else "trash"
    raw = _request(
        "POST", f"{GMAIL_API}/users/me/messages/{quote(message_id)}/{action}", gmail_headers(mailbox)
    )
    return {"id": raw.get("id"), "labels": raw.get("labelIds", []), "action": action}


def gmail_send_message(mailbox, to, subject, body, cc=None, bcc=None, reply_to_message_id=None, thread_id=None):
    """
    Send a plain-text message as the mailbox's own address. Passing
    ``reply_to_message_id`` threads the reply properly (In-Reply-To/References
    off that message's Message-ID) and defaults thread_id to its thread.
    """
    message = EmailMessage()
    message["To"] = _join_addresses(to)
    if cc:
        message["Cc"] = _join_addresses(cc)
    if bcc:
        message["Bcc"] = _join_addresses(bcc)
    message["Subject"] = subject
    message.set_content(body)
    payload = {}
    if reply_to_message_id:
        original = _request(
            "GET",
            f"{GMAIL_API}/users/me/messages/{quote(reply_to_message_id)}",
            gmail_headers(mailbox),
            params={"format": "metadata", "metadataHeaders": ["Message-ID", "References"]},
        )
        headers = _header_map(original.get("payload") or {})
        original_id = headers.get("message-id", "")
        if original_id:
            message["In-Reply-To"] = original_id
            message["References"] = f"{headers.get('references', '')} {original_id}".strip()
        payload["threadId"] = thread_id or original.get("threadId")
    elif thread_id:
        payload["threadId"] = thread_id
    payload["raw"] = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    raw = _request("POST", f"{GMAIL_API}/users/me/messages/send", gmail_headers(mailbox), payload=payload)
    return {"id": raw.get("id"), "thread_id": raw.get("threadId"), "labels": raw.get("labelIds", [])}


def _join_addresses(value):
    """Accept a single address or a list of them; Gmail wants one comma-joined header."""
    if isinstance(value, str):
        return value
    return ", ".join(value)


# %%
# Calendar reads #


def calendar_list_calendars(source):
    """Every calendar on the account, as the web UI's sidebar shows them."""
    calendars = _paged(
        f"{CALENDAR_API}/users/me/calendarList", calendar_headers(source), {"minAccessRole": "reader"}, "items"
    )
    return [
        {
            "id": calendar.get("id"),
            "name": calendar.get("summaryOverride") or calendar.get("summary") or calendar.get("id"),
            "primary": bool(calendar.get("primary")),
            "access_role": calendar.get("accessRole"),
        }
        for calendar in calendars
    ]


def calendar_get_event(source, event_id, calendar_id="primary"):
    """
    One event with the provenance fields the board's summary drops: ``creator``
    (who made the event) and ``organizer`` (whose calendar owns it), plus the
    full attendee list with per-person response status.

    Google records no per-attendee provenance, so who added any individual
    guest after the fact is not answerable from this - creator/organizer is as
    close as the API gets.
    """
    raw = _request(
        "GET",
        f"{CALENDAR_API}/calendars/{quote(calendar_id)}/events/{quote(event_id)}",
        calendar_headers(source),
    )
    return _event_detail(raw)


def _event_detail(raw):
    """Calendar API event -> detail dict (creator/organizer/attendees kept verbatim)."""
    return {
        "id": raw.get("id"),
        "status": raw.get("status"),
        "title": raw.get("summary") or "(no title)",
        "start": raw.get("start"),
        "end": raw.get("end"),
        "location": raw.get("location") or "",
        "description": raw.get("description") or "",
        "creator": raw.get("creator") or {},
        "organizer": raw.get("organizer") or {},
        "attendees": [
            {
                "email": attendee.get("email"),
                "name": attendee.get("displayName") or "",
                "response": attendee.get("responseStatus"),
                "optional": bool(attendee.get("optional")),
                "organizer": bool(attendee.get("organizer")),
                "self": bool(attendee.get("self")),
            }
            for attendee in raw.get("attendees") or []
        ],
        "recurring_event_id": raw.get("recurringEventId") or "",
        "created": raw.get("created") or "",
        "updated": raw.get("updated") or "",
        "link": raw.get("hangoutLink") or raw.get("htmlLink") or "",
    }


def calendar_search_events(source, query="", calendar_id="primary", time_min=None, time_max=None, max_results=25):
    """
    Events on one calendar, optionally full-text filtered by ``query``, as
    detail dicts. Recurring events arrive pre-expanded (singleEvents), so
    ``time_min``/``time_max`` (RFC3339 strings) bound real occurrences.
    """
    params = {"singleEvents": "true", "orderBy": "startTime", "maxResults": max(1, min(int(max_results), 250))}
    if query:
        params["q"] = query
    if time_min:
        params["timeMin"] = time_min
    if time_max:
        params["timeMax"] = time_max
    raws = _paged(
        f"{CALENDAR_API}/calendars/{quote(calendar_id)}/events",
        calendar_headers(source),
        params,
        "items",
        limit=params["maxResults"],
    )
    return [_event_detail(raw) for raw in raws]


# %%
# Calendar writes #


def calendar_create_event(source, summary, start, end, calendar_id="primary", **fields):
    """
    Create an event. ``start``/``end`` are Calendar API date/dateTime objects
    (e.g. ``{"dateTime": "2026-08-27T10:00:00-05:00"}`` or
    ``{"date": "2026-08-27"}``). Extra ``fields`` (description, location,
    attendees, recurrence, ...) pass straight through.
    """
    payload = dict(fields, summary=summary, start=start, end=end)
    send_updates = payload.pop("send_updates", "none")
    raw = _request(
        "POST",
        f"{CALENDAR_API}/calendars/{quote(calendar_id)}/events",
        calendar_headers(source),
        params={"sendUpdates": send_updates},
        payload=payload,
    )
    return _event_detail(raw)


def calendar_update_event(source, event_id, calendar_id="primary", send_updates="none", **fields):
    """
    Patch an existing event - only the passed ``fields`` change. Same field
    names as calendar_create_event.
    """
    if not fields:
        raise ValueError("calendar_update_event needs at least one field to change")
    raw = _request(
        "PATCH",
        f"{CALENDAR_API}/calendars/{quote(calendar_id)}/events/{quote(event_id)}",
        calendar_headers(source),
        params={"sendUpdates": send_updates},
        payload=fields,
    )
    return _event_detail(raw)


def calendar_delete_event(source, event_id, calendar_id="primary", send_updates="none"):
    """Delete an event. Unlike Gmail's trash this is not recoverable through the API."""
    _request(
        "DELETE",
        f"{CALENDAR_API}/calendars/{quote(calendar_id)}/events/{quote(event_id)}",
        calendar_headers(source),
        params={"sendUpdates": send_updates},
    )
    return {"id": event_id, "calendar_id": calendar_id, "deleted": True}


# %%
