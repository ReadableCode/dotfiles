@echo off
rem Portable sshd cannot set the HKLM DefaultShell registry value (needs
rem admin), so it spawns cmd.exe for every session. sshd_config points
rem ForceCommand at this wrapper instead: interactive logins get PowerShell,
rem while exec requests (ssh host <cmd>, scp, rsync, VS Code Remote-SSH, the
rem sftp subsystem) land in SSH_ORIGINAL_COMMAND and are run through cmd /c
rem exactly as the default shell would have run them.
if defined SSH_ORIGINAL_COMMAND (
  cmd.exe /c %SSH_ORIGINAL_COMMAND%
) else (
  C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -NoLogo
)
exit /b %ERRORLEVEL%
