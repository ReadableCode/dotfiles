# Settingn Up Local AI

- Download ollama from [Ollama](https://ollama.com/download)

- Open the application, it will open a powershell window and suggest running a model, you can swap it for any other model listed at: [Here](https://ollama.com/library)
- To run a model, use the command `ollama run <model_name>` in the powershell window. For example, to run the Llama2 model, use `ollama run llama2`.
- Instead of using the cli you can also run like this with it open to local network

```bash
$env:OLLAMA_HOST="0.0.0.0"
ollama serve
```

## Setting up OpenWebUI

```bash
docker run -d --network host -v open-webui:/app/backend/data -e OLLAMA_BASE_URL=http://localhost:11434 --name open-webui --restart always ghcr.io/open-webui/open-webui:latest
```

- Open a browser and go to `http://localhost:8080` to access the OpenWebUI interface.
