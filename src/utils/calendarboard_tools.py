# %%
# Imports #

import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

import requests
import yaml
from utils.inventory_tools import credentials_context, find_credentials_dirs
from utils.statusboard_tools import resolve_secret

# %%
# Variables #

SOURCE_TYPES = ("google_calendar", "outlook_calendar")
DEFAULT_INTERVAL = 300
DEFAULT_HTTP_TIMEOUT = 30

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_API = "https://www.googleapis.com/calendar/v3"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"

GRAPH_API = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "offline_access https://graph.microsoft.com/Calendars.Read"

# Normalized attendance states, in "how much this needs your eyes" order.
RESPONSE_STATES = ("organizer", "accepted", "tentative", "needs_action", "declined")

GOOGLE_RESPONSE_MAP = {
    "accepted": "accepted",
    "tentative": "tentative",
    "needsAction": "needs_action",
    "declined": "declined",
}

GRAPH_RESPONSE_MAP = {
    "organizer": "organizer",
    "accepted": "accepted",
    "tentativelyAccepted": "tentative",
    "notResponded": "needs_action",
    "declined": "declined",
    # "none" = an event nobody invited you to (your own, or a shared calendar's)
    "none": "accepted",
}


# %%
# Results #


class SourceResult:
    """
    Outcome of one calendar-source fetch: ok + a flat list of normalized event
    dicts (see normalize_* for the shape) covering the requested window, or
    ok=False with the error text in ``error``.
    """

    def __init__(self, ok, events, summary="", error=""):
        self.ok = ok
        self.events = events
        self.summary = summary
        self.error = error
        self.fetched_at = time.time()

    @classmethod
    def failure(cls, message):
        return cls(False, [], "error", str(message))


# %%
# Config discovery #


def discover_calendarboard_configs(credentials_root, repo_root=None):
    """
    Locate every calendarboard config to load: an optional ``calendarboard.yaml``
    in the dotfiles repo root (tracked, so secrets-free sources only) plus, for
    each sibling ``*_credentials`` repo, an optional ``<context>_calendarboard.yaml``
    - the same overlay pattern the status board uses. Returns a list of
    (config_path, base_dir) pairs, overlays sorted for determinism.
    """
    configs = []
    if repo_root:
        main_config = os.path.join(repo_root, "calendarboard.yaml")
        if os.path.exists(main_config):
            configs.append((main_config, repo_root))
    for credentials_dir in find_credentials_dirs(credentials_root):
        overlay = os.path.join(credentials_dir, f"{credentials_context(credentials_dir)}_calendarboard.yaml")
        if os.path.exists(overlay):
            configs.append((overlay, credentials_dir))
    return configs


def load_sources(credentials_root, repo_root=None, config_path=None):
    """
    Load every discovered calendarboard config, returning (sources, config_paths).
    Each source is stamped with ``_base_dir`` (its config's repo root, which
    env_file paths resolve against) and ``_config`` (for error messages).
    Source names must be unique across ALL loaded configs.

    Passing config_path (the --config test escape hatch) loads only that file,
    base_dir its containing directory, skipping discovery.
    """
    if config_path:
        located = [(config_path, os.path.dirname(os.path.abspath(config_path)))]
    else:
        located = discover_calendarboard_configs(credentials_root, repo_root)
    sources = []
    seen: dict = {}
    for path, base_dir in located:
        for source in _parse_config_file(path):
            if source["name"] in seen:
                raise ValueError(
                    f"Duplicate calendarboard source name '{source['name']}' in {path} "
                    f"(already defined in {seen[source['name']]})"
                )
            seen[source["name"]] = path
            source["_base_dir"] = base_dir
            source["_config"] = path
            sources.append(source)
    return sources, [path for path, _ in located]


def _parse_config_file(config_path):
    """Parse one calendarboard config and validate the source schema, returning a list of source dicts."""
    with open(config_path, "r", encoding="utf-8") as file_handle:
        sources = yaml.safe_load(file_handle) or []
    if not isinstance(sources, list):
        raise ValueError(f"Calendarboard config {config_path} must be a YAML list of sources")
    for source in sources:
        _validate_source(source, config_path)
        source.setdefault("interval", DEFAULT_INTERVAL)
    return sources


