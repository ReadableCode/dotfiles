# Xcode Setup Guide (Beta Workflow)

How Xcode, the iOS and watchOS simulator runtimes and the toolchain are
installed for building iPhone, iPad and Apple Watch apps, in two layouts: the
**internal-only layout** (a Mac with internal disk to spare) and the
**external-SSD layout** (a space-constrained Mac with an APFS external drive).
Written against the beta flow actually used (macOS 27 beta host, Xcode 27
beta); non-beta differences are noted where relevant.

---

## Which Macs get Xcode

Xcode is a per-host install, not a fleet one. Nothing in `app_lists/Brewfile`
or a context's `<context>_app_lists.yaml` installs it, so bootstrap and
myupdater never put it on a Mac; this page is the only way it arrives.

Install Xcode if you want to build for iOS, iPadOS or watchOS and the Mac has
the free internal space: about 30 GB for the internal-only layout, or about
25 GB for the external-SSD layout, which moves the app and Derived Data to an
APFS external drive. The simulator runtimes (~20 GB for iOS and watchOS on
27.2) stay on the internal disk in either layout. Without that space, keep
Command Line Tools only.

Homebrew's Command Line Tools stay on every Mac; they are not Xcode and build
nothing for iOS or watchOS.

---

## What goes where

| Component | Approx. size | Relocatable? | Internal-only layout | External-SSD layout |
|---|---|---|---|---|
| `Xcode-beta.app` | ~4 GB (Xcode 27 beta; older release Xcode was 30+ GB) | Yes, plain app bundle | `/Applications/` | `/Volumes/EnvyExtSSD/Applications/` |
| iOS runtimes (iPhone **and** iPad simulators) | 8.25 GB general + 8.05 GB iPhone Duo (iOS 27.2 beta), see Step 4 | **No**, cryptex-mounted by the OS | Internal | Internal (forced) |
| watchOS runtime (Apple Watch simulators) | 3.89 GB (watchOS 27.2 beta) | **No**, cryptex-mounted by the OS | Internal | Internal (forced) |
| Derived Data (build products, intermediates, module caches) | Grows with use | Yes, supported setting | Default `~/Library/Developer/Xcode/DerivedData` | `/Volumes/EnvyExtSSD/XCode/DerivedData` |
| Archives | Small unless releasing often | Yes, supported setting | Default | Optional |
| Simulator devices/data | GBs over time | Not practically | Internal | Internal |

Key architectural fact learned the hard way: **simulator runtimes cannot live on external storage.** They install as security-verified disk images mounted via cryptexd at `/private/var/run/com.apple.security.cryptexd/mnt/...`; they are mounted volumes, not files an app opens. Budget internal space for them (~20 GB for iOS + watchOS together on 27.2). The external-SSD layout moves the app and Derived Data off the internal disk, never the runtimes.

Second fact: **modern Xcode is small.** Xcode 27 beta downloads as a ~1.8 GB `.xip` expanding to ~3.9 GB. Everything platform-specific arrives afterward via on-demand runtime downloads. The runtimes are now the bulk.

---

## Prerequisites

- Free Apple ID (no paid developer membership needed for simulator work or personal-device installs).
- Command Line Tools are already present (Homebrew installs them). Check:

```bash
xcode-select -p
```

- `/Library/Developer/CommandLineTools`: CLT only (the pre-Xcode state)
- `/Applications/Xcode-beta.app/Contents/Developer` (or the SSD equivalent): full Xcode already selected

CLT (~2 to 3 GB) is fine to leave installed; `xcode-select -s` later points the toolchain at full Xcode.

**On a beta host OS, download the matching beta Xcode.** Apple pairs beta OS releases with beta Xcode; release Xcode may refuse to run, and targeting a beta iOS on-device requires the matching beta SDK anyway. Pick the Xcode beta whose number matches the macOS beta (macOS 27.2 beta: Xcode 27.2 beta). `sw_vers` shows the host's version; a build number ending in a lowercase letter (`26B5112a`) is a beta.

