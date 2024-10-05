# Setting Up Python

Here are the revised instructions that include installing Python from the Windows Store, adding Python to the PATH, and enabling long path support:

## Setting Up Python 3.10 on Windows

### Option 1: Installing from the Windows Store

* Open the Microsoft Store on your Windows system.

* Search for "Python 3.10" in the store.

* Select the "Python 3.10" app from the search results.

* Click on the "Get" or "Install" button to download and install Python 3.10 from the Windows Store.

   **Note:** By default, Python installed from the Windows Store is already added to the system's PATH.

### Option 2: Installing from the Python Site

* Visit the official Python site at python.org and navigate to the downloads section.

* Click on the "Downloads" tab and choose Python 3.10 for Windows.

* Download the Python 3.10 installer appropriate for your system architecture (32-bit or 64-bit).

* Run the downloaded installer and follow the installation wizard. Make sure to select the option to customize the installation.

* In the customization options, enable the "Add Python to PATH" checkbox. This will add Python to the system's PATH for easy accessibility.

* Continue with the installation process and complete the installation.

### Enabling Long Path Support on Windows

* Open a PowerShell or Command Prompt window as an administrator.

* Run the following command to enable long path support in the Windows registry:

   ```bash
   reg add HKLM\SYSTEM\CurrentControlSet\Control\FileSystem /v LongPathsEnabled /t REG_DWORD /d 1 /f
   ```

   This command enables long path support for the system.

### Verifying Python Installation on Windows

* Open a new command prompt or PowerShell window.

* Verify that Python 3.10 is installed correctly by running the following command:

   ```bash
   python --version
   ```

   This command should display the installed Python version as "Python 3.10.x".

### Installing pipenv on Windows

* In powershell as admin install pipenv:

   ```bash
   pip install pipenv
   # It may ask for installing a version of python with pyenv, say yes
   ```

* Add pipenv to path

  * Open the start menu and search for "Environment Variables" and click on "Edit the system environment variables"
  * In the System Properties window click on "Environment Variables"
  * Get the path pipenv was installed at:
    * Run:

         ```bash
         pip show pipenv
         ```

    * copy the path from the "Location" field
  * Add to user path:
    * In the environment variables window, under the "User variables" section, find the "Path" variable and click "Edit"
    * Click "New" and paste the path to pipenv
  * Add to system path:
    * In the Environment Variables window, under the "System variables" section, find the "Path" variable and click "Edit"
    * Click "New" and paste the path to pipenv

## Setting Up Python 3.10 on Debian Based Linux

* Open a terminal on your Debian system.

* Check if Python 3.10 is already installed by running the following command:

   ```bash
   python3 --version
   ```

   If Python 3.10 is already installed, the command will display the installed version. If not, proceed to the next step.

* Update the package lists by running the following command:

   ```bash
   sudo apt update
   ```

* Install Python 3.10 using the following command:

   ```bash
   sudo apt install python3.10
   ```

* After the installation is complete, verify that Python 3.10 is installed correctly by running the following command:

   ```bash
   python3.10 --version
   ```

   This command should display the installed Python version as "Python 3.10.x".

Please note that Python 3.10 may already be installed on your Debian system by default, and you can skip the installation steps if it's already present.

## Setting up python on macOS

* macOS comes with a version of python installed by default that is probably not the version you want to use. To install a different version of python, you can use Homebrew to install it and pyenv to manage the different versions.

* Install Homebrew if not already installed:

   ```bash
   /bin/bash -c "$(curl -fsSL <https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh>)"
   ```

* Install pyenv using Homebrew:

   ```bash
   brew install pyenv
   ```

* Add the following to your shell configuration file (e.g., ~/.zshrc for Zsh or ~/.bashrc for bash):

   ```bash
   export PATH="$HOME/.pyenv/bin:$PATH"
   ```

  * Source the shell configuration file to apply the changes or restart your terminal:

      ```bash
      source ~/.zshrc
      ```

* Select your python version globally:

   ```bash
   pyenv global 3.10.0
   ```

* Verify that Python 3.10 is installed correctly by running the following command:

   ```bash
   python --version
   ```

   This command should display the installed Python version as "Python 3.10.x".

## Setting up pipenv on Debian Based Linux or macOS

* In terminal install pipenv:

   ```bash
   pip install pipenv
   ```

## Setting up and using Virtual Environments for Python: pyenv

* This enables installing multiple versions of python on the same system

* Install pyenv:

  * On Linux:
  
      ```bash
      sudo apt update
      sudo apt install -y \
      build-essential \
      libbz2-dev \
      libncurses-dev \
      libffi-dev \
      libreadline-dev \
      libssl-dev \
      zlib1g-dev \
      libsqlite3-dev \
      tk-dev \
      libgdbm-dev \
      libdb-dev \
      libexpat1-dev \
      liblzma-dev \
      libgmp-dev \
      libcurl4-openssl-dev \
      uuid-dev \
      curl
      ```

      ```bash
      curl https://pyenv.run | bash
      ```

  * Add the following to your shell config file (e.g., ~/.bashrc or ~/.zshrc):

      ```bash
      export PYENV_ROOT="$HOME/.pyenv"
      export PATH="$PYENV_ROOT/bin:$PATH"
      eval "$(pyenv init --path)"
      eval "$(pyenv init -)"
      ```

  * Restart your terminal or run the following command to apply the changes:

      ```bash
      source ~/.bashrc
      ```

  * Check if pyenv is available on the terminal

      ```bash
      pyenv --version
      ```

  * To install a version of python, run:

      ```bash
      pyenv install 3.10.0
      ```

## Setting up and using Virtual Environments for Python: venv

* This is an alternative to pipenv not to pyenv

* On Windows (PowerShell):

  * Create the Virtual Environment:
    * To create a virtual environment named your_env_name in ~\venvs\, use the following command:

      ```bash
      python -m venv C:\Users\<username>\venvs\your_env_name
      ```

  * Activate the Virtual Environment:

      ```bash
      C:\Users\<username>\venvs\your_env_name\Scripts\Activate
      ```

  * Deactivate the Virtual Environment:

      ```bash
      deactivate
      ```

* On Linux or macOS:

  * Create the Virtual Environment:
    * To create a virtual environment named your_env_name in ~/venvs/, use:

      ```bash
      python -m venv ~/venvs/your_env_name
      ```

  * Activate the Virtual Environment:

      ```bash
      source ~/venvs/your_env_name/bin/activate
      ```

  * Deactivate the Virtual Environment:

      ```bash
      deactivate
      ```
