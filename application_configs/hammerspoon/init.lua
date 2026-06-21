-- Hammerspoon config — equivalent of sheets.ahk
-- Mac equivalent of AutoHotkey

----------Hotkey Reference----------
-- Update this table whenever you add or remove a binding
local hotkeyRef = {
    {"Ctrl+Shift+C",  "Open selected ID as Google Sheet"},
    {"Ctrl+Shift+F",  "Open selected ID as Google Drive folder"},
    {"Cmd+Shift+V",   "Paste as plain text (strips formatting)"},
    {"Ctrl+Shift+T",  "Open front Finder window in Terminal"},
    {"Ctrl+Shift+L",  "Apply saved window layout (KVM fix)"},
    {"Ctrl+Shift+S",  "Snapshot windows -> layout code in console"},
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

----------Window Layouts (KVM monitor-shuffle fix)----------
-- Problem: switching the KVM re-enumerates displays, so macOS dumps every
-- window onto one screen. Display IDs/UUIDs are NOT stable across the switch,
-- so we anchor layouts on screen ORIENTATION (portrait vs landscape) instead.
-- One monitor is vertical, so "the portrait screen" is unambiguous and survives
-- the KVM flip.
--
-- Usage:
--   1. Arrange your windows the way you want them.
--   2. Press Ctrl+Shift+S -> a layout block is printed to the Hammerspoon
--      console (it auto-opens). Copy it.
--   3. Paste it into `wl.layouts.default` below, then commit init.lua.
--   4. After any KVM switch, press Ctrl+Shift+L to snap everything back.
local wl = {}

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
local function placeWindow(win, orientation, unit, spaceIndex)
    local screen = wl.screenFor(orientation)
    if not (win and screen) then return end
    local f = screen:frame()
    -- Optional, best-effort: move to a Mission Control desktop by index first.
    -- Space IDs aren't stable, so we address by position (1 = leftmost).
    if spaceIndex and hs.spaces then
        local ok, spaces = pcall(hs.spaces.spacesForScreen, screen:getUUID())
        if ok and spaces and spaces[spaceIndex] then
            pcall(hs.spaces.moveWindowToSpace, win:id(), spaces[spaceIndex])
        end
    end
    win:setFrame({
        x = f.x + unit.x * f.w,
        y = f.y + unit.y * f.h,
        w = unit.w * f.w,
        h = unit.h * f.h,
    })
end

-- Saved layouts. Each entry targets one app's main window.
-- screen = "landscape" | "portrait"; space is optional (1-based desktop index).
-- Replace the example with the output of Ctrl+Shift+S.
wl.layouts = {
    default = {
    {app = "Code", screen = "landscape", unit = {x=0.000, y=0.000, w=1.000, h=1.000}, space = 1},
    {app = "Google Chrome", screen = "landscape", unit = {x=0.163, y=0.121, w=0.603, h=0.700}, space = 1},
    {app = "YouTube", screen = "portrait", unit = {x=0.001, y=0.000, w=1.000, h=0.367}, space = 2},
    {app = "Claude", screen = "portrait", unit = {x=0.440, y=0.355, w=0.559, h=0.369}, space = 1},
    {app = "Messages", screen = "portrait", unit = {x=0.000, y=0.355, w=0.474, h=0.369}, space = 1},
    {app = "Messenger", screen = "portrait", unit = {x=0.000, y=0.724, w=0.430, h=0.276}, space = 1},
    {app = "eufyMake Studio 3D", screen = "landscape", unit = {x=0.000, y=0.000, w=1.000, h=1.000}, space = 1},
    {app = "Finder", screen = "landscape", unit = {x=0.062, y=0.235, w=0.412, h=0.527}, space = 1},
    {app = "Tailscale", screen = "landscape", unit = {x=0.034, y=0.350, w=0.333, h=0.481}, space = 1},
    {app = "Bitwarden", screen = "landscape", unit = {x=0.280, y=0.433, w=0.584, h=0.469}, space = 2},
    {app = "Weather", screen = "landscape", unit = {x=0.142, y=0.177, w=0.562, h=0.661}, space = 1},
    {app = "Personal Calendar", screen = "landscape", unit = {x=0.889, y=0.302, w=0.419, h=0.474}, space = 1},
    {app = "Mail", screen = "landscape", unit = {x=0.152, y=0.254, w=0.713, h=0.662}, space = 2},
    {app = "Terminal", screen = "landscape", unit = {x=0.192, y=0.275, w=0.469, h=0.467}, space = 2},
    {app = "Reminders", screen = "landscape", unit = {x=0.285, y=0.145, w=0.501, h=0.708}, space = 1},
    {app = "Calendar", screen = "landscape", unit = {x=0.125, y=0.416, w=0.562, h=0.491}, space = 1},
},
}

function wl.apply(layout)
    for _, item in ipairs(layout) do
        local app = hs.application.get(item.app)
        local win = app and app:mainWindow()
        if win then
            placeWindow(win, item.screen, item.unit, item.space)
        end
    end
    hs.alert.show("Applied window layout")
end

-- Print the current window arrangement as a paste-ready layout block.
function wl.snapshot()
    local out = {"wl.layouts.default = {"}
    for _, win in ipairs(hs.window.orderedWindows()) do
        if win:isStandard() then
            local s = win:screen()
            local f, wf = s:frame(), win:frame()
            local orientation = (f.h > f.w) and "portrait" or "landscape"
            local spacePart = ""
            if hs.spaces then
                local wins = hs.spaces.windowSpaces and hs.spaces.windowSpaces(win:id())
                local screenSpaces = select(2, pcall(hs.spaces.spacesForScreen, s:getUUID()))
                if wins and wins[1] and type(screenSpaces) == "table" then
                    for idx, sid in ipairs(screenSpaces) do
                        if sid == wins[1] then spacePart = string.format(", space = %d", idx) end
                    end
                end
            end
            table.insert(out, string.format(
                '    {app = %q, screen = %q, unit = {x=%.3f, y=%.3f, w=%.3f, h=%.3f}%s},',
                win:application():name(), orientation,
                (wf.x - f.x) / f.w, (wf.y - f.y) / f.h, wf.w / f.w, wf.h / f.h,
                spacePart))
        end
    end
    table.insert(out, "}")
    print(table.concat(out, "\n"))
    hs.openConsole()
    hs.alert.show("Window layout printed to console — copy it into init.lua")
end

hs.hotkey.bind({"ctrl", "shift"}, "l", function() wl.apply(wl.layouts.default) end)
hs.hotkey.bind({"ctrl", "shift"}, "s", wl.snapshot)
