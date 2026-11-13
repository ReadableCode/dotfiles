
# Setting Up SSH Server

* open elevated powershell window
* run commands:
  
  ```bash
  winget install --id Microsoft.OpenSSH.Preview --exact
  ```

  This is the Win32-OpenSSH release in `C:\Program Files\OpenSSH`, and it is
  on the winget list of `app_lists/base_app_lists.yaml`, so `myupdater` offers
  it too. Do not also add the Windows "OpenSSH Server" optional feature: that
  is an older in-box build in `System32\OpenSSH`, and `app_removals.yaml`
  retires it on any machine where this package is installed. Removing that
  feature deletes the `sshd` service this package uses, so the removal runs
  `scripts/repair_sshd.ps1` straight after; if ssh is ever down with the
  package installed, run that script from an elevated console.

  * if not using bootstrap script:
  
    ```bash
    winget install -e --id Notepad++.Notepad++
    ```

* run command:

  ```bash
  New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
  ```
  
* run command:

  ```bash
  Set-Service sshd -StartupType Automatic
  ```
  
* run command:
  
  ```bash
  net start sshd
  ```
  
  * (might say already started, thats OK)
* get rsa.pub from the controlling machine using this command executed on it:

  ```bash
  cat ~/.ssh/id_rsa.pub
  ```

* make directory if doesnt exist: "$env:USERPROFILE\\.ssh\" by running this:

  ```bash
  if (!(Test-Path -Path "$env:USERPROFILE\.ssh\")) { New-Item -ItemType Directory -Path "$env:USERPROFILE\.ssh\" }
  ```
  
* Pick one of the following to get ssh pub key onto new windows client:
  * Using admin powershell on remote machine or some ssh connection already set up (password pased or from machine with key already set up) NOTE: both of these fail to add a newline at the end of the line
  
    ```bash
    Add-Content -Path "$env:USERPROFILE\.ssh\authorized_keys" -Value "CONTENTS_OF_ID_RSA_PUB"
    Add-Content -Path "C:\ProgramData\ssh\administrators_authorized_keys" -Value "CONTENTS_OF_ID_RSA_PUB"
    ```

  * Using notepad++ on the client:
  
    ```bash
    Start-Process "notepad++.exe" "$env:USERPROFILE\.ssh\authorized_keys"
    Start-Process "notepad++.exe" "C:\ProgramData\ssh\administrators_authorized_keys" -Verb "runas"
    ```

  * Using admin powershell on remote machine or some ssh connection already set up (password pased or from machine with key already set up)(might replace existing file):

    ```bash
    echo "CONTENTS_OF_ID_RSA_PUB" | Out-File -FilePath "$env:USERPROFILE\.ssh\authorized_keys" -Encoding ASCII -Force
    echo "CONTENTS_OF_ID_RSA_PUB" | Out-File -FilePath "C:\ProgramData\ssh\administrators_authorized_keys" -Encoding ASCII -Force
    ```

