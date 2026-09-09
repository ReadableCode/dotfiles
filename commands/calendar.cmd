# The calendar board (src/calendar_board.py) as a cmdr command: a Textual
# TUI, so the step is terminal and cmdr's TUI hands the screen over. The
# check is the board's static render of today, which proves every source
# still authenticates without opening the TUI.
description: calendar board - google and outlook day columns side by side
order: 220
platforms: darwin linux windows
steps:
  calendar_board requires=uv terminal
