# VS Code Cleanup

Runbook for applying the VS Code cleanup to another machine. The settings
themselves (`application_configs/vscode/settings.*.json`) are already committed
and deployed via `deploy_configs.py`, so **do not re-edit settings** — this doc
only covers the per-machine work: extension removals and health checks. This is
written so Claude Code (or another AI agent) can execute it on any machine.

## Background

An audit of the envy multiroot workspace (28 folders) found the slowness was
mostly: git autofetch across ~26 repositories every 3 minutes (now 900s in
settings), GitLens duplicating that git churn, a handful of broken extension
installs, and ~17 extensions with no matching usage in any repository.
Terminal/tmux and the Python/Jupyter stack were healthy and untouched.

A second pass (July 2026) on a Linux Remote-SSH host extended the list: it
removed both SQLFluff extensions (one crashing on activation every session),
both GitHub Actions extensions (one failing on the GitHub repos API), and a set
of low-usage extensions Jason confirmed he doesn't use (PlantUML, Helm
Intellisense, XML Tools, PowerShell, ChatGPT/Codex). It kept SQLite Viewer, and
confirmed several keeps by repository evidence (Terraform, YAML, Makefile Tools,
Live Preview, Container Tools) — note the Terraform keep was **reversed in the
fourth pass**; repository evidence is not the same as Jason using the extension.
See the remote-server section for the CLI mechanics, which differ from a plain
`code` install.

A third pass (July 2026, MacbookProM5) added removals Jason confirmed: the C#
stack (`ms-dotnettools.csdevkit`, `ms-dotnettools.csharp`, and their
`vscode-dotnet-runtime` dependency — no C# in any repository; uninstalling the
csdevkit pack also removes csharp) and `github.vscode-pull-request-github`
(PRs are handled via `gh`/browser). Clarification: the ruff keep's
"herdstone only" refers to the **herdstone repo** being present on the machine
(its ruff config is `backends/python/pyproject.toml`), not a hostname.

A fourth pass (July 2026, RyzenWhite) added three removals — `gruntfuggly.todo-tree`
(startup-activating workspace scan; ripgrep/search covers it),
`shahilkumar.docxreader` (no `.docx` anywhere under `~/GitHub`), and
`hashicorp.terraform`, **moved off the keep list** because Jason confirmed he
doesn't use it. It also established two Windows keeps, because the
"no C# / no Rust in any repository" premises are **machine-specific and false
on RyzenWhite**: see Platform exceptions. It also confirmed that a Windows box
can hold a live `~/.vscode-server` set of its own (it is reachable via
Remote-SSH), so the remote-server procedure applies on Windows too — with
`code-server.cmd` in place of `code-server`.

## Extensions to remove

Run on the target machine (adjust `code` to `code-insiders`/`codium` if
applicable; on a Remote-SSH host use `code-server` — see the remote-server
section). Skipping ones that aren't installed is fine — the loop tolerates
that. Order matters where noted: an extension **pack must be uninstalled before
its members**, or the member's uninstall is refused.

Three entries are **conditional, not unconditional** — check for repository
evidence before running them, and read Platform exceptions first: the C# stack
(`csdevkit`/`csharp`/`vscode-dotnet-runtime`) and `rust-lang.rust-analyzer` are
removed only where no C#/Rust project is present, and `ms-vscode.powershell`
only off Windows.

```bash
for e in \
    eamodio.gitlens \
    ms-vsliveshare.vsliveshare \
    foxundermoon.shell-format \
    rust-lang.rust-analyzer \
    ms-vscode.azure-repos \
    github.remotehub \
    ms-vscode.remote-repositories \
    christian-kohler.npm-intellisense \
    leizongmin.node-module-intellisense \
    ms-python.gather \
    negokaz.live-server-preview \
    george-alisson.html-preview-vscode \
    donjayamanne.githistory \
    sqlfluff.vscode-sqlfluff \
    dorzey.vscode-sqlfluff \
    github.vscode-github-actions \
    me-dutour-mathieu.vscode-github-actions \
    jebbs.plantuml \
    tim-koehler.helm-intellisense \
    dotjoshjohnson.xml \
    ms-vscode.powershell \
    openai.chatgpt \
    formulahendry.docker-extension-pack \
    formulahendry.docker-explorer \
    sergey-tihon.openxml-explorer \
    gruntfuggly.todo-tree \
    shahilkumar.docxreader \
    hashicorp.terraform \
    github.vscode-pull-request-github \
    ms-dotnettools.csdevkit \
    ms-dotnettools.csharp \
    ms-dotnettools.vscode-dotnet-runtime; do
    code --uninstall-extension "$e"
done
```

