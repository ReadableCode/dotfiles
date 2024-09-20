# Using Playbooks in Ansible

- install_all_apps

    ```bash
    ansible-playbook ansible_playbooks/install_all_apps.yml --ask-become-pass -i ./inventory/hosts
    ```

- install_windows_apps

    ```bash
    ansible-playbook ansible_playbooks/install_windows_apps.yml --ask-become-pass -i ./inventory/hosts
    ```

- install_linux_apps

    ```bash
    ansible-playbook ansible_playbooks/install_linux_apps.yml --ask-become-pass -i ./inventory/hosts
    ```

- install_mac_apps

    ```bash
    ansible-playbook ansible_playbooks/install_mac_apps.yml --ask-become-pass -i ./inventory/hosts
    ```

- pip_modules

    ```bash
    ansible-playbook ansible_playbooks/pip_modules.yml --ask-become-pass -i ./inventory/hosts
    ```

- ping_all_hosts

    ```bash
    ansible-playbook ansible_playbooks/ping_all_hosts.yml -i ./inventory/hosts
    ```

    ```bash
    ansible-playbook ansible_playbooks/ping_all_hosts.yml -i ./inventory/hosts --limit linux_workstations
    ```

    ```bash
    ansible-playbook ansible_playbooks/ping_all_hosts.yml -i ./inventory/hosts --limit windows_workstations:linux_workstations:raspbian:macs:rebeca_windows:unraid
    ```
