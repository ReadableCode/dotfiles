
# Setting Up SSH Server

* open elevated powershell window
* run commands:
  
  ```bash
  winget install "openssh beta"
  ```

  * if not using bootstrap script:
  
    ```bash
    winget install -e --id Notepad++.Notepad++
    ```

* run command:

  ```bash
  New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
  ```
  
* run command:

  ```bash
  Set-Service sshd -StartupType Automatic
  ```
  
* run command:
  
  ```bash
  net start sshd
  ```
  
  * (might say already started, thats OK)
* get rsa.pub from ansible server using this command executed client machine:

  ```bash
  cat ~/.ssh/id_rsa.pub
  ```

* make directory if doesnt exist: "$env:USERPROFILE\\.ssh\" by running this:

  ```bash
  if (!(Test-Path -Path "$env:USERPROFILE\.ssh\")) { New-Item -ItemType Directory -Path "$env:USERPROFILE\.ssh\" }
  ```
  
* Pick one of the following to get ssh pub key onto new windows client:
  * Using admin powershell on remote machine or some ssh connection already set up (password pased or from machine with key already set up) NOTE: both of these fail to add a newline at the end of the line
  
    ```bash
    Add-Content -Path "$env:USERPROFILE\.ssh\authorized_keys" -Value "CONTENTS_OF_ID_RSA_PUB"
    Add-Content -Path "C:\ProgramData\ssh\administrators_authorized_keys" -Value "CONTENTS_OF_ID_RSA_PUB"
    ```

  * Using notepad++ on the client:
  
    ```bash
    Start-Process "notepad++.exe" "$env:USERPROFILE\.ssh\authorized_keys"
    Start-Process "notepad++.exe" "C:\ProgramData\ssh\administrators_authorized_keys" -Verb "runas"
    ```

  * Using admin powershell on remote machine or some ssh connection already set up (password pased or from machine with key already set up)(might replace existing file):

    ```bash
    echo "CONTENTS_OF_ID_RSA_PUB" | Out-File -FilePath "$env:USERPROFILE\.ssh\authorized_keys" -Encoding ASCII -Force
    echo "CONTENTS_OF_ID_RSA_PUB" | Out-File -FilePath "C:\ProgramData\ssh\administrators_authorized_keys" -Encoding ASCII -Force
    ```

* Change persmissions for the administrators_authorized_keys file:

  ```bash
  icacls C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r
  icacls C:\ProgramData\ssh\administrators_authorized_keys /grant SYSTEM:`(F`)
  icacls C:\ProgramData\ssh\administrators_authorized_keys /grant BUILTIN\Administrators:`(F`)
  ```
  
* Change settings in sshd_config file:

  ```bash
  Start-Process "notepad++.exe" "C:\ProgramData\ssh\sshd_config" -Verb "runas"
  ```
  
  * Uncomment and change the following lines, adding if they dont exist:

    ```bash
    StrictModes no
    PubkeyAuthentication yes
    ```

* Run these commands in admin powershell to set the default shell to powershell:

  ```bash
  New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -PropertyType String -Force
  New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShellCommandOption -Value "/c" -PropertyType String -Force
  ```
  
* Run these commands in admin powershell to restart ssh-server and apply changes:

  ```bash
  net stop sshd
  net start sshd
  ```
