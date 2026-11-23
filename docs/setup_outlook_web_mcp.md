# Outlook web MCP - an Exchange mailbox through the signed-in Outlook tab

`src/outlook_web_mcp.py` is a stdio MCP server that reads one Exchange
mailbox and calendar, and writes your own calendar events there, through the
Outlook on the web tab already signed in inside a browser profile on this Mac.
Readers and writers are in `src/utils/outlookweb_tools.py`.

## Why this exists next to the mac and Google servers

A tenant that blocks consent for every app of our own cannot be reached by
`google_mcp.py` or by Microsoft Graph (see the auth facts in
[setup_calendar_board.md](setup_calendar_board.md)). `mac_mcp.py` gets around
that by reading what Mail.app and Calendar.app have synced, but only while the
account is in Internet Accounts on that Mac. When it is not, the one client
the tenant still allows is Outlook on the web itself.

The page keeps Outlook's own access token for the Outlook REST API
(`https://outlook.office.com/api/v2.0`, `Calendars.ReadWrite` and mail scopes)
in its localStorage. Each call runs JavaScript inside the tab over AppleScript
(`execute javascript`): it picks that token in the page, calls the API with
`fetch` from the tab, and only the API's answer comes back. The token never
leaves the browser and nothing is stored on disk. The tab refreshes its own
token; one about to expire gets the tab reloaded once.

macOS and Edge put background tabs to sleep, and a sleeping tab takes no
script: it only times out. Each call goes to the tab that answered last, skips
any tab that does not answer within 5 seconds (remembered for the rest of the
process), and when no Outlook tab is open and awake it opens a fresh one in
the configured profile and waits for it to sign in. A read whose tab falls
asleep mid-call runs again; a write does not, since it may have landed, and
says to read it back first.

## Registering it

Each credentials repo that needs it declares its own instance, pinned with
`--context` (a server is always pinned: one tab is one mailbox):

```yaml
- name: acme_outlook_web
  command: uv
  args: ["run", "--project", "{repo_root}", "python",
         "{repo_root}/src/outlook_web_mcp.py", "--context", "acme"]
```

and names the account in `<context>_outlookweb.yaml`:

```yaml
- name: acme                       # the account name tools return
  address: jason@acme.com          # the mailbox address
  sign_in: jason@acme-corp.com     # what the tenant signs it in as; any other tab is refused
  browser: Microsoft Edge          # the app the tab lives in
  profile: Profile 1               # profile directory a tab is opened in when none is open
```

`sign_in` is checked against the token's own `upn` on every call, so a tab
signed in to another account in another profile is refused, never used.

## One-time setup on the Mac

1. Sign in to Outlook on the web in the configured profile and leave a tab
   open (mail or calendar, any `outlook.cloud.microsoft` or
   `outlook.office.com` page).
2. In that browser: View > Developer > Allow JavaScript from Apple Events.
3. The app running Claude asks once to control the browser; approve it.

Check it, read-only:

```bash
uv run --project ~/GitHub/dotfiles python ~/GitHub/dotfiles/src/outlook_web_mcp.py --check --context acme
```

It prints who the tab is signed in as, the calendars and the newest message's
date.

## Tools

Same names and shapes as the mac server's mail and calendar tools, so a
caller switches by changing the server: `list_accounts`,
`mail_list_mailboxes`, `mail_search`, `mail_get_message`,
`mail_download_attachment`, `calendar_list_calendars`, `calendar_agenda`,
`calendar_get_event`, `calendar_create_event`, `calendar_update_event`,
`calendar_delete_event`. Differences:

- Message ids are the server's strings, not Mail.app row numbers.
- Mail search is the server's own (whole bodies included).
- Every read is live, so `last_synced` on a calendar is always now.
- Created events are busy, with no attendees and no reminder; update and
  delete refuse meetings with attendees and recurring series.
