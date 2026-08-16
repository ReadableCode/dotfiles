#Requires AutoHotkey v2.0
#SingleInstance Force

; Ctrl+Alt+C — jump to VS Code, launching it if it is not already running.
^!c:: {
    if WinExist("ahk_exe Code.exe")
        WinActivate          ; the window WinExist just found
    else
        Run "C:\Program Files\Microsoft VS Code\Code.exe"
}
