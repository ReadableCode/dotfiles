# Setup Git

## Install Git

### Install Git on Windows

* To install using winget:
  * Open Powershell as Admin by right clicking on the start menu and selecting "Windows Powershell (Admin)"
  * Verify winget is installed by typing:

  ```bash
  winget --version
  ```

  * If winget is not installed, open Microsoft store and update "app installer" and verify with the above command

* To Install using chocolatey:
  * Open Powershell as Admin by right clicking on the start menu and selecting "Windows Powershell (Admin)"
  * Verify chocolatey is installed by typing:

  ```bash
  choco --version
  ```

  * If chocolatey is not installed, follow the instructions in [setup_windows_chocolatey.md](setup_windows_chocolatey.md)
  
  * Run the following command to install Git:

    ```bash
    choco install git.install
    ```

* Run the following command to install Git:

    ```bash
    winget install Git.Git
    ```

### Install Git on Linux

* Git is installed in most distributions by default, but if it is not, you can install it with the following command:

  ```bash
  sudo apt install -y git-all
  ```

* To verify Git is installed, run the following command:

  ```bash
  git --version
  ```

### Install Git on macOS

* Git is installed in macOS by default but the first Git command you run may error with the message:
  
    ```bash
    No Developer Tools were found
    ```
  
  * If this happens you may get a popup icon in the bottom right corner asking if you want to install the developer tools. Click "Install" and follow the prompts.

## Set Up Git

### Set Up Git on Windows

* Open Git bash: right click on desktop or in the empty space in a folder you want your code in and select "Git Bash Here"
  * On windows 11 you will need to click "Show More Options"
* Run the following commands (one line at a time) to set up Git:

  ```bash
  git config --global user.email "emailaddress@gmail.com"
  git config --global user.name "your_username_or_name"
  git config --global core.fileMode false
  git config --global core.autocrlf false
  ```

* If you want to check your configuration settings, you can use:

  ```bash
  git config --list
  ```

### Set Up Git on Linux

* open terminal and run commands:

  ```bash
  sudo apt install -y git-all
  git config --global user.email "emailaddress@gmail.com"
  git config --global user.name "your_username_or_name"
  git config --global core.editor nano
  git config --global core.fileMode false
  git config --global core.autocrlf false
  ```

* If you want to check your configuration settings, you can use:

  ```bash
  git config --list
  ```

### Set Up Git on macOS

* open terminal and run commands:

  ```bash
  git config --global user.email "emailaddress@gmail.com"
  git config --global user.name "your_username_or_name"
  git config --global core.fileMode false
  git config --global core.autocrlf false
  ```

* If you want to check your configuration settings, you can use:

  ```bash
  git config --list
  ```

## Generate SSH Keys

### Windows

* copy public key from target and put it on GitHub using Git bash

    ```bash
    cd ~
    ls
    ```

* if .ssh directory doesn't exist:

    ```bash
    mkdir .ssh
    ```

* enter .ssh directory

    ```bash
    cd .ssh
    ```

* if .pub key doesn't exist:

    ```bash
    ssh-keygen -t rsa -b 4096 # press enter to accept defaults
    ```

* Run the following command and copy just the key to GitHub:

    ```bash
    cat ~/.ssh/id_rsa.pub
    ```

### Linux or macOS

* open terminal and run commands:

  ```bash
  cd ~
  ls -a
  ```
  
* if .ssh directory doesn't exist:

  ```bash
  mkdir .ssh
  ```
  
* enter .ssh directory

  ```bash
  cd .ssh
  ```
  
* if .pub key doesn't exist:

  ```bash
  ssh-keygen # press enter to accept defaults
  ```
  
* Run the following command and copy just the key to GitHub:

  ```bash
  cat ~/.ssh/id_rsa.pub
  ```

## Put the public SSH key to GitHub

* add key to GitHub:
  * <https://github.com/settings/keys>
  * click "New SSH Key"
  * paste key into "Key" field
  * click "Add SSH Key"
  * Enable SSO if needed

## Clone into an existing folder

* open terminal or Git bash and navigate to the folder you want to clone into

* Run the following command to clone the repository:

  ```bash
  # Initialize Git if not already initialized
  git init

  # Add the remote repository (skip if already set)
  git remote add origin <repo-url>

  # Fetch the remote branches without modifying local files
  git fetch origin

  # Create and checkout the 'master' branch from remote without overwriting files
  git checkout -b master origin/master --track

  # Pull the latest changes from the remote master branch
  git pull
  ```

## Cloning from a local directory

* You can clone from a local or accessible remote directory and treat it as a Git remote. This is useful for private data (e.g., secrets) you don’t want on GitHub.

```bash
git clone 192.168.xx.xx:/mnt/user/GitHub/test_clone_local
# or to use a different user
git clone root@192.168.xx.xx:/mnt/user/GitHub/test_clone_local
```

* To allow pushing to a non-bare repository, run this in the target repository:

```bash
git config receive.denyCurrentBranch updateInstead
```

## Using Separate Git Directories

* Useful for putting code into a synced directory but keeping .git folder out of synced directory

* If you want to use a separate Git directory (e.g., for a private repository), you can set it up as follows:

  * cd to location where worktree will be

  ```bash
  git init --separate-git-dir path/to/folder/for/.git/contents
  ```

* Clone existing repository into the separate Git directory:

  ```bash
  git clone --separate-git-dir path/to/folder/for/.git/contents <repo-url>
  ```

## Resolve Common Problems

### Git diff and Git status don't show the updated files as changed

* To check for non-obviouse changes:

  ```bash
  git status -vvv
  ```

* Use input method of crlf and `git add --renormalize .` to fix the issue if the difference is due to line endings:

  * To tell Git to ignore line ending differences and use lf always:

  ```bash
  git config core.autocrlf input
  ```

  * Then set all the files correct

  ```bash
  git add --renormalize .
  ```

* Run the following command to fix the issue temporarily:

  ```bash
  git update-index --really-refresh
  ```

* To fix for a single file:

  ```bash
  git rm --cached <filename>
  git add <filename>
  git status
  ```

* To fix for all files:

  * **Warning**: Possibly destructive!
  
    ```bash
    git rm --cached -r .
    git add .
    git status
    ```

### Cannot pull because of changes locally but there are no changes locally

* **Warning**: Possibly destructive!

  ```bash
  git rm --cached -r .
  git reset --hard
  git pull
  ```
