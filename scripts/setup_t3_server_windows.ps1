# Headless T3 Code server setup for a Windows box (Remote-link environment).
# Run ON the Windows machine (locally or over SSH):
#   powershell -ExecutionPolicy Bypass -File setup_t3_server_windows.ps1
# What it does (idempotent, safe to re-run):
#   1. verifies Node meets T3's requirement (^22.16 || ^23.11 || >=24.10)
#   2. installs t3@<Version> globally (match the desktop app version)
#   3. opens an inbound firewall rule for the port
#   4. registers + starts a logon scheduled task running `t3 serve`, with
#      output captured to ~\.t3\server.log (a serve started over SSH dies
#      with the session - the task survives it)
#   5. waits for the port, then mints a SINGLE-USE pairing code and prints it
#      - paste it into the desktop's Add environment -> Remote link dialog
#      (host must be http://<lan-ip>:<port>, http:// prefix required).
# Need another code later (they're single-use, one per client device)?
#   t3 pair
# See docs/setup_t3_code.md - note this recipe is still unverified end-to-end.

param(
    [string]$Version = "0.0.31",
    [int]$Port = 3773
)

$ErrorActionPreference = "Stop"

# 1. Node check - install via the app lists (choco/winget), not ad-hoc here
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
    Write-Error "node not found on PATH. Install it via app_lists (choco/winget) first."
}
$v = (node -v).TrimStart("v").Split(".")
$major = [int]$v[0]; $minor = [int]$v[1]
$ok = ($major -ge 25) -or
      ($major -eq 24 -and $minor -ge 10) -or
      ($major -eq 23 -and $minor -ge 11) -or
      ($major -eq 22 -and $minor -ge 16)
if (-not $ok) {
    Write-Error "node $($v -join '.') is too old for T3 (needs ^22.16 || ^23.11 || >=24.10)."
}
Write-Output "node $($v -join '.') OK"

# 2. Install the server CLI, pinned to the desktop app's version
npm install -g "t3@$Version"
$t3 = Join-Path $env:APPDATA "npm\t3.cmd"
if (-not (Test-Path $t3)) { Write-Error "t3 CLI not found at $t3 after install." }

# 3. Firewall
if (-not (Get-NetFirewallRule -DisplayName "t3code-server" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName "t3code-server" -Direction Inbound `
        -Protocol TCP -LocalPort $Port -Action Allow | Out-Null
    Write-Output "Firewall rule added for TCP $Port"
} else {
    Write-Output "Firewall rule already present"
}

# 4. Logon task (survives SSH disconnect, unlike a shell-started serve)
$logDir = Join-Path $env:USERPROFILE ".t3"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "server.log"
$action = New-ScheduledTaskAction -Execute "cmd.exe" `
    -Argument "/c `"`"$t3`" serve --host 0.0.0.0 --port $Port >> `"$log`" 2>&1`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
Register-ScheduledTask -TaskName "t3code-server" -Action $action -Trigger $trigger -Force | Out-Null
Start-ScheduledTask -TaskName "t3code-server"
Write-Output "Scheduled task t3code-server registered and started (log: $log)"

# 5. Wait for the server, then mint a pairing code for this client
$up = $false
foreach ($i in 1..30) {
    if ((Test-NetConnection -ComputerName localhost -Port $Port -WarningAction SilentlyContinue).TcpTestSucceeded) {
        $up = $true; break
    }
    Start-Sleep -Seconds 2
}
if (-not $up) {
    Write-Error "Server never opened port $Port after 60s - check $log"
}

Write-Output ""
Write-Output "=== Pairing code (single-use - paste into Remote link dialog) ==="
& $t3 pair
Write-Output "=== Desktop host field: http://<this-machine-lan-ip>:$Port ==="
