# windows: an upgrade of Stream Deck closes the app and nothing starts it again

    found:  2026-10-05
    status: open
    verify: sshryzenwhite, then `Get-Process StreamDeck` (running or not) and `Get-Content $env:APPDATA\Elgato\StreamDeck\logs\StreamDeck.log -Tail 3` (the last line is "Application session ended" when it is down)

The deck on RyzenWhite was dark from 2026-10-02 20:00 until it was started by
hand on 2026-10-05 07:44, two and a half days, with the machine logged in the
whole time.

## Evidence

Read over ssh on 2026-10-05:

- no `StreamDeck` process; the device itself present and healthy
  (`USB\VID_0FD9&PID_0080\A00TA5432IOEQN`, status OK)
- uninstall registry: `Elgato Stream Deck 7.6.0.23012`, `InstallDate 20261002`
- `StreamDeck.log` ends in a clean shutdown, not a crash:

      2026-10-02T20:00:14.739  StreamDeck  inf main  Application event loop ended (0)
      2026-10-02T20:00:14.808  StreamDeck  inf main  Application session ended

  and has no line after it until the manual start
- the only autostart is `HKCU\...\Run`, `"C:\Program Files\Elgato\StreamDeck\StreamDeck.exe" --runinbk`,
  which fires at logon; `query user` showed the console session logged on
  since 2026-10-01 16:58, so it never fired
- the companion `ElgatoAudioControlServer` did come back by itself at 20:01:14

Not established: what ran the upgrade. No app list names Stream Deck
(`grep -ri 'stream.deck\|elgato' app_lists/` and the personal context's app
list both return nothing), so it was either `my_updater.ps1` upgrading an
unlisted package, which was still possible on 2026-10-02 (see
`docs/repo_app_removals.md`, "Upgrades keep to the manager that installed the
app"), or the app's own updater. The Mac got the same 7.6.0.23012 from the
brew cask on 2026-10-05 07:11 and the app was running again a minute later.

## fix

First find the upgrader, on RyzenWhite:

    Get-WinEvent -FilterHashtable @{LogName='Application';ProviderName='MsiInstaller';StartTime='2026-10-02 19:55';EndTime='2026-10-02 20:05'} | Format-List TimeCreated,Message
    Select-String -Path C:\ProgramData\chocolatey\logs\chocolatey.log -Pattern 'stream' | Select-Object -Last 5
    Get-ChildItem "$env:LOCALAPPDATA\Packages\Microsoft.DesktopAppInstaller_8wekyb3d8bbwe\LocalState\DiagOutputDir" | Where-Object LastWriteTime -gt '2026-10-02 19:55' | Select-Object -First 5

Then one of:

- it was a package manager: since the 2026-10-02 change winget upgrades only
  what a winget list names, so confirm with `python src/app_lists.py --upgrades winget`
  and `--upgrades choco` that Stream Deck is in neither plan. If it is in one,
  add it to `app_upgrade_holds.yaml` (it updates itself).
- it was the app's own updater: nothing in this repo closed it, and the entry
  is deleted with that noted in the commit message.

Starting it from ssh, when it is down again (ssh cannot show a window, so it
has to be launched into the desktop session):

    $a = New-ScheduledTaskAction -Execute 'C:\Program Files\Elgato\StreamDeck\StreamDeck.exe' -Argument '--runinbk'
    $p = New-ScheduledTaskPrincipal -UserId (whoami) -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName start_stream_deck_once -Action $a -Principal $p -Force
    Start-ScheduledTask -TaskName start_stream_deck_once
    Unregister-ScheduledTask -TaskName start_stream_deck_once -Confirm:$false

## blast radius

The checks read logs only. A hold line changes nothing but who upgrades the
app. The launch starts one tray app in the logged-in session and leaves no
task behind.

## not doing yet

Found while starting the app by hand; the upgrader is unidentified, and the
fix depends on which one it was.
