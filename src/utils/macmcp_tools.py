# %%
# Imports #

import email
import email.policy
import glob
import html
import os
import re
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

import yaml
from dateutil import rrule

from utils.inventory_tools import credentials_context, find_credentials_dirs

# %%
# Variables #

# Every store this module reads is the local copy an Apple app keeps in sync.
# Reading them needs Full Disk Access on whatever launched the process (see
# docs/setup_mac_mcp.md) and no Google or Microsoft app registration at all:
# Mail.app and Calendar.app already hold the tenant's approval.
LIBRARY_DIR = os.path.join(os.path.expanduser("~"), "Library")
MAIL_ROOT = os.path.join(LIBRARY_DIR, "Mail")
MESSAGES_DB = os.path.join(LIBRARY_DIR, "Messages", "chat.db")
CALENDAR_DB = os.path.join(LIBRARY_DIR, "Group Containers", "group.com.apple.calendar", "Calendar.sqlitedb")
ACCOUNTS_DB = os.path.join(LIBRARY_DIR, "Accounts", "Accounts4.sqlite")
ADDRESS_BOOK_DIR = os.path.join(LIBRARY_DIR, "Application Support", "AddressBook")
ADDRESS_BOOK_NAME = "AddressBook-v22.abcddb"

# Core Data and Messages count from 2001-01-01 UTC, not the Unix epoch.
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)
# Messages switched from seconds to nanoseconds; anything this large is the latter.
NANOSECOND_THRESHOLD = 10**11

# <context>_macaccounts.yaml: which of this Mac's accounts a context reaches.
CONFIG_KIND = "macaccounts"
ACCOUNT_TYPES = ("internet_account", "messages")

# Mail folders left out of a search unless include_spam_trash is set.
SPAM_TRASH_PATTERN = re.compile(r"(^|/)(\[gmail\]/)?(trash|spam|junk|junk email|junk e-mail|deleted items|bin)$", re.I)

# Calendar item entity_type for events (reminders live in the same table).
EVENT_ENTITY = 2
# Participant.entity_type: 7 an attendee row, 8 the organizer row.
ATTENDEE_ENTITY = 7
ORGANIZER_ENTITY = 8
# Participant.status is iCalendar PARTSTAT order, not EventKit's enum - checked
# against the Google API's own responseStatus for the same meetings. Your answer
# is on the attendee row carrying your address; Participant.is_self is not kept
# up to date, and CalendarItem.invitation_status is not a response at all.
PARTICIPANT_STATUS = {
    0: "needs_action",
    1: "accepted",
    2: "declined",
    3: "tentative",
    4: "delegated",
    5: "completed",
    6: "in_process",
}
PARTICIPANT_ROLE = {0: "unknown", 1: "required", 2: "optional", 3: "chair", 4: "non_participant"}

# recipients.type in Mail's index.
RECIPIENT_TYPES = {0: "to", 1: "cc", 2: "bcc"}

# Messages stores a tapback as its own row; associated_message_type 0 is a real message.
PLAIN_MESSAGE_TYPE = 0
# U+FFFC marks where an attachment sat in the message text.
ATTACHMENT_PLACEHOLDER = "￼"

# Recurrence.frequency, and week_start (1 Monday .. 7 Sunday, 0 unset = RFC 5545's Monday default).
RRULE_FREQUENCY = {1: rrule.DAILY, 2: rrule.WEEKLY, 3: rrule.MONTHLY, 4: rrule.YEARLY}
RRULE_WEEKDAYS = {
    "MO": rrule.MO,
    "TU": rrule.TU,
    "WE": rrule.WE,
    "TH": rrule.TH,
    "FR": rrule.FR,
    "SA": rrule.SA,
    "SU": rrule.SU,
}
RRULE_WEEK_START = {
    0: rrule.MO,
    1: rrule.MO,
    2: rrule.TU,
    3: rrule.WE,
    4: rrule.TH,
    5: rrule.FR,
    6: rrule.SA,
    7: rrule.SU,
}
# Recurrence.specifier keys holding plain integers, and the rrule argument each becomes.
SPECIFIER_KEYS = {"M": "bymonthday", "O": "bymonth", "S": "bysetpos", "Y": "byyearday", "W": "byweekno"}

# A CalDAV calendar's path ends /inbox/ or /outbox/ for the scheduling mailboxes.
SCHEDULING_MAILBOX_PATTERN = re.compile(r"/(inbox|outbox)/?$")

OSASCRIPT_TIMEOUT = 60
MAX_RESULTS = 500


# %%
# Platform #


def require_macos():
    """Every reader here is a macOS app's store; say so plainly anywhere else."""
    if sys.platform != "darwin":
        raise RuntimeError(
            "the mac server reads Mail.app, Calendar.app and Messages stores and only runs on macOS "
            "(Windows and Linux are tracked in backlog/mac-mcp-windows-linux.md)"
        )


