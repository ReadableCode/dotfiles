# %%
# Imports #

# An MCP stdio server speaks JSON-RPC on stdout, so anything else printed there
# corrupts the protocol - and importing config creates missing repo dirs with a
# print. Every import that could talk to stdout goes through this redirect.
import argparse
import contextlib
import os
import sys
from datetime import date, datetime, timedelta

with contextlib.redirect_stdout(sys.stderr):
    from mcp.server.mcpserver import MCPServer  # noqa: E402

    from config import grandparent_dir, parent_dir  # noqa: E402
    from utils import googlemcp_tools as gtools  # noqa: E402
    from utils.calendarboard_tools import (  # noqa: E402
        fetch_google_events,
        load_sources,
    )
    from utils.inventory_tools import (  # noqa: E402
        credentials_context,
        find_credentials_dirs,
    )

# %%
# Variables #

REPO_ROOT = parent_dir
CREDENTIALS_ROOT = grandparent_dir

# Set by --context: pins account discovery to ONE context's configs, so a
# declaration like `acme_google --context acme` reaches exactly that
# context's accounts and a multi-context machine registers one clearly
# labeled server per context instead of an unlabeled union. Empty = discover
# every cloned credentials repo (the calendar board's behaviour).
_context = ""

SERVER_INSTRUCTIONS = """
Jason's own Google Calendar, Gmail and Drive, over his own Google Cloud OAuth
client - independent of the model provider, so it behaves identically on AWS
Bedrock and on Claude Enterprise.

Calendar sources come from <context>_calendarboard.yaml, mailboxes from
<context>_googlemail.yaml and Drive accounts from <context>_googledrive.yaml in
the sibling *_credentials repos. Each defaults to the only configured account
when there is exactly one, so `source`/`mailbox`/`drive` can usually be left
out. Call list_accounts to see what is configured.

Writes are enabled: calendar create/update/delete, Gmail label/trash/send and
Drive upload/update/create-folder/trash. Calendar writes default to
sendUpdates="none" (no invite mail to attendees) - pass send_updates="all"
deliberately when guests should be notified. Gmail and Drive trash are
recoverable and nothing here deletes a message or file permanently; calendar
delete is not recoverable.
""".strip()

server = MCPServer(name="google", instructions=SERVER_INSTRUCTIONS, version="0.1.0")


# %%
# Account resolution #


def _pinned_config(kind):
    """
    The pinned context's ``<context>_<kind>.yaml`` path, or None when that
    repo is not cloned or has no such config (a pinned server with nothing
    configured reports no accounts rather than leaking another context's).
    """
    for credentials_dir in find_credentials_dirs(CREDENTIALS_ROOT):
        if credentials_context(credentials_dir) == _context:
            path = os.path.join(credentials_dir, f"{_context}_{kind}.yaml")
            return path if os.path.exists(path) else None
    return None


def _calendar_sources():
    """
    Every configured google_calendar source. Outlook sources live in the same
    calendarboard configs but are the board's business, not this server's.
    """
    if _context:
        path = _pinned_config("calendarboard")
        if not path:
            return []
        sources, _ = load_sources(CREDENTIALS_ROOT, REPO_ROOT, config_path=path)
    else:
        sources, _ = load_sources(CREDENTIALS_ROOT, REPO_ROOT)
    return [source for source in sources if source["type"] == "google_calendar"]


def _accounts(kind):
    """Every entry in the ``<context>_<kind>.yaml`` configs (``googlemail`` or ``googledrive``)."""
    if _context:
        path = _pinned_config(kind)
        if not path:
            return []
        accounts, _ = gtools.load_accounts(kind, CREDENTIALS_ROOT, REPO_ROOT, config_path=path)
    else:
        accounts, _ = gtools.load_accounts(kind, CREDENTIALS_ROOT, REPO_ROOT)
    return accounts


def _mailboxes():
    return _accounts("googlemail")


def _drives():
    return _accounts("googledrive")


