-- Hammerspoon config — equivalent of sheets.ahk
-- Mac equivalent of AutoHotkey

-- Command-line access: enables the `hs` CLI (brew's hammerspoon ships it) so
-- config can be probed/driven from a shell: `hs -c "wl.applyAll()"`.
require("hs.ipc")

----------Hotkey Reference----------
-- Update this table whenever you add or remove a binding
local hotkeyRef = {
    {"Ctrl+Shift+C",  "Open selected ID as Google Sheet"},
    {"Ctrl+Shift+F",  "Open selected ID as Google Drive folder"},
    {"Cmd+Shift+V",   "Paste as plain text (strips formatting)"},
    {"Ctrl+Shift+T",  "Open front Finder window in Terminal"},
    {"Ctrl+Shift+L",  "Apply saved layouts to every desktop in sequence"},
    {"Ctrl+Shift+A",  "Apply saved layout to THIS desktop only"},
    {"Ctrl+Shift+S",  "Recapture ALL windows on this desktop"},
    {"Ctrl+Shift+W",  "Recapture only the focused app's window(s)"},
    {"Ctrl+Shift+E",  "Open the visual layout editor in a browser"},
    {"Ctrl+Shift+P",  "Enforce every app's desktop assignment"},
    {"Ctrl+Shift+G",  "Send visible windows to the desktop they belong on"},
    {"Ctrl+Shift+H",  "Show this hotkey cheatsheet"},
}

hs.hotkey.bind({"ctrl", "shift"}, "h", function()
    local lines = {}
    for _, entry in ipairs(hotkeyRef) do
        table.insert(lines, string.format("%-22s  %s", entry[1], entry[2]))
    end
    hs.alert.show(table.concat(lines, "\n"), 5)
end)

----------Go To Selected Sheet ID----------
-- Ctrl+Shift+C: copy selection, open as Google Sheet
hs.hotkey.bind({"ctrl", "shift"}, "c", function()
    hs.eventtap.keyStroke({"cmd"}, "c", 200000)
    hs.timer.doAfter(0.15, function()
        local id = hs.pasteboard.getContents()
        if id and id ~= "" then
            hs.urlevent.openURL("https://docs.google.com/spreadsheets/d/" .. id:gsub("%s+", ""))
        end
    end)
end)

----------Go To Selected GDrive Folder ID----------
-- Ctrl+Shift+F: copy selection, open as Google Drive folder
hs.hotkey.bind({"ctrl", "shift"}, "f", function()
    hs.eventtap.keyStroke({"cmd"}, "c", 200000)
    hs.timer.doAfter(0.15, function()
        local id = hs.pasteboard.getContents()
        if id and id ~= "" then
            hs.urlevent.openURL("https://drive.google.com/drive/folders/" .. id:gsub("%s+", ""))
        end
    end)
end)

----------Paste as Plain Text----------
-- Cmd+Shift+V: strip formatting from clipboard then paste
hs.hotkey.bind({"cmd", "shift"}, "v", function()
    local txt = hs.pasteboard.getContents()
    if txt then
        hs.pasteboard.setContents(txt)
        hs.timer.doAfter(0.05, function()
            hs.eventtap.keyStroke({"cmd"}, "v")
        end)
    end
end)

----------Open Finder Folder in Terminal----------
-- Ctrl+Shift+T: open front Finder window's path in a new Terminal window
hs.hotkey.bind({"ctrl", "shift"}, "t", function()
    local ok, path = hs.osascript.applescript([[
        tell application "Finder"
            POSIX path of ((target of front window) as alias)
        end tell
    ]])
    if not ok or not path then return end
    local safePath = path:gsub("'", "'\\''")
    hs.application.open("Terminal")
    hs.timer.doAfter(0.5, function()
        hs.osascript.applescript(string.format([[
            tell application "Terminal"
                activate
                do script "cd '%s'"
            end tell
        ]], safePath))
    end)
end)

----------Window Layouts (per-space, KVM monitor-shuffle fix)----------
-- Problem: switching the KVM re-enumerates displays, so macOS dumps every
-- window onto one screen. Display IDs/UUIDs are NOT stable across the switch,
-- so we anchor layouts on screen ORIENTATION (portrait vs landscape) instead.
-- One monitor is vertical, so "the portrait screen" is unambiguous and survives
-- the KVM flip.
--
-- Spaces: Mission Control space IDs aren't stable across logins, so layouts are
-- stored PER SPACE under its POSITION number (desktop 1 -> "1"). The position is
-- detected automatically; you are only asked if detection fails.
--
-- Layouts live in `window_layouts.json` (NOT in this file). Because init.lua is
-- symlinked into ~/.hammerspoon from the dotfiles repo, we follow that symlink
-- and read/write the JSON next to the real init.lua. That path is itself a
-- symlink deployed from the private credentials repo (window titles carry real
-- hostnames and client Chrome profile names, so the data cannot live in this
-- public repo); reads and editor saves both go through it, so changes land in
-- the credentials repo to be committed there.
--
-- File shape:
--   { "all":    [ {app, screen, unit{x,y,w,h}}, ... ],
--     "1": [...], "2": [...], "3": [...],
--     "assign": { "Mail": "all", "Microsoft Edge": 3 } }
--
-- "all" is the shared layout. An app assigned to All Desktops has ONE window
-- that shows up everywhere, so it cannot be in two places at once and a
-- per-desktop rect for it is a lie waiting to drift. Those windows live in
-- "all" and get applied on every desktop. Numeric keys hold the windows that
-- really are specific to one desktop.
--
-- WHICH DESKTOP and WHERE ON IT are separate questions, so they are separate
-- config:
--
--   "assign"  which desktop an app's windows belong on - "all" for every
--             desktop, or a desktop number. This is the macOS Dock setting
--             (Options > Assign To), which this config enforces. Optional.
--   rectangle where the window sits, in "all" or under a desktop number.
--             Also optional.
--
-- An entry may carry "match": a substring of the window title. That is what
-- tells one VS Code window from another, since the Dock's assignment is
-- per-APP and VS Code wants a different window on each desktop. Titles change
-- as you switch files, so match the stable tail - "envy (Workspace)".
--
-- An entry may also omit "unit" entirely. That says "this window belongs on
-- this desktop, don't manage where it sits" - the per-window version of an
-- assignment, and the only way to say it for an app whose windows want
-- different desktops (Chrome, one profile per desktop).
--
-- Either can exist without the other. "Microsoft Edge": 3 with no rectangle is
-- "keep Edge on desktop 3, I don't care where"; VS Code has a rectangle on all
-- three desktops and no assignment, because it is three separate windows.
--
-- An app with neither is simply not managed: apply never touches it, and
-- un-configuring an app means dropping it from both.
--
-- Three ways to drive it:
--   Hotkeys     Ctrl+Shift+H lists them all.
--   Editor      Ctrl+Shift+E opens a drag-and-drop editor in the browser.
--   HTTP        http://localhost:21212/... (Stream Deck keys, shell, whatever).
wl = {}  -- global so hs -c / the console can reach it

hs.window.animationDuration = 0

wl.PORT = 21212

----------Storage----------

-- Directory of the REAL init.lua (follows the ~/.hammerspoon symlink into the
-- dotfiles repo), so the JSON and the editor HTML land somewhere committable.
function wl.dir()
    if wl._dir then return wl._dir end
    local dir = hs.configdir .. "/"
    local target = hs.execute("readlink '" .. hs.configdir .. "/init.lua' 2>/dev/null")
    target = (target or ""):gsub("%s+$", "")
    if target ~= "" then
        dir = target:match("^(.*/)") or dir
    end
    wl._dir = dir
    return dir
end

function wl.file() return wl.dir() .. "window_layouts.json" end

function wl.loadAll()
    if hs.fs.attributes(wl.file()) then
        local data = hs.json.read(wl.file())
        if type(data) == "table" then return data end
    end
    return {}
end

-- Hand-rolled encoder instead of hs.json.write. Lua tables have no key order, so
-- hs.json would shuffle {x,y,w,h} on every write and every save would show up as
-- a whole-file diff. Emitting a fixed key order keeps the committed JSON stable:
-- a save that changed one window shows one window's worth of diff.
local function num(n)
    local r = math.floor(n * 1000 + 0.5) / 1000
    if r == math.floor(r) then return string.format("%d", r) end
    return (string.format("%.3f", r):gsub("0+$", ""))
end

-- hs.json.encode only accepts tables, so quote strings by hand. App names are
-- plain ("T3 Code (Alpha)", "Outlook (PWA)"), but escape properly anyway.
local function str(s)
    s = tostring(s or "")
    s = s:gsub('[\\"]', '\\%0'):gsub('\n', '\\n'):gsub('\r', '\\r'):gsub('\t', '\\t')
    s = s:gsub('%c', function(c) return string.format('\\u%04x', c:byte()) end)
    return '"' .. s .. '"'
end

local function encodeLayout(list)
    local rows = {}
    for _, item in ipairs(list or {}) do
        local u = item.unit or {}
        local match = ""
        if item.match and item.match ~= "" then
            match = string.format('\n      "match": %s,', str(item.match))
        end
        if item.unit then
            rows[#rows + 1] = string.format(
                '    {\n      "app": %s,%s\n      "screen": %s,\n      "unit": { "x": %s, "y": %s, "w": %s, "h": %s }\n    }',
                str(item.app or "?"), match, str(item.screen or "landscape"),
                num(u.x or 0), num(u.y or 0), num(u.w or 1), num(u.h or 1))
        else
            -- no rectangle: the entry exists only to say which desktop this
            -- window belongs on
            rows[#rows + 1] = string.format('    {\n      "app": %s,%s\n      "screen": %s\n    }',
                str(item.app or "?"), match, str(item.screen or "landscape"))
        end
    end
    if #rows == 0 then return "[]" end
    return "[\n" .. table.concat(rows, ",\n") .. "\n  ]"
end

local function encodeAssign(map)
    local keys = {}
    for k, v in pairs(map or {}) do
        if v == "all" or tonumber(v) then keys[#keys + 1] = k end
    end
    table.sort(keys)
    if #keys == 0 then return '  "assign": {}' end
    local rows = {}
    for _, k in ipairs(keys) do
        local v = map[k]
        rows[#rows + 1] = string.format("    %s: %s", str(k),
            v == "all" and '"all"' or string.format("%d", tonumber(v)))
    end
    return '  "assign": {\n' .. table.concat(rows, ",\n") .. "\n  }"
end

function wl.saveAll(doc)
    local keys = {}
    for k, v in pairs(doc) do
        if tostring(k):match("^%d+$") and type(v) == "table" then keys[#keys + 1] = tostring(k) end
    end
    table.sort(keys, function(a, b) return tonumber(a) < tonumber(b) end)

    local parts = { '  "all": ' .. encodeLayout(doc.all) }
    for _, k in ipairs(keys) do
        parts[#parts + 1] = string.format('  "%s": %s', k, encodeLayout(doc[k]))
    end
    parts[#parts + 1] = encodeAssign(doc.assign)

    local f = io.open(wl.file(), "w")
    if not f then return false end
    f:write("{\n" .. table.concat(parts, ",\n") .. "\n}\n")
    f:close()
    return true
end

-- app -> "all" | desktop number. Missing means the assignment is not managed.
function wl.assignMap()
    local a = wl.loadAll().assign
    return type(a) == "table" and a or {}
end

-- Which apps are supposed to be on every desktop.
local function sharedSet(assign)
    local set = {}
    for app, want in pairs(assign or {}) do
        if want == "all" then set[app] = true end
    end
    return set
end

----------Screens and spaces----------

-- Pick a screen by orientation. Falls back to primary if none matches.
function wl.screenFor(orientation)
    for _, s in ipairs(hs.screen.allScreens()) do
        local f = s:frame()
        local isPortrait = f.h > f.w
        if (orientation == "portrait") == isPortrait then
            return s
        end
    end
    return hs.screen.primaryScreen()
end

-- Which numbered desktop is active right now? Returns index, orderedIDs.
-- Both monitors share one set of spaces here ("Displays have separate
-- Spaces" is off), so either screen reports the same list.
function wl.spaceIndex()
    local ids = {}
    for _, id in ipairs(hs.spaces.spacesForScreen(wl.screenFor("landscape")) or {}) do
        if hs.spaces.spaceType(id) == "user" then table.insert(ids, id) end
    end
    local active = hs.spaces.activeSpaceOnScreen(wl.screenFor("landscape"))
    for i, id in ipairs(ids) do
        if id == active then return i, ids end
    end
    return nil, ids
end

-- Current desktop number as a string key. Prompts only if detection fails,
-- which is the whole point: you should never have to type the number.
function wl.currentKey(action)
    local detected = wl.spaceIndex()
    if detected then
        wl.lastSpace = tostring(detected)
        return wl.lastSpace
    end
    local btn, txt = hs.dialog.textPrompt(
        "Window layout — " .. (action or "save"),
        "Couldn't detect the desktop number. Which desktop is this?",
        tostring(wl.lastSpace or "1"), "OK", "Cancel")
    if btn ~= "OK" then return nil end
    local key = tostring(txt):match("%d+")
    if not key then
        hs.alert.show("Enter a number")
        return nil
    end
    wl.lastSpace = key
    return key
end

----------Capture----------

-- Fractional rect of a window against its own screen's usable frame.
local function unitOf(win)
    local f, wf = win:screen():frame(), win:frame()
    local function round(n) return math.floor(n * 1000 + 0.5) / 1000 end
    return {
        x = round((wf.x - f.x) / f.w),
        y = round((wf.y - f.y) / f.h),
        w = round(wf.w / f.w),
        h = round(wf.h / f.h),
    }, (f.h > f.w) and "portrait" or "landscape"
end

local function entryFor(win)
    local unit, screen = unitOf(win)
    return { app = win:application():name(), screen = screen, unit = unit }
end

-- Does this window satisfy an entry's title match? An entry with no match takes
-- any window of its app, which is the common case.
local function titleMatches(item, win)
    if not item.match or item.match == "" then return true end
    return (win:title() or ""):find(item.match, 1, true) ~= nil
end

-- Every standard window currently visible on this desktop, in stacking order.
local function currentWindows()
    local out = {}
    for _, win in ipairs(hs.window.orderedWindows()) do
        if win:isStandard() then out[#out + 1] = win end
    end
    return out
end

-- Fold freshly captured entries into an existing list, matching per app and in
-- order, so an app with two saved windows (GLKVM) keeps both slots. Entries for
-- apps that were not captured at all are left alone: that is what lets a
-- desktop-1 recapture keep the shared entry for an app that only happens to be
-- minimised right now, instead of silently deleting it.
local function mergeByApp(existing, captured)
    local queue, order = {}, {}
    for _, e in ipairs(captured) do
        if not queue[e.app] then queue[e.app] = {}; order[#order + 1] = e.app end
        table.insert(queue[e.app], e)
    end
    -- A slot with a title match must be refilled from the window it names, not
    -- from whichever window of that app happened to be enumerated first, or a
    -- recapture would swap two VS Code windows' rectangles.
    local function take(slot)
        local q = queue[slot.app]
        if not q or #q == 0 then return nil end
        local pick = 1
        if slot.match and slot.match ~= "" then
            pick = nil
            for i, e in ipairs(q) do
                if e.title and e.title:find(slot.match, 1, true) then pick = i break end
            end
            if not pick then return nil end
        end
        local e = table.remove(q, pick)
        e.match = slot.match            -- the match is config, not something capture sets
        e.title = nil
        -- A slot with no rectangle stays that way: recapturing a desktop must
        -- not quietly start managing where a window sits.
        if not slot.unit then e.unit = nil end
        return e
    end
    local out = {}
    for _, e in ipairs(existing or {}) do
        if not queue[e.app] then
            out[#out + 1] = e                       -- app not on screen, keep as saved
        else
            local filled = take(e)
            if filled then out[#out + 1] = filled end   -- else: stale extra slot, dropped
        end
    end
    for _, app in ipairs(order) do
        for _, e in ipairs(queue[app]) do e.title = nil; out[#out + 1] = e end
    end
    return out
end

-- Split what is on screen into the shared layout and this desktop's layout.
-- All-desktops apps are one window seen from everywhere, so they belong in "all" no
-- matter which desktop you happened to press the key on.
local function captureHere(doc)
    local shared_ = sharedSet(doc.assign)
    local shared, per = {}, {}
    for _, win in ipairs(currentWindows()) do
        local e = entryFor(win)
        e.title = win:title()   -- only so mergeByApp can pair on it; never written out
        if shared_[e.app] then shared[#shared + 1] = e else per[#per + 1] = e end
    end
    return shared, per
end

-- RECAPTURE ALL: replace this desktop's layout with what is on screen now, and
-- refresh the shared layout from the same pass.
function wl.snapshot(key)
    key = key or wl.currentKey("recapture all")
    if not key then return end
    local doc = wl.loadAll()
    local shared, per = captureHere(doc)
    -- Merge, never replace. A saved entry carries hand-written config that no
    -- capture can reconstruct - the title match, and whether the window is
    -- positioned at all - so blowing the list away and rebuilding it from the
    -- screen silently deletes that. Merging also means closing an app does not
    -- delete its layout.
    doc.all = mergeByApp(doc.all, shared)
    doc[key] = mergeByApp(doc[key], per)
    if wl.saveAll(doc) then
        hs.alert.show(string.format("Desktop %s: %d window%s, %d on all desktops",
            key, #per, #per == 1 and "" or "s", #shared))
    else
        hs.alert.show("Failed to write " .. wl.file())
    end
    return per
end

-- RECAPTURE ONE APP: leave the rest of the desktop's saved layout alone and
-- update only this app's entries. This is the one you want after nudging a
-- single window: no risk of a half-arranged desktop overwriting good entries.
-- Matching is positional, so an app with two saved windows (GLKVM) keeps both
-- slots in order; extra saved entries are dropped, extra live windows appended.
function wl.snapshotApp(appName, key)
    key = key or wl.currentKey("recapture app")
    if not key then return end
    if not appName then
        local win = hs.window.focusedWindow()
        if not win then hs.alert.show("No focused window") return end
        appName = win:application():name()
    end

    local doc = wl.loadAll()
    local live = {}
    for _, win in ipairs(currentWindows()) do
        if win:application():name() == appName then
            local e = entryFor(win)
            e.title = win:title()
            live[#live + 1] = e
        end
    end
    if #live == 0 then
        hs.alert.show("No " .. appName .. " window on desktop " .. key)
        return
    end

    -- An all-desktops app's rect is shared, so saving it from any desktop updates
    -- the one entry every desktop uses. Everything else is saved per desktop.
    local shared = sharedSet(doc.assign)[appName]
    local target = shared and "all" or key
    doc[target] = mergeByApp(doc[target], live)

    if wl.saveAll(doc) then
        hs.alert.show(string.format("Saved %d %s window%s (%s)",
            #live, appName, #live == 1 and "" or "s",
            shared and "all desktops" or ("desktop " .. key)))
    else
        hs.alert.show("Failed to write " .. wl.file())
    end
    return doc[target]
end

----------Apply----------

-- Move + resize one window using a fractional rect of its target screen.
-- unit = {x, y, w, h} as fractions (0..1) of the screen's usable frame.
local function placeWindow(win, orientation, unit)
    local screen = wl.screenFor(orientation)
    if not (win and screen) then return end
    local f = screen:frame()
    win:setFrame({
        x = f.x + unit.x * f.w,
        y = f.y + unit.y * f.h,
        w = unit.w * f.w,
        h = unit.h * f.h,
    })
    -- Apps with a minimum size can refuse the requested width/height and end
    -- up hanging off the screen edge; shift them back fully on-screen. Deferred
    -- because some apps apply the resize (and their min-size clamp) async.
    hs.timer.doAfter(0.3, function()
        local wf = win:frame()
        local x = math.max(f.x, math.min(wf.x, f.x + f.w - wf.w))
        local y = math.max(f.y, math.min(wf.y, f.y + f.h - wf.h))
        if x ~= wf.x or y ~= wf.y then
            win:setTopLeft({x = x, y = y})
        end
    end)
end

-- Apply a saved desktop's layout to whatever of its apps are running now.
-- Windows must be matched per space, not via app:mainWindow(): that is the
-- app's globally last-focused window, which for one-window-per-space apps
-- (VS Code, Terminal) usually lives on a DIFFERENT space than the one being
-- applied. orderedWindows() only sees the currently visible spaces, so it
-- yields exactly the windows this pass may move; hand each out at most once
-- so duplicate app entries (e.g. two GLKVM windows) get distinct windows.
function wl.apply(key)
    key = tostring(key)
    local doc = wl.loadAll()
    local per = doc[key]
    if type(per) ~= "table" and type(doc.all) ~= "table" then
        hs.alert.show("No saved layout for desktop " .. key)
        return
    end
    -- Shared entries go FIRST so they get first pick of windows. An All Desktops
    -- window is visible from here too, and a leftover per-desktop entry for the
    -- same app would otherwise claim it and drag it somewhere else.
    -- Entries with no unit are desktop rules, not positions; gather uses them
    -- and apply has nothing to do with them.
    local layout = {}
    for _, e in ipairs(doc.all or {}) do if e.unit then layout[#layout + 1] = e end end
    for _, e in ipairs(per or {}) do if e.unit then layout[#layout + 1] = e end end

    local byApp = {}
    for _, win in ipairs(currentWindows()) do
        local name = win:application():name()
        byApp[name] = byApp[name] or {}
        table.insert(byApp[name], win)
    end
    -- Three matching passes over ALL entries, each handing out at most one
    -- window per entry.
    --   0. entries with a title match take the window they name. A title is a
    --      much stronger signal than a screen, so these get first refusal -
    --      otherwise an unmatched entry could grab the envy VS Code window
    --      simply for being on the right monitor.
    --   1. remaining entries take a window already on their target-orientation
    --      screen.
    --   2. leftovers go cross-screen, which is what recovers from the KVM
    --      dumping every window onto one monitor.
    -- Splitting it this way stops a stale entry (a saved portrait Chrome when no
    -- Chrome is on the portrait screen anymore) from stealing a window that a
    -- later same-app entry would have matched in place.
    local function claim(wins, pred)
        for i, w in ipairs(wins) do
            if pred(w) then return table.remove(wins, i) end
        end
    end
    local assigned = {}
    for idx, item in ipairs(layout) do
        if item.match and item.match ~= "" then
            assigned[idx] = claim(byApp[item.app] or {}, function(w) return titleMatches(item, w) end)
        end
    end
    for idx, item in ipairs(layout) do
        if not assigned[idx] then
            assigned[idx] = claim(byApp[item.app] or {}, function(w)
                local f = w:screen():frame()
                return (item.screen == "portrait") == (f.h > f.w) and titleMatches(item, w)
            end)
        end
    end
    for idx, item in ipairs(layout) do
        if not assigned[idx] then
            assigned[idx] = claim(byApp[item.app] or {}, function(w) return titleMatches(item, w) end)
        end
    end
    local placed = 0
    for idx, item in ipairs(layout) do
        if assigned[idx] then
            placeWindow(assigned[idx], item.screen, item.unit)
            placed = placed + 1
        end
    end
    hs.alert.show(string.format("Applied desktop %s (%d windows)", key, placed))
    return placed
end

-- Apply just this desktop, no walking.
function wl.applyHere()
    local key = wl.currentKey("apply")
    if not key then return end
    wl.gather(function() wl.apply(key) end)
end

-- Switch to the desktop at position i (ids[i] is its space ID).
--
-- Do NOT reach for hs.spaces.gotoSpace as the primary route: it works by
-- opening Mission Control and pressing a desktop button in the Dock's
-- accessibility tree, and on this macOS the Dock's "mc" group is an empty 0x0
-- element with no children (verified via hs.spaces.data_missionControlAXUIElementData),
-- so every call fails with "no display with specified id found". That failure
-- is what stopped the walk after one desktop.
--
-- macOS's own "Switch to Desktop N" shortcut (ctrl+N, System Settings >
-- Keyboard > Shortcuts > Mission Control) DOES fire from a synthesized event,
-- so drive that instead, and keep gotoSpace as the fallback in case the AX
-- route ever comes back. Caveat: a desktop is only reachable this way while its
-- ctrl+N shortcut exists and is enabled — macOS adds one per desktop, but if a
-- switch reports "didn't land", check that list first.
function wl.gotoIndex(i, id)
    if i <= 9 then
        hs.eventtap.keyStroke({"ctrl"}, tostring(i), 0)
        return true
    end
    return hs.spaces.gotoSpace(id) and true or false
end

-- Apply the current desktop's layout, then walk the remaining desktops in
-- Mission Control order, applying each one's saved layout, and finish back on
-- the desktop you started from. AX can't see windows on inactive spaces, so
-- each desktop has to actually be visible when its layout is applied.
--
-- Assignments are repaired FIRST: a window that macOS thinks is on all
-- desktops but has silently stopped following you would otherwise get placed
-- on whichever desktop happens to still hold it, and skipped everywhere else.
function wl.applyAll()
    wl.fixAssign({ quiet = true, then_ = wl.applyAllNow })
end

-- Visit every desktop in Mission Control order, run fn(i) while standing on it,
-- then come home and call done(). Anything that needs a desktop's windows - or
-- needs macOS to think "this desktop" means that one - has to actually be there.
-- fn(i, next) is called standing on desktop i and must call next() when it is
-- finished, which is what lets a step do its own desktop switching (gather has
-- to). wl.walk wraps a plain fn(i) for the synchronous case.
function wl.walkAsync(fn, done)
    local startIdx, ids = wl.spaceIndex()
    if not startIdx then
        hs.alert.show("Can't tell which desktop this is")
        if done then done() end
        return
    end
    local remaining = {}
    for i = 1, #ids do
        if i ~= startIdx then table.insert(remaining, i) end
    end
    local pos = 0
    local step
    step = function()
        pos = pos + 1
        local i = remaining[pos]
        if not i then
            wl.log("walk done, returning to desktop %d", startIdx)
            wl.gotoIndex(startIdx, ids[startIdx])
            if done then hs.timer.doAfter(0.5, done) end
            return
        end
        wl.log("walk -> desktop %d", i)
        wl.gotoIndex(i, ids[i])
        -- Running before the switch lands would act on the WRONG desktop; verify
        -- arrival first. The extra settle after arrival is for the switch
        -- animation — the space ID flips as it starts, before that desktop's
        -- windows are all enumerable.
        local tries = 0
        local function waitRun()
            if wl.spaceIndex() == i then
                hs.timer.doAfter(0.4, function() fn(i, step) end)
            elseif tries < 12 then
                tries = tries + 1
                hs.timer.doAfter(0.25, waitRun)
            else
                hs.alert.show("Switch to desktop " .. i .. " didn't land — skipped")
                step()
            end
        end
        hs.timer.doAfter(0.3, waitRun)
    end
    fn(startIdx, step)
end

function wl.walk(fn, done)
    wl.walkAsync(function(i, next_) fn(i) next_() end, done)
end

-- Which desktop does this window belong on? Sources, in order:
--   the app's assignment, then a rectangle whose title match fits this window,
--   then - if the app has rectangles on exactly one desktop - that one.
-- Anything ambiguous returns nil and the window is left where it is. Two
-- Personal Calendar entries on different desktops with no match is ambiguous;
-- three VS Code entries with distinct matches is not.
function wl.targetDesktop(win, doc)
    doc = doc or wl.loadAll()
    local app = win:application():name()
    local want = (doc.assign or {})[app]
    if want == "all" then return nil end
    if want then return tonumber(want) end

    local title = win:title() or ""
    local matched, matchedN = nil, 0
    local desktops, desktopN = {}, 0
    for k, list in pairs(doc) do
        if tostring(k):match("^%d+$") and type(list) == "table" then
            for _, item in ipairs(list) do
                if item.app == app then
                    if not desktops[tonumber(k)] then
                        desktops[tonumber(k)] = true
                        desktopN = desktopN + 1
                    end
                    if item.match and item.match ~= "" and title:find(item.match, 1, true) then
                        matched, matchedN = tonumber(k), matchedN + 1
                    end
                end
            end
        end
    end
    if matchedN == 1 then return matched end
    if matchedN > 1 then return nil end
    if desktopN == 1 then for d in pairs(desktops) do return d end end
    return nil
end

-- Move ONE window to another desktop.
--
-- hs.spaces.moveWindowToSpace is the obvious call and it is a lie on this macOS:
-- it returns true and the window does not move (verified - windowSpaces reports
-- the same space before and after). The private CGS call behind it no longer
-- does anything here.
--
-- So do what a person does. macOS carries a window that is mid-drag when you
-- press its "switch to desktop N" shortcut, and that shortcut is already the
-- one wl.gotoIndex leans on. Grab the title bar, hold, switch, let go.
--
-- Grab point: 30% across rather than the middle, which keeps clear of both the
-- traffic lights on the left and whatever an app puts in the centre of its title
-- bar (VS Code's command centre). The drag is a few pixels so macOS reads it as
-- a drag and not a click on whatever is under the cursor.
function wl.dragToDesktop(win, n)
    local _, ids = wl.spaceIndex()
    if not (win and ids[n]) then return false end
    local before = hs.spaces.windowSpaces(win) or {}
    local f = win:frame()
    local x = f.x + math.min(f.w - 30, math.max(100, f.w * 0.3))
    local y = f.y + 10
    local ev = hs.eventtap.event
    local at = function(dx, dy) return hs.geometry.point(x + (dx or 0), y + (dy or 0)) end

    win:focus()
    hs.timer.usleep(250000)
    ev.newMouseEvent(ev.types.leftMouseDown, at()):post()
    hs.timer.usleep(150000)
    ev.newMouseEvent(ev.types.leftMouseDragged, at(10, 4)):post()
    hs.timer.usleep(250000)
    wl.gotoIndex(n, ids[n])
    hs.timer.usleep(900000)
    ev.newMouseEvent(ev.types.leftMouseDragged, at(12, 6)):post()
    hs.timer.usleep(150000)
    ev.newMouseEvent(ev.types.leftMouseUp, at(12, 6)):post()

    -- windowSpaces lags the drop by a beat, so poll rather than take one late
    -- reading as a failure - it was reporting "no move" for moves that worked.
    local after, ok = before, false
    for _ = 1, 8 do
        hs.timer.usleep(250000)
        after = hs.spaces.windowSpaces(win) or {}
        if after[1] == ids[n] then ok = true break end
    end
    wl.log("drag %s -> desktop %d: %s (%s)", win:application():name(), n,
        ok and "ok" or "no move", (win:title() or ""):sub(1, 40))
    return ok
end

-- Which windows visible from here are on the wrong desktop?
function wl.gatherPlan()
    local doc = wl.loadAll()
    local _, ids = wl.spaceIndex()
    local plan = {}
    for _, win in ipairs(currentWindows()) do
        local sp = hs.spaces.windowSpaces(win) or {}
        if #sp < #ids then                       -- an all-desktops window is already everywhere
            local target = wl.targetDesktop(win, doc)
            if target and ids[target] and not (#sp == 1 and sp[1] == ids[target]) then
                plan[#plan + 1] = { win = win, target = target }
            end
        end
    end
    return plan
end

-- Send every window visible from here to the desktop the config names, then
-- come back. This is the login fix: VS Code reopens all of its windows on one
-- desktop, and that desktop is the only place anything can see all of them.
-- Each drag leaves you standing on the target, so it returns home between
-- moves, otherwise the rest of the plan would no longer be on screen.
function wl.gather(done)
    local home, ids = wl.spaceIndex()
    local plan = wl.gatherPlan()
    if #plan == 0 then
        if done then done(0) end
        return
    end
    wl.log("gather: %d window(s) to move from desktop %s", #plan, tostring(home))
    local i, moved = 0, 0
    local function step()
        i = i + 1
        local job = plan[i]
        if not job then
            if wl.spaceIndex() ~= home then wl.gotoIndex(home, ids[home]) end
            hs.timer.doAfter(0.6, function() if done then done(moved) end end)
            return
        end
        if wl.dragToDesktop(job.win, job.target) then moved = moved + 1 end
        wl.gotoIndex(home, ids[home])
        hs.timer.doAfter(0.8, step)
    end
    step()
end

-- Gather from EVERY desktop first, then lay everything out. Two passes on
-- purpose: a window gathered onto a desktop that was already positioned would
-- otherwise sit unplaced until the next run.
function wl.applyAllNow()
    local total = 0
    wl.walkAsync(function(_, next_)
        wl.gather(function(n) total = total + n; next_() end)
    end, function()
        wl.log("gathered %d window(s), now applying", total)
        wl.walk(function(i) wl.apply(tostring(i)) end)
    end)
end

-- This desktop only: send away anything that belongs elsewhere, then lay out
-- what is left.
function wl.gatherHere()
    wl.gather(function(moved)
        hs.alert.show(moved > 0 and ("Moved " .. moved .. " window" .. (moved == 1 and "" or "s"))
            or "Nothing to move from here")
    end)
end

----------Desktop assignment (the Dock's "Assign To") ----------
-- Two failure modes this repairs.
--
-- 1. After a KVM flip or enough space shuffling, an app pinned to All Desktops
--    still SHOWS the checkmark in its Dock menu but the window stops following
--    you between desktops. The manual fix is to un-assign it and re-assign All
--    Desktops. Automated below.
-- 2. An app that is supposed to live on one desktop drifts onto another.
--
-- Detection is cheap and needs no menus: hs.spaces.windowSpaces(win) returns
-- every space a window is on, and wl.spaceIndex() gives the space-ID -> desktop
-- number mapping. So "on every space" and "on exactly desktop N" are both
-- directly observable, and a mismatch with "assign" is precisely the bug.
--
-- The repairs drive the Dock's own right-click menu (Options -> All Desktops /
-- This Desktop / None), which is readable and pressable without ever being
-- rendered. macOS resolves "This Desktop" against wherever you are standing, so
-- setting a numbered assignment has to happen while visiting that desktop.
-- (Note this is the Dock's APP menu, which works fine here — unlike the Dock's
-- Mission Control group, the broken one that gotoSpace trips over.)

-- space ID -> desktop position number
local function desktopPositions()
    local _, ids = wl.spaceIndex()
    local pos = {}
    for i, id in ipairs(ids) do pos[id] = i end
    return pos, #ids
end

-- Record what every visible app is doing right now as the intended assignment.
-- Only sees apps with a window open, so it will not invent entries for the rest.
function wl.learnAssign()
    local pos, total = desktopPositions()
    if total < 2 then hs.alert.show("Need more than one desktop") return end
    local assign, seen = {}, {}
    for _, win in ipairs(currentWindows()) do
        local app = win:application():name()
        if not seen[app] then
            seen[app] = true
            local sp = hs.spaces.windowSpaces(win) or {}
            if #sp >= total then
                assign[app] = "all"
            elseif #sp == 1 and pos[sp[1]] then
                assign[app] = pos[sp[1]]
            end
        end
    end
    local doc = wl.loadAll()
    -- Merge rather than replace: apps that are simply not open right now keep
    -- whatever they had, so learning from one desktop cannot wipe the rest.
    doc.assign = doc.assign or {}
    for app, want in pairs(assign) do doc.assign[app] = want end
    wl.saveAll(doc)
    local n = 0
    for _ in pairs(assign) do n = n + 1 end
    hs.alert.show("Recorded assignments for " .. n .. " visible app" .. (n == 1 and "" or "s"))
    return assign
end

-- Apps whose actual desktop does not match "assign". Only judges what is
-- visible from here, which is every all-desktops window plus this desktop's.
-- Each entry: {app, want = "all"|number, have = number|nil, spaces = n}
function wl.brokenAssign()
    local pos, total = desktopPositions()
    if total < 2 then return {} end
    local here = wl.spaceIndex()
    local want = wl.assignMap()
    local out, seen = {}, {}
    for _, win in ipairs(currentWindows()) do
        local app = win:application():name()
        local w = want[app]
        if w and not seen[app] then
            local sp = hs.spaces.windowSpaces(win) or {}
            local on = (#sp == 1) and pos[sp[1]] or nil
            if w == "all" then
                if #sp < total then
                    seen[app] = true
                    out[#out + 1] = { app = app, want = "all", have = on, spaces = #sp }
                end
            elseif tonumber(w) ~= on then
                -- An app wanting desktop N that we can see from desktop M is on the
                -- wrong one, unless we simply cannot tell (multi-space, not all).
                if on ~= nil or #sp > 1 then
                    seen[app] = true
                    out[#out + 1] = { app = app, want = tonumber(w), have = on, spaces = #sp }
                end
            end
        end
    end
    return out
end

function wl.dockItem(name)
    local dock = hs.application.get("Dock")
    if not dock then return nil end
    local ax = hs.axuielement.applicationElement(dock)
    local list = (ax:attributeValue("AXChildren") or {})[1]
    if not list then return nil end
    for _, c in ipairs(list:attributeValue("AXChildren") or {}) do
        if c:attributeValue("AXTitle") == name then return c end
    end
    return nil
end

-- Press one entry under the Dock item's Options submenu ("All Desktops",
-- "This Desktop", "None"). Returns true if it was pressed.
function wl.dockAssign(name, label)
    local item = wl.dockItem(name)
    if not item then return false, "not in Dock" end
    item:performAction("AXShowMenu")
    hs.timer.usleep(400000)
    local menu = (item:attributeValue("AXChildren") or {})[1]
    if not menu then return false, "menu didn't open" end
    local opts
    for _, m in ipairs(menu:attributeValue("AXChildren") or {}) do
        if m:attributeValue("AXTitle") == "Options" then opts = m break end
    end
    local sub = opts and (opts:attributeValue("AXChildren") or {})[1]
    if not sub then
        hs.eventtap.keyStroke({}, "escape", 0)
        return false, "no Options submenu"
    end
    for _, m in ipairs(sub:attributeValue("AXChildren") or {}) do
        if m:attributeValue("AXTitle") == label then
            m:performAction("AXPress")
            hs.timer.usleep(250000)
            return true
        end
    end
    hs.eventtap.keyStroke({}, "escape", 0)
    return false, label .. " not offered"
end

-- The manual All Desktops fix, automated: un-assign, then re-assign.
-- "None" rather than "This Desktop" as the intermediate, so a failure halfway
-- through leaves the app unassigned rather than nailed to the desktop you
-- happened to be standing on.
function wl.repin(name)
    local ok, err = wl.dockAssign(name, "None")
    if not ok then return false, err end
    hs.timer.usleep(300000)
    return wl.dockAssign(name, "All Desktops")
end

-- Move a visible window to the desktop it belongs on. Immediate, and unlike the
-- Dock route it needs no desktop switching or menus.
local function moveToDesktop(win, n)
    local _, ids = wl.spaceIndex()
    if not ids[n] then return false end
    return hs.spaces.moveWindowToSpace(win, ids[n]) and true or false
end

-- Repair what is wrong. opts:
--   quiet   skip the "nothing to do" alert
--   force   act on every assignment, not just the drifted ones
--   dock    also write the Dock's numbered "This Desktop" assignments, which
--           means walking the desktops (Ctrl+Shift+P does this; the automatic
--           post-KVM pass does not, so it never steals your desktop)
--   then_   run this when the repair finishes
function wl.log(fmt, ...)
    hs.printf("[wl] " .. fmt, ...)
end

function wl.fixAssign(opts)
    opts = opts or {}
    local finish = function(msg)
        wl.log("fixAssign done: %s", msg or "nothing to report")
        if msg and not opts.quiet then hs.alert.show(msg) end
        if opts.then_ then opts.then_() end
    end

    local want = wl.assignMap()
    local broken = wl.brokenAssign()

    -- Pass 1: shove misplaced numbered windows onto their desktop. No menus.
    local moved = {}
    for _, b in ipairs(broken) do
        if b.want ~= "all" then
            for _, win in ipairs(currentWindows()) do
                if win:application():name() == b.app then
                    if moveToDesktop(win, b.want) then moved[#moved + 1] = b.app end
                    break
                end
            end
        end
    end

    -- Pass 2: the All Desktops un-pin / re-pin cycle, one app per timer tick so
    -- Hammerspoon stays responsive through the menu work.
    local todo = {}
    if opts.force then
        for app, w in pairs(want) do if w == "all" then todo[#todo + 1] = app end end
        table.sort(todo)
    else
        for _, b in ipairs(broken) do if b.want == "all" then todo[#todo + 1] = b.app end end
    end

    wl.log("fixAssign force=%s dock=%s broken=%d moved=%d repin=%d",
        tostring(opts.force), tostring(opts.dock), #broken, #moved, #todo)
    if #todo == 0 and #moved == 0 and not opts.dock then
        return finish("Desktop assignments all healthy")
    end
    if #todo > 0 then
        hs.alert.show("Re-pinning All Desktops: " .. table.concat(todo, ", "))
    end

    local i, fixed = 0, {}
    local function step()
        i = i + 1
        local name = todo[i]
        if not name then
            local bits = {}
            if #fixed > 0 then bits[#bits + 1] = #fixed .. " re-pinned" end
            if #moved > 0 then bits[#bits + 1] = #moved .. " moved" end
            if opts.dock then
                return wl.assignDesktops(function()
                    finish((#bits > 0 and table.concat(bits, ", ") .. ", " or "") .. "assignments written")
                end)
            end
            return finish(#bits > 0 and table.concat(bits, ", ") or nil)
        end
        local ok, err = wl.repin(name)
        wl.log("repin %s -> %s", name, ok and "ok" or tostring(err))
        if ok then fixed[#fixed + 1] = name end
        hs.timer.doAfter(0.2, step)
    end
    hs.timer.doAfter(0, step)
end

-- Write the Dock's numbered assignments. macOS resolves "This Desktop" against
-- the desktop you are standing on, so this walks them.
function wl.assignDesktops(done)
    local byDesktop = {}
    for app, w in pairs(wl.assignMap()) do
        if w ~= "all" then
            local n = tonumber(w)
            byDesktop[n] = byDesktop[n] or {}
            table.insert(byDesktop[n], app)
        end
    end
    local any = false
    for _ in pairs(byDesktop) do any = true break end
    if not any then if done then done() end return end
    for _, list in pairs(byDesktop) do table.sort(list) end

    wl.walk(function(i)
        for _, app in ipairs(byDesktop[i] or {}) do
            local ok, err = wl.dockAssign(app, "This Desktop")
            wl.log("assign %s -> desktop %d: %s", app, i, ok and "ok" or tostring(err))
        end
    end, done)
end

-- Auto-repair after a display change, which is what the KVM flip looks like
-- from here. Debounced: a KVM switch fires several screen events in a row, and
-- the windows need a moment to settle before windowSpaces() tells the truth.
-- Deliberately without dock=true: this fires on its own, and walking the
-- desktops underneath you unprompted would be obnoxious.
wl.screenWatcher = hs.screen.watcher.new(function()
    if wl._assignTimer then wl._assignTimer:stop() end
    wl._assignTimer = hs.timer.doAfter(5, function()
        wl.fixAssign({ quiet = true })
    end)
end)
wl.screenWatcher:start()

----------Visual editor + HTTP control----------
-- The JSON is a pain to hand-edit, so serve a drag-and-drop editor for it off
-- the same local HTTP server the Stream Deck already talks to. The page is a
-- plain file in the repo next to this config; it GETs /state, you drag windows
-- around against correctly-proportioned screen outlines, and it POSTs /state
-- back. Nothing leaves the machine: the listener is bound to localhost.

local function urldecode(s)
    return (s:gsub("+", " "):gsub("%%(%x%x)", function(h) return string.char(tonumber(h, 16)) end))
end

local function parseQuery(path)
    local q = {}
    local qs = path:match("%?(.*)$")
    for k, v in (qs or ""):gmatch("([^&=]+)=([^&]*)") do q[urldecode(k)] = urldecode(v) end
    return path:match("^([^?]*)") or path, q
end

local JSON_HDR = { ["Content-Type"] = "application/json" }

-- Everything the editor needs to draw: saved layouts, real screen proportions,
-- which desktop you're standing on, and what's on it right now.
function wl.state()
    local doc = wl.loadAll()
    local spaces = {}
    for k, v in pairs(doc) do
        if tostring(k):match("^%d+$") and type(v) == "table" then spaces[tostring(k)] = v end
    end
    local screens = {}
    for _, orientation in ipairs({ "portrait", "landscape" }) do
        local f = wl.screenFor(orientation):frame()
        screens[orientation] = { w = f.w, h = f.h }
    end
    local idx, ids = wl.spaceIndex()
    local pos = {}
    for i, id in ipairs(ids) do pos[id] = i end
    local live = {}
    for _, win in ipairs(currentWindows()) do
        local e = entryFor(win)
        e.title = win:title()
        local sp = hs.spaces.windowSpaces(win) or {}
        e.on = (#sp >= #ids and "all") or (#sp == 1 and pos[sp[1]]) or nil
        live[#live + 1] = e
    end
    return {
        spaces = spaces,
        shared = doc.all or {},
        assign = doc.assign or {},
        screens = screens,
        activeSpace = idx and tostring(idx) or nil,
        spaceCount = #ids,
        live = live,
        broken = wl.brokenAssign(),
        file = wl.file(),
    }
end

function wl.editorURL() return "http://localhost:" .. wl.PORT .. "/editor" end

function wl.openEditor()
    hs.urlevent.openURL(wl.editorURL())
end

wl.server = hs.httpserver.new(false, false)
pcall(function() wl.server:setInterface("localhost") end)
wl.server:setPort(wl.PORT)
-- The real handler. Kept separate from setCallback so a mistake in here returns
-- a 500 with the message instead of Hammerspoon logging "an error occurred
-- during callback handling" and the browser seeing an empty reply.
function wl.handle(method, rawPath, headers, body)
    local path, q = parseQuery(rawPath)

    if path == "/editor" or path == "/" then
        local f = io.open(wl.dir() .. "window_layout_editor.html", "r")
        if not f then return "editor html missing next to init.lua", 404, {} end
        local html = f:read("*a")
        f:close()
        return html, 200, { ["Content-Type"] = "text/html; charset=utf-8" }
    end

    if path == "/state" and method == "GET" then
        return hs.json.encode(wl.state()), 200, JSON_HDR
    end

    if path == "/state" and method == "POST" then
        local incoming = hs.json.decode(body or "")
        if type(incoming) ~= "table" or type(incoming.spaces) ~= "table" then
            return hs.json.encode({ ok = false, error = "expected {spaces:{}, shared:[], assign:{}}" }), 400, JSON_HDR
        end
        local doc = {}
        for k, v in pairs(incoming.spaces) do doc[tostring(k)] = v end
        doc.all = incoming.shared or wl.loadAll().all or {}
        doc.assign = incoming.assign or wl.assignMap()
        local ok = wl.saveAll(doc)
        return hs.json.encode({ ok = ok, file = wl.file() }), ok and 200 or 500, JSON_HDR
    end

    -- Actions. Deferred by a tick so the browser gets its reply before
    -- Hammerspoon starts throwing windows around.
    local actions = {
        ["/applyLayouts"] = function() wl.applyAll() end,
        ["/apply"]        = function() wl.apply(q.space or wl.currentKey("apply")) end,
        ["/snapshot"]     = function() wl.snapshot(q.space) end,
        ["/snapshotApp"]  = function() wl.snapshotApp(q.app, q.space) end,
        ["/gather"]       = function() wl.gatherHere() end,
        ["/fixAssign"]    = function() wl.fixAssign({ force = q.force == "1", dock = q.dock == "1" }) end,
        ["/learnAssign"]  = function() wl.learnAssign() end,
        ["/reload"]       = function() hs.reload() end,
    }
    local fn = actions[path]
    if fn then
        hs.timer.doAfter(0, fn)
        return hs.json.encode({ ok = true, action = path }), 200, JSON_HDR
    end

    return hs.json.encode({ ok = false, error = "unknown endpoint " .. path }), 404, JSON_HDR
end

wl.server:setCallback(function(method, path, headers, body)
    local ok, a, b, c = pcall(wl.handle, method, path, headers, body)
    if ok then return a, b, c end
    hs.printf("wl.handle error: %s", tostring(a))
    return hs.json.encode({ ok = false, error = tostring(a) }), 500, JSON_HDR
end)
wl.server:start()

----------Bindings----------
-- Stream Deck note: the Elgato Website action silently drops custom URL schemes
-- (hammerspoon://... never arrives, tested with both "Open with" options), but
-- its "GET request in background" mode does a real HTTP GET — so point keys at
-- http://localhost:21212/<action> with Open with: "GET request in background".
hs.hotkey.bind({"ctrl", "shift"}, "l", wl.applyAll)
hs.hotkey.bind({"ctrl", "shift"}, "a", wl.applyHere)
hs.hotkey.bind({"ctrl", "shift"}, "s", function() wl.snapshot() end)
hs.hotkey.bind({"ctrl", "shift"}, "w", function() wl.snapshotApp() end)
hs.hotkey.bind({"ctrl", "shift"}, "e", wl.openEditor)
hs.hotkey.bind({"ctrl", "shift"}, "p", function() wl.fixAssign({ force = true, dock = true }) end)
hs.hotkey.bind({"ctrl", "shift"}, "g", wl.gatherHere)
hs.urlevent.bind("applyLayouts", wl.applyAll)
