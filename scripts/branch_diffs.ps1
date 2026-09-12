# branch_diffs.ps1 - the files this branch changed, opened in the editor.
#
# Compares against the merge-base with the default branch (base...HEAD), so a
# change that only happened upstream is never included, and --diff-filter=d
# drops files this branch deleted. Runs from anywhere inside a checkout.
#
#   branch_diffs.ps1          open every changed file in vs code
#   branch_diffs.ps1 --list   print the paths, open nothing
#   branch_diffs.ps1 --help   this text
#
# Exits 1 when this is not a git repository. An empty list is not an error.

$rest = @($args)

if ($rest.Count -gt 0 -and ($rest[0] -eq '--help' -or $rest[0] -eq '-h')) {
    Get-Content $PSCommandPath | Select-Object -Skip 1 -First 10 |
        ForEach-Object { $_ -replace '^# ?', '' }
    exit 0
}

$repoRoot = git rev-parse --show-toplevel 2>$null
if (-not $repoRoot) {
    Write-Host "branch_diffs: not a git repository: $PWD"
    exit 1
}
Set-Location -LiteralPath $repoRoot

git fetch -q

$base = git symbolic-ref --short refs/remotes/origin/HEAD 2>$null
if (-not $base) { $base = 'origin/master' }

# Test-Path drops paths renamed away on this branch.
$changed = git diff --name-only --diff-filter=d "$base...HEAD" | Where-Object { Test-Path -LiteralPath $_ }

if (-not $changed) {
    Write-Host "no files changed on this branch relative to $base"
    exit 0
}

if ($rest.Count -gt 0 -and $rest[0] -eq '--list') {
    $changed | ForEach-Object { $_ }
    exit 0
}

if (-not (Get-Command code -ErrorAction SilentlyContinue)) {
    Write-Host "branch_diffs: vs code (code) is not on PATH; use --list"
    exit 1
}
code @($changed)
