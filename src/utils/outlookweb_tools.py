# %%
# Imports #

import base64
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import yaml

from utils.inventory_tools import credentials_context, find_credentials_dirs

# %%
# Variables #

# Outlook on the web, signed in inside a browser profile on this Mac, as the
# way to reach an Exchange mailbox and calendar when no desktop app holds the
# account and the tenant refuses consent to any app of our own. The page
# already holds Outlook's own access token in its localStorage; the JavaScript
# below runs inside that tab, reads the token there and calls the Outlook REST
# API from the tab. The token never leaves the browser; only the API's answer
# comes back over AppleScript.

# <context>_outlookweb.yaml: which signed-in Outlook tab a context reaches.
CONFIG_KIND = "outlookweb"
# Hosts Outlook on the web is served from; any open tab on one of them will do.
OUTLOOK_HOSTS = ("outlook.cloud.microsoft", "outlook.office.com", "outlook.office365.com")
OPEN_URL = "https://outlook.cloud.microsoft/calendar/view/week"
API_BASE = "https://outlook.office.com/api/v2.0/me"
# The access token the page keeps for the Outlook REST API carries this scope.
TOKEN_SCOPE = "https://outlook.office.com/Calendars.ReadWrite"
# A token this close to expiry is treated as expired: the tab is reloaded so
# Outlook mints a fresh one.
TOKEN_MARGIN_SECONDS = 120
REQUEST_TIMEOUT_SECONDS = 60
TAB_WAIT_SECONDS = 90
POLL_SECONDS = 0.5

# ResponseStatus.Response in the REST API, as the mac server names them.
RESPONSES = {
    "Organizer": "organizer",
    "Accepted": "accepted",
    "TentativelyAccepted": "tentative",
    "Declined": "declined",
    "NotResponded": "needs_action",
    "None": None,
}

EVENT_FIELDS = (
    "Id,iCalUId,Subject,Start,End,IsAllDay,IsCancelled,ResponseStatus,Attendees,Organizer,IsOrganizer,"
    "Location,Type,SeriesMasterId,ShowAs,OnlineMeetingUrl"
)
MESSAGE_FIELDS = (
    "Id,InternetMessageId,Subject,From,ToRecipients,ReceivedDateTime,BodyPreview,IsRead,Flag,ParentFolderId,WebLink"
)
PAGE_SIZE = 100


# %%
# Config #


def config_path(credentials_root, context):
    """The pinned context's ``<context>_outlookweb.yaml``, or None when it has none."""
    for credentials_dir in find_credentials_dirs(credentials_root):
        if credentials_context(credentials_dir) == context:
            path = os.path.join(credentials_dir, f"{context}_{CONFIG_KIND}.yaml")
            return path if os.path.exists(path) else None
    return None


def load_accounts(path):
    """
    The accounts in one config. Each names the mailbox address the tab must be
    signed in as, and the browser and profile directory a tab is opened in when
    none is open. sign_in is the name the tenant signs the account in as,
    which can differ from the mailbox address; a tab signed in as anyone else
    is refused.
    """
    with open(path, "r", encoding="utf-8") as file_handle:
        payload = yaml.safe_load(file_handle) or []
    if not isinstance(payload, list):
        raise ValueError(f"{path}: expected a list of accounts")
    accounts, seen = [], set()
    for entry in payload:
        if not isinstance(entry, dict) or not all(
            entry.get(key) for key in ("name", "address", "sign_in", "browser", "profile")
        ):
            raise ValueError(f"{path}: every account needs name, address, sign_in, browser and profile")
        if entry["name"] in seen:
            raise ValueError(f"{path}: {entry['name']} is listed twice")
        seen.add(entry["name"])
        accounts.append({**entry, "_config": path})
    return accounts


def require_macos():
    if sys.platform != "darwin":
        raise RuntimeError("the Outlook web server drives a browser through AppleScript and only runs on macOS")


# %%
# Browser #


def _osascript(script):
    out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(
            f"{out.stderr.strip()} - in the browser, enable View > Developer > Allow JavaScript "
            "from Apple Events if that is what it refused"
        )
    return out.stdout.strip()


