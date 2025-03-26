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
```

### Compiling on Linux

```bash
# for windows
GOOS=windows GOARCH=amd64 go build -o git_puller.exe main.go
# for linux
go build -o git_puller main.go
```

### Usage from compiled binary

#### On Windows

```bash
.\git_puller -path "C:\Users\jason\GitHub\dotfiles" -v
.\git_puller -path "C:\Users\jason\GitHub" -v -r
```

#### On Linux

```bash
./git_puller -path "/home/jason/GitHub/dotfiles" -v
```
