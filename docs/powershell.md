# Powershell

## Making Symbolic Links

- open powershell as admin

- make directories if not exist:

```bash
mkdir ~\.config\nvim
```

- cd to directory where the symbolic link is to be placed:

```bash
cd ~\.config\nvim
```

- create the symbolic link:

  - For files:

  ```bash
  cmd /c mklink <name_of_link> <target>
  ```

  - For directories:

  ```bash
  cmd /c mklink /D <name_of_link> <target>
  ```