def _resolve(entries, name, label):
    """
    Pick the named entry, or the only one when the name is omitted - a
    single-account machine should never have to name it.
    """
    if name:
        return gtools.find_by_name(entries, name, label)
    if len(entries) == 1:
        return entries[0]
    if not entries:
        raise ValueError(f"no {gtools.plural(label)} configured - see docs/setup_google_mcp.md")
    available = ", ".join(entry["name"] for entry in entries)
    raise ValueError(f"several {gtools.plural(label)} configured ({available}) - pass {label}= to pick one")


def _source(name=""):
    return _resolve(_calendar_sources(), name, "source")


def _mailbox(name=""):
    return _resolve(_mailboxes(), name, "mailbox")


def _drive(name=""):
    return _resolve(_drives(), name, "drive")


def _jsonable(value):
    """datetimes -> ISO strings, recursively, so a tool result serializes."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _serialize_event(event):
    """
    Board events carry aware UTC datetimes and the TUI converts them for
    display. Emit timed ones in LOCAL time with their offset instead: a bare
    UTC "15:00" for a 10:00 local meeting is exactly the sort of thing that
    gets repeated back to the user as the wrong meeting time.

    All-day events are calendar-date midnights with an exclusive end (both
    APIs' convention), so shifting them into a local offset would move them a
    day - they go out as plain dates.
    """
    serialized = dict(event)
    if event["all_day"]:
        serialized["start"] = event["start"].date().isoformat()
        serialized["end"] = event["end"].date().isoformat()
        serialized["end_is_exclusive"] = True
    else:
        serialized["start"] = event["start"].astimezone().isoformat()
        serialized["end"] = event["end"].astimezone().isoformat()
    return _jsonable(serialized)


# %%
# Discovery #


@server.tool(
    description="List the configured Google Calendar sources, Gmail mailboxes and Drive accounts this server can reach."
)
def list_accounts() -> dict:
    return {
        "calendar_sources": [{"name": source["name"], "config": source["_config"]} for source in _calendar_sources()],
        "mailboxes": [{"name": mailbox["name"], "config": mailbox["_config"]} for mailbox in _mailboxes()],
        "drives": [{"name": drive["name"], "config": drive["_config"]} for drive in _drives()],
    }


# %%
# Calendar tools #


@server.tool(description="List every calendar on a Google account, with ids to pass to the other calendar tools.")
def calendar_list_calendars(source: str = "") -> list:
    return gtools.calendar_list_calendars(_source(source))


@server.tool(
    description=(
        "Agenda across ALL of the account's calendars for a date range - the same view as the calendar board TUI. "
        "start_date is YYYY-MM-DD (default today); days counts forward from it. Returns events sorted by start, "
        "each with title, calendar, start/end, all_day, your attendance response, organizer and attendee list. "
        "Timed events are in LOCAL time with their UTC offset; all-day ones are plain dates with an exclusive end."
    )
)
def calendar_agenda(start_date: str = "", days: int = 1, source: str = "") -> list:
    first = date.fromisoformat(start_date) if start_date else date.today()
    window_start = datetime.combine(first, datetime.min.time()).astimezone()
    window_end = window_start + timedelta(days=max(1, days))
    result = fetch_google_events(_source(source), window_start, window_end)
    if not result.ok:
        raise ValueError(result.error)
    events = [event for event in result.events if event["start"] < window_end and event["end"] > window_start]
    events.sort(key=lambda event: (event["start"], event["title"]))
    return [_serialize_event(event) for event in events]


@server.tool(
    description=(
        "Full detail for one event, including creator (who made it) and organizer (whose calendar owns it) plus "
        "every attendee's response. Note: Google records no per-attendee provenance, so who added an individual "
        "guest after the invite went out is NOT available - creator/organizer is as close as the API gets."
    )
)
def calendar_get_event(event_id: str, calendar_id: str = "primary", source: str = "") -> dict:
    return gtools.calendar_get_event(_source(source), event_id, calendar_id=calendar_id)


@server.tool(
    description=(
        "Search one calendar's events by free text and/or an RFC3339 time window "
        "(time_min/time_max, e.g. 2026-08-27T00:00:00-05:00). Recurring events come pre-expanded."
    )
)
def calendar_search_events(
    query: str = "",
    calendar_id: str = "primary",
    time_min: str = "",
    time_max: str = "",
    max_results: int = 25,
    source: str = "",
) -> list:
    return gtools.calendar_search_events(
        _source(source),
        query=query,
        calendar_id=calendar_id,
        time_min=time_min or None,
        time_max=time_max or None,
        max_results=max_results,
    )


@server.tool(
    description=(
        "Create a calendar event. start/end are RFC3339 timestamps for timed events "
        "(2026-08-27T10:00:00-05:00) or YYYY-MM-DD for all-day ones. attendees is a list of email addresses. "
        "send_updates: none (default, no invite mail), all, or externalOnly."
    )
)
def calendar_create_event(
    summary: str,
    start: str,
    end: str,
    description: str = "",
    location: str = "",
    attendees: list[str] = [],
    calendar_id: str = "primary",
    send_updates: str = "none",
    source: str = "",
) -> dict:
    fields: dict = {"send_updates": send_updates}
    if description:
        fields["description"] = description
    if location:
        fields["location"] = location
    if attendees:
        fields["attendees"] = [{"email": address} for address in attendees]
    return gtools.calendar_create_event(
        _source(source),
        summary,
        _time_field(start),
        _time_field(end),
        calendar_id=calendar_id,
        **fields,
    )


def _time_field(value):
    """YYYY-MM-DD -> an all-day {"date": ...}; anything longer -> a timed {"dateTime": ...}."""
    return {"date": value} if len(value) == 10 else {"dateTime": value}


@server.tool(
    description=(
        "Patch an existing event - only the arguments you pass change. Same formats as calendar_create_event. "
        "send_updates controls whether guests are emailed about the change."
    )
)
def calendar_update_event(
    event_id: str,
    summary: str = "",
    start: str = "",
    end: str = "",
    description: str = "",
    location: str = "",
    attendees: list[str] = [],
    calendar_id: str = "primary",
    send_updates: str = "none",
    source: str = "",
) -> dict:
    fields: dict = {}
    if summary:
        fields["summary"] = summary
    if start:
        fields["start"] = _time_field(start)
    if end:
        fields["end"] = _time_field(end)
    if description:
        fields["description"] = description
    if location:
        fields["location"] = location
    if attendees:
        fields["attendees"] = [{"email": address} for address in attendees]
    return gtools.calendar_update_event(
        _source(source), event_id, calendar_id=calendar_id, send_updates=send_updates, **fields
    )


@server.tool(description="Delete a calendar event. Not recoverable through the API - confirm with the user first.")
def calendar_delete_event(
    event_id: str, calendar_id: str = "primary", send_updates: str = "none", source: str = ""
) -> dict:
    return gtools.calendar_delete_event(_source(source), event_id, calendar_id=calendar_id, send_updates=send_updates)


# %%
# Gmail tools #


@server.tool(description="The mailbox's own address and message totals - the cheapest check that credentials work.")
def gmail_profile(mailbox: str = "") -> dict:
    return gtools.gmail_profile(_mailbox(mailbox))


@server.tool(
    description=(
        "Search the mailbox using Gmail's own query syntax (from:, to:, subject:, newer_than:7d, is:unread, "
        "has:attachment, ...). Returns summaries with ids, headers, snippet and labels - no bodies."
    )
)
def gmail_search(query: str = "", max_results: int = 25, include_spam_trash: bool = False, mailbox: str = "") -> list:
    return gtools.gmail_search(
        _mailbox(mailbox), query=query, max_results=max_results, include_spam_trash=include_spam_trash
    )


@server.tool(
    description=(
        "Every message id (with its thread id) matching a Gmail query, following every page itself - no bodies and "
        "no per-message fetch, so it scales to thousands. Use it to diff a mailbox against a record of what was "
        "already processed, then gmail_get_message only the new ones."
    )
)
def gmail_list_message_ids(query: str = "", include_spam_trash: bool = False, mailbox: str = "") -> list:
    return gtools.gmail_list_message_ids(_mailbox(mailbox), query=query, include_spam_trash=include_spam_trash)


@server.tool(description="One message in full: headers, decoded plain-text body, and attachment names/sizes.")
def gmail_get_message(message_id: str, body_limit: int = 20000, mailbox: str = "") -> dict:
    return gtools.gmail_get_message(_mailbox(mailbox), message_id, body_limit=body_limit)


@server.tool(description="Every label in the mailbox, with the ids gmail_modify_message needs.")
def gmail_list_labels(mailbox: str = "") -> list:
    return gtools.gmail_list_labels(_mailbox(mailbox))


@server.tool(
    description=(
        "Add or remove label ids on a message. UNREAD and STARRED are labels too, so this is also how you "
        "mark read/unread and star/unstar. Get ids from gmail_list_labels."
    )
)
def gmail_modify_message(
    message_id: str, add_labels: list[str] = [], remove_labels: list[str] = [], mailbox: str = ""
) -> dict:
    return gtools.gmail_modify_message(
        _mailbox(mailbox), message_id, add_labels=add_labels, remove_labels=remove_labels
    )


@server.tool(description="Move a message to Trash, or restore it with undo=true. Recoverable either way.")
def gmail_trash_message(message_id: str, undo: bool = False, mailbox: str = "") -> dict:
    return gtools.gmail_trash_message(_mailbox(mailbox), message_id, undo=undo)


@server.tool(
    description=(
        "Send a plain-text email as the mailbox's own address. Pass reply_to_message_id to thread it as a reply. "
        "This sends real mail to real people - confirm recipients and content with the user first."
    )
)
def gmail_send_message(
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] = [],
    bcc: list[str] = [],
    reply_to_message_id: str = "",
    mailbox: str = "",
) -> dict:
    return gtools.gmail_send_message(
        _mailbox(mailbox),
        to,
        subject,
        body,
        cc=cc or None,
        bcc=bcc or None,
        reply_to_message_id=reply_to_message_id or None,
    )


@server.tool(
    description=(
        "Save one Gmail attachment straight into a Drive folder, picked by its filename as gmail_get_message lists "
        "it. Stored as-is, never converted to a Google Doc or Sheet; name defaults to the attachment's filename. "
        "Nothing is written to local disk."
    )
)
def gmail_save_attachment_to_drive(
    message_id: str, filename: str, parent_id: str = "root", name: str = "", mailbox: str = "", drive: str = ""
) -> dict:
    return gtools.gmail_save_attachment_to_drive(
        _mailbox(mailbox), _drive(drive), message_id, filename, parent_id=parent_id, name=name
    )


# %%
# Drive tools #


@server.tool(
    description="The Drive account's own address and storage quota - the cheapest check that credentials work."
)
def drive_about(drive: str = "") -> dict:
    return gtools.drive_about(_drive(drive))


@server.tool(
    description=(
        "Search Drive with its own query syntax: name contains 'x', '<folder id>' in parents, "
        "mimeType = 'application/vnd.google-apps.folder', modifiedTime > '2026-09-01T00:00:00'. Covers My Drive and "
        "every shared drive. Trashed files are excluded unless the query mentions trashed itself."
    )
)
def drive_search(query: str = "", max_results: int = 50, order_by: str = "modifiedTime desc", drive: str = "") -> list:
    return gtools.drive_search(_drive(drive), query=query, max_results=max_results, order_by=order_by)


@server.tool(description="One Drive file's name, type, size, parent folders, created/modified times and web link.")
def drive_get_metadata(file_id: str, drive: str = "") -> dict:
    return gtools.drive_get_metadata(_drive(drive), file_id)


@server.tool(
    description=(
        "Read a Drive file as text: Google Docs and Slides export as plain text, Sheets as CSV of the first tab "
        "(sheets_get_values reaches any tab), stored files decode as UTF-8. Binary files are refused - use "
        "drive_download_file."
    )
)
def drive_read_file(file_id: str, max_chars: int = 100000, drive: str = "") -> dict:
    return gtools.drive_read_file(_drive(drive), file_id, max_chars=max_chars)


@server.tool(
    description=(
        "Download a Drive file to a local path that does not exist yet (Google-native files exported as for "
        "drive_read_file). Never overwrites."
    )
)
def drive_download_file(file_id: str, local_path: str, drive: str = "") -> dict:
    return gtools.drive_download_file(_drive(drive), file_id, local_path)


@server.tool(
    description=(
        "Read one A1 range of a spreadsheet ('Tab name'!A1:Z50, or a bare tab name for the whole tab). render: "
        "FORMATTED_VALUE (default), UNFORMATTED_VALUE, or FORMULA to see each cell's formula instead of its value."
    )
)
def sheets_get_values(spreadsheet_id: str, cell_range: str, render: str = "FORMATTED_VALUE", drive: str = "") -> dict:
    return gtools.sheets_get_values(_drive(drive), spreadsheet_id, cell_range, render=render)


@server.tool(
    description=(
        "Create a file in a Drive folder (parent_id, default My Drive root) from text content or a local_path file - "
        "pass exactly one. Stored exactly as given, never converted. mime_type is guessed from the name when omitted. "
        "Drive allows duplicate names, so this always adds a new file; use drive_update_file to replace one."
    )
)
def drive_upload_file(
    name: str, parent_id: str = "root", content: str = "", local_path: str = "", mime_type: str = "", drive: str = ""
) -> dict:
    return gtools.drive_upload_file(
        _drive(drive), name, parent_id=parent_id, content=content, local_path=local_path, mime_type=mime_type
    )


@server.tool(
    description=(
        "Replace an existing Drive file's content in place from text content or a local_path file, keeping its id, "
        "name, folder and sharing."
    )
)
def drive_update_file(
    file_id: str, content: str = "", local_path: str = "", mime_type: str = "", drive: str = ""
) -> dict:
    return gtools.drive_update_file(_drive(drive), file_id, content=content, local_path=local_path, mime_type=mime_type)


@server.tool(description="Create a folder in Drive (parent_id, default My Drive root).")
def drive_create_folder(name: str, parent_id: str = "root", drive: str = "") -> dict:
    return gtools.drive_create_folder(_drive(drive), name, parent_id=parent_id)


@server.tool(
    description=(
        "Move a Drive file or folder to the trash, or restore it with undo=true. Recoverable for 30 days; there is "
        "no permanent delete."
    )
)
def drive_trash_file(file_id: str, undo: bool = False, drive: str = "") -> dict:
    return gtools.drive_trash_file(_drive(drive), file_id, undo=undo)


# %%
# Entry point #


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Google Calendar, Gmail and Drive MCP stdio server.")
    parser.add_argument(
        "--context",
        default="",
        help="pin account discovery to one context's <context>_calendarboard.yaml / "
        "<context>_googlemail.yaml / <context>_googledrive.yaml instead of every cloned credentials repo",
    )
    parser.add_argument(
        "--auth",
        metavar="DRIVE",
        default="",
        help="run the one-time browser consent for the named <context>_googledrive.yaml entry, print the "
        "token line for its env file, and exit instead of serving",
    )
    return parser.parse_args(argv)


def main(argv=None):
    global _context
    args = parse_args(argv)
    _context = args.context
    if args.auth:
        return gtools.run_drive_auth(gtools.find_by_name(_drives(), args.auth, "drive"))
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# %%
