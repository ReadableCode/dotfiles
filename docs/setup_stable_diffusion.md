# Stable Diffusion

Stable Diffusion runs on JasonZephyrus as the Forge Neo web UI in Docker, with
models kept on the host and mapped into the container. It deploys from git
like elitedesk and nukbuntu. The compose file, model layout, GPU sharing with
Odysseus and first-time bootstrap are documented once, in the Docker repo's
`README.md` under "JasonZephyrus Stable Diffusion".

## Why Forge Neo, in Docker

- AUTOMATIC1111 has had no release since v1.10.1 (July 2024), and
  lllyasviel's Forge has been idle since July 2025. Forge Neo
  (`Haoming02/sd-webui-forge-classic`, `neo` branch) is the maintained
  continuation of the same UI, with lower VRAM use and SDXL, Flux, Z-Image and
  Qwen-Image support.
- Docker costs nothing in GPU speed: the NVIDIA container toolkit hands the
  container the host driver and the real device, so CUDA kernels run exactly
  as they would natively. What it buys is a pinned torch/CUDA stack that
  cannot break on a Fedora update, and models that live outside the image.

## What fits 6 GB

- SD 1.5 checkpoints: fully on the GPU, fast.
- SDXL / Pony / Illustrious: work, Forge Neo swaps parts to RAM as needed.
  16 GB of system RAM is the tighter limit.
- Flux and Qwen-Image class models: need GGUF or NF4 quantized files, and are
  slow.

## Running on Windows (old A1111 install)

```bash
git clone git@github.com:AUTOMATIC1111/stable-diffusion-webui.git
cd stable-diffusion-webui
webui.bat --listen --gradio-auth username_desired:password_desired
```
