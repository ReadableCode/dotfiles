@echo off
rem T3 Code headless server launcher. Deployed by src/deploy_configs.py
rem (entry t3code_server_launcher) to %USERPROFILE%\.t3\t3serve.cmd, which is
rem the path the t3code-server scheduled task executes - so editing this file
rem changes how the server runs on the next start, and `deploy_configs.py
rem status` reports it when something replaces the link.
rem
rem The restart loop IS the service. Windows has no `t3 service install`
rem ("unavailable on this machine - supported on: Linux with systemd"), and a
rem bare `t3 serve` action leaves the box serverless the moment the process
rem dies: on RyzenWhite the server leaked to V8's 4 GB heap cap and aborted
rem after 3 days (2026-08-17 00:36, "FATAL ERROR: Ineffective mark-compacts
rem near heap limit"), and with only boot/logon triggers nothing brought it
rem back. The loop recovers in seconds; the task's 15-minute watchdog trigger
rem covers the case where the loop itself dies.
rem
rem Serve options live here on purpose - scripts/setup_t3_server_windows.ps1
rem reads T3_PORT and the --tailscale-serve flag back out of this file rather
rem than taking them as parameters, so there is one source of truth. A machine
rem that needs different ones gets a t3serve.<host>.cmd variant next to this
rem file (deploy resolves hostname before the bare default).
rem The loop's own lines go to t3serve.log, NOT to the server.log the serve
rem writes: only one of these wrappers runs at a time, so its log can never be
rem locked out, while server.log can be (see the kill below).
setlocal
set "T3_CMD=%APPDATA%\npm\t3.cmd"
set "T3_LOG=%USERPROFILE%\.t3\server.log"
set "T3_WRAP_LOG=%USERPROFILE%\.t3\t3serve.log"
set "T3_PORT=3773"

:serve
rem Clear a leftover server first, and note there is NO redirect on the kill.
rem Stopping the task kills this wrapper but leaves the node it called running
rem (Task Scheduler does not take the grandchild with it), and that orphan
rem holds the port AND an exclusive append handle on %T3_LOG%. cmd silently
rem SKIPS any command whose redirect fails, so a kill written as
rem `taskkill ... >>"%T3_LOG%"` would be skipped by the very condition it
rem exists to clear, and this loop would spin forever with no server and no
rem output - which is exactly what it did on 2026-08-17 14:15. Only node.exe
rem is killed, so a desktop-app server on the same port is left alone.
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":%T3_PORT% " ^| findstr LISTENING') do (
    for /f "tokens=1" %%n in ('tasklist /nh /fi "pid eq %%p"') do (
        if /i "%%n"=="node.exe" (
            taskkill /f /t /pid %%p
            echo [%DATE% %TIME%] t3serve: killed leftover node %%p holding port %T3_PORT%>>"%T3_WRAP_LOG%"
        )
    )
)
echo [%DATE% %TIME%] t3serve: starting t3 serve>>"%T3_WRAP_LOG%"
call "%T3_CMD%" serve --port %T3_PORT% --tailscale-serve >>"%T3_LOG%" 2>&1
echo [%DATE% %TIME%] t3serve: t3 serve exited (code %ERRORLEVEL%), restarting in 15s>>"%T3_WRAP_LOG%"
rem `timeout` needs a console handle the scheduled task has not got ("ERROR:
rem Input redirection is not supported"), so ping is the sleep here.
ping -n 16 127.0.0.1 >nul
goto serve
