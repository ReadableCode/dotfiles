# Setting Up Local AI

Local LLM / image-generation setups across my machines. Two stacks are
documented here:

- **Odysseus** — full local AI assistant (chat, agents, RAG, research, email,
  image gen) run via Docker Compose. This is the primary setup.
- **Ollama + OpenWebUI** — lighter-weight model runner + chat UI.

See also: [`stable_diffusion.md`](stable_diffusion.md),
[`setup_docker.md`](setup_docker.md),
[`setup_windows_ssh_server.md`](setup_windows_ssh_server.md).

---

## Machine inventory (which box for what)

| | **Zephyrus** (`sshzephyrus`) | **RyzenWhite** (`sshryzenwhite`) |
|---|---|---|
| Host / IP | ROG Zephyrus G14 GA401QM / 192.168.86.170 | 192.168.86.94 |
| OS | Fedora 43 (Workstation) | Windows 11 Pro |
| CPU | Ryzen 9 5900HS (8C/16T, Zen 3) | Ryzen 7 2700X (8C/16T, Zen+) |
| RAM | 15 GB | **64 GB** |
| GPU | RTX 3060 Laptop **6 GB**, NVIDIA/**CUDA** | RX 6600 XT **8 GB**, AMD (**no CUDA**) |
| Free disk | ~936 GB | ~87 GB (C:) |
| Container stack | Docker + NVIDIA toolkit **working** | Docker Desktop installed (stopped), WSL2 Ubuntu |

**Verdict for local AI: use the Zephyrus.** Despite less VRAM/RAM, its NVIDIA
GPU gives the plug-and-play CUDA path that both llama.cpp and diffusers (Stable
Diffusion) want. The RyzenWhite's AMD card has no CUDA — LLMs would fall back to
Vulkan (slower) and Stable Diffusion on AMD/Windows is painful (ROCm is
Linux-only). RyzenWhite's only real edge is 64 GB RAM, useful only for slow
CPU-offloaded inference of very large (14B–70B) models. The Mac mini is the
control machine (runs admin tooling, holds SSH keys); it does not serve models.

---

## Odysseus

Self-hosted local AI assistant. Repo: <https://github.com/pewdiepie-archdaemon/odysseus>

### Prerequisites

- Docker Engine + the `docker compose` v2 plugin.
  - Fedora ships Podman, **not** Docker. Install real Docker CE — see
    [`setup_docker.md`](setup_docker.md). `podman compose` is hit-or-miss with
    Compose v2 features Odysseus relies on.
- (NVIDIA GPU) the NVIDIA Container Toolkit — see [GPU passthrough](#gpu-passthrough-nvidia-on-fedora) below.

### First-run setup — do these IN ORDER (the right way)

The gotcha: several things must be set **before the first `docker compose up`**,
because the admin account and other state get baked into `./data` on first boot
and are not re-read afterward.

```bash
git clone https://github.com/pewdiepie-archdaemon/odysseus.git
cd odysseus
cp .env.example .env
```

1. **Edit `.env` BEFORE first boot.** At minimum uncomment and set the admin
   password (no leading `#`, no quotes):
   ```bash
   ODYSSEUS_ADMIN_PASSWORD=your_strong_password   # login user is "admin"
   # APP_PORT=7001        # only if 7000 is taken
   # APP_BIND=127.0.0.1   # leave as-is; set 0.0.0.0 ONLY for LAN/reverse-proxy
   ```
   If you skip this, the entrypoint logs `Creating initial admin... Login with
   your existing admin credentials` and you'll have no password — see
   [Troubleshooting](#troubleshooting).

2. **(NVIDIA GPU) set up GPU passthrough BEFORE first boot** so Cookbook detects
   the real GPU instead of the iGPU/CPU. See
   [GPU passthrough](#gpu-passthrough-nvidia-on-fedora).

3. **Bring it up:**
   ```bash
   docker compose up -d --build
   ```
   Optional extras (PDF viewer, Office extraction; pulls in AGPL PyMuPDF):
   ```bash
   docker compose build --build-arg INSTALL_OPTIONAL=true
   docker compose up -d
   ```

4. **Open the UI:** <http://localhost:7000> (or your `APP_PORT`). Log in as
   `admin` with the password you set. The web UI binds to `127.0.0.1` by default.

Bundled services (all bound to `127.0.0.1`): Odysseus (`:7000`), ChromaDB
(`:8100`), SearXNG (`:8080`), ntfy (`:8091`).

### Reconfiguring later

- **Runtime env vars** (`APP_PORT`, `APP_BIND`, API keys, etc.): edit `.env`,
  then `docker compose up -d` — Compose recreates only the changed containers.
  No rebuild needed.
- **Build-time args** (e.g. `INSTALL_OPTIONAL`): require `docker compose build`
  again.
- `./data` is the source of truth for auth + app state. **`docker compose down
  -v` does NOT reset the admin** — that only drops named volumes (chromadb,
  searxng, ntfy). The admin lives in the `./data` bind mount.

### GPU passthrough (NVIDIA, on Fedora)

Symptom if missing: Cookbook/settings don't see the NVIDIA GPU, and
`scripts/check-docker-gpu.sh` fails with `failed to discover GPU vendor from
CDI: no known GPU vendor found`. Host `nvidia-smi` working is **not** enough —
Docker needs the NVIDIA Container Toolkit to hand the GPU to a container.

```bash
# 1. Add NVIDIA's repo (NOT in Fedora's default repos) + install the toolkit.
#    Run as ONE line — a line break splits the pipe and silently fails.
curl -s -L https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo | sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo > /dev/null
sudo dnf install -y nvidia-container-toolkit

# 2. Wire it into the Docker daemon + restart (briefly bounces containers).
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 3. Verify.
docker info | grep -i nvidia              # expect: Runtimes: ... nvidia ...
cd ~/GitHub/odysseus && bash scripts/check-docker-gpu.sh   # want 3 passed, 0 failed
```

Then enable the GPU compose overlay for Odysseus:

```bash
# Safe helper — only edits .env once passthrough is confirmed working:
bash scripts/check-docker-gpu.sh --enable-nvidia-overlay
# (this writes COMPOSE_FILE=docker-compose.yml:docker/gpu.nvidia.yml to .env)

docker compose up -d
docker exec odysseus-odysseus-1 nvidia-smi   # GPU must show up INSIDE the container
```

Note: passthrough means the container can *see* the GPU; it does **not**
guarantee CUDA-built inference engines. The slim image ships no CUDA userspace —
install serve engines (llama.cpp / vLLM / llama-cpp-python) via **Cookbook →
Dependencies** to get CUDA-enabled builds. If logs show `Unable to find cudart
library` / `CUDA Toolkit not found` / layers on CPU, re-install the engine from
Cookbook.

### Choosing an LLM in Cookbook (6 GB VRAM card)

- Models are served as **GGUF** via llama.cpp. Only ~121 of the ~900 registry
  models ship a curated GGUF download (`gguf_sources`); the rest error with
  **"No GGUF source is configured"** — see Troubleshooting.
- "GGUF" is a **file format**, not a service you install/configure. A "GGUF
  source" is just the Hugging Face repo holding the `.gguf` file.
- On 6 GB VRAM, favor **MoE** models (large on disk, few active params → fast
  even when partly in RAM) or a 7B dense model at Q4 (fits fully in VRAM).

**Recommended pick (Zephyrus / RTX 3060 6 GB):**
`Qwen/Qwen2.5-7B-Instruct` → engine **llama.cpp**, quant **Q4_K_M**. ~4.5 GB,
sits fully in VRAM, best all-round assistant in the size class. Source:
`bartowski/Qwen2.5-7B-Instruct-GGUF`.

- The **`-1M`** long-context variant is the *same weights/quality*; its 1M
  context is unusable on 6 GB (KV cache caps you to ~8–16k tokens regardless),
  so it behaves identically. If only the `-1M` shows in your list, just use it —
  no downside.
- Keep context moderate (8–16k); large-context rows eat VRAM via the KV cache.

### Local image generation / Stable Diffusion

Two separate paths in Odysseus:

1. **Chat image gen** (`image_gen` MCP) — **API-only** (gpt-image-1 / DALL·E-3),
   needs an OpenAI key. Not local.
2. **Cookbook → image models** — **local** via 🤗 diffusers: SD 1.5, SDXL,
   SD 3.5, FLUX.1, etc., hardware-fitted like the LLMs.

What fits 6 GB VRAM (needs quant ≤ ~5.4 GB to be marked "fits"):

- ✅ **SD 1.5** family (~2.5–4 GB) — fully GPU-resident, fast. The sweet spot.
- ⚠️ **SDXL** (fp8 ≈ 6 GB) / **Z-Image** (q4 ≈ 6 GB) — just over; run only with
  slow CPU/RAM offload.
- ❌ SD 3.5 Large / FLUX / Qwen-Image / Hunyuan — need 9–22 GB; not practical.

Reality check: Odysseus uses plain diffusers (hungrier than optimized
ComfyUI/A1111). SD 1.5 feels great; SDXL is sluggish. For optimized SDXL/FLUX,
run ComfyUI natively instead.

### Troubleshooting

- **No admin password in logs / "Login with your existing admin credentials".**
  The pre-seed via `ODYSSEUS_ADMIN_PASSWORD` only runs on a *fresh* first boot
  with no existing admin. The admin persists in the `./data` bind mount, which
  `docker compose down -v` does NOT clear. To reset:
  ```bash
  docker compose down
  sudo rm -rf ./data        # wipes admin + app state (and the HF model cache)
  docker compose up -d
  docker logs -f odysseus-odysseus-1 2>&1 | grep -iE 'creating initial admin|admin'
  ```
  (Use `2>&1` — startup banners go to stderr. Grep is case-sensitive; use `-i`.)

- **"No GGUF source is configured for <model>".** That model row has no curated
  GGUF link. Either pick a model that has one, or paste a GGUF repo manually in
  the Download field. There is nothing global to "set up" — it's per-model.

- **Cookbook shows the wrong GPU / iGPU / CPU.** NVIDIA Container Toolkit not
  installed or runtime not configured — see GPU passthrough above.

- **SearXNG won't start / blocks the app.** It's pinned (not `:latest`) on
  purpose; some upstream tags crash on boot and fail the healthcheck that
  Odysseus waits on. Bump the pin only after verifying a newer tag boots clean.

- **Browser MCP unavailable** (`@playwright/mcp` not in npx cache). Optional;
  to enable: `npx -y @playwright/mcp@latest --version` once, then restart.

---

## Ollama

### Installation

#### Windows
- Download from [Ollama](https://ollama.com/download). Models: [Ollama Models](https://ollama.com/models).

#### Linux / WSL
```bash
curl https://ollama.ai/install.sh | sh
```

#### Mac
```bash
brew install ollama
ollama --version
ollama serve            # in one terminal
ollama run llama2-uncensored   # in another
```

### Pull / run models
```bash
ollama pull llama2-uncensored
ollama run llama2-uncensored
```
- Exit the model prompt: `/bye`
- Stop the server: `Ctrl + C` in the `ollama serve` terminal (or `fg` then
  `Ctrl + C` if backgrounded with `%`).

### Running the back end
Starts the Ollama server for HTTP / WebUI access. No need to expose to the
internet — run on localhost.
```bash
ollama serve
```

#### Watch GPU usage
- NVIDIA: `watch -n 0.5 nvidia-smi`
- AMD: use the system monitor.

### Closing Ollama
- From the server terminal: `Ctrl + C`
- From the prompt: `/bye`

## Setting up OpenWebUI

### Front end via Docker — Windows
```bash
docker run -d --rm -p 8080:8080 -v open-webui:/app/backend/data -e OLLAMA_BASE_URL=http://host.docker.internal:11434 --name open-webui ghcr.io/open-webui/open-webui:latest
```

### Front end via Docker — Linux / WSL
```bash
docker run -d --network host -v open-webui:/app/backend/data -e OLLAMA_BASE_URL=http://localhost:11434 --name open-webui --restart always ghcr.io/open-webui/open-webui:latest
```

- Browse to `http://localhost:8080` for the OpenWebUI interface.
