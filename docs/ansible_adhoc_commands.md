# Using Adhoc Commands in Ansible

- ping windows

    ```bash
    ansible -i ./inventory/hosts windows_workstations -m win_ping --user jason
    ```

- ping raspbian

    ```bash
    ansible -i ./inventory/hosts raspbian -m ping
    ```

- cat a file

    ```bash
    ansible -i ./inventory/hosts raspbian -a 'cat /home/pi/GitHub/st_ignore_include_data.txt'
    ```