def _validate_source(source, config_path):
    if not isinstance(source, dict) or "name" not in source or "type" not in source:
        raise ValueError(
            f"Calendarboard source must be a mapping with 'name' and 'type' keys ({config_path}): {source}"
        )
    if source["type"] not in SOURCE_TYPES:
        raise ValueError(
            f"Calendarboard source '{source['name']}' in {config_path} has unknown type '{source['type']}' "
            f"(expected one of {', '.join(SOURCE_TYPES)})"
        )
    required = {
        # Google's token refresh always needs the client secret (installed-app
        # clients get one); Microsoft public clients deliberately have none.
        "google_calendar": ("client_id_env", "client_secret_env", "refresh_token_env"),
        "outlook_calendar": ("client_id_env", "refresh_token_env"),
    }[source["type"]]
    missing = [key for key in required if not source.get(key)]
    if missing:
        raise ValueError(
            f"Calendarboard source '{source['name']}' in {config_path} "
            f"(type {source['type']}) is missing required keys: {', '.join(missing)}"
        )
    if source.get("calendars") is not None and not isinstance(source["calendars"], list):
        raise ValueError(
            f"Calendarboard source '{source['name']}' in {config_path}: 'calendars' must be a list "
            f"of calendar names/ids (omit the key entirely to show every calendar)"
        )


def calendar_selected(source, name, primary=False, calendar_id=None):
    """
    Whether one of the account's calendars is wanted by this source. No
    ``calendars:`` key = every calendar the account can see (the point of the
    board is to catch meetings on secondary calendars too). Otherwise entries
    match the calendar's display name or id case-insensitively, and the
    special token ``primary`` matches the account's default calendar.
    """
    wanted = source.get("calendars")
    if not wanted:
        return True
    for token in wanted:
        token = str(token).strip().lower()
        if token == "primary" and primary:
            return True
        if name and token == name.lower():
            return True
        if calendar_id and token == str(calendar_id).lower():
            return True
    return False


# %%
# Time handling #


def parse_iso_datetime(value, assume_utc=False):
    """
    ISO timestamp string -> aware UTC datetime. Handles the quirks of both
    APIs on Python 3.10: trailing ``Z`` (Google) and 7-digit fractional
    seconds (Graph), neither of which 3.10's fromisoformat accepts. A naive
    result is stamped UTC when assume_utc (Graph values fetched with
    ``Prefer: outlook.timezone="UTC"``), else treated as local time.
    """
    clean = re.sub(r"\.\d+", "", value.replace("Z", "+00:00"))
    parsed = datetime.fromisoformat(clean)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc) if assume_utc else parsed.astimezone()
    return parsed.astimezone(timezone.utc)


def _iso_utc(moment):
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# %%
# Event normalization #
#
# Every fetcher reduces its API's payload to the same flat dict:
#   title, calendar (display name), start/end (aware UTC datetimes; for
#   all-day events these are calendar-date midnights with an EXCLUSIVE end,
#   both APIs' native convention), all_day, response (one of
#   RESPONSE_STATES), conflict (False here; mark_conflicts sets it).


def normalize_google_event(event, calendar_name):
    """Google Calendar API event -> normalized dict, or None for cancelled events."""
    if event.get("status") == "cancelled":
        return None
    start_info = event.get("start") or {}
    end_info = event.get("end") or {}
    all_day = "date" in start_info
    if all_day:
        start = datetime.fromisoformat(start_info["date"]).replace(tzinfo=timezone.utc)
        end_date = end_info.get("date") or start_info["date"]
        end = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
    else:
        start = parse_iso_datetime(start_info["dateTime"])
        end = parse_iso_datetime(end_info.get("dateTime") or start_info["dateTime"])
    return {
        "title": event.get("summary") or "(no title)",
        "calendar": calendar_name,
        "start": start,
        "end": end,
        "all_day": all_day,
        "response": _google_response(event),
        "conflict": False,
    }


def _google_response(event):
    """
    My attendance on a Google event. Google marks the calendar owner's entries
    with ``self: true`` (on the organizer record and/or my attendee record);
    an event with no attendee list at all is my own solo entry - accepted.
    """
    if (event.get("organizer") or {}).get("self"):
        return "organizer"
    for attendee in event.get("attendees") or []:
        if attendee.get("self"):
            return GOOGLE_RESPONSE_MAP.get(attendee.get("responseStatus"), "needs_action")
    return "accepted"


