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
the answer on the closing page, so a package an installer could not find is
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

A web app a browser installed (Chrome, Edge or Brave, "install this site as an
app") is never that copy. `winget list` shows one under the site's name, so a
Messenger web app made the listed `messenger` read as installed outside choco
and it was never offered. The two are told apart by how they uninstall: a web
app's uninstall command is the browser itself with `--uninstall-app-id`
(`app_removals.browser_web_apps`).

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

`installmissing` is the other way back: the same offer as `myupdater`'s,
without the package upgrades or removals, with the ignored apps asked about
too, each marked `(ignored here until you say yes)`. Answering yes installs
the app and takes its line out of the ignore file; not now leaves it ignored.

It is machine state rather than a committed list on purpose: it records one
person's answer at one desk, while the lists stay the record of what a machine
of that kind should have. `src/app_lists.py` is the one reader and writer
(`--ignored`, `--ignore`, `--unignore`, `--ignore-path`); both install helpers
call it, and `installmissing` reaches them as `-OfferIgnored` on Windows and
`OFFER_IGNORED=1` everywhere else. The Termux and MSYS2 installers pass no
manager, so they offer only yes or no.

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
plan holds back with its reason under "left alone".

**winget upgrades an app only when a winget app list names it.** The list is
what makes an app winget's, so nothing is guessed: Chocolatey's apps, a
component another app installs and maintains for itself (Epic Online Services,
which winget offers and then refuses to replace because a different kind of
installer put it there), and anything installed by hand are all left alone.
**Chocolatey upgrades what it installed**, which is all `choco outdated` ever
lists. On top of that:

| Manager | Held back | Why |
| --- | --- | --- |
| either | a package `app_upgrade_holds.yaml` names | an app that updates itself, whose package then fails its own checksum on every run (GoogleChrome, parsec); the install is untouched |
| winget | a listed id Chocolatey also installed | the lists disagree; drop it from one |
| winget | an offer whose leading version numbers are not past the installed ones | it is the release already installed |
| winget | Windows Terminal while a Terminal window is open | Windows will not replace a running package; the Store updates it once closed |
| choco | a package whose app `winget list` shows at or past the version on offer | something else upgraded it and the installer would push an older build over it |

Everything else is upgraded, one package at a time and quietly: the terminal
gets one line per package (`upgraded`, or `failed, reported at the end`) and
everything the manager printed goes to `~/logs/updater/upgrades_<time>.log`.
The failures are listed once, on the closing page, each with a plain reason
read from that output - the package's checksum is out of date, winget will not
replace the installed copy, the app is running, or the installer stopped
because named running programs have its files open (OBS Studio's installer
exits 6 while anything has its virtual camera loaded, which any app that lists
cameras does). A failed upgrade fails the "updating os packages" step.

A second run right after the first has the same plan minus whatever the first
one upgraded. `my_updater.ps1 --check` counts from the same plans. If a plan
cannot be worked out (no uv, the manager not answering) that manager upgrades
nothing and the step fails, rather than falling back to "all".

**An upgrade that closes a logon app starts it again.** An installer closes
the app it replaces, and the app's Run key fires only at logon, so in a session
that stays signed in the app stayed down until the next restart. The run notes
which logon apps (Run-key entries that are switched on) are running before the first upgrade, and after the last one starts any that
are no longer running, on the signed-in desktop and unelevated, through a
one-off scheduled task that it removes again. With nobody signed in the app is
left for logon to start.

Anything the finder cannot see - an optional feature beside a package, like the
in-box OpenSSH server - still takes a line with `replaced_by`.

myupdater runs elevated because choco needs admin, and winget refuses to
uninstall a per-user copy from an elevated shell ("The package installed for
user scope cannot be uninstalled when running with administrator privileges").
The extra copy is usually exactly that, the one an app's own installer left in
AppData. So when the shell is elevated and `winget list --scope user` files the
id under the per-user scope, that one uninstall runs through your own
unelevated token: a one-off scheduled task at the Limited run level, which is
the one way an elevated process can start something without admin and wait for
its exit code. The task is removed as soon as it finishes and its output is
printed in the run.

## Installed another way (Windows)

The `elsewhere` apps from `app_lists.py --missing`: a choco list names the app,
Chocolatey never installed it, and `winget list` shows it anyway, because it was
put there by hand or by winget. Choco never upgrades that copy, and a
`choco install` would lay a second one beside it, which is why the choco
installer leaves them out. The removal step picks them up instead: it lists
every `winget list` row that is the app, then asks once per app to reinstall
it through choco. Each row is uninstalled with `winget uninstall --id <id>
--version <v>`, then `choco install <package> -y` runs. That leaves one copy,
the one the list says choco manages. Uninstalling comes first because the same
vendor installer run twice can share a product code, so uninstalling afterwards
could take choco's copy too. If an uninstall fails, the choco install is not
run. If the choco install fails, the run says the app is now uninstalled and
names the command to finish it. App data under AppData normally survives the
reinstall.

Two checks come before any offer, so nothing is uninstalled that cannot be put
back:

- A web app a browser installed is never one of the copies (see "The choco
  installer asks the same question" above for how they are told apart). The
  first version of this offer uninstalled a Messenger web app that could never
  be put back.
- Chocolatey must carry the package (`choco search <package> --exact`). When it
  does not, the app is reported as `left alone: choco has no package named ...;
  fix the app list that names it` and nothing is offered.

Uninstalling unpins an app from the taskbar and installing does not pin it
back. So the pins (the `.lnk` files and the `Taskband` registry values Explorer
reads them from) are saved before the first uninstall. At the end the run lists
the pins that went missing and whose target exists again, and asks once to put
them back. Explorer has to restart to read them, which closes open folder
windows, which is why it asks. A pin whose target did not come back is named
and left for you to pin again. `src/utils/taskbar_tools.py` does this; the
restart and whether Explorer then shows the restored pins have not yet been
seen on a real reinstall, only the saving and the target check.

A per-user copy is uninstalled without admin, the same route the duplicate
copies above take.

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
