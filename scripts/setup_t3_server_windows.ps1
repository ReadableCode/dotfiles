# Headless T3 Code server setup for a Windows box, linked via T3 Connect.
# Run ON the Windows machine (locally or over SSH):
#   powershell -ExecutionPolicy Bypass -File setup_t3_server_windows.ps1
# What it does (idempotent, safe to re-run):
#   1. verifies Node meets T3's requirement (^22.16 || ^23.11 || >=24.10)
#   2. installs t3@<Version> globally (match the desktop app version)
#   3. registers a logon scheduled task running `t3 serve` (loopback only -
#      T3 Connect's relay client handles reachability, so no 0.0.0.0 bind and
#      no firewall rule), output captured to ~\.t3\server.log
#   4. runs `t3 connect link --headless` in YOUR console: it installs the
#      cloudflared relay client if needed, prints an OAuth URL to open in a
#      browser, and waits for the authorization code shown after sign-in -
#      paste it at the prompt (works over SSH; stdin passes through)
#   5. restarts the serve task so the link takes effect ("on next start")
# Afterwards the environment appears under the same T3 account in the desktop
# app. Check state anytime with: t3 connect status
# See docs/setup_t3_code.md.

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

# 3. Logon task (survives SSH disconnect, unlike a shell-started serve).
#    The serve line lives in a wrapper .cmd so the log redirect survives
#    scheduled-task argument quoting.
$logDir = Join-Path $env:USERPROFILE ".t3"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "server.log"
$wrapper = Join-Path $logDir "t3serve.cmd"
Set-Content -Path $wrapper -Value "`"$t3`" serve --port $Port >> `"$log`" 2>&1" -Encoding Ascii
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

# 4. Link this machine to your T3 account (interactive: open the printed URL,
#    sign in, paste the authorization code back at the prompt)
& $t3 connect link --headless

# 5. The link activates on next server start
Stop-ScheduledTask -TaskName "t3code-server" -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName "t3code-server"
Write-Output "Serve task restarted - environment should now appear under your T3 account."
& $t3 connect status
