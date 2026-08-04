# Plan: Desk and Dev Topology

Status: planning (Aug 2026). This documents the target layout for the desk and
where personal dev compute should live, plus the options still being weighed.

## Goals

- Walk up to the desk any time and work immediately — nothing depends on
  undocking the laptop from the backpack.
- Drive a personal machine and each work-context machine all day without
  remote desktop for real work (screen streaming is too laggy).
- Pick up the same terminal/agent sessions later from the MacBook, from
  anywhere.
- Relieve memory pressure on Envy (M4 Mac mini, 16 GB), which is the
  permanent desk console.

## Findings

- Envy's console workload is irreducible: two browser profiles with standing
  tabs (PR watching, calendars), a second browser required for one work
  context, chat/meeting apps, screen sharing, VNC/KVM viewers, and media to
  the paired headphones. Measured under load, this stack dominates memory;
  swap ran ~7.6 GB during a normal workday.
- Local dev on Envy (VS Code + Claude Code + interpreters, no containers
  running) measured only ~1.5–2 GB resident — but it is the ONLY movable
  load, and it is the bursty allocator (builds, tests, agent subprocesses)
  that spikes during meetings. Any future container work would multiply it.
- Work-context dev already runs on each context's own hardware via VS Code
  Remote; sessions that live on the target machine are what make
  desk-to-laptop handoff seamless. The same pattern should apply to personal
  dev.
- The MacBook's dual-monitor trouble is the video path, not the machine:
  macOS rejects MST fan-out and KVM EDID re-training. The Mac's dock video
  must go straight to spare monitor inputs; the KVM handles keyboard/mouse
  only.

## Desk layout (settled)

- Monitors do the video switching: one input each for Envy and the Windows
  desktop, a spare input for the MacBook's Thunderbolt dock (direct cable,
  never through the KVM).
- KVM/USB switch carries keyboard and mouse only.
- Envy stays the always-on console; the MacBook attaches to the same remote
  sessions over Tailscale when away.

## Personal dev target (deciding between two options)

Either way the target is a full personal rig: keys into all repos, cloned via
the credentials-repo manifests and provisioned by `deploy_configs.py`. The
manual step is registering one new keypair across the accounts (~1 hour).

### Option A: Ubuntu Server VM on behemoth (Unraid NAS)

- 5700G (8c/16t) / 64 GB host with ~48 GB free and a 2 TB NVMe cache pool
  with ~1.5 TB free; host load is light and uptime is measured in weeks.
- VM design: ~6 vCPU pinned to cores 2–7 (cores 0–1 reserved for the host),
  16 GB hard-allocated, vdisk on the NVMe cache (array never touched), br0
  networking with its own IP, joined to the tailnet.
- Docker runs inside the VM on its own kernel/daemon — fully isolated from
  the host's containers (no port, name, or storage overlap; the resource cap
  is a hard ceiling). Same isolation model as the existing Home Assistant VM.
- Pros: always-on by definition, strong isolation, zero new hardware.
- Cons: dev load shares the NAS's physical box; one more guest to maintain.

### Option B: RyzenWhite (Windows gaming desktop), native Windows dev

- 2700X (8c/16t) / 64 GB, already set up, on the tailnet, SSH working,
  dotfiles clone in place (PowerShell aliases already sourced on login).
- Dev is native Windows, NOT WSL2 — WSL2 was rejected because much of the
  code must share storage with Windows-side things, and the cross-boundary
  filesystem story (slow /mnt/c, watchers, permissions) always ends in a
  mess. Agent-driven work (Claude Code over SSH) is proven on native Windows
  in the daily work-context flow.
- Pros: biggest RAM pool available, zero build effort, native filesystem for
  storage-entangled projects, gaming and dev rarely coincide.
- Cons: Docker is never native on Windows (Docker Desktop = WSL2/Hyper-V VM
  underneath), so container projects still belong on the Option A VM when
  one shows up; no tmux, so long-running processes do not survive
  disconnects (Claude Code --resume and VS Code Remote reconnects cover
  most of it); Windows Update reboots; 24/7 idle power draw of a desktop;
  Zen+ is the oldest CPU in the running.

Current direction: Option B now (it exists and matches the storage-sharing
requirement); Option A remains the design for container work and
persistent-process jobs, built when actually needed.

### Ruled out

- EliteDesk: production server, weak CPU, disk nearly full.
- Yoga7i: must stay Windows for a finicky scanner.
- nukbuntu / Pavilioni5: too old to be the primary target (Pavilion may be
  revived as a low-stakes sidecar).
- Replacing Envy: declined; it is adequate once dev moves off.
- Any remote-desktop-based workflow: rejected on latency.

## Provisioning checklist (when a target is chosen)

1. Stand up the OS (VM define + Ubuntu install, or WSL2 distro).
2. Join the tailnet.
3. Clone dotfiles + credentials repos; run `deploy_configs.py`.
4. Generate a keypair, register it across the accounts, clone repos.
5. Add the host to the inventory (`hosts.json`) and ssh fragment/aliases so
   it is one hop from Envy and the MacBook.
6. Adopt tmux-on-target so sessions survive console switches.