def connect(path):
    """
    Open an Apple store strictly read-only. mode=ro still sees the WAL, so the
    result matches what the app shows; immutable=1 would not.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} does not exist - is the app set up on this Mac?")
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.OperationalError as error:
        raise PermissionError(f"cannot open {path} ({error}) - grant Full Disk Access, see docs/setup_mac_mcp.md")
    connection.row_factory = sqlite3.Row
    return connection


def query(path, sql, params=()):
    connection = connect(path)
    try:
        return connection.execute(sql, params).fetchall()
    except sqlite3.DatabaseError as error:
        if "authorization denied" in str(error) or "unable to open" in str(error):
            raise PermissionError(f"cannot read {path} ({error}) - grant Full Disk Access, see docs/setup_mac_mcp.md")
        raise
    finally:
        connection.close()


def placeholders(values):
    return ",".join("?" for _ in values)


# %%
# Time #


def from_apple_seconds(value):
    return APPLE_EPOCH + timedelta(seconds=value)


def to_apple_seconds(moment):
    return (moment - APPLE_EPOCH).total_seconds()


def from_messages_date(value):
    """Messages dates are seconds before macOS 10.13 and nanoseconds after."""
    if not value:
        return None
    seconds = value / 1e9 if abs(value) > NANOSECOND_THRESHOLD else value
    return from_apple_seconds(seconds)


def local_iso(moment):
    return moment.astimezone().isoformat() if moment else None


def parse_moment(value, end_of_day=False):
    """
    YYYY-MM-DD or an ISO timestamp -> an aware datetime. A bare date is local
    midnight (the start of that day, or of the next one for an end bound); a
    naive timestamp is local time.
    """
    if not value:
        return None
    if len(value) == 10:
        day = date.fromisoformat(value) + timedelta(days=1 if end_of_day else 0)
        return datetime.combine(day, datetime.min.time()).astimezone()
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.astimezone()


# %%
# Account config #


def discover_account_configs(credentials_root):
    """Every ``<context>_macaccounts.yaml`` in the sibling ``*_credentials`` repos."""
    configs = []
    for credentials_dir in find_credentials_dirs(credentials_root):
        path = os.path.join(credentials_dir, f"{credentials_context(credentials_dir)}_{CONFIG_KIND}.yaml")
        if os.path.exists(path):
            configs.append(path)
    return configs


def load_accounts(credentials_root, config_path=None):
    """
    Load the configured account entries, returning (accounts, config_paths).
    Names must be unique across every loaded config.
    """
    paths = [config_path] if config_path else discover_account_configs(credentials_root)
    accounts = []
    seen: dict = {}
    for path in paths:
        for account in parse_account_config(path):
            if account["name"] in seen:
                raise ValueError(
                    f"Duplicate {CONFIG_KIND} name '{account['name']}' in {path} "
                    f"(already defined in {seen[account['name']]})"
                )
            seen[account["name"]] = path
            account["_config"] = path
            accounts.append(account)
    return accounts, paths


def parse_account_config(config_path):
    with open(config_path, "r", encoding="utf-8") as file_handle:
        payload = yaml.safe_load(file_handle) or []
    if not isinstance(payload, list):
        raise ValueError(f"{config_path}: expected a list of accounts, got {type(payload).__name__}")
    for account in payload:
        if not isinstance(account, dict):
            raise ValueError(f"{config_path}: expected a list of account mappings, got {type(account).__name__}")
        name = account.get("name")
        if not name or not account.get("type"):
            raise ValueError(f"{config_path}: account {name or '<unnamed>'} needs both name and type")
        if account["type"] not in ACCOUNT_TYPES:
            raise ValueError(
                f"{config_path}: account '{name}' has unknown type '{account['type']}' "
                f"(expected one of {ACCOUNT_TYPES})"
            )
        if account["type"] == "internet_account" and not account.get("address"):
            raise ValueError(f"{config_path}: internet_account '{name}' is missing address")
    return payload


# %%
# Internet Accounts #


def internet_accounts(accounts_db=None):
    """
    Every top-level account in System Settings > Internet Accounts, each with
    the identifiers of its whole subtree. Mail.app names its account folders
    after a child IMAP/Exchange identifier and Calendar.app its stores after a
    child CalDAV one, so walking each child up to its root is what ties a
    mailbox or a calendar to the address the config names.
    """
    rows = query(
        accounts_db or ACCOUNTS_DB,
        "SELECT a.Z_PK AS pk, a.ZIDENTIFIER AS identifier, a.ZPARENTACCOUNT AS parent, a.ZUSERNAME AS username, "
        "a.ZACCOUNTDESCRIPTION AS description, t.ZACCOUNTTYPEDESCRIPTION AS kind "
        "FROM ZACCOUNT a LEFT JOIN ZACCOUNTTYPE t ON t.Z_PK = a.ZACCOUNTTYPE",
    )
    by_pk = {row["pk"]: row for row in rows}
    roots: dict = {}
    for row in rows:
        root, hops = row, 0
        while root["parent"] and root["parent"] in by_pk and hops < len(rows):
            root, hops = by_pk[root["parent"]], hops + 1
        entry = roots.setdefault(
            root["pk"],
            {
                "address": (root["username"] or "").lower(),
                "kind": root["kind"],
                "description": root["description"],
                "identifiers": set(),
            },
        )
        if row["identifier"]:
            entry["identifiers"].add(row["identifier"])
    return list(roots.values())


def resolve_scope(accounts, accounts_db=None):
    """
    Attach to each configured entry the Internet Accounts it covers on this Mac
    (``_identifiers`` and ``_matched``). An address can match more than one -
    one Apple ID is often both the iCloud and the Google account - and the entry
    then covers all of them. An address signed in nowhere matches nothing.
    """
    internet = internet_accounts(accounts_db) if any(a["type"] == "internet_account" for a in accounts) else []
    for account in accounts:
        if account["type"] != "internet_account":
            account["_identifiers"], account["_matched"] = set(), []
            continue
        address = account["address"].lower()
        matched = [entry for entry in internet if entry["address"] == address]
        account["_identifiers"] = set().union(*(entry["identifiers"] for entry in matched)) if matched else set()
        account["_matched"] = matched
    return accounts


def describe_scope(accounts, mail_root=None, calendar_db=None):
    """
    What each resolved entry actually reaches here: the Internet Accounts that
    hold mail or calendars (an Apple ID also owns Game Center, iTunes and the
    like, which are noise), and how many folders and calendars that is.
    """
    mailboxes = scoped_mailboxes(accounts, mail_root)
    calendars = scoped_calendars(accounts, calendar_db)
    used = {box["account_id"] for box in mailboxes.values()} | {cal["_store_id"] for cal in calendars.values()}
    described = {}
    for account in accounts:
        described[account["name"]] = {
            "internet_accounts": [
                f"{entry['kind']} ({entry['description'] or entry['address']})"
                for entry in account.get("_matched", [])
                if entry["identifiers"] & used
            ],
            "mail_folders": sum(1 for box in mailboxes.values() if box["account"] == account["name"]),
            "calendars": sum(1 for cal in calendars.values() if cal["account"] == account["name"]),
        }
    return described


def owner_of(identifier, accounts):
    for account in accounts:
        if identifier in account.get("_identifiers", ()):
            return account["name"]
    return None


# %%
# Mail #


def mail_dir(mail_root=None):
    """Mail keeps everything under ~/Library/Mail/V<n>; the highest n is the live one."""
    root = mail_root or MAIL_ROOT
    versions = [path for path in glob.glob(os.path.join(glob.escape(root), "V*")) if os.path.isdir(path)]
    if not versions:
        raise FileNotFoundError(
            f"no Mail store under {root} - is Mail.app set up, and does this process have Full Disk Access?"
        )
    return max(versions, key=lambda path: int(re.sub(r"\D", "", os.path.basename(path)) or 0))


def envelope_index(mail_root=None):
    return os.path.join(mail_dir(mail_root), "MailData", "Envelope Index")


def split_mailbox_url(url):
    """imap://<account id>/%5BGmail%5D/All%20Mail -> (account id, '[Gmail]/All Mail')."""
    parsed = urlparse(url)
    return parsed.netloc, unquote(parsed.path.lstrip("/"))


def scoped_mailboxes(accounts, mail_root=None):
    """Every Mail folder that belongs to one of the given accounts, keyed by mailbox ROWID."""
    rows = query(envelope_index(mail_root), "SELECT ROWID AS id, url, source, total_count, unread_count FROM mailboxes")
    mailboxes = {}
    for row in rows:
        account_id, path = split_mailbox_url(row["url"])
        owner = owner_of(account_id, accounts)
        if owner:
            mailboxes[row["id"]] = {
                "id": row["id"],
                "account": owner,
                "account_id": account_id,
                "path": path,
                "is_label": row["source"] is not None,
                "total": row["total_count"],
                "unread": row["unread_count"],
            }
    return mailboxes


def mail_list_mailboxes(accounts, mail_root=None):
    mailboxes = scoped_mailboxes(accounts, mail_root)
    return sorted(
        ({key: box[key] for key in ("account", "path", "is_label", "total", "unread")} for box in mailboxes.values()),
        key=lambda box: (box["account"], box["path"].lower()),
    )


