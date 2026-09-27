# %%
# Imports #

import sqlite3
import time
from datetime import date, datetime, timedelta, timezone

import config_test_utils  # noqa F401
import pytest

from utils import macmcp_tools as mtools

# %%
# Helpers #

ACME_ID = "AAAA-ACME-ROOT"
ACME_IMAP_ID = "AAAA-ACME-IMAP"
ACME_CALDAV_ID = "AAAA-ACME-CALDAV"
HOME_ID = "BBBB-HOME-ROOT"
HOME_IMAP_ID = "BBBB-HOME-IMAP"


def apple_seconds(moment):
    return (moment - mtools.APPLE_EPOCH).total_seconds()


def build(path, script, rows=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(script)
    for sql, values in rows:
        connection.execute(sql, values)
    connection.commit()
    connection.close()
    return str(path)


@pytest.fixture(autouse=True)
def central_time(monkeypatch):
    """Local-time output and all-day windows depend on the zone; pin one with a DST change in it."""
    monkeypatch.setenv("TZ", "America/Chicago")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.fixture
def accounts_db(tmp_path):
    return build(
        tmp_path / "Accounts4.sqlite",
        """
        CREATE TABLE ZACCOUNTTYPE (Z_PK INTEGER PRIMARY KEY, ZACCOUNTTYPEDESCRIPTION TEXT);
        CREATE TABLE ZACCOUNT (Z_PK INTEGER PRIMARY KEY, ZIDENTIFIER TEXT, ZPARENTACCOUNT INTEGER,
            ZUSERNAME TEXT, ZACCOUNTDESCRIPTION TEXT, ZACCOUNTTYPE INTEGER);
        INSERT INTO ZACCOUNTTYPE VALUES (1, 'Gmail'), (2, 'IMAP'), (3, 'CalDAV'), (4, 'Exchange');
        """,
        [
            ("INSERT INTO ZACCOUNT VALUES (?, ?, ?, ?, ?, ?)", (1, ACME_ID, None, "Me@Acme.com", "Acme", 1)),
            ("INSERT INTO ZACCOUNT VALUES (?, ?, ?, ?, ?, ?)", (2, ACME_IMAP_ID, 1, None, None, 2)),
            ("INSERT INTO ZACCOUNT VALUES (?, ?, ?, ?, ?, ?)", (3, "AAAA-ACME-CALPARENT", 1, None, None, 3)),
            ("INSERT INTO ZACCOUNT VALUES (?, ?, ?, ?, ?, ?)", (4, ACME_CALDAV_ID, 3, "me@acme.com", None, 3)),
            ("INSERT INTO ZACCOUNT VALUES (?, ?, ?, ?, ?, ?)", (5, HOME_ID, None, "me@home.test", "Home", 1)),
            ("INSERT INTO ZACCOUNT VALUES (?, ?, ?, ?, ?, ?)", (6, HOME_IMAP_ID, 5, None, None, 2)),
        ],
    )


def scope(accounts_db, *names):
    entries = {
        "acme": {"name": "acme", "type": "internet_account", "address": "me@acme.com"},
        "home": {"name": "home", "type": "internet_account", "address": "me@home.test"},
    }
    return mtools.resolve_scope([dict(entries[name]) for name in names], accounts_db)


# %%
# Account config #


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_load_accounts_reads_internet_accounts_and_messages(tmp_path):
    config = _write(
        tmp_path / "acme_credentials" / "acme_macaccounts.yaml",
        "- name: acme\n  type: internet_account\n  address: me@acme.com\n- name: texts\n  type: messages\n",
    )
    accounts, paths = mtools.load_accounts(str(tmp_path))
    assert [account["name"] for account in accounts] == ["acme", "texts"]
    assert paths == [str(config)]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("- name: acme\n  type: internet_account\n", "missing address"),
        ("- name: acme\n  type: carrier_pigeon\n", "unknown type"),
        ("- type: messages\n", "needs both name and type"),
        ("name: acme\n", "expected a list"),
    ],
)
def test_parse_account_config_rejects_bad_entries(tmp_path, body, message):
    config = _write(tmp_path / "acme_macaccounts.yaml", body)
    with pytest.raises(ValueError, match=message):
        mtools.parse_account_config(str(config))


