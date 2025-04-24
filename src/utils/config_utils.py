# %%
# Imports #

import os
import sys
from os.path import expanduser

home_dir = expanduser("~")
file_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
grandparent_dir = os.path.dirname(parent_dir)
great_grandparent_dir = os.path.dirname(grandparent_dir)

data_dir = os.path.join(grandparent_dir, "data")
templates_dir = os.path.join(grandparent_dir, "templates")
log_dir = os.path.join(grandparent_dir, "logs")
src_dir = os.path.join(grandparent_dir, "src")
src_utils_dir = os.path.join(src_dir, "utils")
drive_download_cache_dir = os.path.join(data_dir, "drive_download_cache")
s3_download_cache = os.path.join(data_dir, "s3_download_cache")

directories = [
    data_dir,
    templates_dir,
    log_dir,
    src_dir,
    src_utils_dir,
    drive_download_cache_dir,
    s3_download_cache,
]
for directory in directories:
    if not os.path.exists(directory):
        print(f"Creating directory: {directory}")
        os.makedirs(directory)

sys.path.append(file_dir)
sys.path.append(parent_dir)
sys.path.append(grandparent_dir)
sys.path.append(src_dir)
sys.path.append(src_utils_dir)

if __name__ == "__main__":
    print(f"home_dir: {home_dir}")
    print(f"file_dir: {file_dir}")
    print(f"parent_dir: {parent_dir}")
    print(f"grandparent_dir: {grandparent_dir}")
    print(f"data_dir: {data_dir}")


# %%