def mail_search(
    accounts,
    query_text="",
    sender="",
    recipient="",
    subject="",
    mailbox="",
    since="",
    until="",
    unread_only=False,
    include_spam_trash=False,
    max_results=25,
    mail_root=None,
):
    """
    Search Mail's own index across the given accounts. ``query_text`` matches
    the subject, the sender and the preview Mail stores for each message -
    not the whole body. Newest first, one row per message per account.
    """
    mailboxes = scoped_mailboxes(accounts, mail_root)
    if not mailboxes:
        return []
    searched = {
        box_id for box_id, box in mailboxes.items() if include_spam_trash or not SPAM_TRASH_PATTERN.search(box["path"])
    }
    clauses = [f"m.deleted = 0 AND m.mailbox IN ({placeholders(searched)})"]
    params: list = list(searched)
    if mailbox:
        wanted = [box_id for box_id, box in mailboxes.items() if box["path"].lower() == mailbox.lower()]
        if not wanted:
            raise ValueError(f"no mailbox '{mailbox}' in these accounts - mail_list_mailboxes lists them")
        clauses.append(
            f"(m.mailbox IN ({placeholders(wanted)}) OR EXISTS (SELECT 1 FROM labels l WHERE l.message_id = m.ROWID "
            f"AND l.mailbox_id IN ({placeholders(wanted)})))"
        )
        params += wanted + wanted
    if query_text:
        like = f"%{query_text}%"
        clauses.append("(s.subject LIKE ? OR a.address LIKE ? OR a.comment LIKE ? OR su.summary LIKE ?)")
        params += [like] * 4
    if sender:
        clauses.append("(a.address LIKE ? OR a.comment LIKE ?)")
        params += [f"%{sender}%"] * 2
    if subject:
        clauses.append("s.subject LIKE ?")
        params.append(f"%{subject}%")
    if recipient:
        clauses.append(
            "EXISTS (SELECT 1 FROM recipients r JOIN addresses ra ON ra.ROWID = r.address "
            "WHERE r.message = m.ROWID AND (ra.address LIKE ? OR ra.comment LIKE ?))"
        )
        params += [f"%{recipient}%"] * 2
    if since:
        clauses.append("m.date_received >= ?")
        params.append(parse_moment(since).timestamp())
    if until:
        clauses.append("m.date_received < ?")
        params.append(parse_moment(until, end_of_day=True).timestamp())
    if unread_only:
        clauses.append("m.read = 0")
    limit = max(1, min(max_results, MAX_RESULTS))
    rows = query(
        envelope_index(mail_root),
        "SELECT m.ROWID AS id, m.global_message_id AS global_id, m.mailbox, m.date_received, m.read, m.flagged, "
        "m.subject_prefix, s.subject, a.address AS sender_address, a.comment AS sender_name, su.summary "
        "FROM messages m JOIN subjects s ON s.ROWID = m.subject LEFT JOIN addresses a ON a.ROWID = m.sender "
        f"LEFT JOIN summaries su ON su.ROWID = m.summary WHERE {' AND '.join(clauses)} "
        "ORDER BY m.date_received DESC LIMIT ?",
        params + [limit * 3],
    )
    results, seen = [], set()
    for row in rows:
        box = mailboxes[row["mailbox"]]
        key = (row["global_id"], box["account"])
        if key in seen:
            continue
        seen.add(key)
        results.append((row, box))
        if len(results) == limit:
            break
    labels = mail_labels([row["id"] for row, _ in results], mailboxes, mail_root)
    recipients = mail_recipients([row["id"] for row, _ in results], mail_root)
    return [
        {
            "message_id": row["id"],
            "account": box["account"],
            "mailbox": box["path"],
            "labels": labels.get(row["id"], []),
            "date": local_iso(datetime.fromtimestamp(row["date_received"], tz=timezone.utc)),
            "from": format_address(row["sender_address"], row["sender_name"]),
            "to": recipients.get(row["id"], {}).get("to", []),
            "subject": f"{row['subject_prefix'] or ''}{row['subject']}",
            "snippet": (row["summary"] or "")[:300],
            "read": bool(row["read"]),
            "flagged": bool(row["flagged"]),
        }
        for row, box in results
    ]


def format_address(address, name):
    if not address:
        return name or ""
    return f"{name} <{address}>" if name else address


def mail_labels(message_ids, mailboxes, mail_root=None):
    """Gmail keeps each message once, in All Mail, and its labels in a join table."""
    if not message_ids:
        return {}
    rows = query(
        envelope_index(mail_root),
        f"SELECT message_id, mailbox_id FROM labels WHERE message_id IN ({placeholders(message_ids)})",
        message_ids,
    )
    labels: dict = {}
    for row in rows:
        if row["mailbox_id"] in mailboxes:
            labels.setdefault(row["message_id"], []).append(mailboxes[row["mailbox_id"]]["path"])
    return labels


def mail_recipients(message_ids, mail_root=None):
    if not message_ids:
        return {}
    rows = query(
        envelope_index(mail_root),
        "SELECT r.message, r.type, a.address, a.comment FROM recipients r JOIN addresses a ON a.ROWID = r.address "
        f"WHERE r.message IN ({placeholders(message_ids)}) ORDER BY r.message, r.type, r.position",
        message_ids,
    )
    recipients: dict = {}
    for row in rows:
        kind = RECIPIENT_TYPES.get(row["type"], "other")
        recipients.setdefault(row["message"], {}).setdefault(kind, []).append(
            format_address(row["address"], row["comment"])
        )
    return recipients


def emlx_candidates(mail_version_dir, account_id, mailbox_path, message_id):
    """
    Where Mail keeps one message on disk: <account>/<folder>.mbox/<store>/Data/
    <thousands digits, reversed, one per level>/Messages/<id>[.partial].emlx.
    A .partial.emlx holds the text parts and leaves attachments beside it.
    """
    mbox = os.path.join(mail_version_dir, account_id, *[f"{part}.mbox" for part in mailbox_path.split("/")])
    thousands = message_id // 1000
    levels = list(str(thousands)[::-1]) if thousands else []
    data_dir = os.path.join("Data", *levels, "Messages")
    found = []
    for suffix in (".emlx", ".partial.emlx"):
        pattern = os.path.join(glob.escape(mbox), "*", data_dir, f"{message_id}{suffix}")
        found += glob.glob(pattern)
        found += glob.glob(os.path.join(glob.escape(mbox), data_dir, f"{message_id}{suffix}"))
    return found


def parse_emlx(path):
    """An .emlx is a byte count line, that many bytes of RFC 822, then a plist."""
    with open(path, "rb") as file_handle:
        length = int(file_handle.readline().strip())
        raw = file_handle.read(length)
    return email.message_from_bytes(raw, policy=email.policy.default)


def html_to_text(markup):
    markup = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", markup)
    text = html.unescape(re.sub(r"<[^>]+>", " ", markup))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def message_body(message):
    part = message.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        content = part.get_content()
    except (LookupError, UnicodeDecodeError):
        content = part.get_payload(decode=True).decode("utf-8", errors="replace")
    return html_to_text(content) if part.get_content_type() == "text/html" else content.strip()


