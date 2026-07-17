#!/bin/bash
mkdir -p ~/.claude
cat > ~/.claude/settings.json <<'EOF'
{
  "attribution": {
    "commit": "",
    "pr": "",
    "sessionUrl": false
  }
}
EOF
git config --global commit.gpgsign false