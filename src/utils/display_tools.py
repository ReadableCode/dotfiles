# %%
# Imports #

import datetime
import json
import os
import sys

import pandas as pd
import pytz
from tabulate import tabulate

# append grandparent
if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import utils.config_utils  # noqa F401

# %%
# Variables #


# if log level is defined in environment
if "LOG_LEVEL" in os.environ:
    LOG_LEVEL = os.environ["LOG_LEVEL"]
else:
    LOG_LEVEL = "info"


# %%
# Functions #


def pprint_df(dframe, showindex=False, num_cols=None, num_decimals=2):
    """
    Pretty prints a pandas DataFrame with specified formatting options.

    This function uses the tabulate library to format and print a pandas DataFrame
    with options to limit the number of columns, adjust the number of decimal places
    for float values, and choose whether to display the index.

    Args:
        dframe (DataFrame): The pandas DataFrame to be pretty printed.
        showindex (bool, optional): Whether to show the DataFrame index.
            Defaults to False.
        num_cols (int, optional): The maximum number of columns to display.
            If None, all columns are displayed. Defaults to None.
        num_decimals (int, optional): The number of decimal places to
            format float values. Defaults to 2.

    Returns:
        None
    """
    floatfmt_str = f".{num_decimals}f"

    if num_cols is not None:
        print(
            tabulate(
                dframe.iloc[:, :num_cols],
                headers="keys",
                tablefmt="psql",
                showindex=showindex,
                floatfmt=floatfmt_str,
            )
        )
    else:
        print(
            tabulate(
                dframe,
                headers="keys",
                tablefmt="psql",
                showindex=showindex,
                floatfmt=floatfmt_str,
            )
        )


def pprint_rows(df, rows=None):
    """
    Pretty-print specific rows (or a DataFrame slice) in transposed form.

    rows:
        - None  → use the df slice passed in (df.head(3))
        - int   → single row number
        - list/tuple of ints → multiple rows
        - DataFrame → use directly
    """

    # --- Figure out input type ---
    if isinstance(rows, pd.DataFrame):
        sub = rows.copy()
    elif rows is None:
        sub = df.copy()  # e.g. user passed df.head(n)
    elif isinstance(rows, int):
        sub = df.iloc[[rows]]  # make into 1-row df
    else:
        sub = df.iloc[rows]  # list/tuple of row numbers

    # --- Transpose into Field / Row_# structure ---
    out = sub.T
    out.reset_index(inplace=True)
    out.columns = ["Field"] + [f"Row_{i}" for i in range(out.shape[1] - 1)]

    pprint_df(out, showindex=False)


def df_to_string(df):
    # Convert dataframe to markdown table
    markdown_table = tabulate(df, headers="keys", tablefmt="pipe", showindex=False)

    return markdown_table