def test_duplicate_names_across_configs_are_refused(tmp_path):
    entry = "- name: shared\n  type: messages\n"
    _write(tmp_path / "acme_credentials" / "acme_macaccounts.yaml", entry)
    _write(tmp_path / "home_credentials" / "home_macaccounts.yaml", entry)
    with pytest.raises(ValueError, match="Duplicate"):
        mtools.load_accounts(str(tmp_path))


# %%
# Internet Accounts #


def test_resolve_scope_walks_child_accounts_up_to_the_named_address(accounts_db):
    (acme,) = scope(accounts_db, "acme")
    # the CalDAV grandchild and the IMAP child both belong to the acme root, case-insensitively
    assert {ACME_ID, ACME_IMAP_ID, ACME_CALDAV_ID} <= acme["_identifiers"]
    assert HOME_IMAP_ID not in acme["_identifiers"]


def test_an_address_signed_in_nowhere_reaches_nothing(accounts_db):
    entry = {"name": "ghost", "type": "internet_account", "address": "nobody@nowhere.test"}
    (ghost,) = mtools.resolve_scope([entry], accounts_db)
    assert ghost["_identifiers"] == set()
    assert mtools.owner_of(ACME_IMAP_ID, [ghost]) is None


# %%
# Mail #

RECEIVED = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def mail_root(tmp_path):
    root = tmp_path / "Mail"
    build(
        root / "V10" / "MailData" / "Envelope Index",
        """
        CREATE TABLE mailboxes (ROWID INTEGER PRIMARY KEY, url TEXT, source INTEGER, total_count INTEGER,
            unread_count INTEGER);
        CREATE TABLE subjects (ROWID INTEGER PRIMARY KEY, subject TEXT);
        CREATE TABLE addresses (ROWID INTEGER PRIMARY KEY, address TEXT, comment TEXT);
        CREATE TABLE summaries (ROWID INTEGER PRIMARY KEY, summary TEXT);
        CREATE TABLE messages (ROWID INTEGER PRIMARY KEY, global_message_id INTEGER, mailbox INTEGER,
            date_received INTEGER, read INTEGER, flagged INTEGER, deleted INTEGER, subject_prefix TEXT,
            subject INTEGER, sender INTEGER, summary INTEGER);
        CREATE TABLE recipients (ROWID INTEGER PRIMARY KEY, message INTEGER, address INTEGER, type INTEGER,
            position INTEGER);
        CREATE TABLE labels (message_id INTEGER, mailbox_id INTEGER);
        """,
        [
            (
                "INSERT INTO mailboxes VALUES (?, ?, ?, 0, 0)",
                (1, f"imap://{ACME_IMAP_ID}/%5BGmail%5D/All%20Mail", None),
            ),
            ("INSERT INTO mailboxes VALUES (?, ?, ?, 0, 0)", (2, f"imap://{ACME_IMAP_ID}/INBOX", 1)),
            ("INSERT INTO mailboxes VALUES (?, ?, ?, 0, 0)", (3, f"imap://{ACME_IMAP_ID}/%5BGmail%5D/Trash", None)),
            ("INSERT INTO mailboxes VALUES (?, ?, ?, 0, 0)", (4, f"imap://{HOME_IMAP_ID}/INBOX", None)),
            ("INSERT INTO subjects VALUES (?, ?)", (1, "Quarterly invoice")),
            ("INSERT INTO subjects VALUES (?, ?)", (2, "Old news")),
            ("INSERT INTO subjects VALUES (?, ?)", (3, "Home invoice")),
            ("INSERT INTO addresses VALUES (?, ?, ?)", (1, "billing@vendor.test", "Vendor Billing")),
            ("INSERT INTO addresses VALUES (?, ?, ?)", (2, "me@acme.com", "Me")),
            ("INSERT INTO summaries VALUES (?, ?)", (1, "Please find the invoice attached")),
            (
                "INSERT INTO messages VALUES (?, ?, ?, ?, 0, 1, 0, '', ?, ?, ?)",
                (1001, 50, 1, RECEIVED.timestamp(), 1, 1, 1),
            ),
            # the same message again in another folder of the same account - one result, not two
            (
                "INSERT INTO messages VALUES (?, ?, ?, ?, 0, 1, 0, '', ?, ?, ?)",
                (1002, 50, 1, RECEIVED.timestamp() - 1, 1, 1, 1),
            ),
            (
                "INSERT INTO messages VALUES (?, ?, ?, ?, 1, 0, 0, 'Re: ', ?, ?, NULL)",
                (1003, 51, 3, RECEIVED.timestamp() - 60, 2, 1),
            ),
            (
                "INSERT INTO messages VALUES (?, ?, ?, ?, 0, 0, 0, '', ?, ?, NULL)",
                (1004, 52, 4, RECEIVED.timestamp(), 3, 1),
            ),
            ("INSERT INTO recipients VALUES (?, ?, ?, ?, ?)", (1, 1001, 2, 0, 0)),
            ("INSERT INTO labels VALUES (?, ?)", (1001, 2)),
        ],
    )
    raw = (
        b"From: Vendor Billing <billing@vendor.test>\r\nTo: Me <me@acme.com>\r\nSubject: Quarterly invoice\r\n"
        b"Message-ID: <inv-1@vendor.test>\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
        b"<html><body><p>Total due: <b>$40</b></p><p>Thanks</p></body></html>\r\n"
    )
    messages_dir = root / "V10" / ACME_IMAP_ID / "[Gmail].mbox" / "All Mail.mbox" / "STORE" / "Data" / "1" / "Messages"
    messages_dir.mkdir(parents=True)
    (messages_dir / "1001.emlx").write_bytes(str(len(raw)).encode() + b"\n" + raw + b"<?xml plist?>")
    return str(root)


