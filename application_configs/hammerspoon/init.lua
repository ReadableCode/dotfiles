-- Hammerspoon config — equivalent of sheets.ahk
-- Mac equivalent of AutoHotkey

----------Hotkey Reference----------
-- Update this table whenever you add or remove a binding
local hotkeyRef = {
    {"Ctrl+Shift+C",  "Open selected ID as Google Sheet"},
    {"Ctrl+Shift+F",  "Open selected ID as Google Drive folder"},
    {"Cmd+Shift+V",   "Paste as plain text (strips formatting)"},
    {"Ctrl+Shift+T",  "Open front Finder window in Terminal"},
    {"Ctrl+Shift+L",  "Load a saved window layout (asks for space #)"},
    {"Ctrl+Shift+S",  "Save current space's windows (asks for space #)"},
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
-- Spaces: Mission Control space IDs aren't stable and can't be reliably
-- detected, so layouts are stored PER SPACE under a number you type. You run
-- the hotkey once on each space and tell it which space you're on.
--
-- Layouts live in `window_layouts.json` (NOT in this file). Because init.lua is
-- symlinked into ~/.hammerspoon from the dotfiles repo, we follow that symlink
-- and write the JSON next to the real init.lua, so it can be committed.
--
-- Usage:
--   Save: go to a space, arrange its windows, press Ctrl+Shift+S, type the
--         space number. Repeat on each space. Commit window_layouts.json.
--   Load: go to a space, press Ctrl+Shift+L, type the same number. Repeat on
--         each space (e.g. after a KVM switch) to snap everything back.
local wl = {}

-- Where to read/write the saved layouts. Follows the init.lua symlink so the
-- file lands in the dotfiles repo (committable), not in ~/.hammerspoon.
function wl.file()
    if wl._file then return wl._file end
    local dir = hs.configdir .. "/"
    local target = hs.execute("readlink '" .. hs.configdir .. "/init.lua' 2>/dev/null")
    target = (target or ""):gsub("%s+$", "")
    if target ~= "" then
        dir = target:match("^(.*/)") or dir
    end
    wl._file = dir .. "window_layouts.json"
    return wl._file
end

function wl.loadAll()
    if hs.fs.attributes(wl.file()) then
        local data = hs.json.read(wl.file())
        if type(data) == "table" then return data end
    end
    return {}
end

function wl.saveAll(all)
    return hs.json.write(all, wl.file(), true, true)
end

-- Ask which space this is. Returns a string key (digits) or nil if cancelled.
function wl.askSpace(action)
    local btn, txt = hs.dialog.textPrompt(
        "Window layout — " .. action,
        "Which space number is this? (run once per space)",
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
end

local function round(n) return math.floor(n * 1000 + 0.5) / 1000 end

-- Save the windows on the CURRENT space under the given number, then write the
-- whole file back (preserving the other spaces' saved layouts).
function wl.snapshot()
    local key = wl.askSpace("save")
    if not key then return end
    local layout = {}
    for _, win in ipairs(hs.window.orderedWindows()) do
        if win:isStandard() then
            local s = win:screen()
            local f, wf = s:frame(), win:frame()
            table.insert(layout, {
                app = win:application():name(),
                screen = (f.h > f.w) and "portrait" or "landscape",
                unit = {
                    x = round((wf.x - f.x) / f.w),
                    y = round((wf.y - f.y) / f.h),
                    w = round(wf.w / f.w),
                    h = round(wf.h / f.h),
                },
            })
        end
    end
    local all = wl.loadAll()
    all[key] = layout
    if wl.saveAll(all) then
        hs.alert.show(string.format("Saved %d windows for space %s", #layout, key))
    else
        hs.alert.show("Failed to write " .. wl.file())
    end
end

-- Apply a saved space's layout to whatever of its apps are running now.
function wl.apply(key)
    local layout = wl.loadAll()[key]
    if type(layout) ~= "table" then
        hs.alert.show("No saved layout for space " .. tostring(key))
        return
    end
    local placed = 0
    for _, item in ipairs(layout) do
        local app = hs.application.get(item.app)
        local win = app and app:mainWindow()
        if win then
            placeWindow(win, item.screen, item.unit)
            placed = placed + 1
        end
    end
    hs.alert.show(string.format("Applied space %s (%d windows)", key, placed))
end

hs.hotkey.bind({"ctrl", "shift"}, "l", function()
    local key = wl.askSpace("load")
    if key then wl.apply(key) end
end)
hs.hotkey.bind({"ctrl", "shift"}, "s", wl.snapshot)