---

## Step 1: Download

Go to **https://developer.apple.com/download/all/** (sign in with Apple ID; free tier works) and download the Xcode `.xip`.

- **Internal-only layout:** the default `~/Downloads` is fine; leave ~15 GB free for download + extraction headroom (beta sizes; older/full releases needed ~40 GB).
- **External-SSD layout:** set the browser's download destination to the external drive first; extraction needs working space and there's no reason to touch internal.

### Why not Homebrew

Homebrew has no Xcode cask (`brew info --cask xcode`: no cask by that name);
Apple's license does not allow redistributing Xcode, so any install goes
through an Apple ID download. The only brew route is the third-party `xcodes`
formula, which signs in to that same Apple ID and fetches the same `.xip`.

`brew install xcodesorg/made/xcodes` **fails to build on macOS 27 beta**: no bottle exists for the pre-release OS, brew compiles from source, and the build dies linking an x86_64 slice against the macOS 27 SDK (`ld: symbol(s) not found for architecture x86_64`). Homebrew classifies beta macOS as Tier 2 (unsupported), and the tap's only bottles are tagged `mojave` (checked 2026-10-16 against xcodes 2.1.0), so every newer macOS builds it from source. The browser download is the method this page uses.

If `xcodes` is wanted anyway, use the prebuilt binary from the project's GitHub releases instead of brew. On a **release** macOS with a bottle, `brew install xcodesorg/made/xcodes aria2` is the alternative (Brewfile syntax: `tap "xcodesorg/made"` + `brew "xcodesorg/made/xcodes"`), scoped to the Xcode host through its context's app list with `hosts:`, never the shared Brewfile.

---

## Step 2: Extract

```bash
cd ~/Downloads                # or /Volumes/EnvyExtSSD on the SSD layout
xip --expand Xcode_*.xip
```

Notes:

- `xip` verifies Apple's signature during expansion; a successful expand **is** the integrity check. Truncated/corrupt downloads refuse to expand. Success output looks like:
  `xip: signing certificate was "Software Update" (validation not attempted)` followed by `xip: expanded items from "..."`.
- **Betas expand as `Xcode-beta.app`**, not `Xcode.app`. Adjust paths accordingly.
- The app directory timestamp reflects Apple's packaging date, not your extraction time.
- Expansion takes a while with no progress indicator; apparent stalls are normal.

Then place it and delete the archive:

```bash
# Internal-only layout
mv Xcode-beta.app /Applications/
rm Xcode_*.xip

# External-SSD layout
mkdir -p /Volumes/EnvyExtSSD/Applications
mv Xcode-beta.app /Volumes/EnvyExtSSD/Applications/
rm Xcode_*.xip
```

Running the app from an external volume requires the volume to be **APFS** (not HFS+/exFAT). Performance over Thunderbolt/USB4 is indistinguishable from internal for build work.

---

## Step 3: Wire up the toolchain

```bash
# Internal-only layout
sudo xcode-select -s /Applications/Xcode-beta.app/Contents/Developer

# External-SSD layout
sudo xcode-select -s /Volumes/EnvyExtSSD/Applications/Xcode-beta.app/Contents/Developer

# Both layouts
sudo xcodebuild -license accept
sudo xcodebuild -runFirstLaunch
xcodebuild -version
```

`-runFirstLaunch` installs embedded components non-interactively (prints a percentage progress line) so the first GUI launch doesn't stall on a progress bar. The final `xcodebuild -version` printing a version (e.g. `Xcode 27.2 / Build version 27B5038j`) is the all-clear that the app is complete and selected.

---

## Step 4: Platform runtimes (the real download)

The runtimes for iPhone, iPad and Apple Watch:

- **iOS**: covers iPhone **and** iPad simulators (one shared runtime)
- **watchOS**: Apple Watch simulators
- Skip tvOS/visionOS unless targeting them

From the terminal (same downloads as the GUI, scriptable):

