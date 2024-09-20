# Setting Up Chocolatey on Windows

## Run in an elevated powershell prompt (copy the code block and right click in an elevated powershell prompt to paste)

```bash
# Check if chocolatey is installed
if (!(Get-Command choco -ErrorAction SilentlyContinue)) {
    # Allow running of scripts that were downloaded from the internet
    Set-ExecutionPolicy Bypass -Scope Process -Force;
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072;
    # Download and run the Chocolatey installation script
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))
}
```