def test_mail_search_stays_inside_the_scoped_accounts(accounts_db, mail_root):
    results = mtools.mail_search(scope(accounts_db, "acme"), query_text="invoice", mail_root=mail_root)
    assert [result["message_id"] for result in results] == [1001]
    assert results[0]["account"] == "acme"
    assert results[0]["mailbox"] == "[Gmail]/All Mail"
    assert results[0]["labels"] == ["INBOX"]
    assert results[0]["to"] == ["Me <me@acme.com>"]


def test_mail_search_skips_trash_unless_asked(accounts_db, mail_root):
    acme = scope(accounts_db, "acme")
    assert 1003 not in [result["message_id"] for result in mtools.mail_search(acme, mail_root=mail_root)]
    with_trash = mtools.mail_search(acme, include_spam_trash=True, mail_root=mail_root)
    assert 1003 in [result["message_id"] for result in with_trash]


def test_mail_search_filters_by_gmail_label(accounts_db, mail_root):
    results = mtools.mail_search(scope(accounts_db, "acme"), mailbox="INBOX", mail_root=mail_root)
    assert [result["message_id"] for result in results] == [1001]


def test_mail_search_rejects_an_unknown_mailbox(accounts_db, mail_root):
    with pytest.raises(ValueError, match="no mailbox"):
        mtools.mail_search(scope(accounts_db, "acme"), mailbox="Nope", mail_root=mail_root)


def test_mail_get_message_reads_the_emlx_body(accounts_db, mail_root):
    message = mtools.mail_get_message(scope(accounts_db, "acme"), 1001, mail_root=mail_root)
    assert message["body_is_preview_only"] is False
    assert "Total due: $40" in message["body"]
    assert "<b>" not in message["body"]
    assert message["message_id_header"] == "<inv-1@vendor.test>"


def test_mail_get_message_falls_back_to_the_preview_without_a_file(accounts_db, mail_root):
    message = mtools.mail_get_message(scope(accounts_db, "acme"), 1002, mail_root=mail_root)
    assert message["body_is_preview_only"] is True
    assert message["body"] == "Please find the invoice attached"


def test_mail_get_message_refuses_another_contexts_message(accounts_db, mail_root):
    with pytest.raises(ValueError, match="no message 1004"):
        mtools.mail_get_message(scope(accounts_db, "acme"), 1004, mail_root=mail_root)


def test_emlx_path_spreads_thousands_digits_reversed(tmp_path):
    folder = tmp_path / "ACCT" / "[Gmail].mbox" / "All Mail.mbox" / "STORE" / "Data" / "6" / "0" / "5" / "Messages"
    folder.mkdir(parents=True)
    (folder / "506862.partial.emlx").write_text("")
    found = mtools.emlx_candidates(str(tmp_path), "ACCT", "[Gmail]/All Mail", 506862)
    assert found == [str(folder / "506862.partial.emlx")]


