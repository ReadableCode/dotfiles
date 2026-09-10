# Diagnosing a Shelly crash

Shelly is the Windows 10 gaming PC in the personal inventory. On 2026-09-10 it
was set up so the next crash leaves evidence: sensor logging, fan curves, a
debugger for crash dumps. Start here after any crash, work through the steps in
order, and record what you find in the open issues in
`personal_credentials/backlog/`:

- `shelly-eac-unload-bluescreen.md`: blue screen as Fortnite exited
  (2026-09-09), while the Easy Anti-Cheat driver unloaded
- `shelly-ram-mixed-kits-untested.md`: two mixed RAM kits at 2133, never tested
- `shelly-hard-power-offs.md`: eleven power-offs with no dump since 2024-11

Related: [setup_windows_sensor_logging.md](setup_windows_sensor_logging.md) and
[setup_windows_fancontrol.md](setup_windows_fancontrol.md).

## Access

ssh as the user and address in the `Shelly` entry of
`personal_credentials/personal_hosts.json`:

```bash
SHELLY=<user>@<hostname>
ssh "$SHELLY" "query user"
```

- The ssh default shell on Shelly is PowerShell, so a `$` inside a
  double-quoted command is expanded on Shelly before your command runs. Put
  anything that uses `$` in a script file and send it encoded (UTF-16LE
  base64). Keep scripts under about 10 KB; the encoded command must fit
  Windows' 32767 character command line.

  ```bash
  enc() { python3 -c 'import base64,sys; print(base64.b64encode(open(sys.argv[1],encoding="utf-8").read().encode("utf-16le")).decode())' "$1"; }
  ssh "$SHELLY" "powershell -NoProfile -NonInteractive -EncodedCommand $(enc script.ps1)"
  ```

- The ssh session is elevated but is session 0, with no desktop. GUI programs
  and winget (its source fails over ssh) need the signed-in session: register
  a temporary scheduled task with
  `New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest`,
  start it, have it write its output to a file under `C:\Temp`, read the file,
  then unregister the task. A program whose manifest sets `uiAccess="true"`
  must be started through `cmd.exe /c start "" "<exe>"` in that task.
- Check `query user` first. Reboots, stress runs and memory tests only when
  nobody is using the machine.
- The account has a password, so after a reboot Windows waits at the sign-in
  screen. Nothing that starts at sign-in (sensor logging, FanControl) runs
  until someone signs in.

## 1. What kind of crash

```bash
ssh "$SHELLY" "wevtutil qe System /q:\"*[System[Provider[@Name='Microsoft-Windows-Kernel-Power'] and (EventID=41)]]\" /rd:true /f:xml" | grep -oE "SystemTime='[^']+'|Name='BugcheckCode'>[0-9]+" | paste - -
```

One line per unexpected shutdown, logged at the next boot, times in UTC.
`BugcheckCode` 0 is a hard power-off or hang with no dump. Anything else is a
blue screen with a dump (190 is `0xBE`).

