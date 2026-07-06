# %%
# Imports #

import glob
import os
import re
import warnings
from datetime import date

from config_scripts import log_dir

warnings.filterwarnings("ignore")

iso_year, iso_week, _ = date.today().isocalendar()
WorkingWeek = f"{iso_year}-W{iso_week:02d}"

# %%
# Read Logs #

log_file_locs = glob.glob(os.path.join(log_dir, "*.txt")) + glob.glob(
    os.path.join(log_dir, "*.log")
)

for file_loc in log_file_locs:
    file_name = os.path.basename(file_loc)
    print(f"file_name: {file_name}")
    file_path = os.path.dirname(file_loc)
    print(f"file_path: {file_path}")
    file_name_with_week = WorkingWeek + "_" + file_name
    print(f"new file name: {file_name_with_week}")
    archive_folder_name = re.sub(r"\.(txt|log)$", "", file_name)
    os.makedirs(os.path.join(file_path, archive_folder_name), exist_ok=True, mode=0o777)
    os.rename(
        file_loc, os.path.join(file_path, archive_folder_name, file_name_with_week)
    )
    open(file_loc, "a").close()
    os.chmod(file_loc, 0o777)


# %%
