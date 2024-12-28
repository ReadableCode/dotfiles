# Setup Syncthing

## Install Syncthing

### Install Syncthing on Windows

* To install using winget:
  * Open Powershell as Admin by right clicking on the start menu and selecting "Windows Powershell (Admin)"
  * Verify winget is installed by typing:

  ```bash
  winget --version
  ```

  * If winget is not installed, open microsfot store and update "app installer" and verify with the above command

* Run the following command to install syncthing:

    ```bash
    winget install synctrayzor
    ```

* Enable access from other machines:

  * Right click on SyncTrayzor icon in system tray
  * On the syncthing tab change the GUI Listen Address to:

    ```bash
    0.0.0.0:8384
    ```

### Install Syncthing on Linux

```bash
sudo apt install syncthing
```

* Start and close syncthing.

  ```bash
  syncthing
  # CTRL+C
  ```

* Open Syncthing’s configuration file using nano:

  ```bash
  nvim ~/.config/syncthing/config.xml
  ```

* Find the GUI section similar to this:

  ```xml
  <gui enabled="true" tls="false" debugging="false">
      <address>127.0.0.1:8384</address>
      <apikey></apikey>
      <theme>default</theme>
  </gui>
  ```

* And replace the `127.0.0.1:8384` with `0.0.0.0:8384`
* Now any machine on the local network can access the program.
* Save and Close with `CTRL+X`, `Y`, `ENTER`.
* Run as a service on startup
  * <https://docs.syncthing.net/users/autostart.html#linux>
  * Create the user who should run the service, or choose an existing one.
  * Copy the Syncthing/etc/linux-systemd/system/syncthing@.service file into the load path of the system instance.
  * file was found at
    * <https://github.com/syncthing/syncthing/blob/master/etc/linux-systemd/system/syncthing%40.service>
  * path was found at
    * <https://www.freedesktop.org/software/systemd/man/systemd.unit.html#Unit%20File%20Load%20Path>
  * I did this and it worked, create file below at:

    ```bash
    sudo nvim /etc/systemd/system/syncthing@.service
    ```

    * change file to be:

      ```bash
      [Unit]
      Description=Syncthing - Open Source Continuous File Synchronization for %I
      Documentation=man:syncthing(1)
      After=network.target

      [Service]
      User=%i
      ExecStart=/usr/bin/syncthing -no-browser -no-restart -logflags=0
      Restart=on-failure
      RestartSec=5
      SuccessExitStatus=3 4
      RestartForceExitStatus=3 4

      # Hardening
      ProtectSystem=full
      PrivateTmp=true
      SystemCallArchitectures=native
      MemoryDenyWriteExecute=true
      NoNewPrivileges=true

      [Install]
      WantedBy=multi-user.target
      ```

* Enable and start the service. Replace “myuser” with the actual Syncthing user after the @:  in my case jason or pi

  ```bash
  systemctl enable syncthing@jason.service
  systemctl start syncthing@jason.service
  ```

* Navigate your browser to the computers IP, hostname, or localhost with port 8384. [localhost:8384](localhost:8384)
* Delete default folder sync
* Delete folder it created with:

  ```bash
  rm -r ~/Sync/
  ```

## Configure Syncthing

* Set up ignore and unignore if needed:
  * Important Note: in line comments do not work in .syncignore # like this will ruin the line
  
  * Just non git tracked data in GitHub:
  
      ```bash
      // Switches, change these depending on system
      !**/data/

      // Keep these because they are not committed and are needed on any project
      !**/.env
      !**/hellofres_credentials/
      !**/personal_credentials/
      *
      ```

  * Just Plex Versions Media

      ```bash
      !Plex Versions/**
      *
      ```
