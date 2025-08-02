# Settingn Up Local AI

## Ollama

### Installation

#### Installation on Windows

- Download ollama from [Ollama](https://ollama.com/download)

- Models can be found and pulled from [Ollama Models](https://ollama.com/models)

#### Installation on Linux / WSL

- Install Ollama with installation script

```bash
curl https://ollama.ai/install.sh | sh
```

### Pull at least one model

```bash
ollama pull llama2-uncensored
```

### Running Models Directly

```bash
ollama run llama2-uncensored
```

- To Exit the model prompt, type:

```bash
/bye
```

### Running the Back End

- This will start the Ollama server, which allows you to run models and access them via HTTP requests or WebUI like OpenWebUI. We do not need to expose this to the internet, so we will run it on localhost since the open-webui will be running on the same machine.

```bash
ollama serve
```

#### To watch GPU usage while running, open a new terminal

- Nvidia Card:

```bash
watch -n 0.5 nvidia-smi
```

- AMD Card:

  - Will have to use standard system monitor

### Closing Ollama

- To close Ollama from the server terminal:

```bash
Ctrl + C
```

- To close from the terminal you are prompting from:

```bash
/bye
```

## Setting up OpenWebUI

### Running Front End with Docker on Windows

```bash
docker run -d --rm -p 8080:8080 -v open-webui:/app/backend/data -e OLLAMA_BASE_URL=http://host.docker.internal:11434 --name open-webui ghcr.io/open-webui/open-webui:latest
```

### Running Front End with Docker on Linux / WSL

```bash
docker run -d --network host -v open-webui:/app/backend/data -e OLLAMA_BASE_URL=http://localhost:11434 --name open-webui --restart always ghcr.io/open-webui/open-webui:latest
```

- Open a browser and go to `http://localhost:8080` to access the OpenWebUI interface.
