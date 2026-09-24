# Put the winget OpenSSH back in charge of the sshd service.
#
# Run by src/app_removals.py right after it removes the in-box OpenSSH server
# feature (the `after:` of inbox_openssh_server in app_removals.yaml). Both
# copies register a service named sshd, and removing the feature deletes that
# service even when the winget copy in C:\Program Files\OpenSSH had taken it
# over: seen on RyzenWhite 2026-09-24, where the removal left no sshd and no
# listener on port 22. The ssh session that ran the removal survives it, so
# running this in the same session restores ssh before that session ends.
#
# Safe to run any time: every step checks first and changes only what is
# wrong. Exits 1 unless sshd ends up running from C:\Program Files\OpenSSH.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$installDir = 'C:\Program Files\OpenSSH'

function Get-Sshd {
    Get-CimInstance Win32_Service -Filter "Name='sshd'"
}

if (-not (Test-Path (Join-Path $installDir 'sshd.exe'))) {
    Write-Host "  $installDir\sshd.exe is missing; reinstalling Microsoft.OpenSSH.Preview"
    winget install --id Microsoft.OpenSSH.Preview --exact --force --disable-interactivity `
        --accept-package-agreements --accept-source-agreements
}

$service = Get-Sshd
if (-not $service -or $service.PathName -notlike "*$installDir*") {
    Write-Host "  registering the sshd service from $installDir"
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $installDir 'install-sshd.ps1')
}

Set-Service sshd -StartupType Automatic
Start-Service sshd

$open = Get-NetFirewallPortFilter -Protocol TCP -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -contains '22' } |
    Get-NetFirewallRule |
    Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Allow' }
if (-not $open) {
    Write-Host "  no enabled inbound rule for port 22; adding one"
    New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound `
        -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
}

$service = Get-Sshd
Write-Host "  sshd: $($service.PathName) $($service.State) $($service.StartMode)"
if (-not $service -or $service.State -ne 'Running' -or $service.PathName -notlike "*$installDir*") {
    Write-Host "  sshd is not running from $installDir; fix it at the console"
    exit 1
}
exit 0
