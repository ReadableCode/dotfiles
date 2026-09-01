# ensure_go.ps1 - resolve a usable Go toolchain on this machine, installing one
# if there is none. The Windows counterpart of scripts/ensure_go.sh.
#
# The only thing written to the success stream is the full path to go.exe, so a
# caller can use it directly:
#
#   $go = & scripts\ensure_go.ps1
#   if ($LASTEXITCODE -eq 0) { & $go build . }
#
# Progress goes to the host, not the pipeline. Exit 0 = a path was emitted.
#
# Usage:
#   .\ensure_go.ps1             resolve, installing if needed
#   .\ensure_go.ps1 -Check      resolve only, never install (exit 1 = missing)
#   .\ensure_go.ps1 -Quiet      no progress chatter (failures still print)

[CmdletBinding()]
param(
    [switch]$Check,
    [switch]$Quiet
)

# go_apps/*/go.mod all declare `go 1.26.x`. A toolchain from 1.21 onward
# downloads a newer one on demand (GOTOOLCHAIN=auto is the default), so 1.21 is
# the floor; anything older cannot build these modules and is treated as absent.
$script:MinVersion = [version]'1.21'

function Say  { param($m) if (-not $Quiet) { Write-Host "ensure_go: $m" -ForegroundColor DarkGray } }
function Warn { param($m) Write-Host "ensure_go: $m" -ForegroundColor Yellow }

function Get-GoVersion {
    # Parses "go version go1.26.7 windows/amd64"; $null when the exe will not run.
    param([string]$Path)
    try {
        $raw = & $Path version 2>$null
    } catch {
        return $null
    }
    if ($raw -match 'go(\d+)\.(\d+)') {
        return [version]("{0}.{1}" -f $Matches[1], $Matches[2])
    }
    return $null
}

function Find-Go {
    # PATH first, then the install roots that are commonly NOT on PATH - the
    # msi lands in Program Files and does not reach an already-open shell, and
    # chocolatey's own go shim lives under its tools dir.
    $candidates = @()
    $onPath = Get-Command go.exe -ErrorAction SilentlyContinue
    if ($onPath) { $candidates += $onPath.Source }
    $candidates += @(
        (Join-Path $env:ProgramFiles 'Go\bin\go.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Go\bin\go.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Go\bin\go.exe'),
        'C:\Go\bin\go.exe',
        (Join-Path $env:ChocolateyInstall 'lib\golang\tools\go\bin\go.exe')
    )
    foreach ($candidate in $candidates) {
        if (-not $candidate) { continue }
        if (-not (Test-Path -LiteralPath $candidate)) { continue }
        $version = Get-GoVersion $candidate
        if ($version -and $version -ge $script:MinVersion) { return $candidate }
    }
    return $null
}

function Install-Go {
    # Out-Host on every installer, because the success stream here belongs to
    # the caller: winget and choco both narrate to stdout, and without this the
    # caller gets a package list glued onto the front of the go path.
    #
    # winget first: it needs no elevated shell (it raises its own UAC prompt),
    # whereas choco silently does nothing useful from an unelevated one.
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Say "installing GoLang.Go with winget"
        winget install --id GoLang.Go --exact --silent --accept-package-agreements --accept-source-agreements | Out-Host
        if ($LASTEXITCODE -eq 0) { return }
        Warn "winget install failed (exit $LASTEXITCODE)"
    }
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        Say "installing golang with chocolatey"
        choco install golang -y | Out-Host
        if ($LASTEXITCODE -eq 0) { return }
        Warn "choco install failed (exit $LASTEXITCODE)"
    }
    Warn "neither winget nor chocolatey is available - install go from https://go.dev/dl/"
}

# --- main ---------------------------------------------------------------

$go = Find-Go
if ($go) { $go; exit 0 }

if ($Check) {
    Warn "no go toolchain (>= $script:MinVersion) found"
    exit 1
}

Say "no go toolchain found on $env:COMPUTERNAME - installing one"
Install-Go

# An installer that just extended the machine PATH did not touch this process,
# so re-read it before looking again.
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
            [Environment]::GetEnvironmentVariable('Path', 'User')

$go = Find-Go
if ($go) {
    Say "using $go ($(& $go version))"
    $go
    exit 0
}

Warn "could not install go automatically - see docs/setup_go.md"
exit 1