Why each one goes:

| Extension | Reason |
|---|---|
| gitlens | Heavy background git work; replaced by built-in blame settings (`git.blame.*`) + Git Graph for the tree view |
| vsliveshare | Broken against current VS Code API, unused |
| shell-format | Broken install (missing wasm), removed rather than reinstalled |
| rust-analyzer | Heavy, activates at startup via `workspaceContains:Cargo.toml`. **Conditional** — remove where no Rust project exists. Removed on RyzenWhite even though `Data_Tool_Pack_RS` / `Rust_Tutorial` are present: both dormant 10+ months and neither is in the workspace, so a reinstall on demand is cheaper than the startup cost |
| azure-repos / remotehub / remote-repositories | Remote-repository browsing, unused |
| npm-intellisense / node-module-intellisense | Barely any JS/TS work |
| gather | Abandoned by Microsoft |
| live-server-preview / html-preview-vscode | Redundant with the kept live-preview extension (`ms-vscode.live-server` or `ritwickdey.liveserver`) |
| githistory | Redundant with Git Graph (`mhutchie.git-graph`, kept) |
| sqlfluff.vscode-sqlfluff | Broken — crashes on activation every session (`command 'sqlfluff.quickfix.excludeRule' already exists`); SQL is linted per-repo, not in-editor |
| dorzey.vscode-sqlfluff | Old SQLFluff publisher; orphaned leftover after the move to the `sqlfluff.*` publisher |
| github.vscode-github-actions | Fails to activate (`HttpError: Not Found` on the GitHub repos API); Actions aren't edited in-editor |
| me-dutour-mathieu.vscode-github-actions | Third-party GitHub Actions duplicate |
| jebbs.plantuml | UML diagram preview; only one `.puml` file across all repositories |
| tim-koehler.helm-intellisense | Helm chart autocomplete; only one `Chart.yaml` across all repositories |
| dotjoshjohnson.xml | XML formatting/tree view; not used |
| ms-vscode.powershell | PowerShell language support. **Conditional** — removed on macOS/Linux where `.ps1` files aren't edited; kept on Windows (see Platform exceptions) |
| openai.chatgpt | OpenAI in-editor assistant; overlaps with Claude Code (kept) |
| docker-extension-pack | Wrapper pack around docker-explorer, redundant with the official Docker extensions — remove **before** docker-explorer or that uninstall is refused |
| docker-explorer | Redundant with the official Docker extensions |
| openxml-explorer | Raw Office-XML inspection, not used (Excel viewing stays via `gc-excelviewer`) |
| todo-tree | TODO/FIXME sidebar tree; activates on startup and scans every workspace folder — ripgrep/search covers the same ground |
| docxreader | In-editor `.docx` viewer; no `.docx`/`.dotx` files in any repository |
| terraform | **Reversal of an earlier keep.** Jason confirmed he does not use it. The "heavily used" note came from file count, not from him — the only `.tf` files are 10 under `na-finops/terraform/`, which he doesn't edit in-editor. It also activates at startup via `workspaceContains:**/*.tf,**/*.tfvars` and was the noisiest extension log in the session |
| vscode-pull-request-github | In-editor GitHub PR/issue review; PRs are handled via `gh` CLI and browser |
| csdevkit / csharp | C# Dev Kit + language support. **Conditional** — remove only where no C# project exists (kept on Windows, see Platform exceptions). Uninstall the csdevkit **pack first** — it takes csharp with it |
| vscode-dotnet-runtime | Only existed as a dependency of openxml-explorer / csdevkit — remove it **after** those or the uninstall is refused, and keep it wherever csdevkit is kept |

## Platform exceptions

- **Windows**: keep `mark-wiemer.vscode-autohotkey-plus-plus` — AHK scripts
  are actively edited there. It was removed on macOS only.
