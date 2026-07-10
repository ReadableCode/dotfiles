#!/bin/bash
# Claude Code status line: model | dir  branch(*dirty)
# Receives session JSON on stdin; deployed to ~/.claude/statusline.sh.
input=$(cat)
model=$(echo "$input" | jq -r '.model.display_name // .model.id // "?"')
dir=$(echo "$input" | jq -r '.workspace.current_dir // .cwd // "?"')

git_part=""
branch=$(git -C "$dir" branch --show-current 2>/dev/null)
if [ -n "$branch" ]; then
    dirty=""
    [ -n "$(git -C "$dir" status --porcelain 2>/dev/null | head -1)" ] && dirty="*"
    git_part="  ${branch}${dirty}"
fi

printf '%s | %s%s' "$model" "${dir/#$HOME/~}" "$git_part"
