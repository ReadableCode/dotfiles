# %%
# Imports #

import json

# %%
# Functions #


def load_inventory_hostnames(inventory_path):
    """
    Parse the personal_credentials hosts.json inventory and return the set of
    uppercase short hostnames it declares.

    Each entry's "name" contributes its first dot-separated token, uppercased,
    matching how deploy_configs compares manifest hosts entries.
    """
    with open(inventory_path, "r", encoding="utf-8") as file_handle:
        inventory = json.load(file_handle)
    return {
        str(host["name"]).split(".")[0].upper()
        for host in inventory.get("hosts", [])
    }


# %%
