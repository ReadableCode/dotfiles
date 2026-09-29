# t3 code: never offers a claude code update on envy, its brew reads a cache no shell refreshes

    found:  2026-09-29
    status: open
    verify: ls -la ~/Library/Caches/Homebrew/api/internal /Volumes/EnvyExtSSD/HomebrewCache/api/internal   # different dates means still split

T3 Code decides whether Claude Code is behind by asking the installer that
owns the binary. On Envy that is Homebrew (`claude-code@latest` cask), so the
server runs `brew info --json=v2 claude-code@latest` once an hour and compares
the answer with `claude --version`. It never asks npm when brew owns the
install.

`brew info` answers from Homebrew's local API cache and only refreshes that
cache when it is older than 7 days (`DEFAULT_API_STALE_SECONDS` in
`Library/Homebrew/api.rb`). Envy has two such caches:

- every shell exports `HOMEBREW_CACHE=/Volumes/EnvyExtSSD/HomebrewCache`
  (`application_configs/bash/zshenv_local.envy`), so `brew update` in
  myupdater refreshes the one on the SSD
- the T3 Code app is launched outside a shell and takes only `PATH` from it,
  so its brew uses the default `~/Library/Caches/Homebrew`, which nothing
  refreshes

## Evidence

All read on 2026-09-29 at 07:57 CDT, with Claude Code 2.1.280 installed and
2.1.284 published.

    ~/Library/Caches/Homebrew/api/internal/packages.arm64_golden_gate.jws.json     Sep 23 15:55   claude-code@latest 2.1.280
    /Volumes/EnvyExtSSD/HomebrewCache/api/internal/packages.arm64_golden_gate.jws.json   Sep 29 07:55   claude-code@latest 2.1.284

The server process (`ps eww`) carries `PATH` and no `HOMEBREW_*` variable.
What it reports to the UI, from `~/.t3/caches/claudeAgent.json`:

    "message": "Claude Code v2.1.280 is too old for Claude Sonnet 5.5. Upgrade to v2.1.284 or newer to access it.",
    "versionAdvisory": {
      "status": "current",
      "currentVersion": "2.1.280",
      "latestVersion": "2.1.280",
      "updateCommand": "brew upgrade --cask claude-code@latest",

The prompt only shows for `status: behind_latest`
(`isProviderUpdateCandidate` in T3's
`apps/web/src/components/ProviderUpdateLaunchNotification.logic.ts`). The brew
probe itself is healthy: the `runHomebrew` span at 07:34 took 456 ms. No
dismissal is stored (`dismissedProviderUpdateNotificationKeys: []`).

Left alone it heals for a moment each time the internal cache passes 7 days
(next: 2026-09-30 15:55), then goes stale again for another week.

## fix

Upstream, in T3 Code. The desktop app copies a fixed list of variables from
the login shell (`LOGIN_SHELL_ENV_NAMES` in
`apps/desktop/src/shell/DesktopShellEnvironment.ts`): `PATH`,
`SSH_AUTH_SOCK`, `HOMEBREW_PREFIX`, `HOMEBREW_CELLAR`, `HOMEBREW_REPOSITORY`
and the XDG and locale names. Add `HOMEBREW_CACHE` to that list, one line,
from the `t3code` checkout. After a release carrying it, confirm with
`ps eww -p <server pid> | tr ' ' '\n' | grep HOMEBREW_CACHE`.

This also fixes where T3's own update button downloads to: today its
`brew upgrade --cask claude-code@latest` would put the 217 MB download on the
internal disk, which the redirect exists to prevent.

Rejected: a LaunchAgent running `launchctl setenv HOMEBREW_CACHE ...`. No
manifest deploys a LaunchAgent today, it would be a second place the redirect
is defined, and it changes brew for every app launched from the Dock.

## blast radius

None on this machine until a T3 release carries the change. After it, T3's
brew uses the SSD cache; with the SSD unmounted its probe fails and the
advisory becomes `unknown` (no prompt), which matches the no-fallback rule in
`zshenv_local.envy`. The 30 MB of API data under `~/Library/Caches/Homebrew`
becomes dead weight to delete by hand.

## not doing yet

Found while answering a question, not asked to change anything, and the
change is a pull request to a repo that is not mine. Updating Claude Code
itself does not need this fix: myupdater, or
`brew upgrade --cask claude-code@latest` from a shell, uses the fresh cache.
