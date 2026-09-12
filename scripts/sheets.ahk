#Requires AutoHotkey v2.0
#SingleInstance Force

SendMode "Input"
SetWorkingDir A_ScriptDir

; ^ for Ctrl
; ! for Alt
; # for Win
; + for Shift

; Copy the selection, then open it as a Google Docs id. ClipWait waits for the
; copy to actually land rather than sleeping a fixed interval, and the function
; does nothing at all when the copy produced no text; without that check it
; would open the URL with the PREVIOUS clipboard contents.
OpenCopiedId(urlPrefix) {
    A_Clipboard := ""
    Send "^c"
    if !ClipWait(1)
        return
    id := Trim(A_Clipboard)
    if id != ""
        Run urlPrefix . id
}

;----------Go To Selected Sheet ID----------

^+c:: OpenCopiedId("https://docs.google.com/spreadsheets/d/")

;----------Go To Selected GDrive Folder ID----------

^+f:: OpenCopiedId("https://drive.google.com/drive/folders/")
