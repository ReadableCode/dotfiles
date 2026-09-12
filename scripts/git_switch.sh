#!/usr/bin/env bash
# git_switch.sh - fuzzy-pick a branch and switch to it.
#
# Lists every branch, local and remote, most recently committed first, in fzf,
# with that branch's last ten commits as the preview. A leading origin/ is
# stripped before `git switch`, so picking a remote-only branch creates the
# local tracking branch. Git finds the repo itself, so this runs from any
# subdirectory of a checkout.
#
#   git_switch.sh          pick a branch and switch to it
#   git_switch.sh --help   this text
#
# Esc aborts and changes nothing. Exit 1 when fzf is missing or this is not a
# git repository.

set -u

usage() { sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; }

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
esac

command -v fzf >/dev/null 2>&1 || {
    echo "git_switch: fzf is not installed" >&2
    exit 1
}

git rev-parse --git-dir >/dev/null 2>&1 || {
    echo "git_switch: not a git repository: $PWD" >&2
    exit 1
}

# A remote's HEAD pointer (refs/remotes/origin/HEAD) renders as the bare
# remote name, which is not a branch: `git switch origin` fails. Drop any row
# that is exactly a remote name.
remotes=$(git remote)
branch=$(git branch -a --sort=-committerdate --format='%(refname:short)' \
    | sed 's|^origin/||' | grep -vx 'HEAD' | grep -vxF "$remotes" | awk '!seen[$0]++' \
    | fzf --preview 'git log --oneline --color=always -10 {}' --ansi)

# Empty means Esc or an empty branch list; neither is an error.
[ -n "$branch" ] || exit 0

git switch "$branch"
