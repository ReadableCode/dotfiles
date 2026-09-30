# go_apps: syncthing_artifact_cleanup has no callers and hard-codes personal folders

    found:  2026-09-30
    status: open
    verify: git grep -ln "syncthing_artifact_cleanup" -- ':!go_apps/syncthing_artifact_cleanup'

On 2026-09-30 the verify line printed nothing.

## Evidence

- `go_apps/syncthing_artifact_cleanup/` holds `go.mod` and `main.go`, last
  touched 2026-08-26 ("give each go app its own module file").
- Nothing builds, ships or runs it: no alias, script, manifest entry or doc.
- Its delete patterns name personal folders (`stable-diffusion-webui*`,
  `Something-Familiar/Library`), so it is not configuration for any machine.

## fix

If it is no longer run by hand:

    git rm -r go_apps/syncthing_artifact_cleanup

If it still is, move it to `personal_dev` (for example `personal_dev/go_apps/`)
and delete it here.

## blast radius

None: nothing calls it.

## not doing yet

Needs Jason to say whether he still runs it by hand.
