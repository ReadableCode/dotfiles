# cmdr: the fleet CLI and TUI

`go_apps/cmdr` is one entry point for machine operations: the pulls, deploys
and package updates every machine runs, plus whatever the sibling repos
contribute. The design it follows is `plan_unified_cli_tui.md`; this is the
reference for using and extending it.

## Running it

The `cmdr` shell function (`.shared_aliases`, `powershell_aliases.ps1`)
builds the binary on first use and rebuilds it whenever the Go sources are
newer, installing a Go toolchain first if the machine has none
(`setup_go.md`). Nothing is committed or installed on PATH.

```bash
cmdr                          # the TUI: click a row to run it, c to check it
cmdr commands [--json]        # what was discovered and where it runs
cmdr doctor [command] [--json]
cmdr <command> [args...]      # show the plan, ask, apply
cmdr <command> --check        # read-only drift probe, exit 1 on drift
cmdr <command> --yes          # apply without the question
cmdr logs [command] [--list]  # run logs
cmdr fleet <command>          # the command's check on every inventory host
cmdr repos ensure [--check]   # built in: clone what this machine is entitled to
```

## Where commands come from

cmdr globs `<gitdir>/*/commands/*.cmd` on every start. Any sibling repo
joins by adding a `commands/` folder; dotfiles never learns its name. A
machine only holds the repos it is entitled to clone, so it only discovers
those commands, which is how client isolation falls out for free.

A `.cmd` file is one command: gating headers, then the ordered step names.

```
description: drive sync - mirror configured media onto a drive
order: 210                       # sort position in the list, default 1000
platforms: darwin linux windows  # optional; mac is an alias for darwin
hosts: ENVY ELITEDESK            # optional allow list, exclude_hosts blocks
steps:
  drive_sync requires=uv terminal
```

Step options: `requires=a,b` is a PATH lookup only (the core never probes
for privileges; some hosts email on every failed sudo), and `terminal` marks
a step that needs the real screen (its own TUI, a prompt).

What a step does lives next to the `.cmd` in `lib.sh` (macOS and Linux) and
`lib.ps1` (Windows): a function per step, plus `<step>_check`, its read-only
twin that exits nonzero on drift. The function name is the whole contract.
cmdr sources the lib and calls the function with these variables set:

| Variable | Meaning |
|----------|---------|
| `CMDR_REPO_DIR` | the repo holding the `.cmd` |
| `CMDR_GIT_DIR` | the folder holding every sibling repo |
| `CMDR_BIN` | this binary, for calling built-ins back (`repos ensure --check`) |
| `CMDR_LOG` | the run log being written |
| `CMDR_ARGC`, `CMDR_ARG1..N` | positional arguments given after the command name |

## The check/apply convention

Every command has the same three shapes: bare shows the plan and asks,
`--check` reports drift and changes nothing, `--yes` applies without asking.
`doctor` enforces the half the runner cannot: a step with no `_check`, a
check whose body runs `--apply`, a lib missing a step on one platform, a
`requires` binary absent on this host.

## Terminal steps

The TUI streams a normal run into a pane. A command with a `terminal` step
cannot be piped, so the TUI suspends, runs `cmdr <command> --yes` (or
`--check`) in the foreground, and resumes when it exits. Such a run ends by
holding its screen until enter, otherwise the alternate screen would wipe a
traceback the moment it appeared.

## Logs, kill, fleet

- **Logs**: every run writes `~/logs/cmdr/<command>-<mode>-<timestamp>.log`
  ending in a `result:` line (ok, drift, failed, killed). A terminal step's
  own output goes to the screen, so the log only notes it ran. `cmdr logs`
  lists the newest runs; `cmdr logs <command>` prints its latest log.
- **Kill**: in the TUI, `x` kills the running step and its children (it runs
  in its own process group), and ctrl+c kills then quits. The done screen
  says KILLED and names the log.
- **Fleet**: `cmdr fleet <command>` runs the check on every ssh-reachable
  inventory host except this one, eight at a time, through an interactive
  shell there so the `cmdr` shim (and its rebuild) applies. Hosts come from
  `src/ssh_aliases.py --format hosts`, so jumps, ports and users are the
  inventory's, implemented once. The table says ok, drift, failed,
  unreachable, or "no cmdr" (dotfiles not deployed for that user); each
  host's full output is in `~/logs/cmdr/fleet-<command>-<host>-*.log`. Check
  only on purpose: nothing applies fleet-wide from one keypress.