- **Windows**: keep `ms-vscode.powershell` — ~16 `.ps1` scripts live across
  `dotfiles/scripts/`, `na-faba`, `na-finops`, and `Our_Cash`, and they are
  maintained from the Windows box. The remove-list entry applies to macOS/Linux
  only.
- **Windows**: keep the C# stack (`ms-dotnettools.csdevkit`,
  `ms-dotnettools.csharp`, `ms-dotnettools.vscode-dotnet-runtime`) plus
  `visualstudiotoolsforunity.vstuc` — the `Something-Familiar` repository is a
  real Unity/C# project (`Assembly-CSharp.csproj`, `Packages/manifest.json`,
  `Assets/Scenes/*.unity`). vstuc depends on csdevkit, so removing csdevkit
  while vstuc is installed just makes it reinstall.
- **Remote-SSH hosts** have their own remote extension sets; apply the same
  removal list on the remote side where the extensions appear. See below.

The general rule these encode: the "no X in any repository" reasons in the
table were measured on the machine that pass ran on. **Re-measure before
acting** — `find ~/GitHub -maxdepth 3 -name Cargo.toml`, `-name "*.csproj"`,
`-name "*.ps1"` — rather than trusting the reason text.

## Remote-SSH / code-server hosts

On a machine reached through Remote-SSH (a `~/.vscode-server` directory is
present), the plain `code` CLI does not work from a normal shell — it prints
"Command is only available in WSL or inside a Visual Studio Code terminal." Use
the server's own offline CLI instead; it operates directly on the remote
extension directory without a running instance:

```bash
CS=~/.vscode-server/cli/servers/Stable-<commit>/server/bin/code-server
"$CS" --list-extensions --show-versions
"$CS" --uninstall-extension <publisher.name>
```

Pick the newest `Stable-<commit>` directory — `cli/servers/lru.json` lists them
most-recently-used first, which is more reliable than mtime. Notes:

- **This also applies to Windows machines that are themselves SSH targets.** A
  Windows box has both a local install (driven by `code`) and, if anything ever
  connects to it over Remote-SSH, its own `%USERPROFILE%\.vscode-server` set
  that `code --list-extensions` does not show. Apply the remove list to **both**.
  The binary is `code-server.cmd` there, and it works fine from Git Bash.
- Check nothing is live first — `Get-Process node | Where-Object { $_.Path -like
  "*vscode-server*" }` on Windows — before deleting leftover directories.

- `code-server` unregisters the extension from `extensions.json` but often
  leaves its directory on disk (marked in
  `~/.vscode-server/extensions/.obsolete`) while the running extension host
  still holds handles. Remove the leftover
  `~/.vscode-server/extensions/<publisher.name>-<version>/` directory manually
  for a clean state.
- Removals take effect on the next **window reload / reconnect** — the running
  extension host keeps them in memory until then.
- A machine may also carry a second, stale local set under `~/.vscode/extensions/`
  from an old native install. Older versions have no `extensions.json` (they
  scan directories), so just delete the matching `<publisher.name>-<version>/`
  directories there too. Apply the same remove list to whichever of our removed
  IDs are present.

## Intentional keep list

Python stack (python, pylance, debugpy, black-formatter, flake8, isort,
mypy-type-checker, python-envs), Jupyter stack (jupyter, renderers, keymap,
cell-tags, slideshow — `# %%` code cells are used everywhere), ruff (herdstone
only, configured per-repo), claude-code, go, swiftlang.swift-vscode +
llvm-vs-code-extensions.lldb-dap (Swift debugging needs lldb-dap), remote-ssh
pack, Docker official extensions (`docker.docker`, `ms-azuretools.vscode-docker`,
`ms-azuretools.vscode-containers`), git-graph, live preview
(`ms-vscode.live-server`) or Live Server (`ritwickdey.liveserver`) — keep
whichever is present, markdownlint, prettier, prettier-sql, sqltools (+ pg
driver), rainbow-csv, gc-excelviewer, sqlite-viewer (`qwtel.sqlite-viewer`),
gitignore, yaml
(`redhat.vscode-yaml`, schema validation used everywhere), makefile-tools
(`ms-vscode.makefile-tools`), open-in-github, dracula theme, great-icons,
markdown-mermaid, graphviz-interactive-preview, pdf, stl-viewer, tailscale.

