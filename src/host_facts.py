"""
Collect this machine's own hardware facts for the host inventory.

Stdlib-only and no imports from the rest of this repo, so a bare `python3`
runs it on a fresh machine before any venv exists - same constraint as
`ssh_aliases.py`. Prints one JSON object on stdout:

    {"name": ..., "os": ..., "hardware": {...}, "notes": [...]}

It emits only the fields a machine can actually report about itself. The
judgement fields the dashboard scores on - `arch`, `boost_ghz`, `core_groups` -
are deliberately absent: no OS exposes which cores are performance vs
efficiency at what clock, Apple Silicon exposes no clock at all, and mapping a
CPU model to a microarchitecture is knowledge rather than detection. The
/personal_host_facts command fills those in.

`notes` carries anything the caller should not take at face value, because
several of these sources lie: `nproc --all` reports the kernel's compile-time
ceiling on some builds, every Raspberry Pi kernel reports the legacy BCM2835
alias whatever silicon it has, and unconfigured boards report placeholder
product names.
"""

import json
import os
import platform
import re
import subprocess
import sys

# Installed DIMMs never total exactly what the OS reports (firmware reserves
# some), so snap to the nearest real module size rather than recording 62.
COMMON_MEMORY_GB = [0.5, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256]


def run(*argv):
    """Command stdout, or "" if it is missing or fails. Never raises."""
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def read(path):
    try:
        with open(path, "r", errors="replace") as handle:
            return handle.read().strip().replace("\x00", "")
    except OSError:
        return ""


def snap_memory_gb(raw_gb):
    """Nearest plausible installed capacity to what the OS reported."""
    if not raw_gb:
        return None
    best = min(COMMON_MEMORY_GB, key=lambda size: abs(size - raw_gb))
    # Guard against a genuinely unusual size being rounded into a lie.
    return best if abs(best - raw_gb) / best < 0.2 else round(raw_gb, 1)


def collect_darwin(hw, notes):
    hw["cpu"] = run("sysctl", "-n", "machdep.cpu.brand_string")
    for key, field in (("hw.physicalcpu", "cores"), ("hw.logicalcpu", "threads")):
        value = run("sysctl", "-n", key)
        if value.isdigit():
            hw[field] = int(value)

    hertz = run("sysctl", "-n", "hw.cpufrequency_max") or run("sysctl", "-n", "hw.cpufrequency")
    if hertz.isdigit():
        hw["core_speed_ghz"] = round(int(hertz) / 1e9, 2)
    else:
        notes.append(
            "no clock available (Apple Silicon exposes none) - core_speed_ghz "
            "and boost_ghz have to come from published specs"
        )

    performance = run("sysctl", "-n", "hw.perflevel0.physicalcpu")
    efficiency = run("sysctl", "-n", "hw.perflevel1.physicalcpu")
    if performance.isdigit() and efficiency.isdigit():
        notes.append(
            "hybrid CPU: {} performance + {} efficiency cores - needs "
            "core_groups, one clock cannot describe it".format(performance, efficiency)
        )

    total = run("sysctl", "-n", "hw.memsize")
    if total.isdigit():
        hw["memory_gb"] = snap_memory_gb(int(total) / 1024**3)

    model = run("sysctl", "-n", "hw.model")
    if model:
        hw["model"] = model

    chipsets = re.findall(r"Chipset Model: (.+)", run("system_profiler", "SPDisplaysDataType"))
    if chipsets:
        hw["gpu"] = "; ".join(chip.strip() for chip in chipsets)


