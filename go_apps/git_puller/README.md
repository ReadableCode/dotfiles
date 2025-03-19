# Git Puller

## Usage

### A single repo

```bash
go run main.go -path "C:\Users\jason\GitHub\dotfiles"
```

### Multiple repos

- Multiple paths can be specified, if some are not git repos they will be skipped and put in a section of repos that were skipped

```bash
go run main.go -path "C:\Users\jason\GitHub\dotfiles" -path "C:\Users\jason\GitHub\Data_Tool_Pack_Py" -path "C:\Users\jason\GitHub\Archived_Projects" -path "C:\Users\jason\GitHub\server_configs"
```

### Full Directory of repos

- A root directory can be specified, if some are not git repos they will be skipped and put in a section of repos that were skipped

```bash
go run main.go -path "C:\Users\jason\GitHub" -r -v
```
