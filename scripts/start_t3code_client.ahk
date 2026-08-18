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
;
; This script used to detect the t3code-server scheduled task and, on that one
; machine, pin the client to port 3774 and T3CODE_HOME=~/.t3-client to keep the
; desktop backend away from the headless server's port and data directory. That
; whole split was retired on 2026-08-17 when RyzenWhite moved to the combo (one
; backend, the desktop app's, on ~/.t3) - see "Combo backend" in
; docs/setup_t3_code.md. There is no longer a second server to avoid, and the
; split was actively harmful: the account session (clerk-tokens.json) and the
; paired-environment catalog (connection-catalog.json) both live in ~/.t3, so
; every launch that took the split branch came up signed out with no
; environments, which read as "signing in with GitHub does not work".

installDir := EnvGet("LOCALAPPDATA") "\Programs\t3code"

; Pin the backend to 3773 rather than letting resolveDesktopBackendPort() scan
; upward from it. The scan would also land on 3773 while it is free, but the
; tailnet path is a `tailscale serve` proxy hardwired to http://127.0.0.1:3773,
; so a silent drift to 3774 (anything else holding the port at logon) would take
; that path down with no error anywhere. Pinning makes the port a stated
; requirement instead of a coincidence. Read by the Electron parent, which
; passes the resolved port to the backend explicitly and strips T3CODE_PORT from
; the child env (DESKTOP_BACKEND_ENV_NAMES).
EnvSet("T3CODE_PORT", "3773")

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
