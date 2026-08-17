#Requires AutoHotkey v2.0
#SingleInstance Force

; Start the T3 Code desktop client at logon. Deployed into the Startup folder
; by src/deploy_configs.py (entry t3code_client_startup) exactly like the other
; .ahk files here - a symlinked file in that folder is the one Windows autostart
; the manifest can own. The app's own "open at login" toggle writes an
; HKCU\Software\Microsoft\Windows\CurrentVersion\Run value instead: nothing in
; the repo, nothing `deploy_configs.py status` can see, and it was simply never
; on (RyzenWhite had no T3 entry in Run or Startup at all, 2026-08-17).
;
; Exits without doing anything when T3 Code is not installed or is already
; running, so the entry is safe on every personal Windows machine.

installDir := EnvGet("LOCALAPPDATA") "\Programs\t3code"

Loop Files installDir "\*.exe"
{
    ; "T3 Code (Alpha).exe" today, and the uninstaller sits next to it - match
    ; by exclusion so the rename that drops "(Alpha)" doesn't break this
    if InStr(A_LoopFileName, "Uninstall")
        continue
    if !ProcessExist(A_LoopFileName)
        Run('"' A_LoopFileFullPath '"')
    break
}
