# Mac MCP - Mail.app, Calendar.app and Messages in Claude Code

`src/mac_mcp.py` is a stdio MCP server that lets Claude Code read the mail,
calendars and texts already synced onto a Mac, and add events to those
calendars. It reads the local copies Mail.app, Calendar.app and Messages keep,
so it reaches any account signed in under System Settings > Internet Accounts
(Exchange, Google Workspace, iCloud, IMAP) with no OAuth app of its own.

## Why this exists next to the Google server

Every program that calls the Google or Microsoft APIs is a registered OAuth
client, and a company tenant decides which clients its users may approve.
Most tenants turn off user consent for unverified publishers, which is every
app of our own: `google_mcp.py` works for accounts whose owner can approve our
Cloud project, and hits "ask your admin" everywhere else. Mail.app and
Calendar.app are registered too, but by Apple, and tenants allow them because
blocking them breaks every iPhone in the company. Once they have synced, the
data is a set of files on this Mac, and reading files needs only a macOS
privacy grant. So this server rides on Apple's approval instead of asking each
tenant for one.

The Google server stays the tool for accounts it can reach: it talks to the
live API (labels, send, Drive) where this one is read-only for mail.

## Registering it

The same declare-and-generate flow as the Google server
([setup_google_mcp.md](setup_google_mcp.md)). dotfiles holds the code and
declares no instance; each credentials repo declares its own, pinned with
`--context`:

```yaml
- name: acme_mac
  command: uv
  args: ["run", "--project", "{repo_root}", "python",
         "{repo_root}/src/mac_mcp.py", "--context", "acme"]
```

and lists the accounts that context reaches in `<context>_macaccounts.yaml`:

```yaml
- name: acme
  type: internet_account
  address: me@acme.com      # the address shown in Internet Accounts
- name: acme_messages       # only the context that owns the Apple ID lists this
  type: messages
```

An `internet_account` entry covers every account in Internet Accounts whose
top-level username is that address, and both apps' data under it: Mail.app
names its account folders after a child IMAP/Exchange account and
Calendar.app its stores after a child CalDAV one, and the server walks each
child up to its root in `~/Library/Accounts/Accounts4.sqlite`. One Apple ID is
often both the iCloud and a Google account, and then one entry covers both.
Local-only data ("On My Mac" mailboxes, subscribed and birthday calendars)
belongs to no account and is never reached.

Mail.app and Calendar.app hold every context's accounts side by side, so the
pin is what keeps a session in one client's repo from reading another's mail:
a pinned server sees only its own entries, a message or calendar id from
another account reads as not found, and a pinned context with no config
reports no accounts. `list_accounts` shows, per entry, which Internet Accounts
it matched here and how many mail folders and calendars that is.

## Granting access

Reading needs **Full Disk Access** on the app that launches Claude Code: macOS
attributes the server's file reads to that app, not to the Python process.
System Settings > Privacy & Security > Full Disk Access, add T3 Code (and
Terminal / VS Code / whatever else runs `claude`); restart that app if reads
still fail. Without it every read fails with "authorization denied" /
"Operation not permitted".
This also lets every shell command Claude runs in that app read the same
folders; that is the trade for having no helper app of our own.

Calendar writes need **Automation** permission for that app to control
Calendar: the first write prompts "T3 Code wants to control Calendar". Not a
Calendars permission: the app itself would have to declare one, T3 Code does
not, and Calendar.app already has access to every calendar anyway.

## How each app is read

**Mail** - `~/Library/Mail/V<n>/MailData/Envelope Index` (SQLite) for search,
the message's own `.emlx` file for the body. Search matches subject, sender
and the preview Mail stores for each message, not whole bodies. Gmail keeps
each message once in All Mail with its labels in a join table, so `mailbox`
filters by folder or label alike. A message Mail never downloaded returns its
preview with `body_is_preview_only`.

**Messages** - `~/Library/Messages/chat.db`. Newer rows leave `text` empty and
keep the words in `attributedBody`, an archived NSAttributedString the server
decodes. Handles resolve to names through the Contacts databases under
`~/Library/Application Support/AddressBook`. Tapbacks are left out.

**Calendar** - `~/Library/Group Containers/group.com.apple.calendar/Calendar.sqlitedb`.
Recurring series are expanded by the server from their stored rules
(`Recurrence`, `ExceptionDate`, detached occurrences), in the event's own time
zone so a 09:00 meeting stays at 09:00 across a DST change. Calendar.app's own
`OccurrenceCache` looks like the shortcut but is sparse and misses most
occurrences. A rule part the server does not know is refused by name rather
than guessed.

Every store is opened with SQLite `mode=ro`, which still reads the WAL, so
results match what the apps show. Nothing here ever writes to an Apple
database.

## Writes

Calendar writes go through Calendar.app over AppleScript, which owns the sync
to the account. Its AppleScript addresses calendars and events by the same
calendar UUID and event UID the readers return, and values travel as `osascript`
arguments, never spliced into the script.

- `calendar_create_event` on any calendar in scope. Timestamps convert to local
  wall-clock time (AppleScript dates have no zone); `YYYY-MM-DD` bounds make an
  all-day event with an exclusive end, as in the Google tools. No attendees and
  no invitations.
- `calendar_update_event` / `calendar_delete_event` only on your own single
  events. A meeting with attendees belongs to its organizer's mail flow and a
  series edit moves every occurrence, so both are refused. Delete is not
  recoverable.

Mail and Messages have no write tools.

## Tools

`list_accounts`; mail: `mail_list_mailboxes`, `mail_search`, `mail_get_message`;
messages: `messages_list_chats`, `messages_get_chat`, `messages_search`;
calendar: `calendar_list_calendars`, `calendar_agenda`, `calendar_search_events`,
`calendar_get_event`, `calendar_create_event`, `calendar_update_event`,
`calendar_delete_event`. `account` defaults to every entry of the context.

## Limits

- macOS only. Windows and Linux are tracked in
  `backlog/mac-mcp-windows-linux.md`.
- The stores are private formats. Mail's `V<n>` folder, the Messages archive and
  the Calendar schema are what macOS 27 writes; a macOS upgrade that changes
  them shows up as a failing read, and the fix is in `src/utils/macmcp_tools.py`.
- Anticipated failures (not configured, access denied, a refused write) are
  raised as the SDK's `ToolError` so their reason reaches the model; any other
  exception type shows only "Error executing tool".
