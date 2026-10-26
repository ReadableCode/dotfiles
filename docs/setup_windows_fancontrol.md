# FanControl curves on Windows

Fan curves for FanControl (Rem0o), written directly to its config file,
running on Shelly. A FanControl update can replace that config with a fresh
default and leave every fan on the BIOS, so check the curves after one.

## Shelly (MSI MPG B550 GAMING PLUS, NCT6687D)

LibreHardwareMonitor reads rpm on only two channels: `System Fan #1` to `#6` read
0 rpm although the case fans are plugged into those headers. Only the rpm
reading is wrong. FanControl still sets their duty and turns the case fans
down. Leaving those six controls disabled
hands the case fans back to the BIOS, which runs them at full speed. The
channel it calls Pump Fan holds a PWM fan, not a pump: its speed follows its
duty (1767 rpm at 100%, 1026 rpm at 48%).

Both curves follow `Core (Tctl/Tdie)`, with hysteresis 2 degrees up and 3 down,
response time 1 s up and 3 s down.

| Curve | Header | Points (degrees C, %) |
| --- | --- | --- |
| `CPU` | CPU_FAN (`/lpc/nct6687d/control/0`) | 40,35 50,45 60,60 70,80 78,95 85,100 |
| `Case` | PUMP_FAN and SYS_FAN1 to 6 (`/lpc/nct6687d/control/1` to `/7`) | 40,40 55,50 65,65 75,85 85,100 |

Check them against the sensor log
([setup_windows_sensor_logging.md](setup_windows_sensor_logging.md)): at any
CPU temperature each header's duty is what its curve gives there.

## Load check

After setting the curves, run ten minutes on all threads with a PowerShell
arithmetic loop (no AVX, so lighter than Prime95) and an abort at 90 degrees C,
and read Tctl, package power, fan duty and VRM from the sensor log. Look for
throttle, WHEA or Kernel-Power events afterwards. Both curves reach 100% at 85
degrees, so a load that holds Tctl past 85 has no more cooling to give.

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
