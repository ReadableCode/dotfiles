#NoEnv
#Warn
SendMode Input
SetWorkingDir %A_ScriptDir%

; ^ for Ctrl
; ! for Alt
; # for Win
; + for Shift

;----------Go To Selected Sheet ID----------

^+c::
{
 Send, ^c
 Sleep 50
 Run, https://docs.google.com/spreadsheets/d/%clipboard%
 Return
}

;----------Go To Selected GDrive Folder ID----------

^+f::
{
 Send, ^c
 Sleep 50
 Run, https://drive.google.com/drive/folders/%clipboard%
 Return
}
