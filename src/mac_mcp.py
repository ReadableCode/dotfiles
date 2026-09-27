# %%
# Imports #

# An MCP stdio server speaks JSON-RPC on stdout, so anything else printed there
# corrupts the protocol - and importing config creates missing repo dirs with a
# print. Every import that could talk to stdout goes through this redirect.
import argparse
import contextlib
import functools
import os
import sys
from datetime import date, datetime, timedelta

with contextlib.redirect_stdout(sys.stderr):
    from mcp.server.mcpserver import MCPServer  # noqa: E402
    from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

    from config import grandparent_dir  # noqa: E402
    from utils import macmcp_tools as mtools  # noqa: E402
    from utils.inventory_tools import (  # noqa: E402
        credentials_context,
        find_credentials_dirs,
    )

# %%
# Variables #

CREDENTIALS_ROOT = grandparent_dir

# Set by --context: pins account discovery to ONE context's
# <context>_macaccounts.yaml, so `acme_mac --context acme` reaches exactly the
# Mail and Calendar accounts that context names, even though Mail.app and
# Calendar.app on this Mac hold every context's accounts side by side. Empty =
# every cloned credentials repo's config at once (ad-hoc use only).
_context = ""

SERVER_INSTRUCTIONS = """
Jason's Mail.app, Calendar.app and Messages on this Mac, read from the local
copies those apps keep in sync - so it reaches any account signed in there
(Exchange, Google Workspace, iCloud, IMAP) with no Google or Microsoft app
registration of its own.

Which accounts this instance reaches comes from <context>_macaccounts.yaml in
the context's credentials repo. `account` can be left out to search every
account this context has; list_accounts shows them and what each matched on
this Mac.

Mail and Messages are read-only. Calendar writes go through Calendar.app, which
syncs them to the owning account: create on any writable calendar, update and
delete only on your own single events (never meetings with attendees or
recurring series). Calendar.app sends no invitations from here, and calendar
delete is not recoverable. Mail search matches subject, sender and Mail's stored
preview, not whole bodies.
""".strip()

server = MCPServer(name="mac", instructions=SERVER_INSTRUCTIONS, version="0.1.0")

# Failures the readers raise on purpose - an account not configured, a store
# macOS will not open, Calendar.app refusing a write. The SDK shows the model
# only "Error executing tool <name>" for any other exception type, so these
# are re-raised as ToolError to carry their reason through.
ANTICIPATED_ERRORS = (ValueError, PermissionError, FileNotFoundError, RuntimeError)


