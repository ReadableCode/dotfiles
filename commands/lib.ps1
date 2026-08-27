# Step functions for dotfiles commands (windows). Dot-sourced by cmdr.
# Same contract as lib.sh: <step> applies, <step>_check is read-only and
# exits nonzero on drift. cmdr sets $env:CMDR_REPO_DIR / $env:CMDR_GIT_DIR.

function dotfiles_pull {
    git -C $env:CMDR_REPO_DIR pull --ff-only
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARNING: dotfiles pull failed (offline or diverged) - resolve manually in $env:CMDR_REPO_DIR"
    }
    exit 0
}

function dotfiles_pull_check {
    git -C $env:CMDR_REPO_DIR fetch --quiet
    $behind = git -C $env:CMDR_REPO_DIR rev-list --count "HEAD..@{u}"
    if ([int]$behind -gt 0) {
        Write-Host "dotfiles: $behind commit(s) behind origin"
        exit 1
    }
    Write-Host "dotfiles: up to date"
    exit 0
}

function configs_deploy {
    Set-Location $env:CMDR_REPO_DIR
    uv run python src/deploy_configs.py
    exit $LASTEXITCODE
}

function configs_deploy_check {
    Set-Location $env:CMDR_REPO_DIR
    uv run python src/deploy_configs.py status
    exit $LASTEXITCODE
}

function packages_upgrade {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget upgrade --all --accept-source-agreements --accept-package-agreements
    } elseif (Get-Command choco -ErrorAction SilentlyContinue) {
        choco upgrade all -y
    } else {
        Write-Host "neither winget nor choco found, skipping package upgrades"
    }
    exit 0
}

function packages_upgrade_check {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        # winget prints a table of upgradable packages; anything beyond the
        # header/separator/summary rows counts as drift.
        $out = winget upgrade | Out-String
        Write-Host $out
        $lines = @($out -split "`n" | Where-Object { $_ -match '\S' })
        if ($lines.Count -gt 3) { exit 1 }
        exit 0
    } elseif (Get-Command choco -ErrorAction SilentlyContinue) {
        choco outdated
        exit $LASTEXITCODE
    }
    Write-Host "no package manager to check"
    exit 0
}

function sysinfo {
    fastfetch
}

# demo_hello only: demo_tick and demo_done are deliberately absent here so
# `cmdr doctor demo` has real coverage drift to show.
function demo_hello {
    Write-Host "hello from $env:COMPUTERNAME (windows)"
}
