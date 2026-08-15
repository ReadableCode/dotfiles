# Setup Rust

## Setup on Linux

- Using apt

  - Open terminal and run the following commands:

  ```bash
  sudo apt update
  sudo apt install rustc cargo
  ```

## Setup on macOS

- Using Rustup

  - Open terminal and run the following command:

  ```bash
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
  ```

  - Follow the prompts to complete the installation.
  
  ```bash
  source "$HOME/.cargo/env"
  ```

## Setup on Windows

- Using WinGet

  - Open powershell as administrator and run:

  ```bash
  winget install -e --id Rustlang.Rustup
  winget install -e --id Microsoft.VisualStudio.2022.BuildTools --source winget --override "--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --includeOptional"
  ```
  
  To finish installaion:
  - Visual Studio Build Tools window may open:
    - If it does:
      - select "Desktop Development with C++"
      - press Install
      - wait for installation to finish
      - close the window
    - If it does not:
      - open Visual Studio Installer
      - press Modify
      - check Desktop Development with C++
      - press Modify
  
  - Will need to close and reopen all VSCode windows to make sure the powershell window can access cargo and rustc.

## Setup on Locked-Down Windows (No Admin Rights)

Use this path when you can't run `winget`, can't install the Visual Studio
Build Tools, and can only write to your user profile. We install everything
under `C:\Users\<you>\userapps\rust` and use the **GNU toolchain** (which links
against MinGW gcc) so we don't need MSVC at all.

Prerequisite: MSYS2 (set it up by following [msys2.md](./msys2.md)) with the
`mingw-w64-x86_64-gcc` package from
[app_lists/msys2_packages.txt](../app_lists/msys2_packages.txt) installed:

```powershell
C:\msys64\usr\bin\bash.exe -lc "pacman -S --needed --noconfirm mingw-w64-x86_64-gcc"
```

The path mod block below already adds `C:\msys64\mingw64\bin` to `PATH`,
which is where `gcc.exe` and `ld.exe` live.

### 1. Download the rustup installer

In PowerShell:

```powershell
$dest = "$env:USERPROFILE\userapps\rust"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Invoke-WebRequest `
  -Uri "https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-gnu/rustup-init.exe" `
  -OutFile "$dest\rustup-init.exe"
```

### 2. Point rustup / cargo at userapps and install the GNU toolchain

`RUSTUP_HOME` and `CARGO_HOME` must be set **before** running `rustup-init` so
that the toolchain, registry cache, and installed binaries all land inside
`userapps` (the default is `%USERPROFILE%\.rustup` / `%USERPROFILE%\.cargo`,
which also works without admin but is less tidy).

```powershell
$env:RUSTUP_HOME = "$env:USERPROFILE\userapps\rust\rustup"
$env:CARGO_HOME  = "$env:USERPROFILE\userapps\rust\cargo"

& "$env:USERPROFILE\userapps\rust\rustup-init.exe" `
    -y `
    --no-modify-path `
    --default-host x86_64-pc-windows-gnu `
    --default-toolchain stable `
    --profile minimal
```

Flags explained:

- `-y` — accept defaults (no interactive prompts).
- `--no-modify-path` — don't touch the user `PATH` registry key; the
  PowerShell profile block below handles `PATH` instead.
- `--default-host x86_64-pc-windows-gnu` — install the GNU toolchain so
  builds use MinGW gcc/ld and don't require MSVC Build Tools.
- `--profile minimal` — skip docs/components we don't need on this machine.

### 3. Add Rust to the PowerShell profile

Edit `$PROFILE` (run `notepad $PROFILE` if it doesn't exist yet) and extend
the existing `## Path Mods ###` block so the `cargo\bin` directory is on
`PATH` and `RUSTUP_HOME` / `CARGO_HOME` are exported for every session:

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
        'rust\cargo\bin'
    )

    # Windows and msys64 are not under userapps, so they are spelled out in full. Entries
    # are prepended in order, so the last ones here end up first in PATH: msys64 wins,
    # then the userapps tools, then System32.
    $paths = @('C:\Windows\System32')
    $paths += $userappPaths | Where-Object { $_ } | ForEach-Object { "$userapps\$_" }
    $paths += 'C:\msys64\mingw64\bin', 'C:\msys64\usr\bin'

    $curr = ($env:Path -split ';') | Where-Object { $_ }
    foreach ($p in $paths) {
        if (-not (Test-Path -LiteralPath $p)) {
            Write-Host "portable config: not on disk, leaving off PATH: $p" -ForegroundColor Yellow
            continue
        }
        if (-not ($curr -contains $p)) {
            $env:Path = "$p;$env:Path"
        }
    }
    Remove-Item Env:\GIT_SSH -ErrorAction SilentlyContinue

    # Set CC to gcc so any crate with a build.rs that compiles C picks up MinGW
    $env:CC = "gcc"

    # Tell rustup/cargo to keep their state under userapps instead of the home dir
    $env:RUSTUP_HOME = "$env:USERPROFILE\userapps\rust\rustup"
    $env:CARGO_HOME  = "$env:USERPROFILE\userapps\rust\cargo"

    Write-Host 'portable toolchain config loaded' -ForegroundColor Green
}
```

Close and reopen PowerShell (and VS Code), then verify with the commands in
the next section. If `cargo build` later complains about a missing linker,
double-check that `gcc.exe` resolves on `PATH` (`where.exe gcc`) — that's the
MSYS2 mingw64 link that replaces the MSVC `link.exe`.

## Testing and Finishing Installation

- If using VSCode, install the Rust extension by searching for `rust-analyzer` in the extensions tab.

- Close and reopen the terminal to make sure installation is successful and then run the folling commands to verify the versions of rustup and rustc:

  ```bash
  rustup --version
  rustc --version
  cargo --version
  ```

## Compile and Run a Rust Program with Rustc

- Create a new file with the `.rs` extension and write the following code:

  ```rust
  fn main() {
      println!("hello world!");
  }
  ```

- Compile the program using the following command:

  - This will create the compiled program in the same directory as the source file for the operating system you are using to compile it:

  ```bash
  rustc <filename>.rs
  ```

- Run the compiled program using the following command:

  - For Windows this will be a `.exe` file, for Linux it will be the same name as the file:
  
  ```bash
  ./<filename>
  ```

## Compile and Run a Rust Program with Cargo

- Create a new project using the following command:

  - This will create a new directory with the project name and the necessary files for a cargo project:

  ```bash
  cargo new <project_name>
  ```

- Navigate to the project directory and run the following command to  build the project:

  ```bash
  cargo build
  ```

- Run the project manually using the following command:

  ```bash
  cd target/debug
  ./<project_name>
  ```

- Or run the project using the following command:

  ```bash
  cargo run
  ```

## Checking and Formatting

- Run the following command to check without compiling:

  ```bash
  cargo check
  ```

- Run the following command to format the code:

  ```bash
  cargo fmt
  ```
