#Requires AutoHotkey v2.0
; Win+Alt+1..9 → switch to Desktop 1..9

dllPath := A_ScriptDir "\VirtualDesktopAccessor.dll"
url     := "https://github.com/Ciantic/VirtualDesktopAccessor/releases/latest/download/VirtualDesktopAccessor.dll"

; Download DLL if missing
if !FileExist(dllPath) {
    RunWait('"' A_WinDir '\System32\curl.exe" -fL --retry 3 -o "' dllPath '" "' url '"', , 'Hide')
    if !FileExist(dllPath) || FileGetSize(dllPath) < 10240 {
        MsgBox "Download failed or file invalid."
        ExitApp
    }
}

; Load DLL
hMod := DllCall("LoadLibrary", "str", dllPath, "ptr")
if !hMod {
    MsgBox "LoadLibrary failed (check 64-bit AHK vs 64-bit DLL)."
    ExitApp
}

; Find exported function name
exportName := ""
if DllCall("GetProcAddress","ptr",hMod,"astr","SwitchDesktopByNumber","ptr")
    exportName := "SwitchDesktopByNumber"
else if DllCall("GetProcAddress","ptr",hMod,"astr","GoToDesktopNumber","ptr")
    exportName := "GoToDesktopNumber"
else if DllCall("GetProcAddress","ptr",hMod,"astr","SwitchDesktopToNumber","ptr")
    exportName := "SwitchDesktopToNumber"

if exportName = "" {
    MsgBox "No supported export found in VirtualDesktopAccessor.dll."
    ExitApp
}

switchDesktop(n) => DllCall(dllPath "\" exportName, "int", n-1, "int", 0, "cdecl")

#!1::switchDesktop(1)
#!2::switchDesktop(2)
#!3::switchDesktop(3)
#!4::switchDesktop(4)
#!5::switchDesktop(5)
#!6::switchDesktop(6)
#!7::switchDesktop(7)
#!8::switchDesktop(8)
#!9::switchDesktop(9)

