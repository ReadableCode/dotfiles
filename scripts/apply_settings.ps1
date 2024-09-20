# PowerShell script with configurable sections

# --- Enable or Disable Clipboard History and Syncing ---
# Uncomment the lines below to enable clipboard history and syncing
# Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\Clipboard" -Name "EnableClipboardHistory" -Value 1
# Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\Clipboard" -Name "EnableClipboardSyncAcrossDevices" -Value 1

# Uncomment the lines below to disable clipboard history and syncing
# Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\Clipboard" -Name "EnableClipboardHistory" -Value 0
# Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\Clipboard" -Name "EnableClipboardSyncAcrossDevices" -Value 0

# --- Set Chrome as Default Browser if Installed ---
# Uncomment the lines below to set Chrome as the default browser
# $chromePath = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
# if (Test-Path $chromePath) {
#     Start-Process "chrome.exe" "--make-default-browser"
# } else {
#     Write-Host "Google Chrome is not installed."
# }
