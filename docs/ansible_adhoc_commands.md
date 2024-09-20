# Using Adhoc Commands in Ansible

- ping windows

    ```bash
    ansible -i ./inventory/hosts_personal windows_workstations -m win_ping --user jason
    ```

- ping raspbian

    ```bash
    ansible -i ./inventory/hosts_personal raspbian -m ping
    ```