def mail_get_message(accounts, message_id, body_limit=20000, mail_root=None):
    """
    One message in full, read from Mail's own file for it. Refuses a message
    outside the given accounts - an id from another context reads as not found.
    """
    mailboxes = scoped_mailboxes(accounts, mail_root)
    rows = query(
        envelope_index(mail_root),
        "SELECT m.ROWID AS id, m.mailbox, m.date_received, m.read, m.flagged, m.subject_prefix, s.subject, "
        "a.address AS sender_address, a.comment AS sender_name, su.summary FROM messages m "
        "JOIN subjects s ON s.ROWID = m.subject LEFT JOIN addresses a ON a.ROWID = m.sender "
        "LEFT JOIN summaries su ON su.ROWID = m.summary WHERE m.ROWID = ?",
        (int(message_id),),
    )
    if not rows or rows[0]["mailbox"] not in mailboxes:
        raise ValueError(f"no message {message_id} in these accounts")
    row, box = rows[0], mailboxes[rows[0]["mailbox"]]
    result = {
        "message_id": row["id"],
        "account": box["account"],
        "mailbox": box["path"],
        "labels": mail_labels([row["id"]], mailboxes, mail_root).get(row["id"], []),
        "date": local_iso(datetime.fromtimestamp(row["date_received"], tz=timezone.utc)),
        "from": format_address(row["sender_address"], row["sender_name"]),
        "subject": f"{row['subject_prefix'] or ''}{row['subject']}",
        "read": bool(row["read"]),
        "flagged": bool(row["flagged"]),
        **mail_recipients([row["id"]], mail_root).get(row["id"], {}),
    }
    files = emlx_candidates(mail_dir(mail_root), box["account_id"], box["path"], row["id"])
    if not files:
        # Mail has the envelope but never downloaded this body (or has since evicted it).
        result.update(body=row["summary"] or "", body_is_preview_only=True, attachments=[])
        return result
    message = parse_emlx(files[0])
    body = message_body(message)
    attachments = [
        {"filename": part.get_filename(), "content_type": part.get_content_type()}
        for part in message.iter_attachments()
        if part.get_filename()
    ]
    attachments += stored_attachments(files[0], row["id"], attachments)
    result.update(
        message_id_header=message.get("Message-ID"),
        reply_to=message.get("Reply-To"),
        body=body[:body_limit],
        body_truncated=len(body) > body_limit,
        body_is_preview_only=False,
        attachments=attachments,
    )
    return result


def stored_attachments(emlx_path, message_id, already):
    """A .partial.emlx leaves its attachments under Attachments/<id>/<part>/<name> next door."""
    root = os.path.join(os.path.dirname(os.path.dirname(emlx_path)), "Attachments", str(message_id))
    known = {item["filename"] for item in already}
    found = []
    for path in sorted(glob.glob(os.path.join(glob.escape(root), "*", "*"))):
        name = os.path.basename(path)
        if os.path.isfile(path) and name not in known:
            found.append({"filename": name, "size": os.path.getsize(path), "local_path": path})
    return found


# %%
# Contacts #

_contact_cache: dict = {}


def normalize_handle(handle):
    """Emails compare lowercased; phone numbers by their last ten digits."""
    handle = (handle or "").strip()
    if "@" in handle:
        return handle.lower()
    digits = re.sub(r"\D", "", handle)
    return digits[-10:] if digits else handle.lower()


def contact_names(address_book_dir=None):
    """
    normalized phone/email -> contact name, from every Contacts database on
    this Mac (the local one plus one per synced account). Cached per process.
    """
    root = address_book_dir or ADDRESS_BOOK_DIR
    if root in _contact_cache:
        return _contact_cache[root]
    paths = glob.glob(os.path.join(glob.escape(root), ADDRESS_BOOK_NAME)) + glob.glob(
        os.path.join(glob.escape(root), "Sources", "*", ADDRESS_BOOK_NAME)
    )
    names: dict = {}
    for path in paths:
        records = {
            row["pk"]: " ".join(part for part in (row["first"], row["last"]) if part) or row["org"] or row["nick"]
            for row in query(
                path,
                "SELECT Z_PK AS pk, ZFIRSTNAME AS first, ZLASTNAME AS last, ZORGANIZATION AS org, "
                "ZNICKNAME AS nick FROM ZABCDRECORD",
            )
        }
        for row in query(path, "SELECT ZOWNER AS owner, ZFULLNUMBER AS value FROM ZABCDPHONENUMBER") + query(
            path, "SELECT ZOWNER AS owner, ZADDRESS AS value FROM ZABCDEMAILADDRESS"
        ):
            name = records.get(row["owner"])
            if name and row["value"]:
                names.setdefault(normalize_handle(row["value"]), name)
    _contact_cache[root] = names
    return names


def display_handle(handle, names):
    name = names.get(normalize_handle(handle))
    return f"{name} ({handle})" if name else handle


# %%
# Messages #


def decode_attributed_body(blob):
    """
    Newer Messages rows leave ``text`` empty and keep the words in
    ``attributedBody``, an NSArchiver typedstream of an NSAttributedString. The
    string sits right after the NSString class name as a '+' tagged value: one
    length byte, or 0x81 + two / 0x82 + four little-endian bytes, then UTF-8.
    """
    if not blob:
        return ""
    blob = bytes(blob)
    marker = blob.find(b"NSString")
    if marker < 0:
        return ""
    start = blob.find(b"\x84\x01+", marker)
    if start < 0:
        return ""
    index = start + 3
    length = blob[index]
    index += 1
    if length == 0x81:
        length = int.from_bytes(blob[index : index + 2], "little")
        index += 2
    elif length == 0x82:
        length = int.from_bytes(blob[index : index + 4], "little")
        index += 4
    return blob[index : index + length].decode("utf-8", errors="replace")


def message_text(row):
    text = row["text"] or decode_attributed_body(row["attributedBody"])
    return text.replace(ATTACHMENT_PLACEHOLDER, "").strip()


def message_attachments(message_ids, messages_db=None):
    if not message_ids:
        return {}
    rows = query(
        messages_db or MESSAGES_DB,
        "SELECT j.message_id, a.transfer_name, a.filename, a.mime_type FROM message_attachment_join j "
        f"JOIN attachment a ON a.ROWID = j.attachment_id WHERE j.message_id IN ({placeholders(message_ids)})",
        message_ids,
    )
    found: dict = {}
    for row in rows:
        found.setdefault(row["message_id"], []).append(
            {
                "name": row["transfer_name"] or os.path.basename(row["filename"] or ""),
                "mime_type": row["mime_type"],
                "local_path": os.path.expanduser(row["filename"]) if row["filename"] else None,
            }
        )
    return found


def chat_participants(chat_ids, names, messages_db=None):
    if not chat_ids:
        return {}
    rows = query(
        messages_db or MESSAGES_DB,
        "SELECT j.chat_id, h.id FROM chat_handle_join j JOIN handle h ON h.ROWID = j.handle_id "
        f"WHERE j.chat_id IN ({placeholders(chat_ids)})",
        chat_ids,
    )
    participants: dict = {}
    for row in rows:
        participants.setdefault(row["chat_id"], []).append(display_handle(row["id"], names))
    return participants