Windows additionally keeps AHK, PowerShell, and the C#/Unity stack — see
Platform exceptions. Note that recent VS Code ships **Copilot Chat as a
built-in**, so it shows up activating in `exthost.log` while being absent from
`code --list-extensions`; that is not an install and needs no action.

## Instructions for Claude on other machines

1. Run `code --list-extensions` (or `code-server --list-extensions` on a
   Remote-SSH host — see the remote-server section) and diff against the
   remove/keep lists above.
2. For any installed extension **not explicitly listed here**, do NOT silently
   uninstall it. Ask Jason about each one, giving a short plain-language
   description of what it does, whether anything in his repositories appears to
   use it, and a keep/remove recommendation — then act on his answers. Matching
   files in a repository are evidence the extension *could* be used, not that it
   is — that assumption is what put Terraform on the keep list for two passes.
   When a keep rests only on file counts, say so and ask.
3. Check the newest full session under the VS Code logs dir for extensions that
   fail to activate, repeated errors, or unresponsive-extension-host events, and
   report findings. Locations: `~/Library/Application Support/Code/logs/`
   (macOS), `%APPDATA%\Code\logs` (Windows), `~/.config/Code/logs` (Linux
   local), and `~/.vscode-server/data/logs/` (Remote-SSH host — the relevant one
   when connected remotely).
4. Watch for stale state the logs reveal: linters pointed at deleted `.venv`s
   (fix with `uv sync` — Jason uses uv, never pip), workspace folders that no
   longer exist, and stale git submodule declarations. On Windows also check
   `ms-python.vscode-python-envs`' log for broken interpreter shims — a
   chocolatey `python3.11.exe` whose target `C:\python311\python.exe` is gone
   makes every discovery pass fail on it — and for
   `Glob expansion took Ns, this may cause client timeouts`, which means the
   workspace folder count is what's slowing discovery, not an extension.
5. **Create any missing workspace venv.** VS Code throws errors when a folder
   is configured for linting but has no interpreter — flake8/black/isort/mypy
   each fail per-folder and the noise looks like an extension problem when it
   isn't. Walk the workspace file's `folders` list; for every folder that has a
   `pyproject.toml` (or `requirements.txt`) but no `.venv/`, run `uv sync` in
   it. Jason uses **uv, never pip** — do not fall back to
   `python -m venv` + `pip install`. Verify each one afterwards with
   `.venv/Scripts/python.exe --version` (`.venv/bin/python` off Windows).

   ```bash
   cd ~/GitHub
   for f in <folders from the workspace file>; do
       [ -d "$f" ] || { echo "MISSING-FOLDER $f"; continue; }
       if [ -f "$f/pyproject.toml" ] && [ ! -d "$f/.venv" ]; then
           echo "== uv sync $f"; (cd "$f" && uv sync)
       fi
   done
   ```

   Folders in the workspace file that aren't cloned on the machine show up in
   the same walk — report them rather than cloning, since which repositories
   belong on which machine is Jason's call.
6. Settings deploy via git — never hand-edit the live settings file; edit
   `application_configs/vscode/` in this repository if a settings change is
   truly needed, and never override the per-repo linter configs (na-finops's are
   carefully tuned and live in that repository).
7. After removing extensions, also prune the multiroot workspace file's
   `extensions.recommendations` list so it no longer recommends anything you
   uninstalled (otherwise VS Code nags to reinstall them), and drop any now-dead
   settings keys tied to removed extensions (e.g. `sqlfluff.dialect`). Each
   machine's workspace file at `~/GitHub/<host>.code-workspace` is a symlink
   into a sibling `*_credentials/vscode/workspace.<host>.code-workspace` —
   resolve the symlink and edit the real target. As of the RyzenWhite pass the
   only files carrying a `recommendations` list are
   `hellofresh_credentials/vscode/workspace.hellofreshjason.code-workspace` and
   `fourteen_foods_credentials/vscode/workspace.fflap-2229.code-workspace`, and
   both list keep-list extensions only — nothing to prune. `workspace.ryzenwhite`
   has no `extensions` block and empty `settings`.