def normalize_graph_event(event, calendar_name):
    """Microsoft Graph event -> normalized dict, or None for cancelled events."""
    if event.get("isCancelled"):
        return None
    all_day = bool(event.get("isAllDay"))
    start = _graph_datetime(event.get("start") or {})
    end = _graph_datetime(event.get("end") or {})
    if event.get("isOrganizer"):
        response = "organizer"
    else:
        raw = (event.get("responseStatus") or {}).get("response")
        response = GRAPH_RESPONSE_MAP.get(raw, "accepted")
    return {
        "title": event.get("subject") or "(no title)",
        "calendar": calendar_name,
        "start": start,
        "end": end,
        "all_day": all_day,
        "response": response,
        "conflict": False,
    }


def _graph_datetime(node):
    """
    Graph's {dateTime, timeZone} pair -> aware UTC datetime. Every fetch sends
    ``Prefer: outlook.timezone="UTC"`` so timeZone is always UTC; treat it as
    such even if the header were ignored (better a shifted time than a crash
    on a Windows-style zone name Python can't parse).
    """
    return parse_iso_datetime(node.get("dateTime", "1970-01-01T00:00:00"), assume_utc=True)


# %%
# Day slicing / conflicts #


def events_for_day(events, day, tz=None):
    """
    The events touching one calendar day, all-day entries first then by start
    time. Timed events are compared against the day's local midnights (tz
    defaults to the machine's zone; tests pass an explicit one) so an event
    crossing midnight shows on both days. All-day events carry calendar
    dates with an exclusive end, timezone-irrelevant by definition.
    """
    day_start = datetime(day.year, day.month, day.day)
    day_start = day_start.replace(tzinfo=tz) if tz else day_start.astimezone()
    day_end = day_start + timedelta(days=1)
    selected = []
    for event in events:
        if event["all_day"]:
            last_day = max(event["end"].date() - timedelta(days=1), event["start"].date())
            if event["start"].date() <= day <= last_day:
                selected.append(event)
        elif event["start"] < day_end and (event["end"] > day_start or event["start"] >= day_start):
            selected.append(event)
    return sorted(selected, key=lambda event: (not event["all_day"], event["start"]))


def assign_lanes(events):
    """
    Google-Calendar-style lane packing for ONE source's timed day events:
    overlapping events split into side-by-side sub-columns ("lanes") so both
    blocks stay visible on the grid. Greedy first-free-lane assignment over
    the events sorted by start. Returns (placed, lane_count) where placed is
    a list of (event, lane_index); all-day events are the banner row's
    problem and are skipped here.
    """
    timed = sorted(
        (event for event in events if not event["all_day"]),
        key=lambda event: (event["start"], event["end"]),
    )
    lane_ends: list = []
    placed = []
    for event in timed:
        for lane, busy_until in enumerate(lane_ends):
            if event["start"] >= busy_until:
                lane_ends[lane] = event["end"]
                placed.append((event, lane))
                break
        else:
            lane_ends.append(event["end"])
            placed.append((event, len(lane_ends) - 1))
    return placed, max(1, len(lane_ends))


def grid_hour_range(events, day, tz=None, day_start=7, day_end=19):
    """
    The [start_hour, end_hour) span the day grid must cover: the working-day
    default, widened (never narrowed) so no timed event falls off the top or
    bottom. Events spilling in from an adjacent day (overnight meetings)
    clamp to this day's midnights.
    """
    start_hour, end_hour = day_start, day_end
    for event in events:
        if event["all_day"]:
            continue
        start_local = event["start"].astimezone(tz)
        end_local = event["end"].astimezone(tz)
        if start_local.date() < day:
            start_hour = 0
        elif start_local.date() == day:
            start_hour = min(start_hour, start_local.hour)
        if end_local.date() > day or (end_local.date() == day and end_local.hour >= day_end):
            boundary = end_local.hour + (1 if (end_local.minute or end_local.second) else 0)
            end_hour = 24 if end_local.date() > day else max(end_hour, min(boundary, 24))
    return start_hour, max(end_hour, start_hour + 1)


def mark_conflicts(events):
    """
    Flag every pair of overlapping timed events across the whole list - the
    caller passes the COMBINED day view of all sources, so a client A meeting
    colliding with a client B meeting lights up on both columns. Declined and
    all-day events never count (a declined meeting is a resolved conflict,
    and an all-day marker overlaps everything by definition). Resets stale
    flags first, so re-marking after a refresh is safe.
    """
    for event in events:
        event["conflict"] = False
    timed = [event for event in events if not event["all_day"] and event["response"] != "declined"]
    for index, first in enumerate(timed):
        for second in timed[index + 1:]:
            if first["start"] < second["end"] and second["start"] < first["end"]:
                first["conflict"] = second["conflict"] = True
    return events


# %%
# Google Calendar fetcher #


