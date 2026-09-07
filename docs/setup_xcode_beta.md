# Xcode Setup Guide (Beta Workflow)

Reference for installing and configuring Xcode as done on Envy (M4 Mac mini, macOS 27 beta, Xcode 27 beta 3), covering both the **external-SSD layout** (space-constrained machines) and the **internal-only layout** (MacBooks with adequate storage). Written against the beta flow actually used; non-beta differences are noted where relevant.

---

## Overview / What goes where

| Component | Approx. size | Relocatable? | External-SSD layout | Internal-only layout |
|---|---|---|---|---|
| `Xcode-beta.app` | ~4 GB (Xcode 27 beta; older release Xcode was 30+ GB) | Yes — plain app bundle | `/Volumes/EnvyExtSSD/Applications/` | `/Applications/` |
| Platform runtimes (iOS, watchOS, ...) | ~5–9 GB each | **No** — cryptex-mounted by the OS | Internal (forced) | Internal |
| Derived Data (build products, intermediates, module caches) | Grows with use | Yes — supported setting | `/Volumes/EnvyExtSSD/XCode/DerivedData` | Default (`~/Library/Developer/Xcode/DerivedData`) |
| Archives | Small unless releasing often | Yes — supported setting | Optional | Default |
| Simulator devices/data | GBs over time | Not practically | Internal | Internal |

Key architectural fact learned the hard way: **simulator runtimes cannot live on external storage.** They install as security-verified disk images mounted via cryptexd at `/private/var/run/com.apple.security.cryptexd/mnt/...` — they are mounted volumes, not files an app opens. Budget internal space for them (~14 GB for iOS + watchOS together).

Second fact: **modern Xcode is small.** Xcode 27 beta downloads as a ~1.8 GB `.xip` expanding to ~3.9 GB. Everything platform-specific arrives afterward via on-demand runtime downloads. The old "Xcode is 30 GB" era ended; the runtimes are now the bulk.

---

## Prerequisites

- Free Apple ID (no paid developer membership needed for simulator work or personal-device installs).
- Command Line Tools may already be present (Homebrew installs them). Check:

```bash
xcode-select -p
```

- `/Library/Developer/CommandLineTools` → CLT only (typical pre-Xcode state)
- `/Applications/Xcode.app/Contents/Developer` (or SSD equivalent) → full Xcode already selected

CLT (~2–3 GB) is fine to leave installed; `xcode-select -s` later points the toolchain at full Xcode.

**On a beta host OS, download the beta Xcode.** Apple pairs beta OS releases with beta Xcode; release Xcode may refuse to run, and targeting a beta iOS on-device requires the matching beta SDK anyway.

---

## Step 1 — Download

Go to **https://developer.apple.com/download/all/** (sign in with Apple ID; free tier works). Download the Xcode `.xip`.

- **SSD layout:** set the browser's download destination to the external drive first — extraction needs working space and there's no reason to touch internal.
- **Internal-only layout:** default Downloads location is fine; ensure ~15 GB free for download + extraction headroom (beta sizes; older/full releases needed ~40 GB).

### Do not use Homebrew `xcodes` on a beta macOS

`brew install xcodesorg/made/xcodes` **fails to build on macOS 27 beta** — no bottle exists for the pre-release OS, brew compiles from source, and the build dies linking an x86_64 slice against the macOS 27 SDK (`ld: symbol(s) not found for architecture x86_64`). Homebrew classifies beta macOS as Tier 2 (unsupported).

If `xcodes` is wanted anyway, use the prebuilt binary from the project's GitHub releases instead of brew. On a **release** macOS, `brew install xcodesorg/made/xcodes aria2` works normally and is a nice alternative (Brewfile syntax: `tap "xcodesorg/made"` + `brew "xcodesorg/made/xcodes"`).

---

## Step 2 — Extract

`cd` to wherever the `.xip` landed and expand:

```bash
cd /Volumes/EnvyExtSSD        # or ~/Downloads on internal-only
xip --expand Xcode_27_beta_3.xip
```

Notes:

- `xip` verifies Apple's signature during expansion — a successful expand **is** the integrity check. Truncated/corrupt downloads refuse to expand. Success output looks like:
  `xip: signing certificate was "Software Update" (validation not attempted)` followed by `xip: expanded items from "..."`.
- **Betas expand as `Xcode-beta.app`**, not `Xcode.app`. Adjust paths accordingly.
- The app directory timestamp reflects Apple's packaging date, not your extraction time — don't let an "old" date alarm you.
- Expansion takes a while with no progress indicator; apparent stalls are normal.

Then place it and delete the archive:

```bash
# SSD layout
mkdir -p /Volumes/EnvyExtSSD/Applications
mv Xcode-beta.app /Volumes/EnvyExtSSD/Applications/
rm Xcode_27_beta_3.xip

# Internal-only layout
mv Xcode-beta.app /Applications/
rm Xcode_27_beta_3.xip
```

