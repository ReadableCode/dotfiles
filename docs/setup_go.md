# Setup Go

## Setup on Linux (not raspberry pi)

- Using apt

  - Open terminal and run the following commands:

  ```bash
  sudo apt update
  sudo apt install golang
  ```

## Setup on Raspberry Pi

- Installing from apt will get you an odler version without support for new features

- Uninstall the apt version first

  ```bash
  sudo apt remove golang
  sudo rm -rf /usr/local/go
  ```

- To install the latest version, download the latest version from the official website

- Open terminal and run the following commands:

```bash
cd && wget https://go.dev/dl/go1.22.2.linux-armv6l.tar.gz
sudo tar -C /usr/local -xzf go1.22.2.linux-armv6l.tar.gz
```

- Add the following to the end of the `~/.profile` file:

```bash
nvim ~/.profile
export PATH=/usr/local/go/bin:$PATH
source ~/.profile
go version
```

## Setup on Windows

- Using WinGet

  - Open powershell as administrator and run:
  
  ```bash
  winget install -e --id GoLang.Go
  ```

## Setup on Locked-Down Windows (No Admin Rights)

Use this path when you can't run `winget` and can only write to your user
profile. Go ships as a plain zip with no installer and no registry writes, so
everything lands under `C:\Users\<you>\userapps\go`, following the layout in
[setup_windows_portable_userapps.md](./setup_windows_portable_userapps.md).

Nothing here needs MSYS2. A pure-Go build (`go_apps/cmdr` included) links with
Go's own linker. MSYS2's `mingw-w64-x86_64-gcc` only matters if a dependency
turns on cgo, and `C:\msys64\mingw64\bin` is already on `PATH` from the shared
portable paths file if that day comes.

### 1. Download and extract the zip

Pick the current `go<version>.windows-amd64.zip` from
[go.dev/dl](https://go.dev/dl/) and set `$ver` to match. The archive contains a
top-level `go\` folder, so extract to `userapps` and not to `userapps\go`, or
you end up with `userapps\go\go\bin`.

```powershell
$ver = "1.25.0"   # pin whatever is current on go.dev/dl
$userapps = "$env:USERPROFILE\userapps"
New-Item -ItemType Directory -Force -Path $userapps | Out-Null
$zip = "$env:TEMP\go$ver.windows-amd64.zip"

# curl.exe ships with Windows and streams to disk. Invoke-WebRequest works too,
# but Windows PowerShell 5.1 renders a progress bar per chunk and drags a ~75MB
# download out to many minutes - if you use it, set
# $ProgressPreference = 'SilentlyContinue' first.
curl.exe -L -o $zip "https://go.dev/dl/go$ver.windows-amd64.zip"
# upgrading in place: delete the old GOROOT first, Expand-Archive won't merge cleanly
Remove-Item -Recurse -Force "$userapps\go" -ErrorAction SilentlyContinue
Expand-Archive -Path $zip -DestinationPath $userapps -Force
Remove-Item $zip
```

### 2. Get it on PATH

Nothing to edit in this repo. `go\bin`, `go-path\bin`, `GOPATH` and `GOCACHE`
belong in the hostname-guarded block in that machine's context shard, alongside
the rust entries — see
[setup_windows_portable_userapps.md](./setup_windows_portable_userapps.md).
Pull the credentials repo on the machine and restart PowerShell.

`GOROOT` is deliberately not set anywhere: the `go` binary infers it from its
own location, which is what makes the zip relocatable. `GOPATH` must not equal
`GOROOT`, hence the separate `go-path` folder. `go` does not create `go-path`
until the first `go install`, so the profile block puts `go-path\bin` on PATH
without a `Test-Path` guard instead of warning about a folder that is
legitimately absent.
The defaults (`%USERPROFILE%\go`, `%LOCALAPPDATA%\go-build`) are user-writable
and would work; pointing them at `userapps` keeps the toolchain in one
directory to back up or delete.

### 3. Verify

Close and reopen PowerShell (and VS Code), then:

```powershell
where.exe go        # expect ...\userapps\go\bin\go.exe
go version
go env GOROOT GOPATH GOCACHE
cmdr                # builds go_apps/cmdr on first run, then runs it
```

If `go build` hangs or fails resolving modules, the corporate proxy is likely
blocking `proxy.golang.org`. Check with `go env GOPROXY` and, if there's an
internal mirror, set `$env:GOPROXY` in the same profile block rather than
falling back to `GOFLAGS=-mod=mod` against a blocked upstream.

## Testing and Finishing Installation

- If using Visual Studio Code, install the Go extension by searching for `@id:golang.go` in the extensions tab.

- Close and reopen the terminal to make sure installation is successful and then run the folling commands to verify the version of Go:

  ```bash
  go version
  ```

## Create and run a simple Go program

- Create a new file named `hello.go` and add the following code:

  ```go
  package main

  import "fmt"

  func main() {
    fmt.Println("Hello, World!")
  }
  ```

## Run Directly from Source

- cd into the src diretory where the hello.go file is located

- Run the program by executing the following command:

  ```bash
  go run hello.go
  ```

## Compiling from source

- To build it and run the executable:

  - cd into the src directory where the hello.go file is located

  ```bash
  go build hello.go
  ```

  - Running on Linux
  
    ```bash
    chmod +x hello
    ./hello
    ```
  
  - Running on Windows
  
    ```bash
    .\hello.exe
    ```
