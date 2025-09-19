# Sym Linking and Hard Linking

## Linux

### Sym Linking on Linux

- To Create at a specific directory

```bash

ln -s source_file myfile

```

- To Create at current directory

```bash

ln -s /path/to/src/file

```

## Windows

### Hard linking on Windows

- To Create at a specific directory

Note: Target is the file that already exists, Path is the new hard link you are creating.

```bash
New-Item -ItemType HardLink `
  -Path "C:\Users\jason\GitHub\dotfiles\application_configs\vscode\ryzen.code-workspace" `
  -Target "C:\Users\jason\GitHub\myworkspace.code-workspace"
```

```bash
New-Item -ItemType HardLink `
  -Path "C:\Users\jason.christiansen\GitHub\dotfiles\application_configs\vscode\fourteen_foods.code-workspace" `
  -Target "C:\Users\jason.christiansen\GitHub\fourteen_foods.code-workspace"
```
