# Git Puller

## Usage - without compiling

### A single repo

```bash
go run main.go -path "C:\Users\jason\GitHub\dotfiles" -v
```

### Multiple repos

- Multiple paths can be specified, if some are not git repos they will be skipped and put in a section of repos that were skipped

```bash
go run main.go -path "C:\Users\jason\GitHub\dotfiles" -path "C:\Users\jason\GitHub\Data_Tool_Pack_Py" -path "C:\Users\jason\GitHub\Archived_Projects" -path "C:\Users\jason\GitHub\personal_credentials" -v
```

### Full Directory of repos

- A root directory can be specified, if some are not git repos they will be skipped and put in a section of repos that were skipped

```bash
go run main.go -path "C:\Users\jason\GitHub" -r -v
```

## Usage - compiling

### Compiling on Windows

```bash
# for windows
go build -o git_puller.exe main.go
# for linux
$env:GOOS="linux"; $env:GOARCH="amd64"; go build -o git_puller main.go; Remove-Item Env:GOOS, Env:GOARCH
# for raspberry pi (arm) in output
$env:GOOS="linux"; $env:GOARCH="arm"; go build -o git_puller_arm main.go; Remove-Item Env:GOOS, Env:GOARCH
# for mac x86
$env:GOOS="darwin"; $env:GOARCH="amd64"; go build -o git_puller_mac_x86 main.go; Remove-Item Env:GOOS, Env:GOARCH
# for mac arm
$env:GOOS="darwin"; $env:GOARCH="arm64"; go build -o git_puller_mac_arm main.go; Remove-Item Env:GOOS, Env:GOARCH
```

### Compiling on Linux

```bash
# for windows
GOOS=windows GOARCH=amd64 go build -o git_puller.exe main.go
# for linux
go build -o git_puller main.go
# for raspberry pi (arm) in output
GOOS=linux GOARCH=arm go build -o git_puller_arm main.go
# for mac x86
GOOS=darwin GOARCH=amd64 go build -o git_puller_mac_x86 main.go
# for mac arm
GOOS=darwin GOARCH=arm64 go build -o git_puller_mac_arm
```

### Usage from compiled binary

#### On Windows

```bash
.\git_puller -path "C:\Users\jason\GitHub\dotfiles" -v
.\git_puller -path "C:\Users\jason\GitHub" -v -r
```

#### On Linux

```bash
# linux (not raspberry pi)
chmod +x git_puller && ./git_puller -path "/home/jason/GitHub/dotfiles" -v
# raspberry pi
chmod +x git_puller_arm && ./git_puller_arm -path "/home/pi/GitHub" -v -r
```
