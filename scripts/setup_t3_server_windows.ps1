# Headless T3 Code server setup for a Windows box, reachable over Tailscale
# Serve by default (or via T3 Connect with -T3ConnectLink, slot permitting).
# Run ON the Windows machine (locally or over SSH):
#   powershell -ExecutionPolicy Bypass -File setup_t3_server_windows.ps1
# What it does (idempotent, safe to re-run):
#   1. verifies Node meets T3's requirement (^22.16 || ^23.11 || >=24.10)
#   2. installs t3@<Version> globally (match the desktop app version)
#   3. registers a boot/logon scheduled task running `t3 serve` (loopback
#      only - Tailscale Serve / the relay dial loopback, so no 0.0.0.0 bind
#      and no firewall rule), output captured to ~\.t3\server.log
#   4. default: prints the tailnet https URL + single-use pairing token for
#      the desktop's Remote link dialog. With -T3ConnectLink: runs
#      `t3 connect link --headless` in YOUR console instead (OAuth URL +
#      code prompt; works over SSH) and restarts the task to activate it -
#      but note T3 Connect accounts are capped at 3 managed tunnels and the
#      relay 403s the link (with no error message) when they're used up.
# Check T3 Connect state anytime with: t3 connect status
# See docs/setup_t3_code.md.

param(
    [string]$Version = "0.0.31",
    [int]$Port = 3773,
    # Expose over Tailscale Serve (HTTPS on the tailnet). This is the default
    # reachability path: T3 Connect accounts are capped at 3 managed tunnels,
    # and Tailscale needs no slot. Requires tailscale logged in on the box.
    [bool]$TailscaleServe = $true,
    # Link to the T3 account instead (uses a managed-tunnel slot; interactive
    # OAuth in the console). Off by default because of the 3-tunnel cap.
    [switch]$T3ConnectLink
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

# 3. Logon task (survives SSH disconnect, unlike a shell-started serve).
#    The serve line lives in a wrapper .cmd so the log redirect survives
#    scheduled-task argument quoting.
$logDir = Join-Path $env:USERPROFILE ".t3"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "server.log"
$wrapper = Join-Path $logDir "t3serve.cmd"
$serveArgs = "serve --port $Port"
if ($TailscaleServe) { $serveArgs += " --tailscale-serve" }
Set-Content -Path $wrapper -Value "`"$t3`" $serveArgs >> `"$log`" 2>&1" -Encoding Ascii
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $wrapper"
# S4U principal: runs without an interactive logon session or stored password
# (a default-principal task silently never starts when no one is logged on).
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U
$triggers = @(
    (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME),
    (New-ScheduledTaskTrigger -AtStartup)
)
Register-ScheduledTask -TaskName "t3code-server" -Action $action -Trigger $triggers `
    -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName "t3code-server"
Write-Output "Scheduled task t3code-server registered and started (log: $log)"

# 4. Optional T3 Connect account link (interactive OAuth; consumes one of the
#    account's 3 managed-tunnel slots - the relay 403s the link when they're
#    all in use, so Tailscale Serve is the default path instead).
if ($T3ConnectLink) {
    & $t3 connect link --headless
    # The link activates on next server start
    Stop-ScheduledTask -TaskName "t3code-server" -ErrorAction SilentlyContinue
    Start-ScheduledTask -TaskName "t3code-server"
    Write-Output "Serve task restarted - environment should now appear under your T3 account."
    & $t3 connect status
} else {
    # Surface what the desktop needs for Remote link pairing over the tailnet
    Start-Sleep -Seconds 5
    if ($TailscaleServe) { tailscale serve status }
    Select-String -Path $log -Pattern "Token:" | Select-Object -Last 1 | ForEach-Object Line
    Write-Output "Pair from the desktop: Add environment -> Remote link -> the https URL above + the token (single-use; mint more with: t3 pair)."
}
