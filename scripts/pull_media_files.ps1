# PowerShell Script to Recursively Copy Files

# To allow script execution, run Set-ExecutionPolicy RemoteSigned or Set-ExecutionPolicy Bypass

# List of paths to check
$paths = @(
    "C:\Users\jason\OneDrive\Desktop\testdir",
    "C:\path2",
    "D:\anotherpath"
    # Add more paths as necessary
)

# Destination path relative to the script's location
$destination = Join-Path $PSScriptRoot "Media"

# Check each path and see if it exists
$source = $null
foreach ($path in $paths) {
    if (Test-Path $path) {
        # print path found
        Write-Output "Found path: $path"
        $source = $path
        break
    }
}

# If a valid source directory is found, proceed
if ($source) {
    Write-Output "Found source directory: $source"
    
    # Confirm with the user
    $userInput = Read-Host "Do you want to copy from $source to $destination? (y/n)"
    if ($userInput -eq 'y') {
        # Copying the files
        Copy-Item -Path $source -Destination $destination -Recurse -Force
        Write-Output "Copy operation completed."
    } else {
        Write-Output "Copy operation aborted by the user."
    }
} else {
    Write-Output "No valid path found in the provided list."
}

# Exit the script
exit
