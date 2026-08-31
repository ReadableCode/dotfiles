# Windows Portable Toolchain (userapps)

On a locked-down Windows machine — no admin, no `winget`, no installers, only
the user profile writable — every tool goes in `%USERPROFILE%\userapps\` as an
extracted archive, and one hostname-guarded block in that machine's context
shard puts them all on `PATH`.

This doc owns the layout and that block. Each tool's own setup doc owns only its
download step, and links back here for the rest.

## Layout

One folder per tool under `%USERPROFILE%\userapps\`:

| Folder | Tool | Setup doc |
|--------|------|-----------|
| `nvim-win64\` | Neovim | [setup_neovim.md](./setup_neovim.md) |
| `node\` | Node.js (Mason, Copilot) | [setup_neovim.md](./setup_neovim.md) |
| `rg\`, `fd\` | ripgrep, fd | [setup_neovim.md](./setup_neovim.md) |
| `WPy64-<ver>\` | WinPython (and uv) | [setup_python_portable.md](./setup_python_portable.md) |
| `PortableGit\` | Git | [setup_git_portable.md](./setup_git_portable.md) |
| `fzf-<ver>\` | fzf | — |
| `rust\` | rustup, cargo | [setup_rust.md](./setup_rust.md) |
| `go\`, `go-path\` | Go toolchain, GOPATH | [setup_go.md](./setup_go.md) |
| `OpenSSH-Win64\` | portable sshd | [setup_windows_ssh_server.md](./setup_windows_ssh_server.md) |

MSYS2 (`C:\msys64`) sits outside `userapps` because its installer picks its own
root — see [msys2.md](./msys2.md).

## How it gets on PATH

Not by hand-editing `$PROFILE`, and not from this repo either. The block lives
in the **context shard** for whichever context owns that machine:

`<context>_credentials/powershell/powershell_local.<context>.ps1`

deployed to `~\.powershell_local.d\<context>.ps1` by that repo's overlay
manifest, and dot-sourced by `application_configs/powershell/powershell_aliases.ps1`
(its `~\.powershell_local.d\` loader). Inside the shard the whole block is
wrapped in a hostname guard, so it fires on the one locked-down machine and
no-ops everywhere else that repo is cloned:

```powershell
if ($env:COMPUTERNAME -eq 'WORK-LAPTOP') {
    ...
}
```

It lives there rather than here for two reasons: the hostname is the guard, and
machine and client names don't go in this public repo; and the set of tools is a
property of that one machine, not of every Windows host that clones dotfiles.
A second locked-down machine gets its own guarded block in its own context's
shard — copy this one and edit the tool list.

What the block does, in order:

1. Resolves `WPy64-*` and `fzf-*` by pattern (newest by write time), since those
   folder names carry a version that changes on every update.
2. Prepends `System32`, then each `userapps` entry, then the MSYS2 bins — so
   MSYS2 wins, then the portable tools, then the system copies.
3. Skips anything not on disk and says so, rather than failing.
4. Sets the toolchain state vars: `RUSTUP_HOME`, `CARGO_HOME`, `GOPATH`,
   `GOCACHE`, and `CC=gcc`.

Generic form, as it stands. A new locked-down machine starts from this, with
its own hostname and its own tool list:

```powershell
if ($env:COMPUTERNAME -eq 'WORK-LAPTOP') {
    $userapps = "$env:USERPROFILE\userapps"

    # WinPython and fzf carry their version in the folder name, so that name changes
    # every time they are updated. Look them up by pattern rather than pinning a version.
    # Newest by write time, not by name: name order is alphabetical, so a leftover
    # WPy64-3900 would beat the newer WPy64-31350.
    function Get-NewestUserApp {
        param([string]$Pattern)
        Get-ChildItem "$userapps\$Pattern" -Directory -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty Name
    }

    $wpy = Get-NewestUserApp 'WPy64-*'
    $fzf = Get-NewestUserApp 'fzf-*'
    if (-not $wpy) { Write-Host 'portable config: no WPy64-* folder in userapps, python is off PATH' -ForegroundColor Yellow }
    if (-not $fzf) { Write-Host 'portable config: no fzf-* folder in userapps, fzf is off PATH' -ForegroundColor Yellow }

    # blank when the lookup above found nothing, which drops them from the list
    $wpyPython = if ($wpy) { "$wpy\python" }
    $wpyScripts = if ($wpy) { "$wpy\python\Scripts" }

    # all relative to userapps
    $userappPaths = @(
        'nvim-win64\bin',
        'node',
        'rg',
        'fd',
        $wpyPython,
        $wpyScripts,
        'PortableGit\bin',
        $fzf,
        'rust\cargo\bin',
        'go\bin'
    )

    # GOPATH\bin holds whatever `go install` has built, and go does not create it
    # until the first install. Add it unconditionally rather than testing for it:
    # an absent directory on PATH is inert, and this way the first install is
    # runnable in the shell that did it instead of after a restart.
    $goBin = "$userapps\go-path\bin"

    # Windows and msys64 are not under userapps, so they are spelled out in full. Entries
    # are prepended in order, so the last ones here end up first in PATH: msys64 wins,
    # then the userapps tools, then System32.
    $paths = @('C:\Windows\System32')
    $paths += $userappPaths | Where-Object { $_ } | ForEach-Object { "$userapps\$_" }
    $paths += $goBin
    $paths += 'C:\msys64\mingw64\bin', 'C:\msys64\usr\bin'

    $curr = ($env:Path -split ';') | Where-Object { $_ }
    foreach ($p in $paths) {
        if ($p -ne $goBin -and -not (Test-Path -LiteralPath $p)) {
            Write-Host "portable config: not on disk, leaving off PATH: $p" -ForegroundColor Yellow
            continue
        }
        if (-not ($curr -contains $p)) {
            $env:Path = "$p;$env:Path"
        }
    }
    Remove-Item Env:\GIT_SSH -ErrorAction SilentlyContinue

    # Set CC to gcc so anything with a C build step picks up MSYS2's MinGW
    $env:CC = "gcc"

    # Toolchain state under userapps instead of scattered through the home dir.
    # GOROOT is deliberately unset: the go binary infers it from its own location.
    $env:RUSTUP_HOME = "$userapps\rust\rustup"
    $env:CARGO_HOME  = "$userapps\rust\cargo"
    $env:GOPATH      = "$userapps\go-path"
    $env:GOCACHE     = "$userapps\go-path\cache"
}
```

The live copy is the shard, not this snippet — check the shard before assuming
this is current.

## Adding a tool

Extract it into `%USERPROFILE%\userapps\<folder>`, add one line to
`$userappPaths` in that shard, commit the credentials repo, pull it on the
machine, restart PowerShell. Tools whose folder name carries a version go
through `Get-NewestUserApp` instead of a literal string.

## Verifying

Restart PowerShell (and VS Code) after a pull, then `where.exe <tool>` — it
should resolve under `userapps`, not to a Store shim or a system copy.