# %%
# Messages #


def archived(text):
    """An attributedBody blob shaped like the ones Messages writes."""
    encoded = text.encode("utf-8")
    if len(encoded) < 0x80:
        length = bytes([len(encoded)])
    else:
        length = b"\x81" + len(encoded).to_bytes(2, "little")
    return (
        b"\x04\x0bstreamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84\x12NSAttributedString\x00\x84\x84\x08NSObject\x00"
        b"\x85\x92\x84\x84\x84\x08NSString\x01\x94\x84\x01+" + length + encoded + b"\x86\x84\x02iI\x01"
    )


def test_decode_attributed_body_short_and_long():
    assert mtools.decode_attributed_body(archived("see you at 6")) == "see you at 6"
    long_text = "word " * 60
    assert mtools.decode_attributed_body(archived(long_text)) == long_text
    assert mtools.decode_attributed_body(None) == ""
    assert mtools.decode_attributed_body(b"no archive here") == ""


SENT = datetime(2026, 9, 25, 18, 0, tzinfo=timezone.utc)


@pytest.fixture
def messages_db(tmp_path):
    nanoseconds = int(apple_seconds(SENT) * 1e9)
    return build(
        tmp_path / "chat.db",
        """
        CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT);
        CREATE TABLE chat (ROWID INTEGER PRIMARY KEY, display_name TEXT, chat_identifier TEXT, service_name TEXT);
        CREATE TABLE message (ROWID INTEGER PRIMARY KEY, date INTEGER, text TEXT, attributedBody BLOB,
            is_from_me INTEGER, cache_has_attachments INTEGER, handle_id INTEGER, associated_message_type INTEGER);
        CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);
        CREATE TABLE chat_handle_join (chat_id INTEGER, handle_id INTEGER);
        CREATE TABLE attachment (ROWID INTEGER PRIMARY KEY, transfer_name TEXT, filename TEXT, mime_type TEXT);
        CREATE TABLE message_attachment_join (message_id INTEGER, attachment_id INTEGER);
        INSERT INTO handle VALUES (1, '+15125550100');
        INSERT INTO chat VALUES (7, '', '+15125550100', 'iMessage');
        INSERT INTO chat_handle_join VALUES (7, 1);
        INSERT INTO attachment VALUES (1, 'menu.jpg', '~/Library/Messages/Attachments/menu.jpg', 'image/jpeg');
        INSERT INTO message_attachment_join VALUES (3, 1);
        INSERT INTO chat_message_join VALUES (7, 1), (7, 2), (7, 3), (7, 4);
        """,
        [
            ("INSERT INTO message VALUES (1, ?, 'Dinner at 7?', NULL, 0, 0, 1, 0)", (nanoseconds,)),
            ("INSERT INTO message VALUES (2, ?, NULL, ?, 1, 0, 0, 0)", (nanoseconds + 10**9, archived("dinner works"))),
            ("INSERT INTO message VALUES (3, ?, ?, NULL, 0, 1, 1, 0)", (nanoseconds + 2 * 10**9, "￼")),
            # a tapback is its own row and is not a message
            (
                "INSERT INTO message VALUES (4, ?, 'Loved “dinner works”', NULL, 0, 0, 1, 2000)",
                (nanoseconds + 3 * 10**9,),
            ),
        ],
    )


@pytest.fixture
def address_book(tmp_path):
    root = tmp_path / "AddressBook"
    build(
        root / "Sources" / "SRC" / mtools.ADDRESS_BOOK_NAME,
        """
        CREATE TABLE ZABCDRECORD (Z_PK INTEGER PRIMARY KEY, ZFIRSTNAME TEXT, ZLASTNAME TEXT, ZORGANIZATION TEXT,
            ZNICKNAME TEXT);
        CREATE TABLE ZABCDPHONENUMBER (Z_PK INTEGER PRIMARY KEY, ZOWNER INTEGER, ZFULLNUMBER TEXT);
        CREATE TABLE ZABCDEMAILADDRESS (Z_PK INTEGER PRIMARY KEY, ZOWNER INTEGER, ZADDRESS TEXT);
        INSERT INTO ZABCDRECORD VALUES (1, 'Pat', 'Doe', NULL, NULL);
        INSERT INTO ZABCDPHONENUMBER VALUES (1, 1, '(512) 555-0100');
        """,
    )
    mtools._contact_cache.clear()
    return str(root)


