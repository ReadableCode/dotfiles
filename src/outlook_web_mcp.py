# %%
# Imports #

# An MCP stdio server speaks JSON-RPC on stdout, so anything else printed there
# corrupts the protocol - and importing config creates missing repo dirs with a
# print. Every import that could talk to stdout goes through this redirect.
import argparse
import contextlib
import json
import sys
from datetime import date, datetime, timedelta

with contextlib.redirect_stdout(sys.stderr):
    from mcp.server.mcpserver import MCPServer  # noqa: E402

    from config import grandparent_dir  # noqa: E402
    from utils import outlookweb_tools as otools  # noqa: E402
    from utils.mcp_tool_errors import tool_decorator  # noqa: E402

# %%
# Variables #

CREDENTIALS_ROOT = grandparent_dir

# Set by --context: the one context whose <context>_outlookweb.yaml this
# instance reaches. A server is always pinned; there is no all-contexts mode,
# because one browser tab is one signed-in mailbox.
_context = ""

SERVER_INSTRUCTIONS = """
An Exchange mailbox and calendar reached through Outlook on the web, signed in
inside a browser profile on this Mac. Each call runs in that tab and calls the
Outlook REST API with the page's own sign-in, so it reaches exactly what the
web page does, live from the server, with no app registration of its own.

Which mailbox this instance reaches comes from <context>_outlookweb.yaml in the
context's credentials repo; list_accounts shows it and whether the tab is
signed in. With no Outlook tab open, one is opened in the configured profile.

Mail is read-only. Calendar writes are your own events only: create on any
writable calendar (busy, no attendees, no reminder, so nothing is sent), update
and delete only single events without attendees. Calendar delete is not
recoverable. Mail search uses the server's own search, whole bodies included.
""".strip()

server = MCPServer(name="outlook_web", instructions=SERVER_INSTRUCTIONS, version="0.1.0")
tool = tool_decorator(server)


# %%
# Account resolution #


def _accounts():
    if not _context:
        raise ValueError("this server must be started with --context")
    path = otools.config_path(CREDENTIALS_ROOT, _context)
    if not path:
        raise ValueError(f"no {_context}_{otools.CONFIG_KIND}.yaml in the {_context} credentials repo")
    return otools.load_accounts(path)


def _account(account=""):
    accounts = _accounts()
    if account:
        accounts = [entry for entry in accounts if entry["name"] == account]
        if not accounts:
            raise ValueError(f"no account named '{account}' configured - call list_accounts")
    if len(accounts) != 1:
        raise ValueError("more than one account configured - pass account")
    return accounts[0]


def _window(start_date, days):
    first = date.fromisoformat(start_date) if start_date else date.today()
    window_start = datetime.combine(first, datetime.min.time()).astimezone()
    return window_start, window_start + timedelta(days=max(1, days))


# %%
# Discovery #


@tool(description="The configured mailbox, the browser profile it lives in, and whether its Outlook tab is signed in.")
def list_accounts() -> dict:
    results = []
    for entry in _accounts():
        row = {key: entry[key] for key in ("name", "address", "sign_in", "browser", "profile")}
        row["config"] = entry["_config"]
        try:
            state = otools.ensure_session(entry)
            row["signed_in_as"] = state["user"]
        except (RuntimeError, PermissionError) as error:
            row["error"] = str(error)
        results.append(row)
    return {"context": _context, "accounts": results}


# %%
# Mail tools #


@tool(description="Every top-level mail folder, with total and unread counts.")
def mail_list_mailboxes(account: str = "") -> list:
    return otools.mail_list_mailboxes(_account(account))


