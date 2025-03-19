param(
    [switch]$Delete
)

# Start searching from one directory up
$startDir = (Get-Item ..).FullName

# Define the patterns to search for
$patterns = @("sync-conflict", "~syncthing")

# Use Windows `dir /s /b` for fast file listing
$files = cmd /c "dir /s /b $startDir" | Where-Object {
    $match = $false
    foreach ($pattern in $patterns) {
        if ($_ -like "*$pattern*") {
            $match = $true
            break
        }
    }
    $match
}

# Output the found files
if ($files) {
    Write-Host "Found files in ${startDir}:"
    $files | ForEach-Object { Write-Host $_ }

    # If -Delete flag is used, delete the files
    if ($Delete) {
        $files | ForEach-Object { Remove-Item $_ -Force }
        Write-Host "Deleted all matching files."
    }
} else {
    Write-Host "No matching files found in ${startDir}."
}