def handles_matching(contact, names, messages_db=None):
    """Handle ROWIDs whose number/address or contact name contains ``contact``."""
    needle = contact.lower()
    digits = re.sub(r"\D", "", contact)
    matched = []
    for row in query(messages_db or MESSAGES_DB, "SELECT ROWID AS id, id AS handle FROM handle"):
        handle = row["handle"] or ""
        name = names.get(normalize_handle(handle), "")
        if (
            needle in handle.lower()
            or needle in name.lower()
            or (len(digits) >= 4 and digits in re.sub(r"\D", "", handle))
        ):
            matched.append(row["id"])
    return matched


def messages_list_chats(query_text="", max_results=30, messages_db=None, address_book_dir=None):
    """Conversations, most recently active first, with who is in them and the last message."""
    names = contact_names(address_book_dir)
    rows = query(
        messages_db or MESSAGES_DB,
        "SELECT c.ROWID AS id, c.display_name, c.chat_identifier, c.service_name, MAX(m.date) AS last_date, "
        "COUNT(m.ROWID) AS message_count FROM chat c JOIN chat_message_join j ON j.chat_id = c.ROWID "
        "JOIN message m ON m.ROWID = j.message_id GROUP BY c.ROWID ORDER BY last_date DESC",
    )
    participants = chat_participants([row["id"] for row in rows], names, messages_db)
    needle = query_text.lower()
    chats = []
    for row in rows:
        people = participants.get(row["id"], [display_handle(row["chat_identifier"], names)])
        title = row["display_name"] or ", ".join(people)
        if needle and needle not in title.lower() and not any(needle in person.lower() for person in people):
            continue
        chats.append(
            {
                "chat_id": row["id"],
                "title": title,
                "participants": people,
                "service": row["service_name"],
                "last_message_at": local_iso(from_messages_date(row["last_date"])),
                "message_count": row["message_count"],
            }
        )
        if len(chats) >= max(1, min(max_results, MAX_RESULTS)):
            break
    return chats


def _message_rows(where, params, limit, messages_db=None, newest_first=True):
    order = "DESC" if newest_first else "ASC"
    return query(
        messages_db or MESSAGES_DB,
        "SELECT m.ROWID AS id, m.date, m.text, m.attributedBody, m.is_from_me, m.cache_has_attachments, "
        "h.id AS handle, j.chat_id FROM message m LEFT JOIN handle h ON h.ROWID = m.handle_id "
        "LEFT JOIN chat_message_join j ON j.message_id = m.ROWID "
        f"WHERE m.associated_message_type = {PLAIN_MESSAGE_TYPE} AND {where} ORDER BY m.date {order} LIMIT ?",
        list(params) + [limit],
    )


def _serialize_messages(rows, names, messages_db=None):
    attachments = message_attachments([row["id"] for row in rows if row["cache_has_attachments"]], messages_db)
    return [
        {
            "message_id": row["id"],
            "chat_id": row["chat_id"],
            "date": local_iso(from_messages_date(row["date"])),
            "from": "me" if row["is_from_me"] else display_handle(row["handle"] or "", names),
            "text": message_text(row),
            **({"attachments": attachments[row["id"]]} if row["id"] in attachments else {}),
        }
        for row in rows
    ]


def _date_clauses(since, until):
    clauses, params = [], []
    if since:
        clauses.append("m.date >= ?")
        params.append(int(to_apple_seconds(parse_moment(since)) * 1e9))
    if until:
        clauses.append("m.date < ?")
        params.append(int(to_apple_seconds(parse_moment(until, end_of_day=True)) * 1e9))
    return clauses, params


def messages_get_chat(chat_id, since="", until="", max_results=100, messages_db=None, address_book_dir=None):
    """One conversation's messages in the window, oldest first (the last ``max_results`` of it)."""
    names = contact_names(address_book_dir)
    clauses, params = _date_clauses(since, until)
    where = " AND ".join(["j.chat_id = ?"] + clauses)
    limit = max(1, min(max_results, MAX_RESULTS * 4))
    rows = _message_rows(where, [int(chat_id)] + params, limit, messages_db)
    return _serialize_messages(list(reversed(rows)), names, messages_db)


def messages_search(
    query_text="", contact="", since="", until="", max_results=50, messages_db=None, address_book_dir=None
):
    """
    Messages matching text and/or a contact (name, number or address), newest
    first. Text is matched against both the plain column and the archived body
    newer macOS versions use instead.
    """
    names = contact_names(address_book_dir)
    clauses, params = _date_clauses(since, until)
    if contact:
        handles = handles_matching(contact, names, messages_db)
        if not handles:
            return []
        clauses.append(
            f"(m.handle_id IN ({placeholders(handles)}) OR j.chat_id IN (SELECT chat_id FROM chat_handle_join "
            f"WHERE handle_id IN ({placeholders(handles)})))"
        )
        params += handles + handles
    if query_text:
        # attributedBody is a blob holding the UTF-8 text; a byte search narrows, the decode below confirms
        clauses.append("(m.text LIKE ? OR (m.text IS NULL AND instr(lower(CAST(m.attributedBody AS TEXT)), ?) > 0))")
        params += [f"%{query_text}%", query_text.lower()]
    limit = max(1, min(max_results, MAX_RESULTS))
    rows = _message_rows(" AND ".join(clauses) or "1 = 1", params, limit * 2, messages_db)
    if query_text:
        rows = [row for row in rows if query_text.lower() in message_text(row).lower()]
    return _serialize_messages(rows[:limit], names, messages_db)


# %%
# Calendar #


def scoped_calendars(accounts, calendar_db=None):
    """
    Every calendar whose store belongs to one of the given accounts, keyed by
    Calendar ROWID. CalDAV scheduling inboxes and outboxes are left out: they
    hold invitations in transit, never events, and a Google account's inbox
    carries the same title as its main calendar.
    """
    rows = query(
        calendar_db or CALENDAR_DB,
        "SELECT c.ROWID AS id, c.UUID AS uuid, c.title, c.owner_identity_email AS owner, c.external_id AS path, "
        "c.self_identity_email AS self, s.external_id AS store_id, s.name AS store, s.last_sync_end AS synced "
        "FROM Calendar c JOIN Store s ON s.ROWID = c.store_id",
    )
    addresses = {account["name"]: account.get("address", "") for account in accounts}
    calendars = {}
    for row in rows:
        owner = owner_of(row["store_id"], accounts)
        if owner and not SCHEDULING_MAILBOX_PATTERN.search(row["path"] or ""):
            calendars[row["id"]] = {
                "calendar_id": row["uuid"],
                "title": row["title"],
                "account": owner,
                "store": row["store"],
                "owner": row["owner"],
                # when Calendar.app last finished syncing this account; a stalled sync means stale reads and
                # writes that never leave this Mac
                "last_synced": local_iso(from_apple_seconds(row["synced"])) if row["synced"] else None,
                "_rowid": row["id"],
                "_store_id": row["store_id"],
                # the addresses that are you on this calendar, for finding your attendee row
                "_me": {address.lower() for address in (addresses[owner], row["self"], row["owner"]) if address},
            }
    return calendars