Running the app from an external volume requires the volume to be **APFS** (not HFS+/exFAT). Performance over Thunderbolt/USB4 is indistinguishable from internal for build work.

---

## Step 3 — Wire up the toolchain

```bash
# SSD layout
sudo xcode-select -s /Volumes/EnvyExtSSD/Applications/Xcode-beta.app/Contents/Developer

# Internal-only layout
sudo xcode-select -s /Applications/Xcode-beta.app/Contents/Developer

# Both layouts
sudo xcodebuild -license accept
sudo xcodebuild -runFirstLaunch
xcodebuild -version
```

`-runFirstLaunch` installs embedded components non-interactively (prints a percentage progress line) so the first GUI launch doesn't stall on a progress bar. The final `xcodebuild -version` printing a version (e.g. `Xcode 27.0 / Build version 27A5218g`) is the all-clear that the app is complete and selected.

---

## Step 4 — Platform runtimes (the real download)

Launch Xcode:

```bash
open /Volumes/EnvyExtSSD/Applications/Xcode-beta.app    # or open -a Xcode-beta
```

Go to **Settings (Cmd+,) → Components** (the beta houses platform downloads here; older Xcode called the tab "Platforms"). Download only what's needed:

- **iOS** — covers iPhone **and** iPad simulators (one shared runtime)
- **watchOS** — only if building watch apps
- Skip tvOS/visionOS unless targeting them

These land **internal** regardless of layout (cryptex mounts, see Overview). Several GB each; runs in background.

Verify when finished:

```bash
xcrun simctl list runtimes
```

Both/all desired runtimes listed as available = environment complete.

### Runtime hygiene (future)

Runtimes accumulate as Xcode versions update (each wants its matching runtime; old ones linger, multi-GB each). Inspect and prune:

```bash
xcrun simctl runtime list
xcrun simctl runtime delete <id>
```

---

## Step 5 — Relocate Derived Data (SSD layout only)

Derived Data is the directory that silently grows with every project — build products, intermediates, indexes, module caches. On the SSD layout, move it; on internal-only, leave the default.

**Settings → Locations → Derived Data.** Beta UI trap: the **"Default" text on the right edge is a popup control**, not a label — click it, choose Custom, set:

```
/Volumes/EnvyExtSSD/XCode/DerivedData
```

If the popup won't cooperate (beta), the same preference via CLI:

```bash
defaults write com.apple.dt.Xcode IDECustomDerivedDataLocation /Volumes/EnvyExtSSD/XCode/DerivedData
```

(Quit and relaunch Xcode after.)

Related settings in the same pane:

- **Build Location** (button next to Derived Data): keep on **Unique** (the default). Do not use Custom/Absolute mode — it funnels all projects into one shared products/intermediates pair and can point Intermediates somewhere silly (it defaulted to Desktop when accidentally engaged). Unique inherits the Derived Data root per-project automatically.
- **Compilation Cache**: nested under Derived Data's path — moves with it automatically, nothing to do.
- **Archives**: relocatable the same way if desired (`IDECustomDistributionArchivesLocation`); low priority for personal projects.

Verification after the first build of any project: the project's folder appears under the SSD path, and `~/Library/Developer/Xcode/DerivedData` stays empty/absent.

---

## Step 6 — First project (beta flow quirks)

The Xcode 27 beta reworked the New Project flow. Differences from the classic flow, all encountered:

1. **No upfront iOS/macOS platform question.** The App template is multiplatform by default — it created **iOS + macOS + visionOS** destinations. Trim under target → **General → Supported Destinations** (select unwanted rows, minus button).

2. **Document-style "untitled" creation.** File → New → Project can create the project immediately in a scratch area — `~/Library/Developer/Xcode/UntitledProjects/Untitled Project/` — without asking for name or location. The save dialog is *deferred*: **Cmd+S** is the naming/placement moment. If the flow misbehaves, `rm -rf` the untitled folder and retry rather than hand-renaming (Xcode project renames touch the folder, xcodeproj, target, scheme, and internal references — never worth it manually).
   - **Watch for accumulation:** abandoned untitled projects pile up silently in that directory. Check it occasionally.
   - **Nesting trap:** the save flow names a project folder; choosing/creating a same-named parent folder yields `name/name/name.xcodeproj`. Flatten with (zsh — note `.[!.]*` triggers history expansion in zsh; use the `(DN)` glob qualifier instead):
     ```bash
     cd ~/GitHub/project-name
     mv project-name/*(DN) . 2>/dev/null
     rmdir project-name
     ```
     `rmdir` failing means something was left behind — investigate before forcing. Note the *source* subfolder (`ProjectName/ProjectName/sources`) is canonical and should remain.

