# Check if the container named "firefox" already exists
$container = docker ps -aq -f name=firefox

if ($container) {
    # Check if the container is already running
    $runningContainer = docker ps -q -f name=firefox
    if ($runningContainer) {
        Write-Output "Container 'firefox' is already running."
    } else {
        Write-Output "Starting existing container 'firefox'."
        docker start firefox
    }
} else {
    Write-Output "Creating and starting a new container 'firefox'."
    docker run -d `
      --name firefox `
      --security-opt seccomp=unconfined `
      -p 3000:3000 `
      -p 3001:3001 `
      -e TZ=America/Chicago `
      -e PUID=1000 `
      -e PGID=1000 `
      --shm-size="1g" `
      --restart unless-stopped `
      -v "${env:USERPROFILE}\docker\firefox\config:/config" `
      linuxserver/firefox
}