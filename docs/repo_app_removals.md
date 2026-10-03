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
context's machines get - a client's cloud CLI, database client and chat app,
the personal context's game, media and streaming apps - lives in that
context's own repo as `<context>_app_lists.yaml`, keyed by the same manager
names as the removals schema:

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
`--where` prints the context files it read. Two contexts may name the same
app: the overlay is deduplicated case-insensitively, both installers add only
the names their dotfiles list lacks, and the installed check runs before the
prompt, so a machine in both contexts sees the app once and never installs it
twice. The one clash is the same app on two managers, below. A context lists each of its apps for
every OS its machines run - a client's chat app on macOS and on Windows alike.

`app_lists.py --missing` is the other half: every listed app this machine's
managers do not report installed, split into `missing` (nothing installed it)
and `elsewhere` (a choco entry `winget list` shows under the same name, put
there by hand or another manager, where a choco install would make a second
copy). `myupdater` asks it once after every step and prints
the answer in the closing summary, so a package an installer could not find is
read at the end rather than lost in the middle of a long run.

The choco installer asks the same question before it offers anything
(`app_lists.py --elsewhere choco`, names on stdin): an `elsewhere` app is
printed under "Installed outside choco, so not offered" and never reaches the
per-app questions. Until 2026-10-02 the installer read `choco list` alone and
offered every one of them; a yes ran Chocolatey's installer over the existing
copy, which on RyzenWhite tried to put Tailscale 1.98.8 over 1.102.4 and
failed. A name matches a `winget list` row by the row's name with what the
installer added around it dropped ("SyncTrayzor (x64) version 2.2.0.0" is
`synctrayzor`), by any part of the winget id, or by the whole id
(`googlechrome` is `Google.Chrome`); always the whole name, never a prefix. A
choco name with nothing in common with the app's own (`vscode`) is not
recognised and is still offered, which is what the check below is for.

### Ignoring an app on one machine

Every listed app is offered at least once. Each installer first asks whether
to go through its missing apps at all, then asks about each one:
`[y]es / [N]ot now / [i]gnore here / [q]uit asking`. Not now asks again next
time, while `i` writes a `manager:package` line to `~/.dotfiles_ignored_apps`
on that machine, and from then on that app is never offered there or reported
missing. Nothing installs until the questions are done; under `myupdater` that
means every package manager's questions, then every install in one go. Every
run that leaves one out ends by naming the file, and deleting a line is how to
be offered that app again. A Mac mini that has no use for docker or DBeaver
answers `i` to each once.

It is machine state rather than a committed list on purpose: it records one
person's answer at one desk, while the lists stay the record of what a machine
of that kind should have. `src/app_lists.py` is the one reader and writer
(`--ignored`, `--ignore`, `--ignore-path`); both install helpers call it. The
Termux and MSYS2 installers pass no manager, so they offer only yes or no.

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
copy kept is the one its manager just brought up to date. After the app list
installs it asks once more (`app_removals.py --duplicates`, the duplicate half
alone), so a second copy an install just made is offered for removal on the
same run.

Two rows with different ids are not a duplicate even under one name: RustDesk's
MSI registers itself twice, and both rows uninstall the one product.

### Upgrades keep to the manager that installed the app

`winget upgrade --all` upgrades every installed program winget can match to
its source, not only the ones winget installed, and `choco upgrade all` runs
an installer for every package whose record is behind its feed, whatever is
really on the disk. Until 2026-10-02 `myupdater` ran both, and on RyzenWhite
every run repeated the same failures:

- winget re-ran Barrier's installer, because Barrier registers `2.4.0-release`
  and winget offers `2.4.0`; the installer aborted on the running Barrier,
  which winget prints as "You cancelled the installation".
- winget went for TightVNC 2.8.89 and OBS Studio, both Chocolatey's.
- winget tried to replace Windows Terminal from inside a Terminal window.
- Chocolatey, whose record said OpenVPN 2.5.7, ran the 2.6.16 MSI over the
  2.7.7 that was really installed and failed with 1603.

`scripts/my_updater.ps1` now upgrades by name from a plan,
`app_lists.py --upgrades winget` and `--upgrades choco`, and prints what each
plan holds back with its reason under "left alone":

| Manager | Held back | Why |
| --- | --- | --- |
| winget | an app Chocolatey installed, matched by name the same way as above with a `.install` / `.portable` suffix dropped (`git.install` is `Git.Git`) | Chocolatey upgrades it next |
| winget | an offer whose leading version numbers are not past the installed ones | it is the release already installed |
| winget | Windows Terminal while a Terminal window is open | Windows will not replace a running package; the Store updates it once closed |
| choco | a package whose app `winget list` shows at or past the version on offer | something else upgraded it and the installer would push an older build over it |

Everything else is upgraded, one manager per app, so a second run right after
the first has the same plan minus whatever the first one upgraded.
`my_updater.ps1 --check` counts from the same plans. If a plan cannot be worked
out (no uv, the manager not answering) that manager upgrades nothing and the
step fails, rather than falling back to "all".

What a plan cannot hold back is an upgrade that is real but fails for a reason
outside this repo, and it is attempted again on every run until the cause goes:
a Chocolatey package whose download no longer matches its own checksum
(GoogleChrome, parsec), or an installer that refuses while another program has
its files open (OBS Studio's while anything has the virtual camera loaded).

Anything the finder cannot see - an optional feature beside a package, like the
in-box OpenSSH server - still takes a line with `replaced_by`.

## What a run does

```bash
uv run python src/app_removals.py --list   # report only, changes nothing
uv run python src/app_removals.py --all    # also list duplicates no app list names
uv run python src/app_removals.py --duplicates  # only the duplicate installs (Windows)
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
