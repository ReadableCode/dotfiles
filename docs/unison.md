# Unison

## Windows Setup and Use

### Installation

- Open powershell as admin

```powershell
choco install unison -y
```

- Open normal powershell

  - Create directories if they don't exist

  ```powershell
  mkdir C:\Users\jason\unison_test_1
  mkdir C:\Users\jason\unison_test_2
  ```
  
  - Make a file in one of them:

  ```powershell
  echo "hello" > C:\Users\jason\unison_test_1\file1.txt
  ```

  - Syncronize

  ```powershell
  unison "C:\Users\jason\unison_test_1" "C:\Users\jason\unison_test_2"
  ```

  - Hit enter to accept changes and y to sync


