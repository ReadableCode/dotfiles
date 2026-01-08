# Loop logging Unraid from powershell ssh client

- In PowerShell, run the following code to log Docker memory usage from an Unraid server at IP

```powershell
while ($true) {
    $out = @()
    $out += (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    $out += ssh root@192.168.86.31 'docker stats --no-stream'
    $out | Set-Content docker-mem.log
    Start-Sleep -Seconds 5
}
```

- To parse the file after a crash or at any time, run the following code in a new PowerShell session:

```powershell
Get-Content docker-mem.log |
Where-Object { $_ -match 'MiB|GiB' -and $_ -notmatch '^CONTAINER ID|^NAME' } |
ForEach-Object {
    $cols = ($_ -split '\s{2,}')

    $name = $cols[1]                 # NAME column
    $memUsageLimit = $cols[3]        # "MEM USAGE / LIMIT" column
    $used = ($memUsageLimit -split '/')[0].Trim()

    $mib = if ($used -match 'GiB') {
        [double]($used -replace 'GiB', '') * 1024
    }
    else {
        [double]($used -replace 'MiB', '')
    }

    [pscustomobject]@{
        Name = $name
        Used = $used
        MiB  = $mib
    }
} |
Sort-Object MiB -Descending |
Select-Object Name, Used
```