def _applescript_string(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _hosts_clause():
    return " or ".join(f"(URL of tb) contains {_applescript_string(host)}" for host in OUTLOOK_HOSTS)


def _on_tab(account, action):
    """Run one AppleScript line against the first Outlook tab, found by URL on every call, never by index."""
    return _osascript(
        f"tell application {_applescript_string(account['browser'])}\n"
        "repeat with win in windows\n"
        "repeat with tb in tabs of win\n"
        f"if {_hosts_clause()} then\n"
        f"{action}\n"
        "end if\n"
        "end repeat\n"
        "end repeat\n"
        'return "NO_TAB"\n'
        "end tell"
    )


def run_js(account, js):
    return _on_tab(account, f"return (execute tb javascript {_applescript_string(js)})")


def open_tab(account):
    """Open Outlook in the account's own profile; never in whichever window is in front."""
    subprocess.run(
        ["open", "-na", account["browser"], "--args", f"--profile-directory={account['profile']}", OPEN_URL],
        check=True,
    )


# The token is chosen and checked in the page. Only its identity and expiry
# come back from here, never the token.
TOKEN_JS = """
(function () {
  const now = Math.floor(Date.now() / 1000);
  const tokens = Object.keys(localStorage)
    .filter(key => key.includes('|accesstoken|'))
    .map(key => { try { return JSON.parse(localStorage.getItem(key)); } catch (e) { return null; } })
    .filter(item => item && (' ' + item.target + ' ').includes(' SCOPE '))
    .sort((a, b) => Number(b.expiresOn) - Number(a.expiresOn));
  if (!tokens.length) return JSON.stringify({state: 'none'});
  const claims = JSON.parse(atob(tokens[0].secret.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
  return JSON.stringify({state: 'ok', expires: Number(tokens[0].expiresOn), now: now,
                         user: (claims.upn || claims.preferred_username || claims.unique_name || '').toLowerCase()});
})()
"""

REQUEST_JS = """
(function () {
  const store = window.__outlookweb = window.__outlookweb || {};
  const token = Object.keys(localStorage)
    .filter(key => key.includes('|accesstoken|'))
    .map(key => { try { return JSON.parse(localStorage.getItem(key)); } catch (e) { return null; } })
    .filter(item => item && (' ' + item.target + ' ').includes(' SCOPE '))
    .sort((a, b) => Number(b.expiresOn) - Number(a.expiresOn))[0];
  const request = REQUEST;
  store[request.id] = {done: false};
  const headers = Object.assign({Authorization: 'Bearer ' + token.secret, Accept: 'application/json'}, request.headers);
  if (request.body !== null) headers['Content-Type'] = 'application/json';
  fetch(request.url, {method: request.method, headers: headers,
                      body: request.body === null ? undefined : JSON.stringify(request.body)})
    .then(response => response.text().then(text => {
      store[request.id] = {done: true, status: response.status, text: text};
    }))
    .catch(error => { store[request.id] = {done: true, status: 0, text: String(error)}; });
  return 'started';
})()
"""


def _token_state(account):
    raw = run_js(account, TOKEN_JS.replace("SCOPE", TOKEN_SCOPE))
    if raw == "NO_TAB":
        return None
    return json.loads(raw)


def ensure_session(account):
    """
    An Outlook tab signed in as the account's sign-in name with a live token. Opens
    a tab in the account's profile when none is open, and reloads the tab once
    when its token is about to expire. Refuses a tab signed in as anyone else.
    """
    require_macos()
    deadline = time.monotonic() + TAB_WAIT_SECONDS
    opened = reloaded = False
    while True:
        state = _token_state(account)
        if state is None and not opened:
            open_tab(account)
            opened = True
        elif state is not None and state["state"] == "ok":
            if state["user"] != account["sign_in"].lower():
                raise PermissionError(
                    f"the open Outlook tab is signed in as {state['user'] or 'nobody'}, not {account['sign_in']} - "
                    f"sign in as {account['sign_in']} in the {account['browser']} profile {account['profile']}"
                )
            if state["expires"] - state["now"] > TOKEN_MARGIN_SECONDS:
                return state
            if not reloaded:
                _on_tab(account, 'tell tb to reload\nreturn "reloaded"')
                reloaded = True
        if time.monotonic() > deadline:
            raise RuntimeError(
                f"no signed-in Outlook tab for {account['address']} in {account['browser']} after "
                f"{TAB_WAIT_SECONDS}s - open {OPEN_URL} in the profile {account['profile']} and sign in"
            )
        time.sleep(2)


def request(account, method, url, body=None, headers=None):
    """One Outlook REST call made from inside the tab. Returns the decoded JSON (or None for an empty reply)."""
    ensure_session(account)
    identifier = uuid.uuid4().hex
    spec = {"id": identifier, "method": method, "url": url, "body": body, "headers": headers or {}}
    started = run_js(account, REQUEST_JS.replace("SCOPE", TOKEN_SCOPE).replace("REQUEST", json.dumps(spec)))
    if started != "started":
        raise RuntimeError(f"the Outlook tab did not start the request ({started})")
    deadline = time.monotonic() + REQUEST_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
        raw = run_js(account, f"JSON.stringify((window.__outlookweb || {{}})['{identifier}'] || null)")
        result = json.loads(raw) if raw not in ("", "NO_TAB") else None
        if result and result["done"]:
            run_js(account, f"delete window.__outlookweb['{identifier}']; 'ok'")
            if not 200 <= result["status"] < 300:
                raise RuntimeError(
                    f"Outlook refused {method} {url.split('?')[0]}: {result['status']} {result['text'][:300]}"
                )
            return json.loads(result["text"]) if result["text"].strip() else None
    raise RuntimeError(f"Outlook did not answer {method} {url.split('?')[0]} within {REQUEST_TIMEOUT_SECONDS}s")


def get_all(account, url, headers=None, limit=None):
    """Every item of a paged collection, following @odata.nextLink."""
    items = []
    while url:
        page = request(account, "GET", url, headers=headers)
        items += page.get("value", [])
        if limit and len(items) >= limit:
            return items[:limit]
        url = page.get("@odata.nextLink")
    return items


# %%
# Time #


def utc_iso(moment):
    """An aware datetime as the naive UTC string the REST API takes with TimeZone UTC."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def from_api(stamp):
    """A DateTimeTimeZone or ISO string the API returned in UTC, as an aware local datetime."""
    text = stamp["DateTime"] if isinstance(stamp, dict) else stamp
    text = text.rstrip("Z").split(".")[0]
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).astimezone()


def parse_moment(text):
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return moment


UTC_HEADERS = {"Prefer": 'outlook.timezone="UTC"'}


# %%
# Calendar #


def calendar_list_calendars(account):
    """Every calendar of the mailbox. last_synced is now: every read is live from the server."""
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    calendars = get_all(account, f"{API_BASE}/calendars?$select=Id,Name,CanEdit,Owner&$top={PAGE_SIZE}")
    return [
        {
            "calendar_id": cal["Id"],
            "title": cal["Name"],
            "account": account["name"],
            "writable": bool(cal.get("CanEdit")),
            "owner": (cal.get("Owner") or {}).get("Address", ""),
            "last_synced": now,
        }
        for cal in calendars
    ]


def serialize_event(account, calendar_id, item):
    all_day = bool(item.get("IsAllDay"))
    start, end = from_api(item["Start"]), from_api(item["End"])
    if all_day:
        # all-day events come back as UTC midnights of their floating dates
        start_text = item["Start"]["DateTime"][:10]
        end_text = item["End"]["DateTime"][:10]
    else:
        start_text, end_text = start.isoformat(), end.isoformat()
    attendees = item.get("Attendees") or []
    organizer = ((item.get("Organizer") or {}).get("EmailAddress") or {}).get("Address")
    return {
        "event_id": item["Id"],
        "ical_uid": item.get("iCalUId"),
        "calendar_id": calendar_id,
        "account": account["name"],
        "title": item.get("Subject") or "",
        "start": start_text,
        "end": end_text,
        "all_day": all_day,
        **({"end_is_exclusive": True} if all_day else {}),
        "location": ((item.get("Location") or {}).get("DisplayName")) or None,
        "response": RESPONSES.get((item.get("ResponseStatus") or {}).get("Response") or "None"),
        "attendees_listed": len(attendees),
        "organizer": organizer,
        "recurring": item.get("Type") in ("Occurrence", "Exception", "SeriesMaster"),
        "has_attendees": bool(attendees),
        "show_as": item.get("ShowAs"),
        "conference_url": item.get("OnlineMeetingUrl"),
    }


def calendar_events(account, window_start, window_end, calendar_id=""):
    """Every occurrence overlapping [window_start, window_end), recurring series expanded by the server."""
    calendars = [calendar_id] if calendar_id else [cal["calendar_id"] for cal in calendar_list_calendars(account)]
    events = []
    for cal_id in calendars:
        url = (
            f"{API_BASE}/calendars/{quote(cal_id, safe='')}/calendarview"
            f"?startDateTime={utc_iso(window_start)}Z&endDateTime={utc_iso(window_end)}Z"
            f"&$select={EVENT_FIELDS}&$top={PAGE_SIZE}&$orderby=Start/DateTime"
        )
        for item in get_all(account, url, headers=UTC_HEADERS):
            if not item.get("IsCancelled"):
                events.append(serialize_event(account, cal_id, item))
    events.sort(key=lambda event: (event["start"], event["title"]))
    return events


def calendar_get_event(account, event_id):
    item = request(account, "GET", f"{API_BASE}/events/{quote(event_id, safe='')}", headers=UTC_HEADERS)
    event = serialize_event(account, "", item)
    event["attendees"] = [
        {
            "address": (attendee.get("EmailAddress") or {}).get("Address"),
            "name": (attendee.get("EmailAddress") or {}).get("Name"),
            "type": attendee.get("Type"),
            "response": RESPONSES.get((attendee.get("Status") or {}).get("Response") or "None"),
        }
        for attendee in item.get("Attendees") or []
    ]
    event["description"] = (item.get("Body") or {}).get("Content")
    return event


def _time_body(start, end):
    if len(start) == 10 and len(end) == 10:
        return {
            "IsAllDay": True,
            "Start": {"DateTime": f"{start}T00:00:00", "TimeZone": "UTC"},
            "End": {"DateTime": f"{end}T00:00:00", "TimeZone": "UTC"},
        }
    return {
        "IsAllDay": False,
        "Start": {"DateTime": utc_iso(parse_moment(start)), "TimeZone": "UTC"},
        "End": {"DateTime": utc_iso(parse_moment(end)), "TimeZone": "UTC"},
    }


def calendar_create_event(account, calendar_id, summary, start, end, location="", description=""):
    """One event of your own, busy, with no attendees and no reminder, so nothing is sent to anyone."""
    body = {
        "Subject": summary,
        **_time_body(start, end),
        "ShowAs": "Busy",
        "IsReminderOn": False,
        "Body": {"ContentType": "Text", "Content": description},
    }
    if location:
        body["Location"] = {"DisplayName": location}
    item = request(
        account, "POST", f"{API_BASE}/calendars/{quote(calendar_id, safe='')}/events", body=body, headers=UTC_HEADERS
    )
    return serialize_event(account, calendar_id, item)


def _own_single_event(account, event_id):
    item = request(account, "GET", f"{API_BASE}/events/{quote(event_id, safe='')}?$select={EVENT_FIELDS}")
    if item.get("Attendees"):
        raise ValueError("refused: the event has attendees - change meetings in Outlook itself")
    if item.get("Type") != "SingleInstance":
        raise ValueError("refused: the event is part of a recurring series - change it in Outlook itself")
    return item


def calendar_update_event(account, event_id, summary="", start="", end="", location="", description=""):
    _own_single_event(account, event_id)
    body: dict = {}
    if summary:
        body["Subject"] = summary
    if start and end:
        body.update(_time_body(start, end))
    elif start or end:
        raise ValueError("pass start and end together")
    if location:
        body["Location"] = {"DisplayName": location}
    if description:
        body["Body"] = {"ContentType": "Text", "Content": description}
    if not body:
        raise ValueError("nothing to change")
    item = request(account, "PATCH", f"{API_BASE}/events/{quote(event_id, safe='')}", body=body, headers=UTC_HEADERS)
    return serialize_event(account, "", item)


def calendar_delete_event(account, event_id):
    _own_single_event(account, event_id)
    request(account, "DELETE", f"{API_BASE}/events/{quote(event_id, safe='')}")
    return {"deleted": event_id}


# %%
# Mail #


def mail_list_mailboxes(account):
    folders = get_all(
        account, f"{API_BASE}/MailFolders?$select=Id,DisplayName,TotalItemCount,UnreadItemCount&$top={PAGE_SIZE}"
    )
    return [
        {
            "mailbox": folder["DisplayName"],
            "folder_id": folder["Id"],
            "account": account["name"],
            "total": folder.get("TotalItemCount"),
            "unread": folder.get("UnreadItemCount"),
        }
        for folder in folders
    ]


def _address(recipient):
    email = (recipient or {}).get("EmailAddress") or {}
    name, address = email.get("Name") or "", email.get("Address") or ""
    return f"{name} <{address}>" if name and name != address else address


def _summary(account, item):
    return {
        "message_id": item["Id"],
        "message_id_header": item.get("InternetMessageId") or "",
        "account": account["name"],
        "date": from_api(item["ReceivedDateTime"]).isoformat(),
        "from": _address(item.get("From")),
        "to": [_address(recipient) for recipient in item.get("ToRecipients") or []],
        "subject": item.get("Subject") or "",
        "snippet": (item.get("BodyPreview") or "")[:300],
        "read": bool(item.get("IsRead")),
        "flagged": ((item.get("Flag") or {}).get("FlagStatus")) == "Flagged",
        # opens the message in Outlook on the web; a message:// link only reaches mail Mail.app holds
        "web_link": item.get("WebLink") or "",
    }


def _kql(text):
    return '"' + text.replace('"', "") + '"'


def mail_search(
    account,
    query_text="",
    sender="",
    recipient="",
    subject="",
    mailbox="",
    since="",
    until="",
    unread_only=False,
    max_results=25,
):
    """
    Newest first. Text, sender, recipient and subject go to the server's own
    search (whole bodies included); a plain listing filters by date instead.
    """
    root = f"{API_BASE}/messages"
    if mailbox:
        matches = [box for box in mail_list_mailboxes(account) if box["mailbox"].lower() == mailbox.lower()]
        if len(matches) != 1:
            raise ValueError(f"no single mailbox '{mailbox}' - mail_list_mailboxes lists them")
        root = f"{API_BASE}/MailFolders/{quote(matches[0]['folder_id'], safe='')}/messages"
    terms = []
    if query_text:
        terms.append(query_text.replace('"', ""))
    if sender:
        terms.append(f"from:{sender}")
    if recipient:
        terms.append(f"to:{recipient}")
    if subject:
        terms.append(f"subject:{subject}")
    if terms:
        if since:
            terms.append(f"received>={since[:10]}")
        if until:
            terms.append(f"received<={until[:10]}")
        if unread_only:
            terms.append("isread:false")
        search = quote(_kql(" ".join(terms)))
        url = f"{root}?$search={search}&$select={MESSAGE_FIELDS}&$top={min(max_results, PAGE_SIZE)}"
    else:
        filters = []
        if since:
            filters.append(f"ReceivedDateTime ge {since[:10]}T00:00:00Z")
        if until:
            filters.append(f"ReceivedDateTime le {until[:10]}T23:59:59Z")
        if unread_only:
            filters.append("IsRead eq false")
        url = f"{root}?$select={MESSAGE_FIELDS}&$top={min(max_results, PAGE_SIZE)}&$orderby=ReceivedDateTime desc"
        if filters:
            url += "&$filter=" + quote(" and ".join(filters))
    items = get_all(account, url, limit=max_results)
    results = [_summary(account, item) for item in items]
    results.sort(key=lambda message: message["date"], reverse=True)
    return results


def mail_get_message(account, message_id, body_limit=20000):
    """One message with its plain-text body and attachment names."""
    base = f"{API_BASE}/messages/{quote(message_id, safe='')}"
    item = request(
        account,
        "GET",
        f"{base}?$select={MESSAGE_FIELDS},CcRecipients,Body,HasAttachments",
        headers={"Prefer": 'outlook.body-content-type="text"'},
    )
    body = (item.get("Body") or {}).get("Content") or ""
    result = _summary(account, item)
    result.update(
        cc=[_address(recipient) for recipient in item.get("CcRecipients") or []],
        body=body[:body_limit],
        body_truncated=len(body) > body_limit,
        attachments=[],
    )
    if item.get("HasAttachments"):
        attachments = get_all(account, f"{base}/attachments?$select=Name,Size,ContentType")
        result["attachments"] = [
            {
                "filename": attachment.get("Name"),
                "size": attachment.get("Size"),
                "mime_type": attachment.get("ContentType"),
            }
            for attachment in attachments
        ]
    return result


def mail_download_attachment(account, message_id, filename, local_path):
    """Write one attachment of a message, by its name, byte for byte to local_path."""
    base = f"{API_BASE}/messages/{quote(message_id, safe='')}"
    matches = [item for item in get_all(account, f"{base}/attachments") if item.get("Name") == filename]
    if len(matches) != 1:
        raise ValueError(f"{len(matches)} attachments named '{filename}' on that message")
    if "ContentBytes" not in matches[0]:
        raise ValueError(f"'{filename}' is not a file attachment")
    data = base64.b64decode(matches[0]["ContentBytes"])
    os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
    with open(local_path, "wb") as file_handle:
        file_handle.write(data)
    return {"local_path": local_path, "size": len(data)}


# %%