```bash
xcodebuild -downloadPlatform iOS
xcodebuild -downloadPlatform watchOS
```

Or in the GUI: `open -a Xcode-beta` (or open the SSD copy by path), then **Settings (Cmd+,) → Components** (older Xcode called the tab "Platforms") and **Get** the iOS and watchOS rows.

These land internal regardless of layout (cryptex mounts, see above).

On 27.2, `-downloadPlatform iOS` installed **two** iOS runtimes: the general one (`com.apple.CoreSimulator.SimRuntime.iOS-27-2`, which carries the iPhone 18 / 17 / Air and all iPad simulators) and a device-specific one (`iOS-27-2-iPhone19-4`, 8 GB, whose only simulator is "iPhone Duo"). Keep both: the iPhone Duo is one of the devices apps here are tested on.

Verify when finished:

```bash
xcrun simctl list runtimes
xcrun simctl list devicetypes | grep -E 'iPhone|iPad|Watch'
```

An iOS and a watchOS runtime listed, plus iPhone, iPad and Apple Watch device types, means the environment is complete.

### First GUI launch

The first launch shows two onboarding screens from a helper process (an agent granted Xcode cannot click either, so a person does):

1. **Import Settings** from another device over iCloud. On the internal-only layout choose **Skip**: an import from an SSD-layout Mac brings its `/Volumes/...` Derived Data path along.
2. **Components**, with iOS and watchOS already switched on when Step 4 ran first. **Download & Install** then just confirms what is installed.

### Runtime hygiene (future)

Runtimes accumulate as Xcode versions update (each wants its matching runtime; old ones linger, multi-GB each). Inspect and prune:

```bash
xcrun simctl runtime list
xcrun simctl runtime delete <id>
```

---

## Step 5: Relocate Derived Data (SSD layout only)

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

## Step 6: First project (beta flow quirks)

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

## Step 7: Session hygiene

Simulators are separate apps that **outlive Xcode** — a booted simulator persists as dozens of background processes (the simulated device's own OS daemons, visible in `ps` as processes under `/private/var/run/com.apple.security.cryptexd/mnt/...`) even after quitting Xcode and with no Simulator window. End-of-session:

```bash
xcrun simctl shutdown all
```

Worth aliasing (`alias simoff='xcrun simctl shutdown all'`). Occasionally-orphaned build daemons (`SourceKitService`, `XCBBuildService`) are safe to `pkill` — they respawn on demand.

---

## Quick-reference: full command sequence

### Internal-only layout

```bash
# download the matching beta .xip to ~/Downloads via browser, then:
cd ~/Downloads
xip --expand Xcode_*.xip
mv Xcode-beta.app /Applications/
rm Xcode_*.xip
sudo xcode-select -s /Applications/Xcode-beta.app/Contents/Developer
sudo xcodebuild -license accept
sudo xcodebuild -runFirstLaunch
xcodebuild -version
xcodebuild -downloadPlatform iOS
xcodebuild -downloadPlatform watchOS
xcrun simctl list runtimes
```

### External-SSD layout

```bash
# download the matching beta .xip to /Volumes/EnvyExtSSD via browser, then:
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
xcodebuild -downloadPlatform iOS
xcodebuild -downloadPlatform watchOS
xcrun simctl list runtimes
```

Internal-only skips the Derived Data relocation entirely; defaults are correct when internal space isn't constrained. Everything else, including all beta quirks in Step 6, applies to both layouts.

---

## Disk budget summary

| | Internal-only | External-SSD |
|---|---|---|
| Internal cost | ~4 GB app + ~20 GB (iOS + watchOS runtimes, 27.2) + simulator device data and Derived Data over time | ~20 GB (iOS + watchOS runtimes, 27.2) + simulator device data over time |
| Practical minimum free internal before starting | ~30 GB | ~25 GB |

On release (non-beta) Xcode versions, expect the `.xip` and expanded app to be larger; check sizes before assuming the beta's slim figures.
