-- Hammerspoon config — equivalent of sheets.ahk
-- Mac equivalent of AutoHotkey

----------Hotkey Reference----------
-- Update this table whenever you add or remove a binding
local hotkeyRef = {
    {"Ctrl+Shift+C",  "Open selected ID as Google Sheet"},
    {"Ctrl+Shift+F",  "Open selected ID as Google Drive folder"},
    {"Cmd+Shift+V",   "Paste as plain text (strips formatting)"},
    {"Ctrl+Shift+T",  "Open front Finder window in Terminal"},
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
    hs.eventtap.keyStroke({"cmd"}, "c")
    hs.timer.doAfter(0.05, function()
        local id = hs.pasteboard.getContents()
        if id and id ~= "" then
            hs.urlevent.openURL("https://docs.google.com/spreadsheets/d/" .. id:gsub("%s+", ""))
        end
    end)
end)

----------Go To Selected GDrive Folder ID----------
-- Ctrl+Shift+F: copy selection, open as Google Drive folder
hs.hotkey.bind({"ctrl", "shift"}, "f", function()
    hs.eventtap.keyStroke({"cmd"}, "c")
    hs.timer.doAfter(0.05, function()
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
