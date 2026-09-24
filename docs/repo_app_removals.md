# App removals

`src/app_removals.py` uninstalls the packages a committed list says must not be
on this machine. It is the app-list twin of `deploy_configs.py prune`, and
`app_removals.yaml` is the twin of `deploy_removals.yaml`.

## Why an explicit list and not "absent from the app list"

The files in `app_lists/` name what should be **installed**. They are not an
inventory of everything allowed to exist, so the negation is not a removal list:

- most of `brew list` and nearly all of `dpkg -l` is dependencies nobody named
- each platform keeps its manual installs in `linux_apps_non_apt.md` and
  `mac_apps_non_brew.md` on purpose

Inverting an app list would propose uninstalling most of the machine. Retiring
an app is therefore an explicit, committed line, exactly like retiring a config
path.

## Why committed and not machine state

Same reasoning as `deploy_removals.yaml`: the machine that drops a package from
an app list is almost never the only machine that installed it. The list travels
with the repo, so every other machine is offered the same removal on its next
`myupdater`.

## The app lists win

A package some app list still names is never a removal candidate. Re-adding a
package beats a stale line here instead of the two fighting each other, and the
contradiction is printed rather than silently resolved:

```
skipping cask:vnc-viewer (retired_cask): an app list still names it, so the app list wins
```

## Schema

`app_removals.yaml` in dotfiles, plus an optional
`<context>_app_removals.yaml` at the root of each overlay repo this machine is a
member of - the same discovery and the same membership gate as
`deploy_configs.discover_removals`, so a credentials repo a box holds only as
its git hub contributes nothing.

| Key | Required | Meaning |
| --- | --- | --- |
| `name` | yes | unique across every removals file |
| `manager` | yes | `brew`, `cask`, `apt`, `dnf`, `flatpak`, `choco`, `winget`, or `capability` for a Windows optional feature |
| `package` | yes | the name that manager knows it by |
| `hosts` | no | limit to named machines, full or short hostname |
| `replaced_by` | no | `manager:package`; offered only where that replacement is installed |
| `after` | no | a `.ps1` or `.sh` script, relative to the removals file's repo, run once the removal succeeded; a failure fails the run |
| `note` | no | why it was retired, printed with the entry |

The manager decides the platform, so there is no platform key. Each manager's
"is it installed" query is the same `list_installed` command the matching
installer in `scripts/` already uses, so the question has one answer per manager
rather than one per direction.

`replaced_by` exists for the in-box OpenSSH server: retiring it on a machine
that has nothing else serving ssh would lock the machine out, so the removal
waits until the winget OpenSSH is installed there. `after` exists for the same
entry: removing the feature deletes the `sshd` service even though the winget
copy owns it (RyzenWhite, 2026-09-24), so `scripts/repair_sshd.ps1` registers it
again from `C:\Program Files\OpenSSH`, starts it and restores the port 22
firewall rule, in the same session that ran the removal - which survives it. Listing optional features
needs an elevated shell; a query that fails is reported in red and fails the
run, rather than reading as "not installed".

## Context app lists

`app_lists/` holds what every machine of a platform gets. What only one
context's machines get - a client's cloud CLI, database client and chat app -
lives in that context's own repo as `<context>_app_lists.yaml`, keyed by the
same manager names as the removals schema:

```yaml
choco: [awscli, dbeaver, slack]
cask: [slack]
```

`src/app_lists.py` reads it from each overlay repo this machine is a member of,
with the same gate as the overlay manifests, so a box holding a credentials repo
only as its git hub gets none of it. Every installer in `scripts/` adds
`app_lists.py --overlay <manager>` to the list it reads, and a lookup that fails
installs nothing rather than a list that only looks complete. The removals side
protects the union: a package any context list names is never offered.
`app_lists.py` with no arguments prints the whole list for this machine, and
`--where` prints the context files it read. A context lists each of its apps for
every OS its machines run - a client's chat app on macOS and on Windows alike.

