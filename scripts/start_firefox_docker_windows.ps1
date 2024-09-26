docker run -d --name firefox --security-opt seccomp=unconfined -p 3000:3000 -p 3001:3001 -e TZ=America/Chicago -e PUID=1000 -e PGID=1000 --shm-size="1g" --restart unless-stopped -v C:\Users\jason\docker\firefox\config:/config linuxserver/firefox