def _google_access_token(source):
    data = {
        "client_id": resolve_secret(source, "client_id_env"),
        "client_secret": resolve_secret(source, "client_secret_env"),
        "refresh_token": resolve_secret(source, "refresh_token_env"),
        "grant_type": "refresh_token",
    }
    response = requests.post(GOOGLE_TOKEN_URL, data=data, timeout=DEFAULT_HTTP_TIMEOUT)
    if response.status_code != 200:
        raise ValueError(
            f"Google token refresh returned {response.status_code}: {response.text[:200]} "
            f"(revoked consent? re-run with --auth {source['name']})"
        )
    return response.json()["access_token"]


def _google_paged(url, headers, params, key="items"):
    items = []
    while True:
        response = requests.get(url, headers=headers, params=params, timeout=DEFAULT_HTTP_TIMEOUT)
        if response.status_code != 200:
            raise ValueError(f"Google API returned {response.status_code} for {url}: {response.text[:200]}")
        payload = response.json()
        items += payload.get(key, [])
        page_token = payload.get("nextPageToken")
        if not page_token:
            return items
        params = dict(params, pageToken=page_token)


def fetch_google_events(source, window_start, window_end):
    """
    Every event on the account's selected calendars between window_start and
    window_end (aware datetimes). Calendars come from calendarList - the same
    set the web UI's sidebar shows, so secondary and subscribed calendars are
    covered - filtered by the source's optional ``calendars:`` list.
    Recurring events arrive pre-expanded (singleEvents).
    """
    headers = {"Authorization": f"Bearer {_google_access_token(source)}"}
    calendars = _google_paged(f"{GOOGLE_API}/users/me/calendarList", headers, {"minAccessRole": "reader"})
    selected = [
        calendar for calendar in calendars
        if calendar_selected(
            source,
            calendar.get("summaryOverride") or calendar.get("summary") or "",
            primary=bool(calendar.get("primary")),
            calendar_id=calendar.get("id"),
        )
    ]
    events = []
    for calendar in selected:
        name = calendar.get("summaryOverride") or calendar.get("summary") or calendar.get("id", "")
        params = {
            "timeMin": _iso_utc(window_start),
            "timeMax": _iso_utc(window_end),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 250,
        }
        for raw in _google_paged(f"{GOOGLE_API}/calendars/{quote(calendar['id'])}/events", headers, params):
            event = normalize_google_event(raw, name)
            if event:
                event["source"] = source["name"]
                events.append(event)
    return SourceResult(True, events, f"{len(selected)} cal · {len(events)} events")


# %%
# Outlook (Microsoft Graph) fetcher #


def _graph_access_token(source):
    tenant = source.get("tenant", "common")
    data = {
        "client_id": resolve_secret(source, "client_id_env"),
        "refresh_token": resolve_secret(source, "refresh_token_env"),
        "grant_type": "refresh_token",
        "scope": GRAPH_SCOPE,
    }
    if source.get("client_secret_env"):
        data["client_secret"] = resolve_secret(source, "client_secret_env")
    response = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token", data=data, timeout=DEFAULT_HTTP_TIMEOUT
    )
    if response.status_code != 200:
        raise ValueError(
            f"Microsoft token refresh returned {response.status_code}: {response.text[:200]} "
            f"(refresh tokens expire when unused ~90 days - re-run with --auth {source['name']})"
        )
    return response.json()["access_token"]


def _graph_paged(url, headers, params=None):
    items = []
    while url:
        response = requests.get(url, headers=headers, params=params, timeout=DEFAULT_HTTP_TIMEOUT)
        if response.status_code != 200:
            raise ValueError(f"Graph API returned {response.status_code} for {url}: {response.text[:200]}")
        payload = response.json()
        items += payload.get("value", [])
        url = payload.get("@odata.nextLink")  # nextLink already carries the query string
        params = None
    return items


