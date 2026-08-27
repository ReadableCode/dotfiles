# Safe end-to-end demo: echo and sleep only, changes nothing.
# demo_tick and demo_done exist only in lib.sh ON PURPOSE - run
# `cmdr doctor demo` to see coverage drift reported instead of hidden.
description: harmless streaming demo (echo + sleep, changes nothing)
steps:
  demo_hello
  demo_tick
  demo_done
