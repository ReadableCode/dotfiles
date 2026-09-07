# Unified CLI and TUI (design plan)

One entry point for machine operations, replacing the scattered aliases,
functions, and remembered script invocations. Not built yet: this is the
agreed design, written down before any code exists.

Scope is deliberately narrow. This covers the fleet-operations layer
(`gitpullall`, `myupdater`, config deploys, repo cloning, setup scripts). It
does not touch the web apps, Streamlit sites, or portfolio sites.

**Building this is a teaching exercise, not a delivery.** Read
[How I want to build this](#how-i-want-to-build-this-working-agreement)
before writing any code.

## The problem

`application_configs/bash/.shared_aliases` is 349 lines.
`application_configs/powershell/powershell_aliases.ps1` is 650 lines. They
implement the same command set twice, in two languages. `gitpullall` and
`myupdater` each exist as both a bash function and a PowerShell function.

They have already drifted, repeatedly. For months the bash `my_updater.sh`
deployed configs after package updates while the PowerShell `myupdater`
deployed before them; worse, both myupdaters pulled **only dotfiles** before
deploying, even though the deploy reads manifests and payloads from every
sibling `*_credentials` repo. That was hand-aligned in 2026-08 (both shells
now compose the same `pullrepos` → `clonerepos` → `updatepackages` →
`deployconfigs` → prune steps), but nothing stops the next drift — the same
sequence still exists twice, once per language.

One more gap from the same cause: neither implementation can report what is
outdated without also upgrading it.

No amount of discipline fixes two implementations. The fix is one
implementation with the platform-specific parts confined to where they
genuinely belong.

## The shape

```
        one binary
       /          \
    CLI          TUI          same command registry, no command
       \          /           registered twice
    core: discovery, gating, ordering, exec, output
             |
   commands in their native languages
   (bash functions, PowerShell functions, Python scripts)
```

**The core knows how to find and run commands. It never knows what they do.**

That is the one rule. The moment the core contains anything that understands
what a config link is, what a repo is for, or how a package manager works,
the design is broken.

The core owns: command registry, discovery, host/platform/context gating,
step ordering, subprocess execution, streamed output, failure policy, the
check/apply convention, and the TUI.

## Commands stay in their own languages

No config DSL, no generated shell. Bash stays bash and PowerShell stays
PowerShell, written the way those languages are meant to be written.

The only shared artifact is a list of step names in order:

```
update:
  dotfiles_pull
  configs_deploy
  packages_upgrade
  tools_upgrade
```

**The function name is the contract.** What `packages_upgrade` means on
darwin is whatever the bash function does (brew). On Windows it is whatever
the PowerShell function does (winget, choco). Nothing translates, nothing
generates.

The runner sources the platform lib and calls the function.

### What this fixes, and what it does not

Ordering can no longer drift, because it exists once.

Coverage still can: bash might define `tools_upgrade` and PowerShell might
not. But it becomes **visible** rather than silent, because the runner can
enumerate declared steps and probe each lib (`declare -F` in bash,
`Get-Command -CommandType Function` in PowerShell):

```
$ <cli> doctor update
darwin   ok
windows  missing: tools_upgrade
linux    missing: tools_upgrade, sysinfo
```

Drift becomes detectable. That is the most that is achievable without
generating code, and generating code is the thing being avoided.

## The check/apply convention

Universal, not per command:

- bare invocation — show the plan, ask
- `--check` — report drift, change nothing, exit nonzero if drift exists
- `--yes` — apply without prompting

This makes "enumerate, confirm, then act" the shape of every command rather
than a rule to remember. `<cli> update --check` across the fleet answers what
is outdated everywhere, which no current script can do.

**Constraint:** a step's `requires` check must be a PATH lookup, never a
privilege probe. Some hosts email on every failed sudo, so nothing in the
core may ever test whether it could escalate. A step needing root declares
it and either runs or is skipped with a message.

## Gating reuses the existing vocabulary

Commands are gated by the same rules as manifest entries and
`personal_repos.yaml`: hosts allow list, `exclude_hosts` block list,
platforms, variants. One scoping model across configs, repos, and commands.

Context isolation falls out for free. A machine only has the credentials
repos it is entitled to, so it only discovers those commands.

## Discovery and bootstrap

Commands are discovered by globbing sibling repos on the machine, the same
way deploy manifests and `personal_repos.yaml` are already discovered. A repo
contributes commands without dotfiles knowing it exists.

Two bootstrap rules:

- `repos ensure` is **built into the core**, not discovered, so a fresh
  machine can clone before anything else exists.
- Discovery must tolerate finding zero sibling repos.

## Language: Go

The startup difference, measured on an M4 Mac with a warm cache:

| | per invocation |
| --- | --- |
| bare `python3 -c pass` | ~24ms |
| `uv run python -c pass` | ~62ms |
| `uv run` + typical imports | ~50ms |
| Go binary | single-digit ms |

At 40 invocations a day that saves about two seconds total, so the argument
is perceptual, not throughput: sub-10ms reads as instant, 60ms reads as a
program launching. Windows will be worse (slower process creation, Defender
scanning each launch, portable WinPython on locked-down machines).

**The deciding argument is bootstrap ordering.** `setup python` cannot be
written in Python. The core has to run before any interpreter exists on the
machine, which rules out a Python core regardless of startup cost.

Go execs Python, bash, and PowerShell without ceremony, so nothing gets
rewritten. `deploy_configs.py`, `clone_repos.py`, `deploy_map.py`,
`host_facts.py`, `ping_hosts.py`, `ssh_aliases.py`, `status_board.py`, and
`ticket_pr.py` all stay as they are and get invoked.

There is precedent in the repo: `go_apps/git_puller` is 327 lines of Go doing
adjacent work. Both existing Go apps now carry their own `go.mod`
(`github.com/ReadableCode/dotfiles/go_apps/<app>`); the runner follows the
same one-module-per-app pattern rather than a shared module, since it shares
no code with them.

## Distribution: releases, not committed binaries

`go_apps/git_puller` currently commits five platform binaries totalling
14.4MB, against a 28MB `.git`. Every rebuild adds new blobs permanently, in a
public repo cloned to every machine. The runner should not repeat that.

Ship GitHub Releases with per-platform artifacts plus a short install script.
The binary contains nothing personal, which is exactly what lets it be a
public release; it discovers private repos at runtime.

**Expect Gatekeeper.** An unsigned binary downloaded from Releases is
quarantined on macOS. Options, cheapest first: have the install script run
`xattr -d com.apple.quarantine`, distribute via a brew tap that builds from
source, or notarize with an Apple Developer account. Windows SmartScreen
warns but does not block.

**One artifact, two modes.** No arguments opens the TUI. Arguments run the
CLI path. If a new command ever fails to appear in both, the design broke.

**No daemon.** Everything is on demand.

## `setup python` as the worked example

The four install paths already documented in `setup_python.md` and
`setup_python_portable.md`, tried in order, reporting which one won:

```
darwin/linux:  brew install uv
               ↓ fail
               curl -LsSf https://astral.sh/uv/install.sh | sh

windows:       irm https://astral.sh/uv/install.ps1 | iex
               ↓ fail (execution policy / no admin)
               choco install uv
               ↓ fail
               WinPython portable → %USERPROFILE%\userapps\WPy64-<ver>\
                 python.exe -m pip install uv

then all:      uv python install <version>
windows only:  PATH fix so bare `python` does not hit the Store shim
```

Do not try to *detect* a locked-down machine. Detection of corporate policy
from the outside is guesswork. Try the paths in order and fall back; the
machine reveals what it is by which step succeeds. `--check` reports which
path it would take without changing anything.

## Docs and code

Neither is generated from the other. Setup docs stop listing commands and
start saying "run `<cli> setup python`; here is the order it tries and why
each fallback exists." Steps live in one place; the doc explains reasoning,
which is the part a program cannot hold.

## Phasing

1. **One entry point, no discovery.** Wrap what already exists in `src/` and
   `scripts/`. The two alias files become thin shims calling the new CLI, so
   muscle memory survives and nothing is deleted.
2. **Sibling repo discovery.** Other repos contribute their own commands
   (launching their own TUIs included).
3. **TUI.** Renders the same registry.
4. **Releases and self-update.** Version reporting from the start, since the
   binary and the repos are distributed separately and will skew.

### TUI scope limit

It lists commands, runs one, and streams stdout in a pane. It never renders
bespoke UI per command. Anything needing rich UI *is* its own TUI and the
core just launches it.

## How I want to build this (working agreement)

This changes how the work happens, not what gets built.

**Teach me Go while we build it. I do the typing.** Treat it like a recorded
tutorial where you set the step up and I perform it. I am fluent in Python
and shell and new to Go, so skip programming fundamentals and explain
Go-specific things as they come up: modules, packages, errors as values,
interfaces, methods on structs, goroutines and channels when we reach them.

Rules for every step:

1. **One step at a time.** Say what we are about to do and why it comes now.
2. **Set the step up, then stop.** Give me the exact command to run or the
   specific function to write, then wait.
3. **Wait for me to confirm.** Never continue on the assumption that it
   worked. I will say I did it, or paste the error.
4. **Every step ends in something runnable.** I want to execute it and see
   output before moving on. No step whose payoff arrives three steps later.
5. **Keep steps small.** More than roughly 30 lines of new code means split
   it.
6. **I write the meat, you write the boilerplate.** Import blocks, struct
   scaffolding, and repetitive cases are fine to hand me. The logic that
   teaches me something is mine to type.
7. **If it fails, fix it with me before moving on.** Do not paper over a
   broken step by rewriting the file.

Explanations go inline and short: a sentence or two on why Go does it this
way, at the moment it matters. Not a lecture up front.

### Arc, simple to complex

Each of these runs on its own.

1. `go mod init` in the new app dir, `main.go` printing a version string, run
   it.
2. Argument parsing: one real subcommand that does nothing yet.
3. Exec a subprocess and stream its stdout live. This is the core's whole
   job, so it comes early.
4. Read a command definition from a file and run it by name.
5. Discovery: glob sibling repos for definitions, list what was found.
6. Gating: filter by host and platform using the existing vocabulary.
7. The check / apply / `--yes` convention on one real command.
8. Wrap one existing script (`deploy_configs.py`) end to end.
9. The TUI, last, over a registry that already works.

## Open questions

- The command name. `hq` is short and unclaimed; `rig` and `cmdr` also work.
- Which shell aliases genuinely cannot move: anything mutating the calling
  shell (`githubdir`, `venvdeactivate`, `ll`, the conditional `claude` shim)
  stays a shell function.
- Whether `deploy_map.json` stays a committed artifact or becomes a live
  query.
