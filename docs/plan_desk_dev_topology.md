# Plan: Desk and Dev Topology

Status: planning (Aug 2026, dev target revised Sep 2026). This documents the
target layout for the desk and where personal dev compute should live, plus
the options still being weighed.

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
  the paired headphones. Swap ran ~7.6 GB during a normal workday.
- That swap was mostly local dev, not the console stack. Resident totals for
  VS Code, Claude Code and interpreters (~1.5-2 GB) hid it: VS Code's Python
  tool extensions (black-formatter, isort, flake8, mypy-type-checker) start
  one runner per workspace folder, and idle runners sit compressed or swapped
  rather than resident. Measured 2026-09-10 with
  `top -stats pid,command,mem,cmprs`: a 54-folder workspace ran 162 runner
  processes holding ~7.1 GB compressed, against 7.7 GB of swap. Local dev is
  the largest load and the only movable one, and it is the bursty allocator
  (builds, tests, agent subprocesses) that spikes during meetings. Any future
  container work would multiply it.
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

### Option B: JasonZephyrus (ROG Zephyrus G14 laptop), Fedora

- Ryzen 9 5900HS (8c/16t, Zen 3) / 16 GB / RTX 3060 Laptop 6 GB, ~936 GB
  free. Reachable over SSH as `sshzephyrus`; Docker and the NVIDIA container
  toolkit already work there, and T3 Code runs as a systemd service
  (`docs/setup_t3_code.md`).
- Linux, so tmux keeps long-running processes alive across disconnects and
  Docker runs natively rather than inside a Windows VM.
- Pros: already running, no Windows Update reboots, native containers and
  tmux, newest CPU in the running.
- Cons: 16 GB is a quarter of RyzenWhite's 64 GB; as a laptop it has to stay
  on power and awake to be always-on; it also hosts the local AI workloads
  (`docs/setup_local_ai.md`), so a large model and a heavy build compete for
  the same memory; no cron (`docs/homelab_deployments.md`); projects that
  must share storage with Windows-side tools are not served by it, which was
  the reason RyzenWhite ran native Windows dev.

Current direction: Option B (Zephyrus). Option A remains the design for
persistent-process jobs and anything that outgrows 16 GB, built when
actually needed.

### Ruled out

- EliteDesk: production server, weak CPU, disk nearly full.
- Yoga7i: must stay Windows for a finicky scanner.
- nukbuntu / Pavilioni5: too old to be the primary target (Pavilion may be
  revived as a low-stakes sidecar).
- RyzenWhite (Windows desktop, 64 GB): Windows Update reboots and shutdowns
  keep taking it down, which an always-on dev target cannot absorb.
- Replacing Envy: declined; it is adequate once dev moves off.
- Any remote-desktop-based workflow: rejected on latency.

## Decisions (August 2026)

- Envy (16 GB Mac mini) stays as the console; it is not being replaced. Its
  irreducible local load is meetings, Chrome, screen sharing, VNC/KVM
  software and audio. Real work runs on remote targets over VS Code Remote
  and ssh, and Claude Code sessions run on the targets, not on Envy. Remote
  desktop is not an option for real work.
- The MacBook's display problem is only the Thunderbolt-dock-through-KVM path
  (macOS rejects MST fan-out and KVM EDID re-training): dock video goes direct
  to spare monitor inputs, the KVM carries keyboard and mouse only.
- Personal dev target: Option B, JasonZephyrus on Fedora. Claude Code over
  ssh does the heavy lifting. Jobs that need
  persistent processes, and anything that outgrows it, go to a behemoth
  Ubuntu VM when one is built.

## Agent server and T3 Connect slots (October 2026)

- JasonZephyrus also becomes the always-on agent server: the jobs that drive
  a browser and sign into sites run there, so they never take over Envy's
  screen. It already runs T3 as a boot service and carries the same repos as
  every other personal machine, and local AI is no longer a standing load,
  so dev and browser jobs share its 16 GB. A spare Dell Latitude 7420
  (i7-1185G7, 16 GB, not in the inventory) was weighed and kept as the
  fallback if that memory runs short; its only edge was keeping the two jobs
  apart. nukbuntu (too slow for heavy sites) and macmini14 (4 GB, stuck on an
  old macOS) were ruled out.
- T3 threads have no computer use (`docs/setup_t3_code.md`, "What T3
  replaces"), so the server drives the browser through a browser-automation
  MCP server with a persistent profile, on a headless Xtigervnc virtual
  desktop (`docs/setup_vnc_server.md`, as on nukbuntu) rather than the
  laptop's own session. Logins and 2FA are typed by hand into that browser
  over VNC, and a password manager extension unlocked there fills the rest;
  passwords never go through chat.
- The three T3 Connect slots go to Envy, the work laptop and JasonZephyrus.
  RyzenWhite and the MacBook are clients only. Reasoning in
  `docs/setup_t3_code.md`, Slot policy; the switch is
  `backlog/t3-connect-slot-switch.md`.

## Provisioning checklist (when a target is chosen)

1. Stand up the OS (VM define + Ubuntu install for Option A; Zephyrus already
   runs Fedora).
2. Join the tailnet.
3. Clone dotfiles + credentials repos; run `deploy_configs.py`.
4. Generate a keypair, register it across the accounts, clone repos.
5. Add the host to the inventory (`personal_hosts.json`) and ssh fragment/aliases so
   it is one hop from Envy and the MacBook.
6. Adopt tmux-on-target so sessions survive console switches.
