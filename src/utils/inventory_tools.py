# %%
# Functions #


def load_inventory_hostnames(inventory_path):
    """
    Parse an Ansible INI inventory (inventory/hosts) and return the set of
    uppercase short hostnames it declares.

    Group headers ([group]) and [group:vars] sections are skipped; each host
    line contributes its first token (with any domain suffix stripped).
    """
    hostnames = set()
    in_vars_section = False
    with open(inventory_path, "r", encoding="utf-8") as file_handle:
        for line in file_handle:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            if line.startswith("["):
                in_vars_section = line.rstrip("]").endswith(":vars")
                continue
            if in_vars_section:
                continue
            token = line.split()[0]
            if "=" in token:
                continue
            hostnames.add(token.split(".")[0].upper())
    return hostnames


# %%
