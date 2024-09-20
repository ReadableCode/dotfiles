# Setup Go

## Setup on Linux

- Using apt

  - Open terminal and run the following commands:

  ```bash
  sudo apt update
  sudo apt install golang
  ```

## Setup on Windows

- Using WinGet

  - Open powershell as administrator and run:
  
  ```bash
  winget install -e --id GoLang.Go
  ```

## Testing and Finishing Installation

- If using VSCode, install the Go extension by searching for `@id:golang.go` in the extensions tab.

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

- Run the program by executing the following command:

  ```bash
  go run hello.go
  ```

## Compiling from source

- To build it and run the executable:

  - cd to directory where the hello.go file is located

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
    ./hello.exe
    ```
