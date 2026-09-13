# Stable Diffusion

Image generation runs on **RyzenWhite** (RTX 5070 Ti 16 GB, 64 GB RAM,
Windows 11) from **Stability Matrix**: a GUI launcher, no Docker, no Windows
service, nothing running unless its window is open. Start it when you want
images, close it before gaming.

JasonZephyrus also has a Docker setup for Forge Neo, kept commented out
because that laptop's 6 GB GPU belongs to Odysseus's always-on LLM. How to
switch it back on is in the Docker repo's `README.md` ("JasonZephyrus") and at
the top of `docker_compose_zephyrus.yaml`.

## Why this setup

- **RyzenWhite over Zephyrus.** 16 GB of VRAM holds SDXL whole and makes
  Flux-class models practical; the laptop's 6 GB only just fits SDXL (1.18
  it/s measured on 2026-09-13) and is needed by Odysseus anyway.
- **Forge Neo** (`Haoming02/sd-webui-forge-classic`, `neo` branch) is the
  maintained continuation of the AUTOMATIC1111 / Forge UI. A1111 has had no
  release since v1.10.1 (July 2024) and lllyasviel's Forge has been idle since
  July 2025.
- **Stability Matrix** installs and updates Forge Neo (and ComfyUI, SwarmUI)
  from a GUI with its own Python and Git, keeps one shared model folder for
  all of them, and has a model browser that downloads straight from Civitai.
  It is portable: one folder, no installer, nothing registered as a service.
  It is not in winget; the release zip is the install method.

## Install (once)

1. Download `StabilityMatrix-win-x64.zip` from
   <https://github.com/LykosAI/StabilityMatrix/releases/latest> and extract it
   to a folder on the drive with the most free space (models are 2 to 7 GB
   each), for example `D:\StabilityMatrix`. Check free space first; C: was
   short on space before the GPU swap.
2. Run `StabilityMatrix.exe`. On first launch choose **Portable mode** so all
   data (packages, models, images) stays inside that folder.
3. Add a package: choose **Stable Diffusion WebUI Forge - Neo**, keep the
   defaults, install. It downloads its own Python and PyTorch (several GB,
   takes a while). If it asks about the GPU, pick NVIDIA / CUDA.
4. Optional, for models that need a signed-in download: create an API key on
   civitai.com (Account Settings, API Keys) and add it in Stability Matrix's
   settings under the account connections.

## Use

- **Start:** open Stability Matrix, press **Launch** on Forge Neo. The web UI
  opens in the browser at `http://127.0.0.1:7860` (local to RyzenWhite only).
- **Get models:** Stability Matrix's **Model Browser**, Civitai tab, search,
  download. It files checkpoints, LoRAs and VAEs into the right shared folder
  by type. Or drop `.safetensors` files into the shared `Models` folder by
  hand (`Models\StableDiffusion` for checkpoints, `Models\Lora`, `Models\VAE`)
  and press refresh next to the checkpoint dropdown in the UI.
- **Images:** the shared `Images` / outputs folder inside the Stability Matrix
  data folder.
- **Stop (before gaming):** press **Stop** on the package, then close
  Stability Matrix. Check Task Manager that no `python.exe` is left holding
  VRAM. Nothing starts again until you open it.

## The model already on JasonZephyrus

SDXL base 1.0 was downloaded to the laptop for testing. Copy it over the
laptop's Samba share instead of downloading again: in File Explorer open
`\\192.168.86.170\stable_diffusion\models\Stable-diffusion`, sign in with the
`SAMBA_BACKUPS_*` user from personal.env, and copy
`sd_xl_base_1.0.safetensors` into Stability Matrix's `Models\StableDiffusion`.
