# Headless T3 Code server setup for a Windows box, reachable over Tailscale
# Serve by default (or via T3 Connect with -T3ConnectLink, slot permitting).
# Run ON the Windows machine (locally or over SSH):
#   powershell -ExecutionPolicy Bypass -File setup_t3_server_windows.ps1
# Deploy configs FIRST - this script no longer generates the two files that
# decide how the server runs, it registers what deploy_configs.py put in
# ~\.t3 (entries t3code_server_launcher / t3code_server_task):
#   uv run python src/deploy_configs.py
# What it does (idempotent, safe to re-run):
#   1. reads the deployed ~\.t3\t3serve.cmd for the port and whether Tailscale
#      Serve is on - that file is the single source of truth for the serve
#      command line, so they are not parameters here
#   2. verifies Node meets T3's requirement (^22.16 || ^23.11 || >=24.10)
#   3. installs t3@latest globally (-Version to hold a machine back)
#   4. registers the boot/logon scheduled task from the deployed
#      ~\.t3\t3code-server-task.xml (loopback only - Tailscale Serve / the
#      relay dial loopback, so no 0.0.0.0 bind and no firewall rule), output
#      captured to ~\.t3\server.log. Restarts a running server onto the
#      deployed definition, which interrupts live threads on that machine.
#   5. default: prints the tailnet https URL + single-use pairing token for
#      the desktop's Remote link dialog. With -T3ConnectLink: runs
#      `t3 connect link --headless` in YOUR console instead (OAuth URL +
#      code prompt; works over SSH) and restarts the task to activate it -
#      but note T3 Connect accounts are capped at 3 managed tunnels and the
#      relay 403s the link (with no error message) when they're used up.
# Check T3 Connect state anytime with: t3 connect status
# See docs/setup_t3_code.md.

param(
    # npm's stable tag. Nightlies ship under a separate `nightly` tag, so this
    # never picks one up. Pass an explicit version only to hold a machine at a
    # known-good release - see "Server version" in docs/setup_t3_code.md for
    # the one thing that couples servers to the repo (keybindings.json).
    [string]$Version = "latest",
    # Link to the T3 account instead of pairing over Tailscale (uses a
    # managed-tunnel slot; interactive OAuth in the console). Off by default
    # because of the 3-tunnel cap.
    [switch]$T3ConnectLink
)

$ErrorActionPreference = "Stop"

# 0. The deployed launcher and task definition. Both used to be generated
#    here, which left the two files that decide how the server runs outside
#    the manifest: invisible to `deploy_configs.py status`, and carrying
#    whatever Register-ScheduledTask defaults to - including the 72-hour
#    ExecutionTimeLimit that closed out RyzenWhite's run on 2026-08-17 after
#    the server OOMed, with nothing left to restart it.
$t3Dir = Join-Path $env:USERPROFILE ".t3"
$wrapper = Join-Path $t3Dir "t3serve.cmd"
$taskXmlPath = Join-Path $t3Dir "t3code-server-task.xml"
$log = Join-Path $t3Dir "server.log"
foreach ($needed in @($wrapper, $taskXmlPath)) {
    if (-not (Test-Path $needed)) {
        Write-Error "$needed is missing. Deploy it from the dotfiles clone first: uv run python src/deploy_configs.py"
    }
}
#    Anchor both reads to real statements - the file's own header comments
#    mention T3_PORT and --tailscale-serve, and a loose match would read those.
$serveLine = Get-Content $wrapper -Raw
$portMatch = [regex]::Match($serveLine, '(?m)^\s*set\s+"T3_PORT=(\d+)"')
if (-not $portMatch.Success) { Write-Error "No T3_PORT assignment found in $wrapper - is it the deployed launcher?" }
$Port = [int]$portMatch.Groups[1].Value
$TailscaleServe = $serveLine -match '(?m)^\s*call\b.*--tailscale-serve'
Write-Output "Launcher $wrapper -> port $Port, tailscale-serve $TailscaleServe"

