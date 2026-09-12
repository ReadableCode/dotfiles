# git_switch.ps1 - fuzzy-pick a branch and switch to it.
#
# Lists every branch, local and remote, most recently committed first, in fzf,
# with that branch's last ten commits as the preview. A leading origin/ is
# stripped before `git switch`, so picking a remote-only branch creates the
# local tracking branch. Git finds the repo itself, so this runs from any
# subdirectory of a checkout.
#
#   git_switch.ps1          pick a branch and switch to it
#   git_switch.ps1 --help   this text
#
# Esc aborts and changes nothing. Exits 1 when fzf is missing or this is not a
# git repository. The macOS/Linux twin is scripts/git_switch.sh.

$rest = @($args)

if ($rest.Count -gt 0 -and ($rest[0] -eq '--help' -or $rest[0] -eq '-h')) {
    Get-Content $PSCommandPath | Select-Object -First 13 |
        ForEach-Object { $_ -replace '^# ?', '' }
    exit 0
}

if (-not (Get-Command fzf -ErrorAction SilentlyContinue)) {
    Write-Host "git_switch: fzf is not installed"
    exit 1
}

git rev-parse --git-dir 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "git_switch: not a git repository: $PWD"
    exit 1
}

# A remote's HEAD pointer (refs/remotes/origin/HEAD) renders as the bare
# remote name, which is not a branch: `git switch origin` fails. Drop any row
# that is exactly a remote name.
$remotes = @(git remote)
$branch = git branch -a --sort=-committerdate --format='%(refname:short)' |
    ForEach-Object { $_ -replace '^origin/', '' } |
    Where-Object { $_ -ne 'HEAD' -and $remotes -notcontains $_ } |
    Select-Object -Unique |
    fzf --preview 'git log --oneline --color=always -10 {}' --ansi

# Empty means Esc or an empty branch list; neither is an error.
if (-not $branch) { exit 0 }

git switch $branch
