#!/bin/bash

# Check if the container named "firefox" is already running or exists
if [ "$(docker ps -aq -f name=firefox)" ]; then
	if [ "$(docker ps -q -f name=firefox)" ]; then
		echo "Container 'firefox' is already running."
	else
		echo "Starting existing container 'firefox'."
		docker start firefox
	fi
else
	echo "Creating and starting a new container 'firefox'."
	docker run -d \
		--name firefox \
		--security-opt seccomp=unconfined \
		-p 3000:3000 \
		-p 3001:3001 \
		-e TZ=America/Chicago \
		-e PUID=1000 \
		-e PGID=1000 \
		--shm-size="1g" \
		--restart unless-stopped \
		-v "${HOME}/docker/firefox/config:/config" \
		linuxserver/firefox
fi
