# %%
# Imports #

import os
import sys

file_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
grandparent_dir = os.path.dirname(parent_dir)
great_grandparent_dir = os.path.dirname(grandparent_dir)

data_dir = os.path.join(parent_dir, "data")
log_dir = os.path.join(parent_dir, "logs")
src_dir = os.path.join(parent_dir, "src")
src_utils_dir = os.path.join(src_dir, "utils")
drive_download_cache_dir = os.path.join(data_dir, "drive_download_cache")
email_attachment_dir = os.path.join(data_dir, "email_attachments")

directories = [
    data_dir,
    log_dir,
    src_dir,
    src_utils_dir,
    drive_download_cache_dir,
    email_attachment_dir,
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
    print(f"file_dir: {file_dir}")
    print(f"parent_dir: {parent_dir}")
    print(f"grandparent_dir: {grandparent_dir}")
    print(f"data_dir: {data_dir}")


# %%