def fetch_outlook_events(source, window_start, window_end):
    """
    Every event on the account's selected Outlook calendars between
    window_start and window_end (aware datetimes), via Microsoft Graph -
    which is the API behind Outlook on the web, so this covers exactly what
    outlook.office.com shows. calendarView expands recurrences; the Prefer
    header pins returned times to UTC so normalization never has to parse
    Windows time-zone names.
    """
    headers = {
        "Authorization": f"Bearer {_graph_access_token(source)}",
        "Prefer": 'outlook.timezone="UTC"',
    }
    calendars = _graph_paged(f"{GRAPH_API}/me/calendars", headers, {"$top": 50})
    selected = [
        calendar for calendar in calendars
        if calendar_selected(
            source,
            calendar.get("name") or "",
            primary=bool(calendar.get("isDefaultCalendar")),
            calendar_id=calendar.get("id"),
        )
    ]
    events = []
    for calendar in selected:
        params = {
            "startDateTime": _iso_utc(window_start),
            "endDateTime": _iso_utc(window_end),
            "$top": 100,
            "$select": "subject,start,end,isAllDay,isCancelled,isOrganizer,responseStatus",
            "$orderby": "start/dateTime",
        }
        for raw in _graph_paged(f"{GRAPH_API}/me/calendars/{calendar['id']}/calendarView", headers, params):
            event = normalize_graph_event(raw, calendar.get("name", ""))
            if event:
                event["source"] = source["name"]
                events.append(event)
    return SourceResult(True, events, f"{len(selected)} cal · {len(events)} events")


# %%
# Dispatch #


def fetch_source(source, window_start, window_end):
    """Dispatch one source fetch; never raises - errors come back as SourceResult.failure."""
    try:
        if source["type"] == "google_calendar":
            return fetch_google_events(source, window_start, window_end)
        return fetch_outlook_events(source, window_start, window_end)
    except Exception as error:  # noqa: BLE001 - a source must never take the board down
        return SourceResult.failure(f"{type(error).__name__}: {error}")


# %%
# Interactive auth (one-time refresh-token minting) #


def _print_refresh_token(source, refresh_token):
    var_name = source["refresh_token_env"]
    env_file = source.get("env_file", "your env file")
    print("\nAuthorization complete. Add this line to " f"{env_file} in {source.get('_base_dir', '')}:\n")
    print(f"  {var_name}={refresh_token}\n")


def run_google_auth(source):
    """
    One-time interactive OAuth for a google_calendar source: opens the consent
    URL, catches the redirect on a localhost loopback server, exchanges the
    code, and prints the refresh token to store in the source's env file.
    Google's device flow does not allow the Calendar scope, so the browser
    must run on THIS machine (or with the shown port forwarded to it).
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import parse_qs, urlparse

    client_id = resolve_secret(source, "client_id_env")
    client_secret = resolve_secret(source, "client_secret_env")
    captured: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            if "code" in query or "error" in query:
                captured.update({key: value[0] for key, value in query.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"calendar board: authorization received - return to the terminal")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    redirect_uri = f"http://localhost:{server.server_port}"
    url = GOOGLE_AUTH_URL + "?" + urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_SCOPE,
        "access_type": "offline",  # offline + consent force a refresh token every time
        "prompt": "consent",
    })
    print(f"Open this URL in a browser on THIS machine (redirect lands on {redirect_uri}):\n\n  {url}\n")
    while "code" not in captured and "error" not in captured:
        server.handle_request()
    server.server_close()
    if "error" in captured:
        print(f"authorization failed: {captured['error']}")
        return 1
    response = requests.post(GOOGLE_TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": captured["code"],
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=DEFAULT_HTTP_TIMEOUT)
    payload = response.json()
    if "refresh_token" not in payload:
        print(f"token exchange failed ({response.status_code}): {response.text[:300]}")
        return 1
    _print_refresh_token(source, payload["refresh_token"])
    return 0


def run_outlook_auth(source):
    """
    One-time interactive OAuth for an outlook_calendar source via the device
    code flow - works over SSH since the browser can be anywhere. Prints the
    refresh token to store in the source's env file. The app registration
    must have "Allow public client flows" enabled.
    """
    client_id = resolve_secret(source, "client_id_env")
    tenant = source.get("tenant", "common")
    base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
    response = requests.post(
        f"{base}/devicecode", data={"client_id": client_id, "scope": GRAPH_SCOPE}, timeout=DEFAULT_HTTP_TIMEOUT
    )
    if response.status_code != 200:
        print(f"device code request failed ({response.status_code}): {response.text[:300]}")
        return 1
    device = response.json()
    print(f"\n{device['message']}\n")
    while True:
        time.sleep(device.get("interval", 5))
        token_response = requests.post(f"{base}/token", data={
            "client_id": client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device["device_code"],
        }, timeout=DEFAULT_HTTP_TIMEOUT)
        payload = token_response.json()
        if "refresh_token" in payload:
            _print_refresh_token(source, payload["refresh_token"])
            return 0
        if payload.get("error") not in ("authorization_pending", "slow_down"):
            print(f"authorization failed: {payload.get('error_description') or payload.get('error')}")
            return 1


# %%
