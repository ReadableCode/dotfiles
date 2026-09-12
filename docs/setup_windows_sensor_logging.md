# Windows sensor logging (LibreHardwareMonitor)

CPU, board and GPU temperatures, fan speeds and CPU power, logged to CSV every
10 seconds from sign-in and kept for 14 days. Running on Shelly.

## Why LibreHardwareMonitor and not HWiNFO

- HWiNFO free refuses command-line logging: `-l` opens an error box reading
  "Command-line parameters are supported in HWiNFO64 Pro only."
- `HWiNFO64.EXE` is `requireAdministrator` with `uiAccess="true"`. A scheduled
  task cannot start a uiAccess exe directly (`LastTaskResult` 2147943140,
  `0x800702E4` ERROR_ELEVATION_REQUIRED), and an ssh session is session 0 with
  no interactive window station, so it cannot start there either.
- LibreHardwareMonitor logs by itself, its exe is `requireAdministrator`
  without uiAccess, and `LibreHardwareMonitorLib.dll` targets .NET Framework
  4.7.2, so Windows PowerShell 5.1 can read the sensors over ssh.
- It uses the same PawnIO driver as FanControl.

## Install

`app_lists\windows_apps_personal_winget.shelly.txt` holds
`LibreHardwareMonitor.LibreHardwareMonitor`.

winget cannot reach its source from an ssh session (source update
`Cancelled`, `winget show` fails with `0x80190194`). Inside the signed-in
session it works, so the install runs from a temporary scheduled task with the
same command `scripts\install_windows_apps_with_winget.ps1` uses:

```powershell
winget install --id LibreHardwareMonitor.LibreHardwareMonitor --exact --accept-package-agreements --accept-source-agreements
```

The package is portable, in
`%LOCALAPPDATA%\Microsoft\WinGet\Packages\LibreHardwareMonitor.LibreHardwareMonitor_Microsoft.Winget.Source_8wekyb3d8bbwe`.
Its `namazso.PawnIO` dependency is met by the copy FanControl installed.

The winget manifest sets `UpgradeBehavior: uninstallPrevious`. The settings
file and the logs live in the package folder, so check both after an upgrade
(unverified whether winget removes files it did not install).

## Settings

`LibreHardwareMonitor.config`, next to the exe. Keys and value formats are from
`MainForm.cs` and `PersistentSettings.cs` at v0.9.6. The app loads the file at
start and writes it on exit, so edit it only while the app is closed.

| Key | Value | Meaning |
| --- | --- | --- |
| `startMinMenuItem` | `true` | start minimized |
| `minTrayMenuItem` | `true` | minimize to tray |
| `logSensorsMenuItem` | `true` | log sensors |
| `loggingInterval` | `3` | index into 1 s, 2 s, 5 s, 10 s, ...: 10 seconds |
| `logger.fileRotation` | `1` | one file a day (`0` is one per session) |
| `hddMenuItem`, `nicMenuItem`, `ramMenuItem`, `psuMenuItem`, `batteryMenuItem`, `powerMonitorMenuItem` | `false` | not read or logged |

"Run On Windows Startup" is not a setting. The GUI shows it ticked when a task
named `LibreHardwareMonitor` exists whose action is the exe path.

## Scheduled tasks

- `\LibreHardwareMonitor`: the definition from `StartupManager.CreateTask`.
  Logon trigger, highest privileges, interactive token, no execution time
  limit, start when available, working directory is the package folder.
- `\lhm_log_pruning`: runs as SYSTEM daily at 12:00, start when available,
  deletes `LibreHardwareMonitorLog-*.csv` older than 14 days from the package
  folder.

## Reading the logs

One file a day, `LibreHardwareMonitorLog-yyyy-MM-dd.csv`, in the package
folder. Row 1 is sensor identifiers, row 2 sensor names, then a row every 10
seconds. With the sensors above that is 140 columns and about 960 bytes a row:
roughly 8 MB a day and 115 MB for the 14 days kept.

Column positions shift when hardware changes, so look columns up by
identifier. On Shelly (MSI MPG B550 GAMING PLUS, NCT6687D):

| Identifier | Sensor |
| --- | --- |
| `/amdcpu/0/temperature/2` | CPU Core (Tctl/Tdie) |
| `/amdcpu/0/power/0` | CPU package power |
| `/amdcpu/0/load/0` | CPU total load |
| `/lpc/nct6687d/0/temperature/0` | board CPU temperature |
| `/lpc/nct6687d/0/fan/0`, `/lpc/nct6687d/0/control/0` | CPU_FAN rpm and duty |
| `/lpc/nct6687d/0/fan/1`, `/lpc/nct6687d/0/control/1` | PUMP_FAN rpm and duty |
| `/gpu-nvidia/0/temperature/0` | GPU core |

FanControl bundles its own LibreHardwareMonitor build, whose SuperIO
identifiers have no chip index (`/lpc/nct6687d/control/0`), so identifiers do
not carry over between the two unchanged. See
[setup_windows_fancontrol.md](setup_windows_fancontrol.md).

## Reading sensors over ssh

With the app closed or running, Windows PowerShell 5.1 can load the library
from an elevated ssh session. Hook `AppDomain.AssemblyResolve` with a small C#
class compiled through `Add-Type` that loads dependencies from the package
folder. A PowerShell scriptblock handler re-enters itself while resolving and
kills the process with StackOverflowException.
