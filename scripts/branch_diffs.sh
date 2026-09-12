#!/usr/bin/env bash
# branch_diffs.sh - the files this branch changed, opened in the editor.
#
# Compares against the merge-base with the default branch (base...HEAD), so a
# change that only happened upstream is never included, and --diff-filter=d
# drops files this branch deleted. Runs from anywhere inside a checkout.
#
#   branch_diffs.sh          open every changed file in vs code
#   branch_diffs.sh --list   print the paths, open nothing
#   branch_diffs.sh --help   this text
#
# Exit 1 when this is not a git repository. An empty list is not an error.

set -u

usage() { sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; }

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
esac

root=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "branch_diffs: not a git repository: $PWD" >&2
    exit 1
}
cd "$root" || exit 1

git fetch -q
base=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/master)

files=()
while IFS= read -r f; do
    [ -e "$f" ] && files+=("$f")
done < <(git diff --name-only --diff-filter=d "$base"...HEAD)

if [ ${#files[@]} -eq 0 ]; then
    echo "no files changed on this branch relative to $base"
    exit 0
fi

if [ "${1:-}" = "--list" ]; then
    printf '%s\n' "${files[@]}"
    exit 0
fi

if ! command -v code >/dev/null 2>&1; then
    echo "branch_diffs: vs code (code) is not on PATH; use --list" >&2
    exit 1
fi
code "${files[@]}"