* Change persmissions for the administrators_authorized_keys file:

  ```bash
  icacls C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r
  icacls C:\ProgramData\ssh\administrators_authorized_keys /grant SYSTEM:`(F`)
  icacls C:\ProgramData\ssh\administrators_authorized_keys /grant BUILTIN\Administrators:`(F`)
  ```
  
* Change settings in sshd_config file:

  ```bash
  Start-Process "notepad++.exe" "C:\ProgramData\ssh\sshd_config" -Verb "runas"
  ```
  
  * Uncomment and change the following lines, adding if they dont exist:

    ```bash
    StrictModes no
    PubkeyAuthentication yes
    ```

  * Key-only logins on portable machines (UltraPocket, Yoga7i): once a
    key login from every machine that needs one works (passwords stop
    working after this), run this in admin PowerShell. It adds
    `PasswordAuthentication no` and `KbdInteractiveAuthentication no` ABOVE
    the `Match Group administrators` block (anything below a `Match` applies
    only inside it) unless they are already there, validates the config and
    restarts sshd only if it passes, so a bad edit cannot lock you out:

    ```powershell
    $f = 'C:\ProgramData\ssh\sshd_config'; $lines = Get-Content $f; if (-not ($lines -match '^\s*PasswordAuthentication\s+no')) { $i = [array]::FindIndex($lines, [Predicate[string]]{ param($l) $l -match '^\s*Match\s' }); if ($i -lt 0) { $i = $lines.Count }; $new = @($lines[0..($i-1)]) + 'PasswordAuthentication no' + 'KbdInteractiveAuthentication no' + @($lines[$i..($lines.Count-1)] | Where-Object { $_ -ne $null }); Set-Content -Path $f -Value $new -Encoding ascii }; & 'C:\Program Files\OpenSSH\sshd.exe' -t -f $f; if ($?) { Restart-Service sshd; 'restarted' }
    ```

    Confirm from another machine that a key login still works and that
    `ssh -o PubkeyAuthentication=no jason@<host>` is refused with
    `Permission denied (publickey)`.

* Run these commands in admin powershell to set the default shell to powershell:

  ```bash
  New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -PropertyType String -Force
  New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShellCommandOption -Value "/c" -PropertyType String -Force
  ```
  
* Run these commands in admin powershell to restart ssh-server and apply changes:

  ```bash
  net stop sshd
  net start sshd
  ```

## Troubleshooting: key auth keeps falling back to a password

* **For Administrator accounts, sshd IGNORES `~/.ssh/authorized_keys`.** The
  default `sshd_config` has a `Match Group administrators` block pointing
  `AuthorizedKeysFile` at `C:\ProgramData\ssh\administrators_authorized_keys`.
  So if your user is an admin (typical on a personal PC), the key MUST be in
  that file — the per-user file does nothing.
* **`ssh-copy-id` puts the key in the wrong place.** It appends to
  `~/.ssh/authorized_keys` (the ignored file), so auth still fails and falls
  back to password. Fix: copy the key into the admin file and lock its perms,
  then restart sshd.

  ```bash
  Copy-Item C:\Users\<you>\.ssh\authorized_keys C:\ProgramData\ssh\administrators_authorized_keys -Force
  icacls C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r
  icacls C:\ProgramData\ssh\administrators_authorized_keys /grant "SYSTEM:F" "BUILTIN\Administrators:F"
  Restart-Service sshd
  ```

* **`StrictModes` / permissions.** If the home dir, `.ssh`, or the keys file is
  group-writable or has loose ACLs, sshd silently refuses the key. Either set
  `StrictModes no` in `sshd_config` (done above) or fix the ACLs.
* **Old RSA (SHA-1) keys.** A legacy `ssh-rsa AAAAB3…` key may be rejected by
  newer SSH servers. Test from the client with
  `ssh -o PubkeyAcceptedAlgorithms=+ssh-rsa <host> hostname`; if that works,
  either add `PubkeyAcceptedAlgorithms +ssh-rsa` server-side or switch to an
  `ed25519` key.
* Diagnose offered/accepted keys from the client with `ssh -v <host> hostname`.

## Entra ID (Azure AD) accounts: key login for the machine's own user

A work laptop joined to Entra ID has no on-prem domain: the account is
`azuread\<name>` (`whoami`), and `nltest /dsgetdc:` answers
`ERROR_NO_SUCH_DOMAIN`. Win32-OpenSSH running as the SYSTEM service cannot
serve that account with a key, and fails in three places, each one a bare
"Connection reset" on the client with nothing in the OpenSSH log:

* Any `DOMAIN\name` login whose domain does not exist (an old on-prem name in
  the inventory or in `AllowUsers`) crashes the session process.
* `Match Group administrators` crashes while looking up the Entra ID
  account's groups. Drop the block and set
  `AuthorizedKeysFile __PROGRAMDATA__/ssh/administrators_authorized_keys`
  globally; with `AllowUsers azuread\<name>` the machine admits only that
  user anyway.
* After the key is accepted (`Authenticated ... using "publickey"` in
  `ssh -v`), the service cannot start a session for the account without its
  password, and resets again.

The working setup runs the same `sshd.exe`, config and host keys as the user
instead of as SYSTEM: a scheduled task, "sshd as me", starts it at logon with
highest privileges, and the sshd service stays stopped and Disabled so port
22 is free. Checked on 9.4 and 10.4: 10.4 as the service still accepts the
key and then drops the session.

The host's inventory entry asks for it, and myupdater makes it true:

```json
"updater": {"windows": {"sshd_as_user": true}}
```

`scripts/my_updater.ps1` registers the task, stops and disables the service
and starts the task, after the package upgrades. That order matters: every
OpenSSH Preview upgrade (winget) sets the service back to Automatic and
starts it, which stops the task's sshd, so the same myupdater run puts it
back and OpenSSH stays current with no manual step. A myupdater run over
SSH survives the upgrade: the session process outlives the sshd it came from.

OpenSSH 10.x's installer also opts `sshd.exe` into RedirectionGuard (its
`Image File Execution Options\sshd.exe` `MitigationOptions` value, bit 0x10 of
byte 18), and every process an SSH session starts inherits it: none can follow
a symlink or junction a non-elevated user made, which is every link the
deploy makes, so `uv` and myupdater fail over SSH with error 448 ("untrusted
mount point"). `sshd_as_user` clears that bit after each upgrade and restarts
the task's sshd. That reopens the local link-planting attack on the sshd
process tree, accepted for a single-user, key-only machine. A process started
on the desktop (a T3 thread, a console) never had the guard.

SSH is then up whenever the user is logged in, with the key and no second
account, and the session is elevated. Each SSH session opens a console window
on the user's desktop, since sshd runs in that session. The inventory's
`user` is `azuread\<name>`; `src/ssh_aliases.py` quotes it so the backslash
survives the shell. Undo: drop the key, then `Set-Service sshd -StartupType
Automatic`, start it, and `Unregister-ScheduledTask 'sshd as me'`.

To find where sshd dies, run it in the foreground as the user for one login
(`Stop-Service sshd`, then `sshd.exe -ddd -E <log>` from admin PowerShell), or
add `SyslogFacility LOCAL0` and `LogLevel DEBUG3` to the service config, which
writes `C:\ProgramData\ssh\logs\sshd.log`.

## Setting up portable SSH server on Windows (no admin)

* Download portable openssh from:

  ```bash
  https://github.com/PowerShell/Win32-OpenSSH/releases
  ```

* Extract to folder like: %USERPROFILE%\userapps\OpenSSH-Win64

* Generate keys and config in a user folder:

```bash
$portableSshd = "$env:USERPROFILE\GitHub\dotfiles\application_configs\portable_sshd"
cd $env:USERPROFILE\userapps\OpenSSH-Win64
mkdir $portableSshd -ea SilentlyContinue
# -N '""' is how you pass an empty passphrase and still let PowerShell expand
# the paths; the older `--%` form stops expansion for the rest of the line.
.\ssh-keygen.exe -t rsa -b 2048 -f "$portableSshd\ssh_host_rsa_key" -N '""'
New-Item -ItemType File -Path "$portableSshd\authorized_keys" -Force | Out-Null
icacls "$portableSshd\authorized_keys" /inheritance:r /grant "$($env:USERNAME):(OI)(CI)F"
icacls "$portableSshd\authorized_keys" /inheritance:r /grant "$($env:USERNAME):F"
```

* Create config file in same folder (portable_sshd). Paths here are literal —
  no `~` and no `$env:` expansion. The one exception is `AuthorizedKeysFile`,
  which expands `%h` to the user's home directory.

* file name will be:

`sshd_config`

```bash
Port 2222
HostKey C:/Users/<you>/GitHub/dotfiles/application_configs/portable_sshd/ssh_host_rsa_key
PubkeyAuthentication yes
PasswordAuthentication yes
AuthorizedKeysFile %h/GitHub/dotfiles/application_configs/portable_sshd/authorized_keys
Subsystem sftp C:/Users/<you>/userapps/OpenSSH-Win64/sftp-server.exe
ForceCommand cmd.exe /c C:\Users\<you>\GitHub\dotfiles\application_configs\portable_sshd\shell_wrapper.cmd
```

* Default shell: without admin the HKLM `DefaultShell` registry value can't
  be set, so sshd would drop interactive logins into `cmd.exe`. The
  `ForceCommand` line points at `shell_wrapper.cmd` (kept in the same
  `portable_sshd` folder), which starts PowerShell for interactive logins and
  passes exec requests (`ssh host <cmd>`, scp, rsync, sftp, VS Code
  Remote-SSH) through `cmd /c` unchanged — the same way the default shell ran
  them. The command must start with `cmd.exe /c`: pty sessions CreateProcess
  the forced command directly, with no shell, and cannot execute a bare `.cmd`
  file. Restart sshd after changing the config or wrapper, and validate first
  with `.\sshd.exe -t -f <config>`.

* Generate keys on other machine, deploy to authorized_keys file

* Launch sshd

```bash
cd $env:USERPROFILE\userapps\OpenSSH-Win64
.\sshd.exe -f "$env:USERPROFILE/GitHub/dotfiles/application_configs/portable_sshd/sshd_config" -D -E "$env:USERPROFILE/.portable-sshd.log"
# to check running
netstat -ano | findstr :2222
```

* Connect to it from the host machine

```bash
ssh -p 2222 <you>@<laptop-ip>
```

## Running commands non-interactively (PowerShell default shell)

The personal Windows machines run OpenSSH Server with PowerShell as the
default shell and the profile dot-sourcing `powershell_aliases.ps1`.

- Nested quoting through `ssh host "powershell -Command ..."` mangles `$`
  expansion, embedded quotes and paths with spaces. Reliable form: build the
  script, base64-encode it as UTF-16LE
  (`python3 -c "import base64,sys; print(base64.b64encode(sys.stdin.read().encode('utf-16-le')).decode())"`),
  and run `ssh host "powershell -NoProfile -EncodedCommand <b64>"`. The
  command line caps around 32k characters.
- Windows PowerShell 5.1 has no `&&` or `||`, and `&` is its call operator,
  not a separator: chain commands with `;`, or `; if ($?) { ... }` to stop on
  a failure.
- `-NoProfile` leaves the shell functions and aliases undefined. To use one
  (`gitpullall`, an ssh alias), run it bare: `ssh host "gitpullall"`.
- The profile's "Sourced:" banner is guarded to interactive sessions. An
  unguarded banner lands in the binary stream and breaks scp and sftp with
  "Received message too long"; if that error reappears, suspect a profile
  printing on a non-interactive shell, not the network.
- Output still carries `#< CLIXML` and a trailing `<Objs ...>` progress blob;
  filter them, they are noise.
