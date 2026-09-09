# Step functions for dotfiles commands (windows). Dot-sourced by cmdr.
# Same contract as lib.sh: <step> applies, <step>_check is read-only and
# exits nonzero on drift. cmdr sets $env:CMDR_REPO_DIR / $env:CMDR_GIT_DIR.

function configs_deploy {
    # --problems: changes only, not the healthy/not-applicable census.
    Set-Location $env:CMDR_REPO_DIR
    uv run python src/deploy_configs.py --problems
    exit $LASTEXITCODE
}

function configs_deploy_check {
    Set-Location $env:CMDR_REPO_DIR
    uv run python src/deploy_configs.py status --problems
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

# --- pull (the gitpullall flow) ---

function repos_pull {
    # Exec the existing git_puller binary: pulls fan out in goroutines there.
    $bin = Join-Path $env:CMDR_GIT_DIR "dotfiles\go_apps\git_puller\git_puller.exe"
    & $bin -path $env:CMDR_GIT_DIR -r
    exit $LASTEXITCODE
}

function repos_pull_check {
    # Read-only twin of repos_pull: one background job per repo, mirroring
    # git_puller's fan-out. Reports repos behind their upstream.
    $repos = Get-ChildItem -Directory $env:CMDR_GIT_DIR |
        Where-Object { Test-Path (Join-Path $_.FullName ".git") }
    $jobs = foreach ($r in $repos) {
        Start-Job -ArgumentList $r.FullName, $r.Name -ScriptBlock {
            param($path, $name)
            git -C $path fetch --quiet 2>$null
            if ($LASTEXITCODE -ne 0) { "$name|0|fetch failed (offline or no remote)"; return }
            $behind = git -C $path rev-list --count "HEAD..@{u}" 2>$null
            if ([int]$behind -gt 0) { "$name|1|$behind commit(s) behind" }
        }
    }
    $results = @($jobs | Wait-Job | Receive-Job)
    $jobs | Remove-Job
    $drift = 0
    foreach ($line in $results) {
        $parts = $line -split '\|', 3
        Write-Host "  $($parts[0]): $($parts[2])"
        if ($parts[1] -eq '1') { $drift++ }
    }
    if ($drift -gt 0) {
        Write-Host "checked $($repos.Count) repos concurrently: $drift behind"
        exit 1
    }
    Write-Host "checked $($repos.Count) repos concurrently: all up to date"
    exit 0
}

function repos_clone {
    Set-Location $env:CMDR_REPO_DIR
    uv run python src/clone_repos.py
    exit $LASTEXITCODE
}

function repos_clone_check {
    # cmdr's built-in already knows the yaml and exits 1 on missing repos.
    & $env:CMDR_BIN repos ensure --check
    exit $LASTEXITCODE
}

function configs_prune {
    # --apply on purpose: the removals files are a committed list of paths
    # that must not exist, so every machine has to act on them.
    Set-Location $env:CMDR_REPO_DIR
    uv run python src/deploy_configs.py prune --apply
    exit $LASTEXITCODE
}

function configs_prune_check {
    # Bare prune is the dry run.
    Set-Location $env:CMDR_REPO_DIR
    uv run python src/deploy_configs.py prune
    exit $LASTEXITCODE
}

# --- calendar ---

function calendar_board {
    Set-Location $env:CMDR_REPO_DIR
    uv run python src/calendar_board.py
    exit $LASTEXITCODE
}

function calendar_board_check {
    Set-Location $env:CMDR_REPO_DIR
    uv run python src/calendar_board.py --once --days 1
    exit $LASTEXITCODE
}

# --- bookmarks ---

function bookmarks_export {
    if (-not (Test-Path (Join-Path $env:CMDR_GIT_DIR 'personal_credentials'))) {
        Write-Host "personal_credentials is not cloned here, nothing to export into"
        exit 0
    }
    Set-Location $env:CMDR_REPO_DIR
    uv run python src/chrome_bookmarks.py
    exit $LASTEXITCODE
}

function bookmarks_export_check {
    $repoCopy = Join-Path $env:CMDR_GIT_DIR 'personal_credentials\bookmarks\personal_bookmarks.json'
    if (-not (Test-Path $repoCopy)) {
        Write-Host "no repo copy at $repoCopy (personal_credentials not cloned, or never exported)"
        exit 0
    }
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("cmdr-bookmarks-" + [System.IO.Path]::GetRandomFileName())
    New-Item -ItemType Directory -Path $tmp | Out-Null
    Set-Location $env:CMDR_REPO_DIR
    uv run python src/chrome_bookmarks.py --output-dir $tmp | Out-Null
    if ($LASTEXITCODE -ne 0) { Remove-Item -Recurse -Force $tmp; exit 1 }
    $same = (Get-FileHash (Join-Path $tmp 'personal_bookmarks.json')).Hash -eq (Get-FileHash $repoCopy).Hash
    Remove-Item -Recurse -Force $tmp
    if ($same) { Write-Host "chrome bookmarks match the repo copy"; exit 0 }
    Write-Host "chrome has bookmark changes the repo copy lacks"
    exit 1
}

# --- branchdiffs ---

function Get-BranchChangedFiles {
    $root = git rev-parse --show-toplevel 2>$null
    if (-not $root) { Write-Host "not in a git repository: $PWD"; return $null }
    Set-Location $root
    git fetch -q
    $base = git symbolic-ref --short refs/remotes/origin/HEAD 2>$null
    if (-not $base) { $base = 'origin/master' }
    return @(git diff --name-only --diff-filter=d "$base...HEAD" | Where-Object { Test-Path $_ })
}

function branch_diffs {
    $files = Get-BranchChangedFiles
    if ($null -eq $files) { exit 1 }
    if ($files.Count -eq 0) { Write-Host "no files changed on this branch"; exit 0 }
    code @files
    exit $LASTEXITCODE
}

function branch_diffs_check {
    $files = Get-BranchChangedFiles
    if ($null -eq $files) { exit 1 }
    if ($files.Count -eq 0) { Write-Host "no files changed on this branch"; exit 0 }
    $files | ForEach-Object { Write-Host $_ }
    exit 1
}
