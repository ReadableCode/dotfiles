#Requires AutoHotkey v2.0
#SingleInstance Force

SendMode "Input"
SetWorkingDir A_ScriptDir

; ^ for Ctrl
; ! for Alt
; # for Win
; + for Shift

; Copy the selection, then open it as a Google Docs id. The v1 original slept
; 50 ms and used whatever was on the clipboard by then; ClipWait waits for the
; copy to actually land instead, and does nothing at all if the copy produced
; no text (which used to open the URL with the PREVIOUS clipboard contents).
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