`app_lists.py --missing` is the other half: every listed app this machine's
managers do not report installed, split into `missing` (nothing installed it)
and `elsewhere` (a choco entry `winget list` shows under the same name, put
there by hand or another manager, where a choco install would make a second
copy). `myupdater` and `installmissing` ask it once after every step and print
the answer in the closing summary, so a package an installer could not find is
read at the end rather than lost in the middle of a long run.

### Ignoring an app on one machine

Every listed app is offered at least once. The installers' single prompt reads
`[Y]es / [n]ot now / [i]gnore all here / numbers to ignore here`: `n` asks
again next time, while `i` or the numbers write `manager:package` lines to
`~/.dotfiles_ignored_apps` on that machine, and from then on that app is never
offered there or reported missing. Every run that leaves one out ends by naming
the file, and deleting a line is how to be offered that app again. A Mac mini
that has no use for docker or DBeaver answers once with their numbers.

It is machine state rather than a committed list on purpose: it records one
person's answer at one desk, while the lists stay the record of what a machine
of that kind should have. `src/app_lists.py` is the one reader and writer
(`--ignored`, `--ignore`, `--ignore-path`); both install helpers call it. The
Termux and MSYS2 installers pass no manager, so they keep the plain skip.

## Duplicate installs (Windows)

The same app installed twice by two routes - Chocolatey's Slack beside a
per-user copy Slack's own installer left in AppData - each starts at logon and
updates itself. `winget list` sees every route and files both copies under one
winget id, so a winget id listed twice is the signal. No line is needed: like a
repo `clone_repos.py` offers, the extra copy is found, not declared.

Which copy is Chocolatey's comes from Chocolatey itself: a package whose name
matches the app (its name, or any part of the winget id) and whose recorded
version matches exactly one copy. Each extra copy is removed by the manager that
installed it, so Chocolatey's own records stay true.

| Case | What happens |
| --- | --- |
| a choco list names it and Chocolatey's copy is found | that copy is kept; each other copy is offered, `winget uninstall --id <id> --version <v>` |
| the winget list names it and Chocolatey also installed a copy (the app moved lists) | Chocolatey's copy is offered, `choco uninstall <package>` |
| both a choco list and the winget list name it | both lists install it; reported as a conflict to fix in the lists, nothing offered |
| a choco list names it but Chocolatey's recorded version matches no copy | reported; myupdater upgrades before it removes, so the next run matches |
| only the winget list names it | every copy answers to that id; reported, nothing offered |
| no app list names it | one summary line (runtime frameworks installed per CPU architecture, versions kept side by side); `--all` lists them |

myupdater upgrades packages (step 2) before it offers removals (step 7), so the
copy kept is the one its manager just brought up to date.

Anything the finder cannot see - an optional feature beside a package, like the
in-box OpenSSH server - still takes a line with `replaced_by`.

## What a run does

```bash
uv run python src/app_removals.py --list   # report only, changes nothing
uv run python src/app_removals.py --all    # also list duplicates no app list names
uv run python src/app_removals.py          # ask per package
uv run python src/app_removals.py --yes    # no prompts (nothing calls this)
```

Nothing is ever uninstalled without being agreed to one package at a time.
Before each prompt the manager's **own dry run** is printed - `apt-get -s
remove`, `dnf remove --assumeno`, `choco uninstall --noop`, `brew uses
--installed` - because unlike a pruned symlink, which the next deploy recreates,
an uninstall can take dependents with it. A manager with no dry run (cask,
flatpak, winget) says so rather than implying the blast radius is one package.

A run with no terminal reports and removes nothing, the same guard
`clone_repos.py` uses.

## Where it runs

Step 7 of `refresh_machine.py`, and only with `--packages` - so `myupdater`, not
every `gitpullall`. It is a package-manager operation and it prompts, so it
rides with the step that already upgrades packages. `myupdater --check` reports
what is present without asking.

## Workflow

1. drop the package from its `app_lists/` file
2. add an entry here
3. every machine is offered the removal on its next `myupdater`
4. once every machine has run, drop the line