def test_messages_search_reads_plain_and_archived_text(messages_db, address_book):
    results = mtools.messages_search(query_text="DINNER", messages_db=messages_db, address_book_dir=address_book)
    assert [(result["message_id"], result["text"]) for result in results] == [(2, "dinner works"), (1, "Dinner at 7?")]
    assert results[0]["from"] == "me"
    assert results[1]["from"] == "Pat Doe (+15125550100)"


def test_messages_search_by_contact_name(messages_db, address_book):
    results = mtools.messages_search(contact="pat", messages_db=messages_db, address_book_dir=address_book)
    assert {result["message_id"] for result in results} == {1, 2, 3}


def test_messages_get_chat_is_oldest_first_with_attachments(messages_db, address_book):
    messages = mtools.messages_get_chat(7, messages_db=messages_db, address_book_dir=address_book)
    assert [message["message_id"] for message in messages] == [1, 2, 3]
    assert messages[0]["date"] == SENT.astimezone().isoformat()
    assert messages[2]["text"] == ""
    assert messages[2]["attachments"][0]["name"] == "menu.jpg"


def test_messages_list_chats_names_participants(messages_db, address_book):
    (chat,) = mtools.messages_list_chats(messages_db=messages_db, address_book_dir=address_book)
    assert chat["title"] == "Pat Doe (+15125550100)"
    assert chat["message_count"] == 4


def test_normalize_handle_matches_formatted_numbers():
    assert mtools.normalize_handle("+1 (512) 555-0100") == mtools.normalize_handle("5125550100")
    assert mtools.normalize_handle("Me@Acme.com") == "me@acme.com"


# %%
# Calendar #


def local(*parts):
    return datetime(*parts).astimezone()


