# Using Adhoc Commands in Ansible

- ping windows

    ```bash
    ansible -i ./inventory/hosts windows_workstations -m win_ping --user jason
    ```

- ping raspbian

    ```bash
    ansible -i ./inventory/hosts raspbian -m ping
    ```