def tool(description):
    def register(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except ANTICIPATED_ERRORS as error:
                raise ToolError(str(error)) from error

        return server.tool(description=description)(wrapped)

    return register


# %%
# Account resolution #


def _pinned_config():
    """
    The pinned context's ``<context>_macaccounts.yaml``, or None when that repo
    is not cloned or has no such config (a pinned server with nothing
    configured reports no accounts rather than leaking another context's).
    """
    for credentials_dir in find_credentials_dirs(CREDENTIALS_ROOT):
        if credentials_context(credentials_dir) == _context:
            path = os.path.join(credentials_dir, f"{_context}_{mtools.CONFIG_KIND}.yaml")
            return path if os.path.exists(path) else None
    return None


def _configured():
    if _context:
        path = _pinned_config()
        if not path:
            return []
        accounts, _ = mtools.load_accounts(CREDENTIALS_ROOT, config_path=path)
    else:
        accounts, _ = mtools.load_accounts(CREDENTIALS_ROOT)
    return accounts


def _scope(account="", kind="internet_account"):
    """
    The configured entries of ``kind`` a call covers: the named one, or every
    one when the name is omitted - a question about "my email" should search
    all of this context's mailboxes, not force a pick.
    """
    mtools.require_macos()
    entries = [entry for entry in _configured() if entry["type"] == kind]
    if account:
        entries = [entry for entry in entries if entry["name"] == account]
        if not entries:
            raise ValueError(f"no {kind} named '{account}' configured - call list_accounts")
    if not entries:
        raise ValueError(f"no {kind} configured for this context - see docs/setup_mac_mcp.md")
    return mtools.resolve_scope(entries)


def _require_messages():
    _scope(kind="messages")


def _window(start_date, days):
    first = date.fromisoformat(start_date) if start_date else date.today()
    window_start = datetime.combine(first, datetime.min.time()).astimezone()
    return window_start, window_start + timedelta(days=max(1, days))


# %%
# Discovery #


@tool(
    description=(
        "List the accounts this server reaches: each configured entry, and which Internet Accounts it matched on "
        "this Mac. An entry that matched nothing is not signed in to Mail.app / Calendar.app here."
    )
)
def list_accounts() -> dict:
    entries = _configured()
    reach: dict = {}
    if sys.platform == "darwin":
        reach = mtools.describe_scope(mtools.resolve_scope(entries))
    return {
        "platform": sys.platform,
        "accounts": [
            {
                "name": entry["name"],
                "type": entry["type"],
                "address": entry.get("address"),
                **reach.get(entry["name"], {}),
                "config": entry["_config"],
            }
            for entry in entries
        ],
    }


# %%
# Mail tools #


@tool(description="Every Mail folder (and Gmail label) in the accounts, with total and unread counts.")
def mail_list_mailboxes(account: str = "") -> list:
    return mtools.mail_list_mailboxes(_scope(account))


@tool(
    description=(
        "Search Mail.app's index across the accounts, newest first. query matches subject, sender and Mail's stored "
        "preview of the body (not the whole body); sender / recipient / subject narrow further. mailbox is a folder "
        "or Gmail label path from mail_list_mailboxes (INBOX, Sent Items, ...). since / until are YYYY-MM-DD or ISO "
        "timestamps. Trash, spam and junk are skipped unless include_spam_trash. Returns ids for mail_get_message."
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
    include_spam_trash: bool = False,
    max_results: int = 25,
    account: str = "",
) -> list:
    return mtools.mail_search(
        _scope(account),
        query_text=query,
        sender=sender,
        recipient=recipient,
        subject=subject,
        mailbox=mailbox,
        since=since,
        until=until,
        unread_only=unread_only,
        include_spam_trash=include_spam_trash,
        max_results=max_results,
    )


@tool(
    description=(
        "One message in full from Mail's own copy: headers, recipients, plain-text body (HTML converted) and "
        "attachment names with local paths where Mail stored them. body_is_preview_only means Mail never downloaded "
        "the body."
    )
)
def mail_get_message(message_id: int, body_limit: int = 20000, account: str = "") -> dict:
    return mtools.mail_get_message(_scope(account), message_id, body_limit=body_limit)


# %%
# Messages tools #


@tool(
    description=(
        "Messages conversations, most recently active first, with participants resolved to contact names. query "
        "filters by conversation name or participant."
    )
)
def messages_list_chats(query: str = "", max_results: int = 30) -> list:
    _require_messages()
    return mtools.messages_list_chats(query_text=query, max_results=max_results)


@tool(
    description=(
        "One conversation's messages, oldest first - the most recent max_results within since / until "
        "(YYYY-MM-DD or ISO). Attachments are listed by name and local path."
    )
)
def messages_get_chat(chat_id: int, since: str = "", until: str = "", max_results: int = 100) -> list:
    _require_messages()
    return mtools.messages_get_chat(chat_id, since=since, until=until, max_results=max_results)


@tool(
    description=(
        "Search Messages (iMessage and SMS) by text and/or contact - a name from Contacts, a phone number or an "
        "address; a contact also matches group chats they are in. Newest first, each with its chat_id."
    )
)
def messages_search(
    query: str = "", contact: str = "", since: str = "", until: str = "", max_results: int = 50
) -> list:
    _require_messages()
    return mtools.messages_search(query_text=query, contact=contact, since=since, until=until, max_results=max_results)


# %%
# Calendar tools #


@tool(description="Every calendar in the accounts, with the calendar_id the other calendar tools take.")
def calendar_list_calendars(account: str = "") -> list:
    return mtools.calendar_list_calendars(_scope(account))


@tool(
    description=(
        "Agenda across every calendar in the accounts for a date range, recurring series expanded. start_date is "
        "YYYY-MM-DD (default today); days counts forward from it. Timed events are LOCAL time with their offset; "
        "all-day ones are plain dates with an exclusive end."
    )
)
def calendar_agenda(start_date: str = "", days: int = 1, calendar_id: str = "", account: str = "") -> list:
    window_start, window_end = _window(start_date, days)
    return mtools.calendar_events(_scope(account), window_start, window_end, calendar_id=calendar_id)


@tool(
    description=(
        "Search events by text in title, notes or location within time_min / time_max (YYYY-MM-DD or ISO; default "
        "from 90 days ago to a year ahead)."
    )
)
def calendar_search_events(
    query: str, time_min: str = "", time_max: str = "", calendar_id: str = "", max_results: int = 50, account: str = ""
) -> list:
    today = datetime.combine(date.today(), datetime.min.time()).astimezone()
    window_start = mtools.parse_moment(time_min) or today - timedelta(days=90)
    window_end = mtools.parse_moment(time_max, end_of_day=True) or today + timedelta(days=365)
    events = mtools.calendar_events(
        _scope(account), window_start, window_end, query_text=query, calendar_id=calendar_id
    )
    return events[: max(1, max_results)]


@tool(
    description=(
        "Full detail for one event by event_id: notes, url, organizer, every attendee's response, and created / "
        "last-modified times. For a recurring event this is the series."
    )
)
def calendar_get_event(event_id: str, calendar_id: str = "", account: str = "") -> dict:
    return mtools.calendar_get_event(_scope(account), event_id, calendar_id=calendar_id)


@tool(
    description=(
        "Create an event through Calendar.app, which syncs it to the calendar's account. start / end are ISO "
        "timestamps (2026-10-01T10:00:00-05:00) or YYYY-MM-DD for all-day with an exclusive end. No attendees or "
        "invitations - this is for your own time. Returns the new event_id."
    )
)
def calendar_create_event(
    calendar_id: str,
    summary: str,
    start: str,
    end: str,
    location: str = "",
    description: str = "",
    url: str = "",
    account: str = "",
) -> dict:
    return mtools.calendar_create_event(
        _scope(account), calendar_id, summary, start, end, location=location, description=description, url=url
    )


@tool(
    description=(
        "Change one of your own single events - only the arguments you pass change. Refuses meetings with attendees "
        "and recurring series. Same time formats as calendar_create_event."
    )
)
def calendar_update_event(
    event_id: str,
    calendar_id: str,
    summary: str = "",
    start: str = "",
    end: str = "",
    location: str = "",
    description: str = "",
    url: str = "",
    account: str = "",
) -> dict:
    return mtools.calendar_update_event(
        _scope(account),
        event_id,
        calendar_id,
        summary=summary,
        start=start,
        end=end,
        location=location,
        description=description,
        url=url,
    )


@tool(
    description=(
        "Delete one of your own single events. Not recoverable - confirm with the user first. Refuses meetings with "
        "attendees and recurring series."
    )
)
def calendar_delete_event(event_id: str, calendar_id: str, account: str = "") -> dict:
    return mtools.calendar_delete_event(_scope(account), event_id, calendar_id)


# %%
# Entry point #


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Mail.app, Calendar.app and Messages MCP stdio server (macOS).")
    parser.add_argument(
        "--context",
        default="",
        help="pin account discovery to one context's <context>_macaccounts.yaml instead of every cloned "
        "credentials repo",
    )
    return parser.parse_args(argv)


def main(argv=None):
    global _context
    args = parse_args(argv)
    _context = args.context
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# %%
