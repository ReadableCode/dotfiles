# %%
# Imports #

import datetime
import json
import os
import sys

from dotenv import load_dotenv
from tabulate import tabulate

# append grandparent
if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config_utils import grandparent_dir

# %%
# Variables #

dotenv_path = os.path.join(grandparent_dir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


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


def df_to_string(df):
    # Convert dataframe to markdown table
    markdown_table = tabulate(df, headers="keys", tablefmt="pipe", showindex=False)

    return markdown_table


def print_logger(message, level="info", as_break=False):
    """
    Prints a message with a preceding timestamp.

    Args:
        message (str): The message to print.
        level (str): The level of the message (e.g., "INFO", "WARNING", "ERROR").

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
    if dict_levels[level.lower()] <= dict_levels[LOG_LEVEL]:
        print_message = (
            f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
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