def print_logger(message, level="info", as_break=False):
    """
    Prints a message with a preceding timestamp in CST timezone.

    Args:
        message (str): The message to print.
        level (str): The level of the message (e.g., "INFO", "WARNING", "ERROR").
        as_break (bool): Whether to print the message in a separated block.

    Returns:
        None
    """
    dict_levels = {
        "debug": 5,
        "info": 4,
        "warning": 3,
        "error": 2,
        "critical": 1,
    }

    # Convert UTC to CST
    cst = pytz.timezone("America/Chicago")
    now_cst = datetime.datetime.now(datetime.timezone.utc).astimezone(cst)

    if dict_levels[level.lower()] <= dict_levels[LOG_LEVEL]:
        print_message = (
            f"{now_cst.strftime('%Y-%m-%d %H:%M:%S %Z')}"  # Includes CST timezone
            f" - {level.upper()} - {message}"
        )
        if not as_break:
            print(print_message)
        else:
            len_total_message = len(print_message)
            padding_text = ((100 - len_total_message - 2) // 2) * "#"
            print("#" * 100)
            print("#" * 100)
            print(f"{padding_text} {print_message} {padding_text}")
            print("#" * 100)
            print("#" * 100)


def print_progress_bar(current, total, bar_length=40):
    fraction = current / total
    arrow_length = int(fraction * bar_length) - 1
    arrow = "=" * arrow_length + ">" if arrow_length >= 0 else ""
    padding = " " * (bar_length - len(arrow))
    percent = fraction * 100
    print(f"\rProgress: [{arrow}{padding}] {percent:.2f}%", end=" ")


def get_progress_bar_string(current, total, bar_length=40):
    fraction = current / total
    arrow_length = int(fraction * bar_length) - 1
    arrow = "=" * arrow_length + ">" if arrow_length >= 0 else ""
    padding = " " * (bar_length - len(arrow))
    percent = fraction * 100
    return f"Progress: [{arrow}{padding}] {percent:.2f}%"


def pprint_ls(ls, ls_title="List"):
    """
    Pretty prints a list with a title.

    Args:
        ls (list): The list to print.
        ls_title (str): The title of the list.

    Returns:
        None
    """

    # if list is empty return
    if len(ls) == 0:
        item_max_len = 0
    else:
        item_max_len = 0
        for item in ls:
            try:
                this_length = len(str(item))
            except Exception:
                this_length = 0
            if this_length > item_max_len:
                item_max_len = this_length

    # get the longest item in the list
    max_len = max(item_max_len, len(ls_title)) + 8

    # print the top of the box
    print(f"{'-' * (max_len + 4)}")

    # print the title with padding
    print(f"| {ls_title.center(max_len)} |")

    # print the bottom of the title box
    print(f"{'-' * (max_len + 4)}")

    # print each item in the list
    for item in ls:
        if isinstance(item, str):
            print(f"| {item.ljust(max_len)} |")
        else:
            print(f"| {str(item).ljust(max_len)} |")

    # print the bottom of the list box
    print(f"{'-' * (max_len + 4)}")


def pprint_dict(data, indent=0):
    try:
        print(json.dumps(data, indent=indent + 2))
        return
    except Exception as e:
        if e:
            pass

    if isinstance(data, dict):
        for key, value in data.items():
            print(" " * indent + str(key) + ": ", end="")
            if isinstance(value, dict):
                print("DICTIONARY {")
                pprint_dict(value, indent + 8)
                print(" " * indent + "}")
            elif isinstance(value, list):
                print("LIST [")
                for item in value:
                    if isinstance(item, dict):
                        pprint_dict(item, indent + 8)
                        print("," + " " * (indent + 8))
                    else:
                        print(" " * (indent + 8) + str(item) + ",")
                print(" " * indent + "]")
            else:
                print(str(value))
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                pprint_dict(item, indent)
                print("," + " " * indent)
            else:
                print(" " * indent + str(item) + ",")
    else:
        print(" " * indent + str(data))


def print_nested_dict(data, indent=0):
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                print("  " * indent + str(key) + ":")
                print_nested_dict(value, indent + 1)
            else:
                print("  " * indent + str(key) + ": " + str(value))
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                print_nested_dict(item, indent)
            else:
                print("  " * indent + str(item))
    else:
        print("  " * indent + str(data))


def print_google_doc_string_for_df(df):
    """
    Print a DataFrame's schema in Google-style docstring format.
    """

    dtype_map = {
        "int64": "int",
        "float64": "float",
        "object": "str",
        "bool": "bool",
        "datetime64[ns]": "datetime",
    }

    sample = df.iloc[0] if not df.empty else None

    print('"""')
    print("Returns:")
    print("    pd.DataFrame: DataFrame with the following columns:")
    for c, t in zip(df.columns, df.dtypes):
        t_str = dtype_map.get(str(t), str(t))
        val = "" if sample is None else str(sample[c])
        if len(val) > 40:
            val = val[:37] + "..."
        print(f"        - {c} ({t_str}): e.g. {val}")
    print('"""')


def check_name_against_ignore_patterns(name, ls_ignore_patterns):
    for pattern in ls_ignore_patterns:
        if pattern in name:
            return True
    return False


def display_file_tree(root_dir, indent=0, ls_ignore_patterns=[]):
    ls_unignored_file_paths = []

    root_base = os.path.basename(root_dir)

    print(" " * (indent) + "├── " + root_base + "/")

    for i, name in enumerate(os.listdir(root_dir)):
        path = os.path.join(root_dir, name)
        if os.path.isdir(path):
            if not check_name_against_ignore_patterns(name, ls_ignore_patterns):
                ls_unignored_file_paths.extend(
                    display_file_tree(path, indent + 8, ls_ignore_patterns)
                )
        elif os.path.isfile(path):
            if not check_name_against_ignore_patterns(name, ls_ignore_patterns):
                print(" " * (indent + 8) + "├── " + name)
                ls_unignored_file_paths.append(path)

    return ls_unignored_file_paths