@pytest.fixture
def calendar_db(tmp_path):
    chicago_9am_monday = datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc)  # 09:00 CDT
    # after DST ends on 2026-11-01, 09:00 Chicago is 15:00 UTC
    cancelled = datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)
    moved_from = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)
    all_day = datetime(2026, 10, 30, tzinfo=timezone.utc)
    single = datetime(2026, 10, 27, 20, 0, tzinfo=timezone.utc)
    return build(
        tmp_path / "Calendar.sqlitedb",
        """
        CREATE TABLE Store (ROWID INTEGER PRIMARY KEY, name TEXT, external_id TEXT, last_sync_end REAL);
        CREATE TABLE Calendar (ROWID INTEGER PRIMARY KEY, UUID TEXT, title TEXT, owner_identity_email TEXT,
            store_id INTEGER, external_id TEXT, self_identity_email TEXT);
        CREATE TABLE Location (ROWID INTEGER PRIMARY KEY, title TEXT);
        CREATE TABLE CalendarItem (ROWID INTEGER PRIMARY KEY, UUID TEXT, unique_identifier TEXT, summary TEXT,
            description TEXT,
            url TEXT, all_day INTEGER, start_date REAL, end_date REAL, start_tz TEXT, calendar_id INTEGER,
            status INTEGER, invitation_status INTEGER, has_recurrences INTEGER, orig_item_id INTEGER, orig_date REAL,
            has_attendees INTEGER, conference_url TEXT, location_id INTEGER, entity_type INTEGER, organizer_id INTEGER,
            last_modified REAL, creation_date REAL);
        CREATE TABLE Recurrence (ROWID INTEGER PRIMARY KEY, owner_id INTEGER, frequency INTEGER, interval INTEGER,
            week_start INTEGER, count INTEGER, end_date REAL, specifier TEXT);
        CREATE TABLE ExceptionDate (ROWID INTEGER PRIMARY KEY, owner_id INTEGER, date REAL);
        CREATE TABLE Participant (ROWID INTEGER PRIMARY KEY, owner_id INTEGER, entity_type INTEGER, status INTEGER,
            role INTEGER, email TEXT, is_self INTEGER, identity_id INTEGER);
        CREATE TABLE Identity (display_name TEXT, address TEXT);
        INSERT INTO Store VALUES (1, 'Acme', 'AAAA-ACME-CALDAV', 812000000), (2, 'Home', 'BBBB-HOME-IMAP', NULL);
        INSERT INTO Calendar VALUES (10, 'CAL-ACME', 'Work', 'me@acme.com', 1, '/calendar/dav/me/events/', NULL),
            (11, 'CAL-ACME-INBOX', 'Work', 'me@acme.com', 1, '/calendar/dav/me/inbox/', NULL),
            (20, 'CAL-HOME', 'Home', NULL, 2, NULL, NULL);
        INSERT INTO Location VALUES (1, 'Room 4');
        INSERT INTO Identity VALUES ('Boss Person', 'boss@acme.com');
        """,
        [
            (
                "INSERT INTO CalendarItem VALUES (1, 'UID-WEEKLY', 'ICAL-WEEKLY', "
                "'Standup', NULL, NULL, 0, ?, ?, 'America/Chicago', "
                "10, 0, 0, 1, 0, NULL, 0, NULL, 1, 2, NULL, NULL, NULL)",
                (apple_seconds(chicago_9am_monday), apple_seconds(chicago_9am_monday + timedelta(minutes=30))),
            ),
            ("INSERT INTO Recurrence VALUES (1, 1, 2, 1, 1, 0, NULL, 'D=0MO')", ()),
            ("INSERT INTO ExceptionDate VALUES (1, 1, ?)", (apple_seconds(cancelled),)),
            # the third week was moved to Tuesday: a detached item pointing at the Monday it replaced
            (
                "INSERT INTO CalendarItem VALUES (2, 'UID-MOVED', 'ICAL-WEEKLY', "
                "'Standup', NULL, NULL, 0, ?, ?, 'America/Chicago', "
                "10, 0, 0, 0, 1, ?, 0, NULL, 1, 2, NULL, NULL, NULL)",
                (
                    apple_seconds(moved_from + timedelta(days=1)),
                    apple_seconds(moved_from + timedelta(days=1, minutes=30)),
                    apple_seconds(moved_from),
                ),
            ),
            (
                "INSERT INTO CalendarItem VALUES (3, 'UID-OFFSITE', 'ICAL-OFFSITE', "
                "'Offsite', NULL, NULL, 1, ?, ?, '_float', 10, 0, "
                "0, 0, 0, NULL, 0, NULL, NULL, 2, NULL, NULL, NULL)",
                (apple_seconds(all_day), apple_seconds(all_day) + 2 * 86400 - 1),
            ),
            (
                "INSERT INTO CalendarItem VALUES (4, 'UID-REVIEW', 'ICAL-REVIEW', "
                "'Review', 'Bring numbers', 'https://x.test', 0, "
                "?, ?, 'America/Chicago', 10, 0, 2, 0, 0, NULL, 1, NULL, NULL, 2, 11, NULL, NULL)",
                (apple_seconds(single), apple_seconds(single + timedelta(hours=1))),
            ),
            ("INSERT INTO Participant VALUES (11, 4, 8, 0, 3, 'boss@acme.com', 0, 1)", ()),
            # status 1 is accepted (iCalendar order); is_self is 0 as Calendar.app leaves it - the address decides
            ("INSERT INTO Participant VALUES (12, 4, 7, 1, 1, 'Me@Acme.com', 0, NULL)", ()),
            ("INSERT INTO Participant VALUES (13, 4, 7, 2, 2, 'other@acme.com', 0, NULL)", ()),
            (
                "INSERT INTO CalendarItem VALUES (5, 'UID-HOME', 'ICAL-HOME', "
                "'Dentist', NULL, NULL, 0, ?, ?, 'America/Chicago', "
                "20, 0, 0, 0, 0, NULL, 0, NULL, NULL, 2, NULL, NULL, NULL)",
                (apple_seconds(single), apple_seconds(single + timedelta(hours=1))),
            ),
        ],
    )


def test_calendar_list_calendars_is_scoped(accounts_db, calendar_db):
    calendars = mtools.calendar_list_calendars(scope(accounts_db, "acme"), calendar_db=calendar_db)
    assert [(cal["calendar_id"], cal["account"]) for cal in calendars] == [("CAL-ACME", "acme")]
    assert calendars[0]["last_synced"] == mtools.local_iso(mtools.from_apple_seconds(812000000))


