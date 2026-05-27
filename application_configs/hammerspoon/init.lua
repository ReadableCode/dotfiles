-- Hammerspoon config — equivalent of sheets.ahk
-- Mac equivalent of AutoHotkey

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
