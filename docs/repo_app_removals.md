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
| `manager` | yes | `brew`, `cask`, `apt`, `dnf`, `flatpak`, `choco` or `winget` |
| `package` | yes | the name that manager knows it by |
| `hosts` | no | limit to named machines, full or short hostname |
| `note` | no | why it was retired, printed with the entry |

The manager decides the platform, so there is no platform key. Each manager's
"is it installed" query is the same `list_installed` command the matching
installer in `scripts/` already uses, so the question has one answer per manager
rather than one per direction.

## What a run does

```bash
uv run python src/app_removals.py --list   # report only, changes nothing
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
