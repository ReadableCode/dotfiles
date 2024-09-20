# Setup Rust

## Setup on Linux

- Using apt

  - Open terminal and run the following commands:

  ```bash
  sudo apt update
  sudo apt install rustc cargo
  ```

## Setup on Windows

- Using WinGet

  - Open powershell as administrator and run:

  ```bash
  winget install -e --id Rustlang.Rustup
  winget install -e --id Microsoft.VisualStudio.2022.BuildTools --source winget --override "--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --includeOptional"
  ```
  
  To finish installaion:
  - open Visual Studio Installer
  - press Modify
  - check Desktop Development with C++
  - press Modify
  
  - Will need to close and reopen all VSCode windows to make sure the powershell window can access cargo and rustc.

## Testing and Finishing Installation

- If using VSCode, install the Rust extension by searching for `rust-analyzer` in the extensions tab.

- Close and reopen the terminal to make sure installation is successful and then run the folling commands to verify the versions of rustup and rustc:

  ```bash
  rustup --version
  rustc --version
  ```

## Compile and Run a Rust Program with Rustc

- Create a new file with the `.rs` extension and write the following code:

  ```rust
  fn main() {
      println!("hello world!");
  }
  ```

- Compile the program using the following command:

  - This will create the compiled program in the same directory as the source file for the operating system you are using to compile it:

  ```bash
  rustc <filename>.rs
  ```

- Run the compiled program using the following command:

  - For Windows this will be a `.exe` file, for Linux it will be the same name as the file:
  
  ```bash
  ./<filename>
  ```

## Compile and Run a Rust Program with Cargo

- Create a new project using the following command:

  - This will create a new directory with the project name and the necessary files for a cargo project:

  ```bash
  cargo new <project_name>
  ```

- Navigate to the project directory and run the following command to  build the project:

  ```bash
  cargo build
  ```

- Run the project manually using the following command:

  ```bash
  cd target/debug
  ./<project_name>
  ```

- Or run the project using the following command:

  ```bash
  cargo run
  ```

## Checking and Formatting

- Run the following command to check without compiling:

  ```bash
  cargo check
  ```

- Run the following command to format the code:

  ```bash
  cargo fmt
  ```
