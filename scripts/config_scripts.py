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

data_dir = os.path.join(parent_dir, "data")
log_dir = os.path.join(parent_dir, "logs")
docs_dir = os.path.join(parent_dir, "docs")
src_dir = os.path.join(parent_dir, "src")
src_utils_dir = os.path.join(src_dir, "utils")

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
    print(f"src_dir: {src_dir}")

# %%