@tool(
    description=(
        "Search the mailbox, newest first. query, sender, recipient and subject use the server's search (whole "
        "bodies included). mailbox is a folder name from mail_list_mailboxes (Inbox, Sent Items, ...). since / until "
        "are YYYY-MM-DD. Returns ids for mail_get_message."
    )
)
def mail_search(
    query: str = "",
    sender: str = "",
    recipient: str = "",
    subject: str = "",
    mailbox: str = "",
    since: str = "",
    until: str = "",
    unread_only: bool = False,
    max_results: int = 25,
    account: str = "",
) -> list:
    return otools.mail_search(
        _account(account),
        query_text=query,
        sender=sender,
        recipient=recipient,
        subject=subject,
        mailbox=mailbox,
        since=since,
        until=until,
        unread_only=unread_only,
        max_results=max_results,
    )


@tool(description="One message in full: headers, recipients, plain-text body and attachment names.")
def mail_get_message(message_id: str, body_limit: int = 20000, account: str = "") -> dict:
    return otools.mail_get_message(_account(account), message_id, body_limit=body_limit)


@tool(description="Save one attachment of a message, by its filename, byte for byte to local_path.")
def mail_download_attachment(message_id: str, filename: str, local_path: str, account: str = "") -> dict:
    return otools.mail_download_attachment(_account(account), message_id, filename, local_path)


# %%
# Calendar tools #


@tool(description="Every calendar in the mailbox, with the calendar_id the other calendar tools take.")
def calendar_list_calendars(account: str = "") -> list:
    return otools.calendar_list_calendars(_account(account))


@tool(
    description=(
        "Agenda for a date range, recurring series expanded. start_date is YYYY-MM-DD (default today); days counts "
        "forward from it. Timed events are LOCAL time with their offset; all-day ones are plain dates with an "
        "exclusive end."
    )
)
def calendar_agenda(start_date: str = "", days: int = 1, calendar_id: str = "", account: str = "") -> list:
    window_start, window_end = _window(start_date, days)
    return otools.calendar_events(_account(account), window_start, window_end, calendar_id=calendar_id)


@tool(description="Full detail for one event by event_id: body, organizer and every attendee's response.")
def calendar_get_event(event_id: str, account: str = "") -> dict:
    return otools.calendar_get_event(_account(account), event_id)


@tool(
    description=(
        "Create an event of your own: busy, no attendees, no reminder, so nothing is sent. start / end are ISO "
        "timestamps (2026-10-01T10:00:00-05:00) or YYYY-MM-DD for all-day with an exclusive end. Returns the event."
    )
)
def calendar_create_event(
    calendar_id: str, summary: str, start: str, end: str, location: str = "", description: str = "", account: str = ""
) -> dict:
    return otools.calendar_create_event(
        _account(account), calendar_id, summary, start, end, location=location, description=description
    )


@tool(
    description=(
        "Change one of your own single events - only the arguments you pass change. Refuses meetings with attendees "
        "and recurring series."
    )
)
def calendar_update_event(
    event_id: str,
    summary: str = "",
    start: str = "",
    end: str = "",
    location: str = "",
    description: str = "",
    account: str = "",
) -> dict:
    return otools.calendar_update_event(
        _account(account), event_id, summary=summary, start=start, end=end, location=location, description=description
    )


@tool(
    description=(
        "Delete one of your own single events. Not recoverable - confirm with the user first. Refuses meetings with "
        "attendees and recurring series."
    )
)
def calendar_delete_event(event_id: str, account: str = "") -> dict:
    return otools.calendar_delete_event(_account(account), event_id)


# %%
# Entry point #


def check():
    """Read-only: who the tab is signed in as, the calendars, and the newest message's date."""
    report = list_accounts()
    report["calendars"] = [cal["title"] for cal in calendar_list_calendars()]
    newest = mail_search(max_results=1)
    report["newest_message"] = newest[0]["date"] if newest else None
    print(json.dumps(report, indent=1))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Outlook on the web MCP stdio server (macOS, drives a browser tab).")
    parser.add_argument("--context", required=True, help="the context whose <context>_outlookweb.yaml to reach")
    parser.add_argument("--check", action="store_true", help="print what the tab reaches and exit; read-only")
    args, _ = parser.parse_known_args(argv)
    return args


def main(argv=None):
    global _context
    args = parse_args(argv)
    _context = args.context
    if args.check:
        check()
        return 0
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# %%
