# mac_mcp: no Windows or Linux equivalent for reading synced mail, calendars and texts

    found:  2026-09-26
    status: open
    verify: grep -n "def require_macos" -A6 src/utils/macmcp_tools.py

`src/mac_mcp.py` reaches accounts whose tenant blocks our own OAuth apps by
reading what Mail.app, Calendar.app and Messages already synced onto a Mac.
It only exists for macOS. On any other machine every tool raises before
touching anything.

## Evidence

`src/utils/macmcp_tools.py`, written 2026-09-26:

    def require_macos():
        """Every reader here is a macOS app's store; say so plainly anywhere else."""
        if sys.platform != "darwin":
            raise RuntimeError(
                "the mac server reads Mail.app, Calendar.app and Messages stores and only runs on macOS "
                "(Windows and Linux are tracked in backlog/mac-mcp-windows-linux.md)"
            )

The `<context>_mac` declarations in the credentials repos carry no host filter
(`src/claude_mcp.py` has none), so a Windows or Linux machine that loads a
context declaring one registers a server whose every call fails with that
message.

## fix

There is no single store to read, so this is a design task per platform, not a
port:

1. Windows: classic Outlook keeps an `.ost` per account, reachable through the
   Outlook COM object model (`win32com.client.Dispatch("Outlook.Application")`
   then `GetNamespace("MAPI")`), which covers mail and calendar for every
   account Outlook has signed in, Exchange included. New Outlook (`olk.exe`)
   keeps no local store a script can open. Check which one each Windows
   machine runs before choosing.
2. Linux: Thunderbird keeps mail as mbox/maildir under
   `~/.thunderbird/<profile>/` with a `global-messages-db.sqlite` index, and
   calendars in `calendar-data/local.sqlite`; GNOME/Evolution keeps both
   behind evolution-data-server. Pick whichever client the Linux machines
   actually use.
3. Add the readers beside `macmcp_tools.py`, keep the tool names and the
   `<context>_macaccounts.yaml` shape (renaming the server to something
   platform-neutral at the same time), and dispatch on `sys.platform`.
4. Until then, if a non-Mac machine ever loads a context declaring
   `<context>_mac`, give `claude_mcp.py` a per-host variant of the declaration
   (`<base>.<host>.<ext>`) rather than a filter.

## blast radius

None today: no Windows or Linux machine is known to load a context that
declares `<context>_mac`. A port adds code paths only; the macOS readers are
untouched.

## not doing yet

Nothing needs it yet: the synced client accounts live in Mail.app on the
personal Macs. Decide first which mail and calendar client each non-Mac
machine really runs, and whether any of them hold accounts the Google server
cannot reach.
