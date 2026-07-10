# VS Code Cleanup

Runbook for applying the July 2026 VS Code cleanup to another machine. The
settings themselves (`application_configs/vscode/settings.*.json`) are already
committed and deployed via `deploy_configs.py`, so **do not re-edit settings** —
this doc only covers the per-machine work: extension removals and health
checks. This is written so Claude Code (or another AI agent) can execute it
on any machine.

## Background

An audit of the envy multiroot workspace (28 folders) found the slowness was
mostly: git autofetch across ~26 repos every 3 minutes (now 900s in settings),
GitLens duplicating that git churn, a handful of broken extension installs,
and ~17 extensions with no matching usage in any repo. Terminal/tmux and the
Python/Jupyter stack were healthy and untouched.

## Extensions to remove

Run on the target machine (adjust `code` to `code-insiders`/`codium` if
applicable). Skipping ones that aren't installed is fine — the loop tolerates
that.

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
    formulahendry.docker-explorer \
    sergey-tihon.openxml-explorer \
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
| rust-analyzer | No Rust in any repo |
| azure-repos / remotehub / remote-repositories | Remote-repo browsing, unused |
| npm-intellisense / node-module-intellisense | Barely any JS/TS work |
| gather | Abandoned by Microsoft |
| live-server-preview / html-preview-vscode | Redundant with Live Server (`ritwickdey.liveserver`, kept) |
| githistory | Redundant with Git Graph (`mhutchie.git-graph`, kept) |
| docker-explorer | Redundant with the official Docker extensions |
| openxml-explorer | Raw Office-XML inspection, not used (Excel viewing stays via `gc-excelviewer`) |
| vscode-dotnet-runtime | Only existed as a dependency of openxml-explorer — remove it **after** openxml-explorer or the uninstall is refused |

## Platform exceptions

- **Windows**: keep `mark-wiemer.vscode-autohotkey-plus-plus` — AHK scripts
  are actively edited there. It was removed on macOS only.
- **Remote-SSH hosts** have their own remote extension sets; apply the same
  removal list on the remote side where the extensions appear.

## Intentional keep list

Python stack (python, pylance, debugpy, black-formatter, flake8, isort,
mypy-type-checker, python-envs), Jupyter stack (jupyter, renderers, keymap,
cell-tags, slideshow — `# %%` code cells are used everywhere), ruff (herdstone
only, configured per-repo), claude-code, go, swiftlang.swift-vscode +
llvm-vs-code-extensions.lldb-dap (Swift debugging needs lldb-dap), remote-ssh
pack, Docker official extensions, git-graph, liveserver, markdownlint,
prettier, prettier-sql, sqltools (+ pg driver), rainbow-csv, gc-excelviewer,
gitignore, github-actions, open-in-github, dracula theme, great-icons,
markdown-mermaid, graphviz-interactive-preview, pdf, stl-viewer, tailscale.

## Instructions for Claude on other machines

1. Run `code --list-extensions` and diff against the remove/keep lists above.
2. For any installed extension **not explicitly listed here**, do NOT silently
   uninstall it. Ask Jason about each one, giving a short plain-language
   description of what it does, whether anything in his repos appears to use
   it, and a keep/remove recommendation — then act on his answers.
3. Check the newest full session under the VS Code logs dir
   (`~/Library/Application Support/Code/logs/` on macOS, `%APPDATA%\Code\logs`
   on Windows, `~/.config/Code/logs` on Linux) for extensions that fail to
   activate, repeated errors, or unresponsive-extension-host events, and
   report findings.
4. Watch for stale state the logs reveal: linters pointed at deleted `.venv`s
   (fix with `uv sync` — Jason uses uv, never pip), workspace folders that no
   longer exist, and stale git submodule declarations.
5. Settings deploy via git — never hand-edit the live settings file; edit
   `application_configs/vscode/` in this repo if a settings change is truly
   needed, and never override the per-repo linter configs (na-finops's are
   carefully tuned and live in that repo).