def calendar_list_calendars(accounts, calendar_db=None):
    return sorted(
        (
            {key: value for key, value in cal.items() if not key.startswith("_")}
            for cal in scoped_calendars(accounts, calendar_db).values()
        ),
        key=lambda cal: (cal["account"], cal["title"].lower()),
    )


def calendar_by_id(calendars, calendar_id):
    for cal in calendars.values():
        if cal["calendar_id"] == calendar_id:
            return cal
    raise ValueError(f"no calendar {calendar_id} in these accounts - calendar_list_calendars lists them")


EVENT_COLUMNS = (
    "ci.ROWID AS rowid, ci.UUID AS uid, ci.unique_identifier AS ical_uid, ci.summary, ci.all_day, ci.start_date, "
    "ci.end_date, ci.calendar_id, ci.status, ci.has_recurrences, ci.orig_item_id, "
    "ci.has_attendees, ci.conference_url, ci.start_tz, l.title AS location"
)


def _event_zone(row):
    """The zone a timed event's wall clock lives in; floating ones follow this Mac."""
    name = row["start_tz"]
    if name and not name.startswith("_"):
        try:
            return ZoneInfo(name)
        except (KeyError, ValueError):
            pass
    return datetime.now().astimezone().tzinfo


def _all_day_date(seconds):
    """An all-day item stores its date as that day's UTC midnight (inclusive 23:59:59 end)."""
    return from_apple_seconds(seconds).date()


def _all_day_span(row):
    return max(1, round((row["end_date"] - row["start_date"]) / 86400))


def _single_window(row):
    """(start, end) of a non-recurring item: plain dates with an exclusive end for all-day, instants otherwise."""
    if row["all_day"]:
        first = _all_day_date(row["start_date"])
        return first, first + timedelta(days=_all_day_span(row))
    return from_apple_seconds(row["start_date"]), from_apple_seconds(row["end_date"])


def _weekday(token):
    """'0TU' every Tuesday, '+2MO' the second Monday, '-1FR' the last Friday."""
    ordinal, day = token[:-2], token[-2:]
    weekday = RRULE_WEEKDAYS[day]
    return weekday(int(ordinal)) if ordinal and int(ordinal) else weekday


def parse_specifier(specifier):
    """
    Recurrence.specifier -> rrule keyword arguments. It is RFC 5545's BY*
    parts in Calendar's own spelling, ';'-separated: D= weekdays with an
    ordinal, M= days of the month, O= months, S= set positions, Y= days of the
    year, W= weeks of the year. Anything else is refused rather than guessed.
    """
    kwargs: dict = {}
    for token in (specifier or "").split(";"):
        if not token:
            continue
        key, _, values = token.partition("=")
        items = [item for item in values.split(",") if item]
        if key == "D":
            kwargs["byweekday"] = [_weekday(item) for item in items]
        elif key in SPECIFIER_KEYS:
            kwargs[SPECIFIER_KEYS[key]] = [int(item) for item in items]
        else:
            raise ValueError(f"unknown recurrence specifier '{token}'")
    return kwargs


def expand_series(row, rule, skipped, window_start, window_end):
    """
    The (start, end) occurrences of one recurring series that overlap the
    window. Timed series recur on the wall clock of their own zone, so a 9:00
    meeting stays at 9:00 across a DST change. ``skipped`` holds the original
    starts (Apple seconds) of deleted or detached occurrences; a detached one
    is its own CalendarItem and is found by the single-event query.
    """
    all_day = bool(row["all_day"])
    if all_day:
        dtstart = datetime.combine(_all_day_date(row["start_date"]), datetime.min.time())
        length = timedelta(days=_all_day_span(row))
        until = datetime.combine(_all_day_date(rule["end_date"]), datetime.max.time()) if rule["end_date"] else None
        lower = datetime.combine(window_start.astimezone().date(), datetime.min.time())
        upper = datetime.combine(_window_days(window_start, window_end)[1], datetime.min.time())
        skipped_days = {_all_day_date(value) for value in skipped}
    else:
        zone = _event_zone(row)
        dtstart = from_apple_seconds(row["start_date"]).astimezone(zone)
        length = timedelta(seconds=row["end_date"] - row["start_date"])
        until = from_apple_seconds(rule["end_date"]).astimezone(zone) if rule["end_date"] else None
        lower, upper = window_start, window_end
        skipped_seconds = {round(value) for value in skipped}
    series = rrule.rruleset()
    series.rrule(
        rrule.rrule(
            RRULE_FREQUENCY[rule["frequency"]],
            dtstart=dtstart,
            interval=rule["interval"] or 1,
            wkst=RRULE_WEEK_START.get(rule["week_start"] or 0),
            count=rule["count"] or None,
            until=until,
            **parse_specifier(rule["specifier"]),
        )
    )
    # RFC 5545: DTSTART is always the first instance, even when the rule would not produce it
    series.rdate(dtstart)
    occurrences = []
    for start in series.between(lower - length, upper, inc=False):
        end = start + length
        if all_day:
            if start.date() in skipped_days:
                continue
            occurrences.append((start.date(), end.date()))
        else:
            start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
            if round(to_apple_seconds(start)) in skipped_seconds:
                continue
            occurrences.append((start, end))
    return occurrences


def _skipped_occurrences(path, master_ids):
    """Per series: the original starts of occurrences deleted (ExceptionDate) or detached (orig_date)."""
    if not master_ids:
        return {}
    skipped: dict = {}
    for row in query(
        path, f"SELECT owner_id, date FROM ExceptionDate WHERE owner_id IN ({placeholders(master_ids)})", master_ids
    ) + query(
        path,
        "SELECT orig_item_id AS owner_id, orig_date AS date FROM CalendarItem "
        f"WHERE orig_item_id IN ({placeholders(master_ids)}) AND orig_date IS NOT NULL",
        master_ids,
    ):
        skipped.setdefault(row["owner_id"], set()).add(row["date"])
    return skipped


def _participation(path, rowids, calendars):
    """
    rowid -> who is on that item: ``response`` is your answer (the status on
    your attendee row, "organizer" when the organizer row is you, "unknown"
    when you are listed under no known address), ``attendees_listed`` counts the
    attendee rows and ``organizer`` is the organizer's address. An item with no
    participant rows is absent. A hidden guest list shows up as you being the
    only attendee listed - the shape of a broadcast invite to a big event.
    """
    if not rowids:
        return {}
    rows = query(
        path,
        "SELECT p.owner_id, p.entity_type, p.status, lower(p.email) AS email, ci.calendar_id FROM Participant p "
        f"JOIN CalendarItem ci ON ci.ROWID = p.owner_id WHERE p.owner_id IN ({placeholders(rowids)}) "
        f"AND p.entity_type IN ({ATTENDEE_ENTITY}, {ORGANIZER_ENTITY})",
        list(rowids),
    )
    found: dict = {}
    for row in rows:
        item = found.setdefault(row["owner_id"], {"response": None, "attendees_listed": 0, "organizer": None})
        me = calendars[row["calendar_id"]]["_me"] if row["calendar_id"] in calendars else set()
        if row["entity_type"] == ATTENDEE_ENTITY:
            item["attendees_listed"] += 1
        else:
            item["organizer"] = row["email"]
        if row["email"] not in me:
            item["response"] = item["response"] or "unknown"
        elif row["entity_type"] == ATTENDEE_ENTITY:
            item["response"] = PARTICIPANT_STATUS.get(row["status"] or 0, "unknown")
        elif item["response"] in (None, "unknown"):
            item["response"] = "organizer"
    return found


