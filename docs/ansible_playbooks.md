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

- collect_crontabs

    Snapshots `crontab -l` from every POSIX host into
    `triggers/crontab_extraction_<hostname>.txt` (read-only on the remotes; uses
    `raw`, so hosts without python work too). Root crontabs are read with
    `sudo -n` and saved to `crontab_extraction_<hostname>_root.txt` only where
    passwordless sudo works — no `--ask-become-pass` needed, and hosts without
    it are skipped instead of prompting. Hosts with no crontab get a one-line
    `# no user crontab ...` header file. Windows hosts use Task Scheduler, not
    cron, so they are out of scope.

    ```bash
    ansible-playbook ansible_playbooks/collect_crontabs.yml -i ./inventory/hosts
    ```

    Keep it non-interactive when some hosts are offline or missing SSH keys
    (they fail fast instead of prompting for a password):

    ```bash
    ANSIBLE_SSH_ARGS='-o BatchMode=yes -o ConnectTimeout=10' ansible-playbook ansible_playbooks/collect_crontabs.yml -i ./inventory/hosts --timeout 10
    ```

    ```bash
    ansible-playbook ansible_playbooks/collect_crontabs.yml -i ./inventory/hosts --check --limit linux_workstations
    ```