The time in `EventLog` 6008 ("The previous system shutdown at ... was
unexpected") is the last timestamp Windows saved, not the crash: on 2026-09-09
it said 19:29:44 and the crash was at 19:55:38. For a blue screen use the dump's
`Debug session time`; for a power-off, the last sensor log row.

History as of 2026-09-10 (local time of going down, from 6008, so possibly
early):

| Date | Time | Bugcheck |
| --- | --- | --- |
| 2024-11-30 | 12:22 | 0 |
| 2025-04-14 | 13:19 | 0 |
| 2025-05-13 | 19:18 | 0 |
| 2025-05-18 | 13:39 | 0 |
| 2025-05-30 | 18:20 | 0 |
| 2025-06-04 | 12:52 | 0 |
| 2025-09-30 | 12:53 | 0 |
| 2026-04-12 | 01:13 | 0 |
| 2026-06-21 | 18:06 | 0 |
| 2026-08-25 | 01:01 | 0 |
| 2026-08-25 | 01:14 | 0 |
| 2026-09-09 | 19:55 (dump time) | `0xBE` |

## 2. The crash dump (blue screens)

Dumps go to `C:\Windows\Minidumps`, with an `s`: `CrashControl\MinidumpDir` is
set to that non-default path and `C:\Windows\Minidump` stays empty. There is no
`MEMORY.DMP`.

```bash
ssh "$SHELLY" "powershell -NoProfile -Command \"Get-ChildItem C:\Windows\Minidumps -File | Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize\""
```

Analyse on Shelly with `kd`. WinDbg is installed from
`app_lists\windows_apps_personal_winget.shelly.txt`, but `kd.exe` run from its
WindowsApps folder over ssh writes nothing, so copy the folder out first (send
as an encoded script):

```powershell
Copy-Item "$((Get-AppxPackage Microsoft.WinDbg).InstallLocation)\amd64" C:\Temp\windbg_amd64 -Recurse
C:\Temp\windbg_amd64\kd.exe -z C:\Windows\Minidumps\<file>.dmp -y "srv*C:\Temp\symbols*https://msdl.microsoft.com/download/symbols" -c "!analyze -v; lm t n; q" -logo C:\Temp\kd.txt
Select-String -Path C:\Temp\kd.txt -Pattern '^(BUGCHECK_CODE|PROCESS_NAME|IMAGE_NAME|MODULE_NAME|SYMBOL_NAME|FAILURE_BUCKET_ID)'
```

- Read `STACK_TEXT` from the bottom up for what was happening, then the
  `lm t n` output: the loaded modules and the `Unloaded modules` list.
- A minidump has no driver objects, so `!drvobj` and `dt nt!_DRIVER_OBJECT`
  fail. Identify drivers from the module lists.
- Keep `-c` free of `poi(...)`: a parse error stops the command list before `q`
  and `kd` sits waiting for input. Kill it with `Get-Process kd | Stop-Process`.
- First run downloads about 70 MB of symbols. Delete `C:\Temp\windbg_amd64`,
  `C:\Temp\kd.txt` and `C:\Temp\symbols` afterwards.

The 2026-09-09 dump: `0xBE` in `nt!MiSystemFault` while `FortniteClient`
exited, during a driver unload with `EasyAntiCheat_EOS.sys` still loaded. A new
dump with the same stack after an exit is the same issue.

## 3. The sensor log before the crash

LibreHardwareMonitor logs every 10 seconds from sign-in, one file a day,
14 days kept:

    $env:LOCALAPPDATA\Microsoft\WinGet\Packages\LibreHardwareMonitor.LibreHardwareMonitor_Microsoft.Winget.Source_8wekyb3d8bbwe\LibreHardwareMonitorLog-yyyy-MM-dd.csv

No rows around the crash means nobody was signed in, or LibreHardwareMonitor
was not running (step 6). Row 1 holds sensor identifiers, row 2 names, then the
readings. Some column names repeat, so `Import-Csv` fails; look columns up by
identifier. Set `$when` to the crash time and send as an encoded script:

```powershell
$when = Get-Date '2026-09-09 19:55:38'
$minutes = 10
$dir = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\LibreHardwareMonitor.LibreHardwareMonitor_Microsoft.Winget.Source_8wekyb3d8bbwe'
$file = Join-Path $dir ('LibreHardwareMonitorLog-{0:yyyy-MM-dd}.csv' -f $when)
$lines = Get-Content -LiteralPath $file
$ids = ($lines[0] -split ',') | ForEach-Object { $_.Trim('"') }
$want = [ordered]@{
  Tctl = '/amdcpu/0/temperature/2'; CpuW = '/amdcpu/0/power/0'; Load = '/amdcpu/0/load/0'
  CpuFan = '/lpc/nct6687d/0/control/0'; CpuRpm = '/lpc/nct6687d/0/fan/0'; SysFan = '/lpc/nct6687d/0/control/2'
  Vrm = '/lpc/nct6687d/0/temperature/2'; Gpu = '/gpu-nvidia/0/temperature/0'; GpuW = '/gpu-nvidia/0/power/0'
}
$idx = @{}
foreach ($k in $want.Keys) { $idx[$k] = [array]::IndexOf($ids, $want[$k]) }
$lines[2..($lines.Count - 1)] | ForEach-Object {
  $c = $_ -split ','
  $t = [datetime]::Parse($c[0])
  if ($t -ge $when.AddMinutes(-$minutes) -and $t -le $when) {
    $row = [ordered]@{ Time = $t.ToString('HH:mm:ss') }
    foreach ($k in $want.Keys) { $row[$k] = if ($idx[$k] -ge 0) { [math]::Round([double]$c[$idx[$k]], 1) } else { 'n/a' } }
    [pscustomobject]$row
  }
} | Format-Table -AutoSize
```

| Identifier | Sensor |
| --- | --- |
| `/amdcpu/0/temperature/2` | CPU Core (Tctl/Tdie) |
| `/amdcpu/0/power/0` | CPU package power |
| `/amdcpu/0/load/0` | CPU total load |
| `/lpc/nct6687d/0/temperature/2` | VRM |
| `/lpc/nct6687d/0/control/0`, `/fan/0` | CPU_FAN1 duty and rpm |
| `/lpc/nct6687d/0/control/1`, `/fan/1` | PUMP_FAN1 duty and rpm |
| `/lpc/nct6687d/0/control/2` to `/7` | SYS_FAN1 to 6 duty (their rpm reads 0, see traps) |
| `/gpu-nvidia/0/temperature/0`, `/power/0` | GPU core temperature and power |

Baselines measured 2026-09-10:

| State | Tctl | CPU power | Fans |
| --- | --- | --- | --- |
| idle | about 52 degrees C | about 31 W | about 50% |
| 10 min all-core load | 85.8 max, plateau 85.5 | 71 to 73 W | CPU_FAN and PUMP_FAN 100%, VRM 37 |

The CPU throttles at 95 degrees C. Reading the rows before a crash:

- Tctl climbing toward 95: cooling.
- GPU temperature or power rising into the gap: GPU or power supply under load.
- Normal readings right up to the last row, then nothing: power delivery
  (`shelly-hard-power-offs.md`).

## 4. Game logs

- Fortnite: `$env:LOCALAPPDATA\FortniteGame\Saved\Logs\FortniteGame.log`, plus
  `FortniteGame-backup-<session end, UTC>.log`. Only the last couple of sessions
  are kept, so copy them soon after a crash. A clean exit ends with
  `LogExit: Exiting.` and `Log file closed, <local time>`; a log that stops
  mid-game means the machine went down during play.
- Epic launcher: `$env:LOCALAPPDATA\EpicGamesLauncher\Saved\Logs`.
- Anti-cheat driver: `C:\Program Files (x86)\EasyAntiCheat_EOS\EasyAntiCheat_EOS.sys`.
  Fortnite rewrites it when it updates; the dump's `lm t n` line shows the build
  date that was loaded. BattlEye and the older EasyAntiCheat are installed too.
- Windows service start and stop events (7036) are not logged on this Windows
  build, so the System log cannot show when a game session ran.

## 5. Hardware errors and the memory test

```bash
ssh "$SHELLY" "powershell -NoProfile -Command \"Get-WinEvent -FilterHashtable @{LogName='System';ProviderName='Microsoft-Windows-WHEA-Logger'} -MaxEvents 20 | Format-List TimeCreated,Id,Message\""
ssh "$SHELLY" "powershell -NoProfile -Command \"Get-WinEvent -FilterHashtable @{LogName='System';ProviderName='Microsoft-Windows-MemoryDiagnostics-Results'} -MaxEvents 5 | Format-List TimeCreated,Id,Message\""
```

"No events were found" is the answer, not an error: as of 2026-09-10 there has
never been a WHEA event and Windows Memory Diagnostic has never run. Any WHEA
event points at hardware (CPU, memory, PCIe). MemTest86 results stay on its USB
stick, so ask for them.

## 6. Is the monitoring and cooling setup still in place

```bash
ssh "$SHELLY" "powershell -NoProfile -Command \"Get-ScheduledTask -TaskName LibreHardwareMonitor,lhm_log_pruning,FanControl | Format-Table TaskName,State -AutoSize; Get-Process LibreHardwareMonitor,FanControl | Format-Table Name,Id,StartTime -AutoSize\""
```

- `\LibreHardwareMonitor`: starts LibreHardwareMonitor elevated at sign-in.
- `\lhm_log_pruning`: SYSTEM, daily at 12:00, deletes logs older than 14 days.
- `\FanControl`: FanControl's own sign-in task.
- FanControl should have curves `CPU` (CPU_FAN1) and `Case` (PUMP_FAN1 and
  SYS_FAN1 to 6) with all eight controls enabled. An update on 2026-08-24
  replaced its config with defaults and the fans fell back to the BIOS at full
  speed, so check after any FanControl update. Config format, backups and how
  to rewrite it: [setup_windows_fancontrol.md](setup_windows_fancontrol.md).
- In the sensor log, the `control` columns should follow those curves.

## 7. Traps

Things that looked like evidence on 2026-09-09 and 2026-09-10 and were not:

- SYS_FAN1 to 6 read 0 rpm in LibreHardwareMonitor and FanControl although the
  case fans are plugged into them. FanControl still sets their duty. It is not
  a wiring fault.
- The 6008 shutdown time lags the real crash (step 1).
- The BIOS "CPU may be overheating" message after the 2026-09-09 crash:
  Windows cannot read any BIOS log, and nothing tied it to a real overheat.
- `MSAcpi_ThermalZoneTemperature` is not supported on this board.
- HWiNFO free refuses command-line logging, and its `uiAccess` manifest stops a
  scheduled task starting it directly. It is not used.
- `winget` from an ssh session cannot reach its source (step Access).

## 8. Machine facts, 2026-09-10

| Part | Detail |
| --- | --- |
| CPU | AMD Ryzen 5 3600, stock AMD cooler from a Ryzen 5 2600, repasted in the 2026-08 rebuild |
| Board | MSI MPG B550 GAMING PLUS (MS-7C56), BIOS 1.I0 (2024-07-12), Nuvoton NCT6687D |
| Fan headers | CPU_FAN1, PUMP_FAN1, SYS_FAN1 to 6 (MSI manual: SYS_FAN default DC mode) |
| RAM | 4 x 8 GB Corsair `CMK16GX4M2B3000C15` (two 2-stick kits), running 2133 |
| GPU | NVIDIA RTX 5070 Ti, driver 32.0.16.1088 (2026-07-21), added in the 2026-08 rebuild |
| PSU | Corsair RM1000e |
| Case | Fractal Design North XL |
| OS | Windows 10 Pro 22H2, build 19045.6466 |

## 9. Planned after 2026-09-10

- A memory test (Windows Memory Diagnostic or MemTest86).
- Reseating the GPU power cables and the 24-pin and CPU 8-pin.
- Repairing Easy Anti-Cheat with
  `C:\Program Files\Epic Games\Fortnite\FortniteGame\Binaries\Win64\EasyAntiCheat\EasyAntiCheat_EOS_Setup.exe`.

Record what was done and when in the matching backlog entry before judging a
new crash against them.

## 10. After diagnosing

Update the backlog entry the crash belongs to, or open a new one; close an
entry by deleting it in the commit that fixes it. Leave nothing of yours in
`C:\Temp`.
