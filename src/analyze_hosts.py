# %%
# Imports #

import json
import os

from config import grandparent_dir, parent_dir
from dotenv import load_dotenv
from utils.display_tools import (  # noqa F401
    pprint_df,
    pprint_dict,
    pprint_ls,
    print_logger,
)

# %%
# Variables #

dotenv_path = os.path.join(parent_dir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

ssh_password = os.getenv("SSH_PASSWORD")

# %%
# Hosts #


def get_hosts_dict():
    with open(os.path.join(parent_dir, "hosts.json"), "r") as f:
        hosts = json.load(f)

    return hosts


def get_hosts_personal_json():
    with open(
        os.path.join(grandparent_dir, "Assistant", "hosts_personal_json.json"), "r"
    ) as f:
        hosts_personal_json_raw = json.load(f)

    hosts_personal_json_raw = hosts_personal_json_raw["hosts"]

    hosts_personal_json = {}
    for host_dict in hosts_personal_json_raw:
        print(f"Processing host: {host_dict}")
        pprint_dict(host_dict)

        hostname = host_dict["hostname"]
        # remove hostname from dict
        del host_dict["hostname"]
        hosts_personal_json[hostname] = host_dict

    return hosts_personal_json


hosts = get_hosts_dict()
hosts_personal_json = get_hosts_personal_json()


print("-" * 1000)
print("hosts")
print(hosts)
print("-" * 1000)
print("hosts_personal_json")
print(hosts_personal_json)
print("-" * 1000)


def get_combined_hosts():
    # get list of all hostnames from both
    set_all_hostnames = set()
    for key in hosts.keys():
        set_all_hostnames.add(key)
    for key in hosts_personal_json.keys():
        set_all_hostnames.add(key)

    ls_all_hostnames = sorted(set_all_hostnames)

    pprint_ls(ls_all_hostnames)

    dict_combined_hosts = {}

    for hostname in ls_all_hostnames:
        hostname_in_hosts = hosts.get(hostname, {})
        hostname_in_personal = hosts_personal_json.get(hostname, {})

        # print if not in both and break
        if not hostname_in_hosts or not hostname_in_personal:
            print(f"Hostname {hostname} not in both hosts and hosts_personal_json")

        dict_combined_hosts[hostname] = {
            **hostname_in_hosts,
            **hostname_in_personal,
        }

    return dict_combined_hosts


dict_combined_hosts = get_combined_hosts()


# %%

print("-" * 1000)
print("dict_combined_hosts")
pprint_dict(dict_combined_hosts)
print("-" * 1000)

output_path = os.path.join(grandparent_dir, "Assistant", "hosts.json")
with open(output_path, "w") as f:
    json.dump(dict_combined_hosts, f, indent=4)
print(f"Wrote combined hosts to {output_path}")

# %%