def _serialize_occurrence(row, calendars, start, end, participation=None):
    cal = calendars[row["calendar_id"]]
    all_day = bool(row["all_day"])
    return {
        "event_id": row["uid"],
        "ical_uid": row["ical_uid"],
        "calendar_id": cal["calendar_id"],
        "calendar": cal["title"],
        "account": cal["account"],
        "title": row["summary"],
        "start": start.isoformat() if all_day else local_iso(start),
        "end": end.isoformat() if all_day else local_iso(end),
        "all_day": all_day,
        **({"end_is_exclusive": True} if all_day else {}),
        "location": row["location"],
        "response": (participation or {}).get("response"),
        "attendees_listed": (participation or {}).get("attendees_listed", 0),
        "organizer": (participation or {}).get("organizer"),
        "recurring": bool(row["has_recurrences"] or row["orig_item_id"]),
        "has_attendees": bool(row["has_attendees"]),
        "conference_url": row["conference_url"],
    }


def calendar_events(accounts, window_start, window_end, query_text="", calendar_id="", calendar_db=None):
    """
    Every event occurrence overlapping [window_start, window_end), sorted.

    Single events (including detached occurrences of a series) come straight
    from CalendarItem. Recurring series are expanded here from their stored
    rule: Calendar.app's own OccurrenceCache is too sparse to trust.
    """
    path = calendar_db or CALENDAR_DB
    calendars = scoped_calendars(accounts, path)
    if calendar_id:
        calendars = {cal["_rowid"]: cal for cal in [calendar_by_id(calendars, calendar_id)]}
    if not calendars:
        return []
    ids = list(calendars)
    text_clause, text_params = "", []
    if query_text:
        text_clause = " AND (ci.summary LIKE ? OR ci.description LIKE ? OR l.title LIKE ?)"
        text_params = [f"%{query_text}%"] * 3
    lower, upper = to_apple_seconds(window_start), to_apple_seconds(window_end)
    base = (
        f"SELECT {EVENT_COLUMNS} FROM CalendarItem ci LEFT JOIN Location l ON l.ROWID = ci.location_id "
        f"WHERE ci.entity_type = {EVENT_ENTITY} AND ci.calendar_id IN ({placeholders(ids)}) "
    )
    # all-day items store UTC-midnight dates, so pad the SQL window a day each side and filter exactly below
    single = query(
        path,
        base + f"AND ci.has_recurrences = 0 AND ci.start_date < ? AND ci.end_date > ?{text_clause}",
        ids + [upper + 86400, lower - 86400] + text_params,
    )
    masters = query(
        path,
        base + f"AND ci.has_recurrences = 1 AND ci.start_date < ?{text_clause}",
        ids + [upper + 86400] + text_params,
    )
    master_ids = [row["rowid"] for row in masters]
    rules: dict = {}
    if master_ids:
        for rule in query(
            path,
            "SELECT owner_id, frequency, interval, week_start, count, end_date, specifier FROM Recurrence "
            f"WHERE owner_id IN ({placeholders(master_ids)})",
            master_ids,
        ):
            rules.setdefault(rule["owner_id"], []).append(rule)
    skipped = _skipped_occurrences(path, master_ids)
    first_day, last_day = _window_days(window_start, window_end)
    participation = _participation(path, [row["rowid"] for row in list(single) + list(masters)], calendars)
    events, seen = [], set()
    for row in single:
        start, end = _single_window(row)
        if row["all_day"]:
            overlaps = start < last_day and end > first_day
        else:
            overlaps = start < window_end and end > window_start
        if overlaps:
            events.append(_serialize_occurrence(row, calendars, start, end, participation.get(row["rowid"])))
    for row in masters:
        for rule in rules.get(row["rowid"], []):
            if rule["end_date"] and rule["end_date"] < lower - 86400:
                continue
            for start, end in expand_series(row, rule, skipped.get(row["rowid"], set()), window_start, window_end):
                key = (row["rowid"], str(start))
                if key not in seen:
                    seen.add(key)
                    events.append(_serialize_occurrence(row, calendars, start, end, participation.get(row["rowid"])))
    events.sort(key=lambda event: (_sort_key(event), event["title"] or ""))
    return events


def _window_days(window_start, window_end):
    """The local calendar days a window touches, as [first, last) for comparing all-day events."""
    local_end = window_end.astimezone()
    last_day = local_end.date() + timedelta(days=0 if local_end.time() == datetime.min.time() else 1)
    return window_start.astimezone().date(), last_day


def _sort_key(event):
    start = event["start"]
    if event["all_day"]:
        return datetime.combine(date.fromisoformat(start), datetime.min.time()).astimezone()
    return datetime.fromisoformat(start)


def calendar_get_event(accounts, event_id, calendar_id="", calendar_db=None):
    """
    Full detail for one event: notes, organizer, attendees. ``event_id`` is the
    per-item UUID, which is also what Calendar.app's AppleScript calls an
    event's uid - the iCal UID (``ical_uid``) is shared by a series and its
    detached occurrences, so it cannot address one item. An occurrence of a
    series carries the series' id, so this returns the series.
    """
    path = calendar_db or CALENDAR_DB
    calendars = scoped_calendars(accounts, path)
    ids = list(calendars)
    if not ids:
        raise ValueError(f"no event {event_id} in these accounts")
    rows = query(
        path,
        f"SELECT {EVENT_COLUMNS}, ci.description, ci.url, ci.organizer_id, ci.last_modified, ci.creation_date "
        "FROM CalendarItem ci LEFT JOIN Location l ON l.ROWID = ci.location_id "
        f"WHERE ci.UUID = ? AND ci.calendar_id IN ({placeholders(ids)})",
        [event_id] + ids,
    )
    if calendar_id:
        rows = [row for row in rows if calendars[row["calendar_id"]]["calendar_id"] == calendar_id]
    if not rows:
        raise ValueError(f"no event {event_id} in these accounts")
    row = rows[0]
    start, end = _single_window(row)
    event = _serialize_occurrence(
        row, calendars, start, end, _participation(path, [row["rowid"]], calendars).get(row["rowid"])
    )
    me = calendars[row["calendar_id"]]["_me"]
    people = query(
        path,
        "SELECT p.entity_type, p.status, p.role, p.email, p.is_self, i.display_name FROM Participant p "
        "LEFT JOIN Identity i ON i.rowid = p.identity_id WHERE p.owner_id = ? ORDER BY p.ROWID",
        (row["rowid"],),
    )
    organizer = next((person for person in people if person["entity_type"] == ORGANIZER_ENTITY), None)
    event.update(
        description=row["description"],
        url=row["url"],
        created=local_iso(from_apple_seconds(row["creation_date"])) if row["creation_date"] else None,
        last_modified=local_iso(from_apple_seconds(row["last_modified"])) if row["last_modified"] else None,
        organizer=format_address(organizer["email"], organizer["display_name"]) if organizer else None,
        attendees=[
            {
                "name": person["display_name"],
                "email": person["email"],
                "response": PARTICIPANT_STATUS.get(person["status"] or 0, "unknown"),
                "role": PARTICIPANT_ROLE.get(person["role"] or 0),
                "is_self": (person["email"] or "").lower() in me,
            }
            for person in people
            if person["entity_type"] == ATTENDEE_ENTITY
        ],
        detached_occurrences=query(
            path, "SELECT COUNT(*) AS n FROM CalendarItem WHERE orig_item_id = ?", (row["rowid"],)
        )[0]["n"],
    )
    return event