def test_weekly_series_keeps_its_wall_clock_across_dst_and_honours_exceptions(accounts_db, calendar_db):
    events = mtools.calendar_events(
        scope(accounts_db, "acme"), local(2026, 10, 26), local(2026, 11, 20), calendar_db=calendar_db
    )
    standups = [event["start"] for event in events if event["title"] == "Standup"]
    assert standups == [
        "2026-10-26T09:00:00-05:00",
        # 2026-11-02 was cancelled; 2026-11-09 moved to the Tuesday; DST ended 2026-11-01 and 09:00 stays 09:00
        "2026-11-10T09:00:00-06:00",
        "2026-11-16T09:00:00-06:00",
    ]


def test_event_id_is_the_per_item_uuid_calendar_app_addresses(accounts_db, calendar_db):
    events = mtools.calendar_events(
        scope(accounts_db, "acme"), local(2026, 10, 26), local(2026, 11, 20), calendar_db=calendar_db
    )
    standups = [(event["event_id"], event["ical_uid"]) for event in events if event["title"] == "Standup"]
    # the series' occurrences carry the series' id; the moved one is its own item sharing the iCal UID
    assert standups == [("UID-WEEKLY", "ICAL-WEEKLY"), ("UID-MOVED", "ICAL-WEEKLY"), ("UID-WEEKLY", "ICAL-WEEKLY")]
    series = mtools.calendar_get_event(scope(accounts_db, "acme"), "UID-WEEKLY", calendar_db=calendar_db)
    assert series["detached_occurrences"] == 1


def test_all_day_events_are_plain_dates_with_an_exclusive_end(accounts_db, calendar_db):
    events = mtools.calendar_events(
        scope(accounts_db, "acme"), local(2026, 10, 31), local(2026, 11, 1), calendar_db=calendar_db
    )
    (offsite,) = [event for event in events if event["title"] == "Offsite"]
    assert (offsite["start"], offsite["end"], offsite["end_is_exclusive"]) == ("2026-10-30", "2026-11-01", True)


def test_agenda_response_is_yours_not_another_attendees(accounts_db, calendar_db):
    events = mtools.calendar_events(
        scope(accounts_db, "acme"), local(2026, 10, 27), local(2026, 11, 1), calendar_db=calendar_db
    )
    by_title = {event["title"]: event for event in events}
    # Review lists you as accepted and someone else as declined; Offsite has no participants at all
    review = by_title["Review"]
    assert (review["response"], review["attendees_listed"], review["organizer"]) == ("accepted", 2, "boss@acme.com")
    assert (by_title["Offsite"]["response"], by_title["Offsite"]["attendees_listed"]) == (None, 0)


def test_calendar_events_search_text_and_scope(accounts_db, calendar_db):
    window = (local(2026, 10, 1), local(2026, 12, 1))
    acme = mtools.calendar_events(scope(accounts_db, "acme"), *window, query_text="numbers", calendar_db=calendar_db)
    assert [event["title"] for event in acme] == ["Review"]
    home = mtools.calendar_events(scope(accounts_db, "home"), *window, calendar_db=calendar_db)
    assert [event["title"] for event in home] == ["Dentist"]


def test_calendar_get_event_has_organizer_and_attendees(accounts_db, calendar_db):
    event = mtools.calendar_get_event(scope(accounts_db, "acme"), "UID-REVIEW", calendar_db=calendar_db)
    assert event["organizer"] == "Boss Person <boss@acme.com>"
    assert event["response"] == "accepted"
    assert event["attendees"] == [
        {"name": None, "email": "Me@Acme.com", "response": "accepted", "role": "required", "is_self": True},
        {"name": None, "email": "other@acme.com", "response": "declined", "role": "optional", "is_self": False},
    ]
    assert event["description"] == "Bring numbers"
    with pytest.raises(ValueError, match="no event"):
        mtools.calendar_get_event(scope(accounts_db, "home"), "UID-REVIEW", calendar_db=calendar_db)


@pytest.mark.parametrize(
    ("specifier", "expected"),
    [
        ("D=0TU", {"byweekday": [mtools.rrule.TU]}),
        ("D=+2MO;O=10", {"byweekday": [mtools.rrule.MO(2)], "bymonth": [10]}),
        ("D=-1FR", {"byweekday": [mtools.rrule.FR(-1)]}),
        ("M=1,15", {"bymonthday": [1, 15]}),
        ("", {}),
    ],
)
def test_parse_specifier(specifier, expected):
    assert mtools.parse_specifier(specifier) == expected


