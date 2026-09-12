# OS package updates for Windows: the `updatepackages` step, nothing more.
# winget first, then Chocolatey, each only when it is installed. Repo pulls and
# config deploys live in src/refresh_machine.py, which runs this between the
# pull and the deploy when called with --packages (the myupdater command). The
# macOS/Linux twin is scripts/my_updater.sh.
#
# Modes: no arguments is the full upgrade run and behaves exactly as it always
# did. --check is the read-only twin, listing what winget and choco would
# upgrade and exiting 1 when anything is outdated, so anything that only wants
# the answer can ask for it. --help prints the modes. The flags are spelled
# with two dashes, not PowerShell's own single dash, so both twins are called
# the same way.

function Show-Usage {
    Write-Host @'
usage: my_updater.ps1 [--check | --help]

  (no arguments)  Upgrade this machine's packages with winget and Chocolatey,
                  each only when it is installed.
  --check         Read-only: list what winget and Chocolatey would upgrade,
                  exit 1 when anything is outdated and 0 when nothing is.
  --help          This page.

The no-argument form is what myupdater runs, through
src/refresh_machine.py --packages. The macOS/Linux twin is scripts/my_updater.sh.
'@
}

$mode = "update"
foreach ($arg in $args) {
    switch ($arg) {
        "--check" { $mode = "check" }
        "--help"  { $mode = "help" }
        "-h"      { $mode = "help" }
        default {
            Write-Host "my_updater.ps1: unknown option '$arg'"
            Show-Usage
            exit 2
        }
    }
}

if ($mode -eq "help") {
    Show-Usage
    exit 0
}

if ($mode -eq "check") {
    $outdated = 0
    $managers = 0
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        $managers += 1
        Write-Host "checking winget..."
        # `winget upgrade` without --all only lists. --include-unknown keeps the
        # packages whose installed version winget cannot read, which are exactly
        # the ones that otherwise look current forever. The trailing summary
        # line is what says whether anything is upgradable; winget's exit code
        # is nonzero when nothing is, which is not a failure of this check.
        $report = (winget upgrade --include-unknown | Out-String)
        Write-Host $report.TrimEnd()
        if ($report -match '(\d+)\s+upgrades?\s+available') {
            $outdated += [int]$Matches[1]
        }
    }
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        $managers += 1
        Write-Host "checking chocolatey..."
        # --limit-output prints one `name|installed|available|pinned` line per
        # outdated package and nothing else, so counting lines is the answer.
        $lines = @(choco outdated --limit-output | Where-Object { $_ -match '\|' })
        foreach ($line in $lines) { Write-Host $line }
        $outdated += $lines.Count
    }
    if ($managers -eq 0) {
        Write-Host "neither winget nor chocolatey found, so there is nothing to check."
        exit 0
    }
    if ($outdated -gt 0) {
        Write-Host "$outdated package(s) outdated."
        exit 1
    }
    Write-Host "all packages are current."
    exit 0
}

if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host "updating via winget..."
    winget upgrade --all
}
if (Get-Command choco -ErrorAction SilentlyContinue) {
    Write-Host "updating via chocolatey..."
    choco upgrade all -y
}

# winget exits nonzero when some package has no applicable upgrade, which is
# not a failure of this step; the upgrade output above is the report.
exit 0
