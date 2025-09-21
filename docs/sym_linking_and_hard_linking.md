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

### Hard linking on Linux

- To Create at a specific directory

Note: Target is the file that already exists, Path is the new hard link you are creating. The one that comes first is the target, the second is the new link.

```bash
ln /home/jason/HelloFresh/GDrive/Projects/hellofresh.code-workspace /home/jason/HelloFresh/GDrive/Projects/dotfiles/application_configs/vscode/hellofresh.code-workspace
```

```bash
ln /home/jason/HelloFresh/GDrive/Projects/dotfiles/application_configs/vscode/settings.json /home/jason/.config/Code/User/settings.json
```

## Windows

### Hard linking on Windows

- To Create at a specific directory

Note: Target is the file that already exists, Path is the new hard link you are creating.

```bash
New-Item -ItemType HardLink `
  -Path "C:\Users\jason\GitHub\dotfiles\application_configs\vscode\ryzen.code-workspace" `
  -Target "C:\Users\jason\GitHub\ryzen.code-workspace"
```

```bash
New-Item -ItemType HardLink `
  -Path "C:\Users\jason\GitHub\yoga.code-workspace" `
  -Target "C:\Users\jason\GitHub\dotfiles\application_configs\vscode\yoga.code-workspace"
```

```bash
New-Item -ItemType HardLink `
  -Path "C:\Users\jason\GitHub\ultrapocket.code-workspace" `
  -Target "C:\Users\jason\GitHub\dotfiles\application_configs\vscode\ultrapocket.code-workspace"
```

```bash
New-Item -ItemType HardLink `
  -Path "C:\Users\jason.christiansen\GitHub\dotfiles\application_configs\vscode\fourteen_foods.code-workspace" `
  -Target "C:\Users\jason.christiansen\GitHub\fourteen_foods.code-workspace"
```

```bash
New-Item -ItemType HardLink `
  -Path "C:\Users\16937827583938060798\HelloFreshProjects\hellofresh.code-workspace" `
  -Target "C:\Users\16937827583938060798\HelloFreshProjects\dotfiles\application_configs\vscode\hellofresh.code-workspace"
```
