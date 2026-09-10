# FanControl curves on Windows

Fan curves for FanControl (Rem0o), written directly to its config file. Running
on Shelly since 2026-09-10, after a FanControl update on 2026-08-24 replaced its
config with a fresh default and left every fan on the BIOS.

## Shelly (MSI MPG B550 GAMING PLUS, NCT6687D)

LibreHardwareMonitor reads rpm on only two channels: `System Fan #1` to `#6` read
0 rpm although the case fans are plugged into those headers. Only the rpm
reading is wrong. FanControl still sets their duty, and it turned the case fans
down before the 2026-08-24 config reset. Leaving those six controls disabled
hands the case fans back to the BIOS, which runs them at full speed. The
channel it calls Pump Fan holds a PWM fan, not a pump: its speed follows its
duty (1767 rpm at 100%, 1026 rpm at 48%).

Both curves follow `Core (Tctl/Tdie)`, with hysteresis 2 degrees up and 3 down,
response time 1 s up and 3 s down.

| Curve | Header | Points (degrees C, %) |
| --- | --- | --- |
| `CPU` | CPU_FAN (`/lpc/nct6687d/control/0`) | 40,35 50,45 60,60 70,80 78,95 85,100 |
| `Case` | PUMP_FAN and SYS_FAN1 to 6 (`/lpc/nct6687d/control/1` to `/7`) | 40,40 55,50 65,65 75,85 85,100 |

Checked against the LibreHardwareMonitor log right after the restart: at 51.8
degrees CPU_FAN and PUMP_FAN sat at 48%, which is what both curves give there.
The system fan headers were added later the same day; their duty went from the
BIOS's 58 to 60% to 55% at 56 degrees, following the `Case` curve
(see [setup_windows_sensor_logging.md](setup_windows_sensor_logging.md)).

## Load check (2026-09-10)

Ten minutes on all 12 threads, from a PowerShell arithmetic loop (no AVX, so
lighter than Prime95), with an abort at 90 degrees C that never fired:

| Phase | Tctl avg / max | Package | CPU_FAN | PUMP_FAN | VRM max |
| --- | --- | --- | --- | --- | --- |
| idle, 2 min before | 52.6 / 53.1 | 31.5 W | 48%, 1181 rpm | 48%, 1018 rpm | 33.0 |
| load | 84.6 / 85.8 | 71.4 W (max 72.8) | 100%, 2547 rpm | 100%, 1777 rpm | 37.0 |
| 90 s after | 59.5 avg, 57.8 at the end | 32.5 W | back to 58% | back to 55% | 36.0 |

Tctl plateaued at 85.5 to 85.8 after about five minutes. No throttle, WHEA or
Kernel-Power events. Both curves reach 100% at 85 degrees, so under sustained
all-core load the fans have nothing left: a heavier load or a warmer case goes
past 85 with no more cooling to give. During this run the system fan headers were
still on the BIOS; they were put on the `Case` curve afterwards.

## Config file format (FanControl V273)

`C:\Program Files (x86)\FanControl\Configurations\userConfig.json`. Read from
`FanControl.Library.dll` and `FanControl.dll` metadata and IL, not from any
documentation.

- There is no type marker. `InterfaceDeserializationMap` loads each curve
  object, ranks every registered curve type by how many of its property names
  appear, and picks the best. A graph curve therefore needs exactly `Name`,
  `Points`, `SelectedTempSource`, `MinimumTemperature`, `MaximumTemperature`,
  `IsHidden`, `CommandMode`, `MaximumCommand` and `HysteresisConfig`. Adding the
  legacy fields (`SelectedHysteresis`, `SelectedResponseTime`,
  `OneWayHysteresis`) makes it load as the legacy type.
- `Points` is a list of `System.Windows.Point`, written by Newtonsoft through
  WPF's `PointConverter` as `"temperature,percent"` strings.
- `SelectedTempSource` is `{"Identifier": "..."}`. `HysteresisConfig` holds
  `HysteresisValueUp`, `HysteresisValueDown`, `IgnoreHysteresisAtLimits`,
  `ResponseTimeUp` and `ResponseTimeDown`.
- A control points at a curve by name: `"Enable": true` and
  `"SelectedFanCurve": {"Name": "CPU"}`.
- `CommandMode` is `0` for percent, `1` for rpm.
- Sensor identifiers are LibreHardwareMonitor's, except that
  `LHMSensor.RemoveZeroIndexedLPCIdentifiers` drops the chip index from `/lpc`
  ones: LibreHardwareMonitor's `/lpc/nct6687d/0/control/0` is FanControl's
  `/lpc/nct6687d/control/0`. CPU and GPU identifiers are unchanged, so the CPU
  temperature is `/amdcpu/0/temperature/2` in both.
- Before a migration FanControl copies the file to
  `Configurations\Backups\backup_V<version>_userConfig.json`.
- Errors in a loaded config (a missing sensor, a duplicate name) are reported
  in the app; the config is not reset.

## Applying a config remotely

1. Keep a copy of the current file next to it (`userConfig.json.bak-<date>`).
2. Stop the `FanControl` process. Kill it rather than closing it, so it does
   not save its in-memory config over the new file.
3. Write the new file, then start the `\FanControl` scheduled task, which is
   how it normally starts at logon.
4. Confirm in the LibreHardwareMonitor log that the header duty follows the
   curves.

Check the curves after every FanControl update.
