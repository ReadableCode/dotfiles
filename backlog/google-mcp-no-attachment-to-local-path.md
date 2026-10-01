# google_mcp: no tool saves a Gmail attachment to a local path

    found:  2026-10-01
    status: open
    verify: grep -c "def gmail_download_attachment" src/google_mcp.py src/utils/googlemcp_tools.py

On 2026-10-01 the verify line printed `0` for both files.

The Gmail server can fetch an attachment's bytes and can only put them in
Drive. A caller that files documents on the machine's own disk has no way to
get an attachment out of Gmail through this server, so mail captures for an
account that does have API access fall back to the macOS-only server, which
reads what Mail.app happened to download.

## Evidence

`src/utils/googlemcp_tools.py`, read 2026-10-01:

    _gmail_attachment(mailbox, message_id, filename)      bytes and mime type, from the Gmail API
    gmail_save_attachment_to_drive(...)                   its only caller; "Nothing touches local disk"
    drive_download_file(drive, file_id, local_path)       writes a Drive file to a new local path, never overwrites

So the fetch exists and the local write exists, for two different sources.
Nothing joins them. The Gmail API itself places no limit here.

The tools `src/google_mcp.py` registers for mail are profile, search, list ids,
get message, list labels, modify, trash, send, and save attachment to Drive.

Why it matters beyond convenience: the macOS server only runs on a Mac
(`mac-mcp-windows-linux.md`) and returns an attachment only when Mail.app has
stored it. The Gmail server runs on every machine and always has the bytes.

## fix

1. In `src/utils/googlemcp_tools.py`, add
   `gmail_download_attachment(mailbox, message_id, filename, local_path)`:
   call `_gmail_attachment`, then write exactly as `drive_download_file` does
   (absolute path, refuse an existing file, create the parent folder), and
   return the path, byte count and sha256.
2. Register it in `src/google_mcp.py` beside `gmail_save_attachment_to_drive`,
   described as a write to local disk that never overwrites.
3. Tests in `tests/test_googlemcp_tools.py`, with the request layer faked the
   way the existing attachment test fakes it: bytes land at the path, an
   existing path is refused, a missing or duplicated filename raises.

## blast radius

Additive: one function, one tool, three tests. The server gains its second
tool that writes to local disk; like the first it cannot overwrite. Every
session that loads the server lists one more tool.

## not doing yet

Nothing is undecided. It waits only for the first caller, which is the mail
capture in the personal dev repo once that reads Gmail.
