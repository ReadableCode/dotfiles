# Installing Docker

## Installing Docker on Windows

- Check System Requirements:

- Enable Hyper-V: Docker for Windows requires Hyper-V to be enabled. Check if your system supports Hyper-V by running the command `systeminfo.exe` in Command Prompt and looking for "Hyper-V Requirements".
  - If it is not installed:
    - Make sure enabled in BIOS
      - AMD
        - SVM Mode
      - Intel
        - VT-x
        - VT-d
    - Enable Hyper-V in Windows Features
      - Hit the Windows key and type "Windows Features".
      - Check the box next to "Hyper-V" and click "OK".

- Download Docker Desktop for Windows:
  - To install using winget:
    - Open PowerShell as an administrator and run the following command:

        ```powershell
        winget install Docker
        ```
  
  - To Install with Chocolatey:
    - Open PowerShell as an administrator and run the following command:

        ```powershell
        choco install docker-desktop
        ```

  - To install using the Docker Desktop for Windows page:
    - Go to the Docker Desktop for Windows page: Docker Desktop for Windows.
    - Click on "Download Docker Desktop for Windows".
    - Run the installer you downloaded.
    - Follow the prompts to install Docker Desktop.
    - When prompted, select the "Use Windows containers" option if you want to use Windows containers. If unsure, you can choose the default option to use Linux containers.
    - Finish Installation:

      - After installation, Docker Desktop will start automatically. It may take a few minutes to start.
      - Once Docker Desktop is running, you'll see a Docker icon in the system tray. Docker is now installed and running on your Windows machine.

## Installing Docker on Ubuntu

- Update Package Index:
  - Open a terminal window by pressing Ctrl+Alt+T.
  - Update the package index with the following command:

      ```bash
      sudo apt update
      ```

- Install packages to allow apt to use a repository over HTTPS and install necessary dependencies:
  - Install the necessary packages with the following command:

      ```bash
      sudo apt install apt-transport-https ca-certificates curl software-properties-common
      ```

- Add Docker GPG Key:

  ```bash
  curl -fsSL <https://download.docker.com/linux/ubuntu/gpg> | sudo apt-key add -
  ```

- Add the Docker repository to your system's software sources:

  ```bash
  sudo add-apt-repository "deb [arch=amd64] <https://download.docker.com/linux/ubuntu> $(lsb_release -cs) stable"
  ```

- Update Package Index Again:

  ```bash
  sudo apt update
  ```

- Install Docker Engine:

  ```bash
  sudo apt install docker-ce docker-ce-cli containerd.io
  ```

- Verify Docker Installation:

  - Check that Docker is installed correctly by running the hello-world image:
    - This command downloads a test image and runs it in a container. If Docker is installed correctly, you should see a message indicating that your installation is working.

      ```bash
      sudo docker run hello-world
      ```

- Manage Docker as a Non-root User (Optional):

  - By default, Docker commands require root privileges. If you want to run Docker commands without sudo, you can add your user to the docker group:

    ```bash
    sudo usermod -aG docker ${USER}
    ```

  - After running this command, log out and log back in or run the following command to activate the changes:

    ```bash
    su - ${USER}
    ```

## Installing Docker on macOS

- Install with Brew:

```bash
brew install --cask docker
```
