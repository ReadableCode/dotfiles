# Open every file this branch changed (relative to origin's default branch)
# in VS Code - the openbranchdiffs shell function, run from the shell's cwd,
# which cmdr inherits. The check lists the files instead of opening them and
# exits 1 when there are any, so `cmdr branchdiffs --check` doubles as
# "what did I touch on this branch".
description: open this branch's changed files in vs code
order: 240
platforms: darwin linux windows
steps:
  branch_diffs requires=git,code