# 1. Tailscale must be up before enabling --tailscale-serve
if ($TailscaleServe) {
    if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) {
        Write-Error "tailscale not found on PATH but $wrapper serves with --tailscale-serve. Install/login tailscale first, or drop that flag from the launcher in the repo and re-deploy."
    }
    $tsStatus = tailscale status 2>&1 | Select-Object -First 1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "tailscale is installed but not up ($tsStatus). Log it in first."
    }
}

# 2. Node check - install via the app lists (choco/winget), not ad-hoc here
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

# 3. Install the server CLI. Unpinned by default, same as the desktop app
#    (brew/winget track their own latest). The one thing that couples the
#    server to this repo is the deployed application_configs/t3code/
#    keybindings.json: a server OLDER than the version those bindings came from
#    logs "ignoring invalid keybinding entry", a NEWER one merges its own
#    defaults in and replaces the deployed symlink with a plain file. So the
#    bare file tracks the OLDEST server running anywhere - after moving a
#    machine up, check the others before promoting new defaults into it.
npm install -g "t3@$Version"
$t3 = Join-Path $env:APPDATA "npm\t3.cmd"
if (-not (Test-Path $t3)) { Write-Error "t3 CLI not found at $t3 after install." }
# Report what npm actually resolved - with no pin, that is the only record of
# which version this box is now on.
$installed = (npm ls -g --depth 0 t3 2>$null | Select-String -Pattern "t3@\S+").Matches.Value
Write-Output "Installed $installed (check the other servers before promoting new default keybindings)."

# Legacy cleanup: the first version of this script opened an inbound firewall
# rule; loopback + Tailscale Serve/relay needs none, so drop it if present.
Get-NetFirewallRule -DisplayName "t3code-server" -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule

# 4. Boot/logon task (survives SSH disconnect, unlike a shell-started serve).
#    Registered from the deployed XML - Task Scheduler keeps its own copy in
#    the registry, so this import is the only way a repo file can own the
#    definition. The wrapper .cmd it points at is deployed too, and exists so
#    the log redirect survives scheduled-task argument quoting (and now so the
#    serve restarts itself when it dies).
$taskXml = (Get-Content $taskXmlPath -Raw).
    Replace("__T3_TASK_USER__", "$env:USERDOMAIN\$env:USERNAME").
    Replace("__T3_SERVE_CMD__", $wrapper)
# -Xml hands the scheduler a UTF-16 string, so whatever the declaration claims
# the bytes were is a lie by then: leaving `encoding="UTF-8"` on it fails with
# "The task XML is malformed. (1,40)::ERROR: unable to switch the encoding"
# (HRESULT 0x8004131a). Drop the declaration - the XML is valid without one,
# and the repo file keeps a declaration that matches its actual bytes.
$taskXml = [regex]::Replace($taskXml, '^\s*<\?xml[^>]*\?>', '')
Register-ScheduledTask -TaskName "t3code-server" -Xml $taskXml -Force | Out-Null
# Re-registering leaves any running instance alone, and MultipleInstances is
# IgnoreNew, so the old serve would keep the port. Stop then start to put the
# deployed definition into effect now - this kills live threads on this box.
Stop-ScheduledTask -TaskName "t3code-server" -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName "t3code-server"
Write-Output "Scheduled task t3code-server registered from $taskXmlPath and started (log: $log)"

# 5. Optional T3 Connect account link (interactive OAuth; consumes one of the
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
    # Surface what the desktop needs for Remote link pairing over the tailnet.
    # Wait for the server, then mint a FRESH token (the one in the log may be
    # stale/consumed on re-runs).
    $up = $false
    foreach ($i in 1..30) {
        if ((Test-NetConnection -ComputerName localhost -Port $Port -WarningAction SilentlyContinue).TcpTestSucceeded) {
            $up = $true; break
        }
        Start-Sleep -Seconds 2
    }
    if (-not $up) { Write-Error "Server never opened port $Port after 60s - check $log" }
    if ($TailscaleServe) { tailscale serve status }
    & $t3 auth pairing create
    Write-Output "Pair from the desktop: Add environment -> Remote link -> the https URL above + the token (single-use, short-lived; mint one per client with: t3 auth pairing create - fine over SSH)."
}
