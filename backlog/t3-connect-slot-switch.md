# t3: the T3 Connect slots still sit on RyzenWhite, not on JasonZephyrus

    found:  2026-10-01
    status: open
    verify: in the T3 desktop app, Settings → Connections, read which environments are T3 Connect-linked with a managed tunnel; this is done when they are exactly Envy, the work laptop and JasonZephyrus

The account has 3 managed tunnels (`DEFAULT_MANAGED_TUNNEL_LIMIT = 3`
upstream). On 2026-10-01 the target was decided (`docs/setup_t3_code.md`,
Slot policy; `docs/plan_desk_dev_topology.md`, "Agent server and T3 Connect
slots"): the slots go to Envy, the client-issued Linux work laptop (recorded
in that context's own `*_hosts.json`) and JasonZephyrus, which becomes the
always-on agent server for browser jobs as well as the dev target.
RyzenWhite and the MacBook become clients only. The switch waits until
JasonZephyrus is back online.

## Evidence

- The fleet table in `docs/setup_t3_code.md` lists RyzenWhite as "T3 Connect
  **and** Tailscale Serve", so it holds a slot, and JasonZephyrus as "Remote
  link over Tailscale Serve", so it holds none.
- The work laptop's own setup commands treat it as a T3 Connect environment.
- Envy's published environment holds the third slot ("The three slots here:
  Envy's published environment plus the two laptop environments", Known
  issues). That line was written before RyzenWhite was linked, so which
  machine holds the third slot today is unconfirmed; the `verify:` line
  settles it.
- On 2026-10-01 `ssh jason@192.168.86.170` returned "Host is down".

## fix

1. Bring JasonZephyrus back online and keep it awake with the lid closed
   through the dotfiles setup (no lid-switch setting exists in the repo yet;
   add one there, not by hand over ssh).
2. Give it a headless virtual desktop for the agent's browser: the Xtigervnc
   unit from "Virtual desktop, headless (Xtigervnc)" in
   `docs/setup_vnc_server.md`, as on nukbuntu. Not the x0vncserver entry: the
   doc keeps JasonZephyrus off port 5900 on purpose.
3. Free RyzenWhite's slot: in its desktop app, Settings → Connections, turn
   T3 Connect publishing off and stay signed into the account, so it matches
   "New Windows client-only machine checklist". If the slot still shows as
   taken, unlink the environment from the T3 Connect account page.
4. Make sure the MacBook does not publish its own environment (same setting).
5. Link JasonZephyrus: `t3 connect link --headless` (it applies on next
   start), then `systemctl --user restart t3code.service` and wait for the 4
   registered tunnel connections in `~/.t3/userdata/logs/boot-service.log`.
6. Check from the phone and from RyzenWhite that Envy, the work laptop and
   JasonZephyrus all show with their threads, and that a finished thread on
   JasonZephyrus pushes to the phone.
7. Update the fleet table in `docs/setup_t3_code.md` (RyzenWhite client-only,
   JasonZephyrus on T3 Connect), fix the stale "two laptop environments" line
   in Known issues, then delete this entry and its index row in the same
   commit.

## blast radius

- RyzenWhite's own threads stop being reachable from other devices. It is
  meant to be a client only, so none are expected to be running there.
- Phone push from RyzenWhite stops; the desktop app on it still raises its
  own notifications for every environment it is connected to.
- Linking JasonZephyrus before a slot is freed fails with a bare `403` from
  the CLI (Known issues), so step 3 must come before step 5.
- The restart in step 5 restarts any thread running on JasonZephyrus.
- Its existing Tailscale Serve pairings keep working alongside the tunnel.

## not doing yet

JasonZephyrus is down. Freeing RyzenWhite's slot now would gain nothing until
it can take the slot.