def collect_linux(hw, notes):
    cpuinfo = read("/proc/cpuinfo")
    model = re.search(r"^model name\s*:\s*(.+)$", cpuinfo, re.M)
    lscpu = run("lscpu")

    board_model = read("/proc/device-tree/model")
    if board_model:
        # Every Pi kernel reports "Hardware: BCM2835" regardless of the actual
        # SoC, so the board string is the only honest identifier here.
        hw["model"] = board_model
        core = re.search(r"^Model name:\s*(.+)$", lscpu, re.M)
        hw["cpu"] = core.group(1).strip() if core else (model.group(1).strip() if model else "")
        notes.append(
            "single-board computer: /proc/cpuinfo reports the legacy BCM2835 "
            "alias on every Pi - take the SoC from the board model"
        )
    elif model:
        hw["cpu"] = re.sub(r"\s+", " ", model.group(1)).strip()

    # nproc --all returns the kernel's CONFIG_NR_CPUS on some builds (Unraid
    # reports 64 on a 4-core box), so trust the enumerated CPUs instead.
    processors = len(re.findall(r"^processor\s*:", cpuinfo, re.M))
    if processors:
        hw["threads"] = processors
    per_socket = re.search(r"^Core\(s\) per socket:\s*(\d+)", lscpu, re.M)
    sockets = re.search(r"^Socket\(s\):\s*(\d+)", lscpu, re.M)
    if per_socket and sockets:
        hw["cores"] = int(per_socket.group(1)) * int(sockets.group(1))
    elif processors:
        hw["cores"] = processors

    threads_per_core = re.search(r"^Thread\(s\) per core:\s*(\d+)", lscpu, re.M)
    # Only worth flagging on x86: no ARM core here has SMT to begin with, so
    # 1 thread per core is unremarkable on a Pi and a real signal on a Xeon.
    is_x86 = re.search(r"Intel|AMD|Xeon", hw.get("cpu", ""), re.I)
    if threads_per_core and threads_per_core.group(1) == "1" and is_x86:
        notes.append(
            "1 thread per core on an x86 CPU - if the part supports SMT it is "
            "disabled in firmware, so its capability differs from what runs"
        )

    khz = read("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
    max_mhz = re.search(r"^CPU max MHz:\s*([\d.]+)", lscpu, re.M)
    if khz.isdigit():
        hw["core_speed_ghz"] = round(int(khz) / 1e6, 2)
    elif max_mhz:
        hw["core_speed_ghz"] = round(float(max_mhz.group(1)) / 1000, 2)

    meminfo = re.search(r"^MemTotal:\s*(\d+) kB", read("/proc/meminfo"), re.M)
    if meminfo:
        hw["memory_gb"] = snap_memory_gb(int(meminfo.group(1)) / 1024**2)

    vendor = read("/sys/class/dmi/id/board_vendor")
    board = read("/sys/class/dmi/id/board_name")
    if board:
        hw["motherboard"] = " ".join(part for part in (vendor, board) if part)
    product = read("/sys/class/dmi/id/product_name")
    # Unconfigured boards ship this placeholder in DMI.
    if product and product not in ("System Product Name", "To be filled by O.E.M.") and "model" not in hw:
        hw["model"] = product

    gpus = [
        re.sub(r"^[0-9a-f:.]+ ", "", line).split(": ", 1)[-1]
        for line in run("lspci").splitlines()
        if re.search(r"VGA compatible controller|3D controller", line)
    ]
    if gpus:
        hw["gpu"] = "; ".join(re.sub(r"\s*\(rev [0-9a-f]+\)$", "", gpu) for gpu in gpus)


WINDOWS_PROBE = r"""
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$gpus = @(Get-CimInstance Win32_VideoController |
    Where-Object { $_.Name -notmatch 'Microsoft Basic|Remote|Virtual' })
$board = Get-CimInstance Win32_BaseBoard
$modules = @(Get-CimInstance Win32_PhysicalMemory)
[pscustomobject]@{
  cpu = $cpu.Name.Trim()
  cores = $cpu.NumberOfCores
  threads = $cpu.NumberOfLogicalProcessors
  base_mhz = $cpu.MaxClockSpeed
  gpu = (@($gpus | ForEach-Object { $_.Name.Trim() }) -join '; ')
  motherboard = ($board.Manufacturer.Trim() + ' ' + $board.Product.Trim())
  memory_bytes = ($modules | Measure-Object -Property Capacity -Sum).Sum
} | ConvertTo-Json -Compress
"""


def collect_windows(hw, notes):
    payload = run("powershell", "-NoProfile", "-NonInteractive", "-Command", WINDOWS_PROBE)
    match = re.search(r"\{.*\}", payload, re.S)
    if not match:
        notes.append("could not query WMI through powershell")
        return
    data = json.loads(match.group(0))
    for source, field in (("cpu", "cpu"), ("cores", "cores"), ("threads", "threads")):
        if data.get(source):
            hw[field] = data[source]
    if data.get("base_mhz"):
        hw["core_speed_ghz"] = round(data["base_mhz"] / 1000, 2)
        notes.append(
            "Win32_Processor.MaxClockSpeed is the BASE clock, not turbo - "
            "boost_ghz still has to come from the vendor spec"
        )
    if data.get("memory_bytes"):
        hw["memory_gb"] = snap_memory_gb(data["memory_bytes"] / 1024**3)
    for field in ("gpu", "motherboard"):
        if data.get(field):
            hw[field] = re.sub(r"\s+", " ", str(data[field])).strip()
    board = str(data.get("motherboard", ""))
    if "Micro-Star" in board:
        hw["motherboard"] = board.replace("Micro-Star International Co., Ltd.", "MSI").strip()


def collect():
    system = platform.system().lower()
    hardware, notes = {}, []
    if system == "darwin":
        collect_darwin(hardware, notes)
    elif system == "linux":
        collect_linux(hardware, notes)
    elif system == "windows":
        collect_windows(hardware, notes)
    else:
        notes.append("unsupported platform: {}".format(system))

    name = (os.environ.get("COMPUTERNAME") or platform.node() or "").split(".")[0]
    ordered = [
        "cpu", "cores", "threads", "core_speed_ghz",
        "memory_gb", "gpu", "motherboard", "model",
    ]
    return {
        "name": name,
        "os": {"darwin": "macos"}.get(system, system),
        "hardware": {k: hardware[k] for k in ordered if hardware.get(k) not in (None, "")},
        "notes": notes,
    }


def main():
    indent = None if "--compact" in sys.argv[1:] else 2
    print(json.dumps(collect(), indent=indent))
    return 0


if __name__ == "__main__":
    sys.exit(main())