3. **Placeholder bundle identifier.** Projects born via the untitled flow carry `devplaceholder.<RANDOM>.<name>` as the bundle ID, and if the project name contains an underscore, the ID inherits it — producing the build error *"invalid character in Bundle Identifier"* (only `A–Z a–z 0–9 - .` are legal). Fix:
   - Target → **General → Identity → Bundle Identifier** → set to reverse-domain form, e.g. `me.tinkernet.appname`. Same ID across iOS/macOS destinations is fine and normal for one app.
   - **Check every destination and level**: each platform destination has its own ID slot, and stale values can hide in **Build Settings → All + Levels → search "bundle identifier"** at both TARGET and PROJECT level.
   - Definitive check/fix from the terminal (close the project first):
     ```bash
     grep -n "devplaceholder\|bad_name" path/to/Project.xcodeproj/project.pbxproj
     sed -i '' 's/devplaceholder\.RANDOM\.bad_name/me.tinkernet.appname/g' path/to/Project.xcodeproj/project.pbxproj
     ```
   - If the error persists after the pbxproj greps clean: it's stale build state. **Shift+Cmd+K** (clean), rebuild; if still present, delete the project's DerivedData folder and reopen.
   - Reverse-domain IDs are convention, not verification — nobody checks domain ownership. It exists to guarantee uniqueness by piggybacking on DNS as a namespace; hierarchy is reversed (general→specific) so identifiers group/sort by owner. Using a domain actually owned (`me.tinkernet.*`) guarantees no collisions with convention-followers.

4. **Minimalist template.** The new template can be a single Swift file: `@main` app struct + ContentView + a `#Playground` block (the beta's inline-playgrounds feature; `import Playgrounds` and the block are droppable). No Assets catalog or separate App file may be visible.

5. **Signing team warning** ("Signing requires a development team") is separate from bundle-ID errors and is **not required for simulator builds** in all cases — but when needed: Settings → **Apple Accounts** → add Apple ID → target → **Signing & Capabilities** tab → check Automatically manage signing → select the "(Personal Team)". Free-tier limits: 7-day profile expiry on physical devices, few app IDs per week, no App Store — all irrelevant to simulator work.

6. **Display Name** (target → General) is the home-screen name; empty falls back to product name.

7. **Run destination**: the toolbar destination defaults to **My Mac** on multiplatform projects — switch to an iPhone simulator before Cmd+R or it builds a Mac app. If no iPhone simulators are listed, the iOS runtime isn't installed yet (the picker offers a GET shortcut).

8. **`.gitignore`** for the repo before first commit:
   ```
   xcuserdata/
   DerivedData/
   *.xcuserstate
   ```

---

## Step 7 — Session hygiene

Simulators are separate apps that **outlive Xcode** — a booted simulator persists as dozens of background processes (the simulated device's own OS daemons, visible in `ps` as processes under `/private/var/run/com.apple.security.cryptexd/mnt/...`) even after quitting Xcode and with no Simulator window. End-of-session:

```bash
xcrun simctl shutdown all
```

Worth aliasing (`alias simoff='xcrun simctl shutdown all'`). Occasionally-orphaned build daemons (`SourceKitService`, `XCBBuildService`) are safe to `pkill` — they respawn on demand.

---

## Quick-reference: full command sequence

### SSD layout (Envy)

```bash
# download .xip to /Volumes/EnvyExtSSD via browser, then:
cd /Volumes/EnvyExtSSD
xip --expand Xcode_*.xip
mkdir -p /Volumes/EnvyExtSSD/Applications
mv Xcode-beta.app /Volumes/EnvyExtSSD/Applications/
rm Xcode_*.xip
sudo xcode-select -s /Volumes/EnvyExtSSD/Applications/Xcode-beta.app/Contents/Developer
sudo xcodebuild -license accept
sudo xcodebuild -runFirstLaunch
xcodebuild -version
defaults write com.apple.dt.Xcode IDECustomDerivedDataLocation /Volumes/EnvyExtSSD/XCode/DerivedData
open /Volumes/EnvyExtSSD/Applications/Xcode-beta.app
# GUI: Settings → Components → download iOS (+ watchOS if needed)
xcrun simctl list runtimes
```

### Internal-only layout (MacBooks)

```bash
# download .xip to ~/Downloads via browser, then:
cd ~/Downloads
xip --expand Xcode_*.xip
mv Xcode-beta.app /Applications/
rm Xcode_*.xip
sudo xcode-select -s /Applications/Xcode-beta.app/Contents/Developer
sudo xcodebuild -license accept
sudo xcodebuild -runFirstLaunch
xcodebuild -version
open -a Xcode-beta
# GUI: Settings → Components → download iOS (+ watchOS if needed)
xcrun simctl list runtimes
```

Internal-only skips the Derived Data relocation entirely; defaults are correct when internal space isn't constrained. Everything else — including all beta quirks in Step 6 — applies identically.

---

## Disk budget summary

| | SSD layout | Internal-only |
|---|---|---|
| Internal cost | ~14 GB (iOS + watchOS runtimes) + simulator device data over time | Same + ~4 GB app + Derived Data growth |
| Practical minimum free internal before starting | ~20 GB | ~30 GB |

On release (non-beta) Xcode versions, expect the `.xip` and expanded app to be larger (~3.5 GB / up to 30+ GB historically) — check sizes before assuming the beta's slim figures.