def test_parse_specifier_refuses_what_it_does_not_know():
    with pytest.raises(ValueError, match="unknown recurrence specifier"):
        mtools.parse_specifier("Q=1")


# %%
# Calendar writes #


@pytest.fixture
def osascript_calls(monkeypatch):
    calls = []

    def fake(script, args):
        calls.append((script, args))
        return "NEW-UID"

    monkeypatch.setattr(mtools, "run_osascript", fake)
    return calls


def test_create_passes_values_as_arguments_in_local_time(accounts_db, calendar_db, osascript_calls):
    result = mtools.calendar_create_event(
        scope(accounts_db, "acme"),
        "CAL-ACME",
        'Say "hi"',
        "2026-10-01T15:00:00+00:00",
        "2026-10-01T16:00:00+00:00",
        calendar_db=calendar_db,
    )
    assert result["event_id"] == "NEW-UID"
    script, args = osascript_calls[0]
    assert script == mtools.CREATE_SCRIPT
    assert args == ["CAL-ACME", 'Say "hi"', "2026 10 1 10 0", "2026 10 1 11 0", "false", "", "", ""]


def test_create_all_day_and_mixed_bounds(accounts_db, calendar_db, osascript_calls):
    acme = scope(accounts_db, "acme")
    mtools.calendar_create_event(acme, "CAL-ACME", "Off", "2026-10-01", "2026-10-02", calendar_db=calendar_db)
    assert osascript_calls[0][1][2:5] == ["2026 10 1 0 0", "2026 10 2 0 0", "true"]
    with pytest.raises(ValueError, match="both be dates"):
        mtools.calendar_create_event(acme, "CAL-ACME", "Off", "2026-10-01", "2026-10-01T10:00", calendar_db=calendar_db)


def test_writes_refuse_a_calendar_outside_the_scope(accounts_db, calendar_db, osascript_calls):
    with pytest.raises(ValueError, match="no calendar CAL-HOME"):
        mtools.calendar_create_event(
            scope(accounts_db, "acme"), "CAL-HOME", "x", "2026-10-01", "2026-10-02", calendar_db=calendar_db
        )
    assert osascript_calls == []


@pytest.mark.parametrize(("event_id", "reason"), [("UID-REVIEW", "has attendees"), ("UID-WEEKLY", "recurring")])
def test_update_and_delete_leave_meetings_and_series_alone(accounts_db, calendar_db, osascript_calls, event_id, reason):
    acme = scope(accounts_db, "acme")
    with pytest.raises(ValueError, match=reason):
        mtools.calendar_update_event(acme, event_id, "CAL-ACME", summary="x", calendar_db=calendar_db)
    with pytest.raises(ValueError, match=reason):
        mtools.calendar_delete_event(acme, event_id, "CAL-ACME", calendar_db=calendar_db)
    assert osascript_calls == []


def test_delete_own_single_event(accounts_db, calendar_db, osascript_calls):
    result = mtools.calendar_delete_event(
        scope(accounts_db, "acme"), "UID-OFFSITE", "CAL-ACME", calendar_db=calendar_db
    )
    assert result["deleted"] == "Offsite"
    assert osascript_calls == [(mtools.DELETE_SCRIPT, ["CAL-ACME", "UID-OFFSITE"])]


# %%
# Time #


def test_parse_moment_dates_are_local_midnights():
    assert mtools.parse_moment("2026-10-01") == local(2026, 10, 1)
    assert mtools.parse_moment("2026-10-01", end_of_day=True) == local(2026, 10, 2)
    assert mtools.parse_moment("") is None


def test_messages_dates_accept_seconds_and_nanoseconds():
    moment = datetime(2026, 1, 1, tzinfo=timezone.utc)
    seconds = apple_seconds(moment)
    assert mtools.from_messages_date(seconds) == moment
    assert mtools.from_messages_date(int(seconds * 1e9)) == moment
    assert date(2026, 1, 1) == mtools.from_messages_date(int(seconds * 1e9)).date()


# %%
