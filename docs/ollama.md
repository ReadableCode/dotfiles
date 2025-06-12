# Ollama

## Setup

- Install Ollama with installation script

```bash
curl https://ollama.ai/install.sh | sh
```

- Pull models

  - Open a WSL or Linux terminal and run:
  
    ```bash
    ollama serve
    ```

  - Open a different terminal and run:
  
    ```bash
    ollama pull llama2-uncensored
    ```

## Running the Back End on Windows

```bash
$env:OLLAMA_HOST="0.0.0.0"
ollama serve
```

## Running Front End with Docker on Windows

```bash
docker run -d --rm -p 8080:8080 -v open-webui:/app/backend/data -e OLLAMA_BASE_URL=<http://host.docker.internal:11434> --name open-webui ghcr.io/open-webui/open-webui:latest
```

## Running in Docker

- If on windows using docker, enable experimental features in docker settings, AMD GPU support still a no go

- Run the following command:

  ```bash
  docker run -d --device=/dev/dri/card0 --device=/dev/dri/renderD128 -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama:rocm
  ```

- once the container is running, you can exec into it

  ```bash
  docker exec -it ollama /bin/bash
  ollama run llama2-uncensored
  ```

## Running on WSL / Linux

- If on Windows in powershell:
  
  ```bash
  wsl
  ```

- Run the server if not already running:

  ```bash
  ollama serve
  ```

- To use, open a different terminal and run

  ```bash
  ollama run llama2-uncensored
  ```

- To watch GPU usage while running, open a new terminal

  - Nvidia Card:
  
    ```bash
    watch -n 0.5 nvidia-smi
    ```
  
  - AMD Card:
  
    - Will have to use standard system monitor

## Closing Ollama

- To close Ollama from the server terminal:

  ```bash
  Ctrl + C
  ```

- To close from the terminal you are prompting from:

  ```bash
  /bye
  ```