# %%
# Calendar writes (Calendar.app over AppleScript) #

# Writes go through Calendar.app rather than its database: the app owns the
# sync to Exchange / Google / iCloud, and its AppleScript addresses calendars
# and events by the same UUID / UID the database readers above return. Values
# travel as argv, never spliced into the script. Dates are built from local
# wall-clock parts because AppleScript dates have no time zone.
APPLESCRIPT_PRELUDE = """
on makeDate(parts)
    set {y, mo, d, h, mi} to parts
    set theDate to current date
    set day of theDate to 1
    set year of theDate to y as integer
    set month of theDate to mo as integer
    set day of theDate to d as integer
    set time of theDate to (h as integer) * 3600 + (mi as integer) * 60
    return theDate
end makeDate

on splitParts(value)
    set AppleScript's text item delimiters to " "
    set parts to text items of value
    set AppleScript's text item delimiters to ""
    return parts
end splitParts
"""

CREATE_SCRIPT = (
    APPLESCRIPT_PRELUDE
    + """
on run argv
    set {calId, theSummary, startParts, endParts, allDay, theLocation, theNotes, theUrl} to argv
    set startDate to my makeDate(my splitParts(startParts))
    set endDate to my makeDate(my splitParts(endParts))
    tell application "Calendar"
        tell calendar id calId
            set props to {summary:theSummary, start date:startDate, end date:endDate, allday event:(allDay is "true")}
            set newEvent to make new event at end of events with properties props
            if theLocation is not "" then set location of newEvent to theLocation
            if theNotes is not "" then set description of newEvent to theNotes
            if theUrl is not "" then set url of newEvent to theUrl
            return uid of newEvent
        end tell
    end tell
end run
"""
)

UPDATE_SCRIPT = (
    APPLESCRIPT_PRELUDE
    + """
on run argv
    set {calId, eventId, theSummary, startParts, endParts, allDay, theLocation, theNotes, theUrl} to argv
    tell application "Calendar"
        set theEvent to event id eventId of calendar id calId
        if allDay is not "" then set allday event of theEvent to (allDay is "true")
        if startParts is not "" then set start date of theEvent to my makeDate(my splitParts(startParts))
        if endParts is not "" then set end date of theEvent to my makeDate(my splitParts(endParts))
        if theSummary is not "" then set summary of theEvent to theSummary
        if theLocation is not "" then set location of theEvent to theLocation
        if theNotes is not "" then set description of theEvent to theNotes
        if theUrl is not "" then set url of theEvent to theUrl
        return uid of theEvent
    end tell
end run
"""
)

DELETE_SCRIPT = """
on run argv
    set {calId, eventId} to argv
    tell application "Calendar"
        delete event id eventId of calendar id calId
    end tell
    return eventId
end run
"""


def run_osascript(script, args):
    require_macos()
    completed = subprocess.run(
        ["osascript", "-", *args],
        input=script,
        capture_output=True,
        text=True,
        timeout=OSASCRIPT_TIMEOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Calendar.app refused: {completed.stderr.strip()}")
    return completed.stdout.strip()


def date_parts(value):
    """
    An API time -> (all_day, "Y M D h m") in local wall-clock time. YYYY-MM-DD
    is all-day; its end is exclusive, as in the Google tools, so it is passed
    through as that day's midnight.
    """
    if len(value) == 10:
        day = date.fromisoformat(value)
        return True, f"{day.year} {day.month} {day.day} 0 0"
    moment = datetime.fromisoformat(value)
    local = moment.astimezone() if moment.tzinfo else moment
    return False, f"{local.year} {local.month} {local.day} {local.hour} {local.minute}"


def _write_guard(accounts, event_id, calendar_id, calendar_db=None):
    """
    Update and delete touch only your own single events. A meeting with
    attendees belongs to its organizer's mail flow and a series edit moves
    every occurrence - both are refused rather than half-done over AppleScript.
    """
    event = calendar_get_event(accounts, event_id, calendar_id=calendar_id, calendar_db=calendar_db)
    if event["has_attendees"]:
        raise ValueError(f"'{event['title']}' has attendees - change meetings in the account's own client")
    if event["recurring"]:
        raise ValueError(f"'{event['title']}' is part of a recurring series - change series in Calendar.app")
    return event


def calendar_create_event(
    accounts, calendar_id, summary, start, end, location="", description="", url="", calendar_db=None
):
    calendar_by_id(scoped_calendars(accounts, calendar_db), calendar_id)
    start_all_day, start_parts = date_parts(start)
    end_all_day, end_parts = date_parts(end)
    if start_all_day != end_all_day:
        raise ValueError("start and end must both be dates (all-day) or both be timestamps")
    uid = run_osascript(
        CREATE_SCRIPT,
        [
            calendar_id,
            summary,
            start_parts,
            end_parts,
            "true" if start_all_day else "false",
            location,
            description,
            url,
        ],
    )
    return {"event_id": uid, "calendar_id": calendar_id, "summary": summary, "start": start, "end": end}


def calendar_update_event(
    accounts, event_id, calendar_id, summary="", start="", end="", location="", description="", url="", calendar_db=None
):
    _write_guard(accounts, event_id, calendar_id, calendar_db)
    all_day, start_parts, end_parts = "", "", ""
    if start:
        is_all_day, start_parts = date_parts(start)
        all_day = "true" if is_all_day else "false"
    if end:
        _, end_parts = date_parts(end)
    uid = run_osascript(
        UPDATE_SCRIPT, [calendar_id, event_id, summary, start_parts, end_parts, all_day, location, description, url]
    )
    return {"event_id": uid, "calendar_id": calendar_id, "updated": True}


def calendar_delete_event(accounts, event_id, calendar_id, calendar_db=None):
    event = _write_guard(accounts, event_id, calendar_id, calendar_db)
    run_osascript(DELETE_SCRIPT, [calendar_id, event_id])
    return {"event_id": event_id, "calendar_id": calendar_id, "deleted": event["title"]}


# %%
