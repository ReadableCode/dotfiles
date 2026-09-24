# vnc: pasting from the Mac into the RyzenWhite VNC session does nothing

    found:  2026-09-24
    status: open
    verify: copy a line on the Mac, run `vncryzenwhite`, click into a PowerShell window there and press Ctrl+V (not Cmd+V); the line either appears or it does not

No command can press keys in a VNC window, so the check is by hand, at the Mac.

## Evidence

On 2026-09-24 ssh to RyzenWhite was down and the repair had to be pasted in
over `vncryzenwhite`. Pasting did nothing, and the commands were typed by hand.

Nothing in the repo turns the clipboard off at either end:

- the viewer is TigerVNC 1.16.2 (`cask "tigervnc"`), launched by
  `src/vnc_connect.py` with `VIEWER_ARGS = ["-RemoteResize=0",
  "-AlwaysCursor=1", "-CursorType=System"]`, so `AcceptClipboard` and
  `SendClipboard` stay at their default of 1, and `~/.vnc/default.tigervnc`
  holds only a `ServerName` line
- the server is TightVNC 2.8.88 (`tvnserver.exe -service`, running). Its
  settings in `HKLM\SOFTWARE\TightVNC\Server` have no clipboard value at all
  (read the same day: `EnableFileTransfers 1`, `BlockRemoteInput 0`,
  `AcceptRfbConnections 1`, ...)

Two causes fit and neither is confirmed:

1. **Cmd+V is not paste in the viewer.** TigerVNC on macOS sends Command as
   the Windows key, so Cmd+V arrives as Win+V, which opens Windows clipboard
   history (turned on per `docs/setup_windows_workstation_personal.md`).
   Ctrl+V, or right-click in a PowerShell window, is the paste there.
2. **The viewer-to-server clipboard between a TigerVNC viewer and a TightVNC
   2.8 server is flaky upstream**, all still open with no fix: text syncs
   server to viewer but not back (TigerVNC issue #2060), the clipboard stops
   after a while with TightVNC 2.8.81 (#1759), and it takes a copy twice
   before it syncs (#1586).

## fix

Run `verify:`. Then:

- **It pastes:** cause 1. Add a "Keyboard" note to the "Clients" section of
  `docs/setup_vnc_server.md` saying that Cmd reaches Windows as the Windows
  key, so paste is Ctrl+V or right-click. Then delete this entry.
- **It pastes only after copying twice, or after reconnecting:** cause 2.
  Write that workaround in the same section; there is no setting to change.
- **It never pastes:** check that TigerVNC is the problem by pasting over a
  second viewer. macOS Screen Sharing works with TightVNC per the table in
  `docs/setup_vnc_server.md`: `open vnc://192.168.86.94:5900`.

## blast radius

None for either doc note. If the answer is a viewer option, `VIEWER_ARGS`
applies to every `vnc<host>` alias on every machine, so test it against a
wayvnc Pi and an x0vncserver host as well as RyzenWhite.

## not doing yet

Deferred on 2026-09-24: typing the commands was fine for that repair, and the
check needs someone at the Mac with the VNC window open.
