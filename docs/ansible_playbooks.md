# Using Playbooks in Ansible

- install_all_apps_personal

    ```bash
    ansible-playbook ansible_playbooks/install_all_apps_personal.yml --ask-become-pass -i ./inventory/hosts_personal
    ```

- install_windows_apps_personal

    ```bash
    ansible-playbook ansible_playbooks/install_windows_apps_personal.yml --ask-become-pass -i ./inventory/hosts_personal
    ```

- install_linux_apps_personal

    ```bash
    ansible-playbook ansible_playbooks/install_linux_apps_personal.yml --ask-become-pass -i ./inventory/hosts_personal
    ```

- install_mac_apps_personal

    ```bash
    ansible-playbook ansible_playbooks/install_mac_apps_personal.yml --ask-become-pass -i ./inventory/hosts_personal
    ```

- pip_modules

    ```bash
    ansible-playbook ansible_playbooks/pip_modules.yml --ask-become-pass -i ./inventory/hosts_personal
    ```

- ping_all_hosts_personal

    ```bash
    ansible-playbook ansible_playbooks/ping_all_hosts_personal.yml -i ./inventory/hosts_personal
    ```

    ```bash
    ansible-playbook ansible_playbooks/ping_all_hosts_personal.yml -i ./inventory/hosts_personal --limit linux_workstations
    ```

    ```bash
    ansible-playbook ansible_playbooks/ping_all_hosts_personal.yml -i ./inventory/hosts_personal --limit windows_workstations:linux_workstations:raspbian:macs:rebeca_windows:unraid
    ```
