# May need this command to trust running file, run in admin powershell window
# Set-ExecutionPolicy RemoteSigned
# run by either double clicking or running the following command in an elevated powershell prompt

# Check for administrative privileges
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Please run this script as an Administrator."
    exit
}

# Check if Chocolatey is installed
if (!(Get-Command choco -ErrorAction SilentlyContinue)) {
    Try {
        # Set TLS 1.2 protocol
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

        # Download and run the Chocolatey installation script
        Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))
    }
    Catch {
        Write-Error "Failed to install Chocolatey. Error: $_"
        exit
    }
}

# Read the list of applications from the windows_apps.txt file in the parent directory
$apps = Get-Content -Path ..\app_lists\windows_apps_personal.txt

foreach ($app in $apps) {
    # Check if the application is already installed
    if (choco list --local-only | Select-String "$app") {
        Write-Host "$app is already installed."
    }
    else {
        Try {
            # Install the application
            choco install $app -y
        }
        Catch {
            Write-Error "Failed to install $app. Error: $_"
        }
    }
}
