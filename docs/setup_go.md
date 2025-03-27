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
