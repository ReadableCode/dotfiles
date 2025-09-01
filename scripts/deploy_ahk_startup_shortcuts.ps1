# deploy_ahk_startup_shortcuts.ps1

$scriptDir = $PSScriptRoot
$startup   = [Environment]::GetFolderPath('Startup')
$ws        = New-Object -ComObject WScript.Shell

Write-Host "Deploying AHK from $scriptDir to $startup"

Get-ChildItem -Path $scriptDir -Filter *.ahk -File | ForEach-Object {
    $name    = $_.Name
    $full    = $_.FullName
    $lnkPath = Join-Path $startup ($_.BaseName + '.lnk')

    $ans = Read-Host "Deploy $name to startup? (y/n)"
    if ($ans -eq 'y') {
        if (Test-Path $lnkPath) { Remove-Item $lnkPath -Force }
        $sc = $ws.CreateShortcut($lnkPath)
        $sc.TargetPath = $full
        $sc.WorkingDirectory = $_.DirectoryName
        $sc.Save()
        Write-Host "Created shortcut for $name"
    } else {
        Write-Host "Skipped $name"
    }
}

