# Determine the base directory based on the paths that exist
if (Test-Path 'C:\Users\jason\GitHub\') {
    $gitDir = 'C:\Users\jason\GitHub\'
} elseif (Test-Path 'C:\Users\16937827583938060798\HelloFreshProjects\') {
    $gitDir = 'C:\Users\16937827583938060798\HelloFreshProjects\'
} else {
    Write-Error "Neither base directory was found."
    exit 1
}

# Define the list of file paths relative to the $gitDir directory
$relativePaths = @(
    "dotfiles\scripts\key_remaps.ahk",
    "dotfiles\scripts\sheets.ahk"
)

# Define the user's startup directory
$startupDir = [System.IO.Path]::Combine($env:APPDATA, 'Microsoft\Windows\Start Menu\Programs\Startup')
Write-Output "Startup directory is: $startupDir"


# Create symbolic links for each file in the list
foreach ($relativePath in $relativePaths) {
    $sourceFile = Join-Path $gitDir $relativePath
    $destinationFile = Join-Path $startupDir (Split-Path $relativePath -Leaf)

    if (Test-Path $destinationFile) {
        # Remove the existing file if it exists
        Remove-Item -Path $destinationFile -Force
        Write-Output "Removed existing file at $destinationFile."
    }

    if (Test-Path $sourceFile) {
        # Create the symbolic link
        New-Item -Path $destinationFile -ItemType SymbolicLink -Value $sourceFile -Force
        Write-Output "Symlink created for $sourceFile at $destinationFile."
    } else {
        Write-Warning "Source file not found: $sourceFile"
    }
}
