# %%
# Imports #

import datetime
import json
import os
import sys
import time
from typing import Optional

import pandas as pd
import pygsheets
import yaml
from dotenv import load_dotenv
from google.auth.exceptions import TransportError
from googleapiclient.errors import HttpError

# append grandparent
if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config_utils import data_dir, file_dir, grandparent_dir
from utils.display_tools import pprint_df, pprint_ls, print_logger

# %%
# Load Environment #

# source .env file
dotenv_path = os.path.join(grandparent_dir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

email_address_for_testing = os.getenv("EMAIL_ADDRESS_FOR_TESTING")

# %%
# Google Credentials #

SERVICE_ACCOUNT_ENV_KEY = "GOOGLE_SERVICE_ACCOUNT"
json_file_path = os.path.join(
    grandparent_dir,
    "service_account_credentials.json",
)
service_account_env_data = os.getenv(SERVICE_ACCOUNT_ENV_KEY)
service_account_env_data_json = None
service_account_email = None

if service_account_env_data is not None:
    print_logger(
        f"Found environment variable for service account with key: {SERVICE_ACCOUNT_ENV_KEY}"
    )

    try:
        if service_account_env_data:
            service_account_env_data_json = json.loads(service_account_env_data)
        else:
            raise ValueError(
                f"Environment variable {SERVICE_ACCOUNT_ENV_KEY} is not set or empty"
            )
    except json.JSONDecodeError as e:
        print_logger(
            f"JSONDecodeError: {e} with reading json from environment variable, trying to repair and reload"
        )
        if service_account_env_data is not None:
            service_account_env_data = service_account_env_data.replace("\n", "\\n")
            service_account_env_data_json = json.loads(service_account_env_data)
        else:
            raise ValueError(
                f"Environment variable {SERVICE_ACCOUNT_ENV_KEY} is not set or empty"
            )

        # fix environment variable without modifying the .env file
        os.environ[SERVICE_ACCOUNT_ENV_KEY] = service_account_env_data

elif os.path.exists(json_file_path):
    print_logger(
        f"No environment varible with key: {SERVICE_ACCOUNT_ENV_KEY}, Found json credentails at: {json_file_path}"
    )
    service_account_env_data = open(json_file_path).read()
    service_account_env_data_json = json.loads(service_account_env_data)

    # add environment variable without modifying the .env file
    os.environ[SERVICE_ACCOUNT_ENV_KEY] = service_account_env_data

else:
    raise ValueError(
        f"No environment varible with key: {SERVICE_ACCOUNT_ENV_KEY}, and no json credentails at: {json_file_path}"
    )

service_account_email = service_account_env_data_json["client_email"]
print_logger(f"google_service_account email: {service_account_email}")

# Create a connection to Google Sheets
gc = pygsheets.authorize(
    service_account_env_var=SERVICE_ACCOUNT_ENV_KEY,
)


# %%
# Sheet Variables #

# load preconfigured sheet ids
if os.path.exists(os.path.join(file_dir, "sheet_ids.yaml")):
    with open(os.path.join(file_dir, "sheet_ids.yaml"), "r") as outfile:
        dict_hardcoded_book_ids = yaml.load(outfile, Loader=yaml.FullLoader)
else:
    dict_hardcoded_book_ids = {}


# %%
# Frequently Used Functions #

dict_connected_books = {}
dict_connected_sheets = {}


def get_book_from_id(id, retry=True):
    global dict_connected_books

    if id in dict_connected_books.keys():
        Workbook = dict_connected_books[id]
        print_logger(f"Using cached connection to {id}", level="debug")
        return Workbook

    try:
        book_from_id = gc.open_by_key(id)
        dict_connected_books[id] = book_from_id
        print_logger(f"Opening new connection to {id}", level="debug")
        return book_from_id
    except TransportError as e:
        print_logger(
            f"Error opening connection to {id}, Trying again in 5 seconds, error: "
            f"{e}",
            level="warning",
        )
        if retry:
            time.sleep(30)
            return get_book_from_id(id, retry=False)
        else:
            print_logger(
                "Failed to connect to Google Sheets even after retrying",
                level="warning",
            )
            raise Exception(
                "Failed to connect to Google Sheets even after retrying because "
                f"of TransportError {e}"
            )
    except HttpError as e:
        if e.resp.status == 429:
            print_logger(
                (
                    "Error HttpError 429, rate limited, opening connection to "
                    + id
                    + ", Trying again in 20 seconds, error: "
                    + str(e)
                ),
                level="warning",
            )
            if retry:
                time.sleep(20)
                return get_book_from_id(id, retry=False)
            else:
                error_message = (
                    "Failed to connect to Google Sheets even after retrying "
                    "because of HttpError 429: " + str(e)
                )
                print_logger(error_message, level="warning")
                raise Exception(error_message)
        elif e.resp.status == 500:
            print_logger(
                "Error HttpError 500, internal server error, opening connection to "
                + id
                + ", Trying again in 120 seconds, error: "
                + str(e),
                level="warning",
            )
            if retry:
                time.sleep(120)
                return get_book_from_id(id, retry=False)
            else:
                error_message = (
                    "Failed to connect to Google Sheets "
                    "even after retrying because of "
                    "HttpError 500: " + str(e)
                )
                print_logger(error_message, level="warning")
                raise Exception(error_message)
        elif e.resp.status == 503:
            print_logger(
                (
                    f"Error HttpError 503, internal server error, opening "
                    f"connection to {id}, Trying again in 120 seconds, error: {e}"
                ),
                level="warning",
            )
            if retry:
                time.sleep(120)
                return get_book_from_id(id, retry=False)
            else:
                print_logger(
                    (
                        "Failed to connect to Google Sheets even after "
                        f"retrying because of HttpError 503: {e}"
                    ),
                    level="warning",
                )
                raise Exception(
                    (
                        "Failed to connect to Google Sheets even "
                        f"after retrying because of HttpError 503: {e}"
                    )
                )
        elif e.resp.status == 404:
            print_logger(
                (
                    f"HttpError 404 opening connection to {id}, "
                    f"Trying again in 5 seconds, error: {e}"
                ),
                level="warning",
            )
            if retry:
                time.sleep(5)
                return get_book_from_id(id, retry=False)
            else:
                print_logger(
                    (
                        "Failed to connect to Google Sheets even "
                        f"after retrying because of HttpError 404: {e}"
                    ),
                    level="warning",
                )
                raise Exception(
                    (
                        "Failed to connect to Google Sheets even after "
                        f"retrying because of HttpError 404: {e}"
                    )
                )

        else:
            raise Exception(
                f"Failed to connect to Google Sheets because of other HttpError {e}"
            )


def get_book(bookName, retry=True):
    global dict_connected_books

    if bookName in dict_hardcoded_book_ids.keys():
        print_logger(
            f"Book {bookName} in hardcoded book ids, using id: "
            + f"{dict_hardcoded_book_ids[bookName]}",
            level="debug",
        )
        return get_book_from_id(dict_hardcoded_book_ids[bookName])
    else:
        print_logger(
            f"Book {bookName} not in hardcoded book ids, trying to open by name",
            level="warning",
        )

    if bookName in dict_connected_books.keys():
        Workbook = dict_connected_books[bookName]
        print_logger(f"Using cached connection to {bookName}", level="debug")
        return Workbook
    else:
        try:
            print_logger(f"Opening new connection to {bookName}", level="debug")
            Workbook = gc.open(bookName)

            # print out what should add
            workbook_id_to_add_to_dict = Workbook.id
            print_logger(
                "Consider adding this to dict hardcoded book ids: "
                + f'"{bookName}": "{workbook_id_to_add_to_dict}"',
                level="warning",
            )
            # write to file what should add
            with open(
                os.path.join(data_dir, "dict_hardcoded_book_ids_to_add.txt"), "a"
            ) as f:
                f.write(f'"{bookName}": "{workbook_id_to_add_to_dict}"\n')

            dict_connected_books[bookName] = Workbook
            return Workbook
        except TransportError as e:
            print_logger(
                "Error opening connection to "
                + bookName
                + ", Trying again in 5 seconds, "
                "error: " + str(e),
                level="warning",
            )
            time.sleep(5)
            if retry:
                return get_book(bookName, retry=False)
            else:
                print_logger(
                    "Failed to connect to Google Sheets even after retrying",
                    level="warning",
                )
                raise e
        except HttpError as e:
            if e.resp.status == 429:
                print_logger(
                    "Error HttpError 429, rate limited, opening connection to "
                    + bookName
                    + ", Trying again in 20 seconds, error: "
                    + str(e),
                    level="warning",
                )
                time.sleep(20)
                if retry:
                    return get_book(bookName, retry=False)
                else:
                    print_logger(
                        "Failed to connect to Google Sheets even after retrying",
                        level="warning",
                    )
                    raise e
            else:
                raise e


def get_book_with_create(bookName, parent_folder_id=None, template_id=None):
    """
    This function will create a new google sheet with the name
        bookName and return a Workbook object.

    Parameters:
    -----------
    bookName: str, the name of the Google Sheet.
    parent_folder_id: str, the id of the parent folder to
        create the sheet in (default is None).

    Returns:
    -----------
    a Workbook object.

    """
    global dict_connected_books

    # if already in dict_hardcoded_book_ids[bookName], then just get from there
    if bookName in dict_hardcoded_book_ids.keys():
        print_logger(
            "Book {} in hardcoded book ids, using id: {}".format(
                bookName, dict_hardcoded_book_ids[bookName]
            ),
            level="info",
        )
        return get_book_from_id(dict_hardcoded_book_ids[bookName])
    else:
        try:
            print_logger(
                f"Book {bookName} not in hardcoded book ids, trying to open by name",
                level="info",
            )
            Workbook = gc.open(bookName)
            print_logger(
                f"Book {bookName} already exists, using existing connection",
                level="info",
            )
            return Workbook
        except Exception:
            pass

    print_logger(f"Creating book: {bookName}", level="info")
    Workbook = gc.create(bookName, template=template_id, folder=parent_folder_id)
    if template_id is not None and email_address_for_testing is not None:
        Workbook.share(email_address_for_testing, role="writer")
    dict_connected_books[bookName] = Workbook
    dict_hardcoded_book_ids[bookName] = Workbook.id
    # append new sheet id to yaml
    with open(os.path.join(file_dir, "sheet_ids.yaml"), "a") as outfile:
        yaml.dump({bookName: Workbook.id}, outfile, default_flow_style=False)

    return Workbook


def get_book_sheet(bookName, sheetName, retries=3) -> pygsheets.Worksheet:
    """
    Returns a Worksheet object from a Google Sheet using the sheet name and the spreadsheet name.
    If a cached connection exists, it will be used instead of creating a new one.

    Args:
        bookName (str): The name of the Google Sheet.
        sheetName (str): The name of the sheet within the Google Sheet.
        retries (int, optional): The maximum number of retries in case of failure. Defaults to 3.

    Returns:
        pygsheets.Worksheet: A Worksheet object from the specified Google Sheet.

    Raises:
        Exception: If the maximum number of retries is exceeded.
    """

    global dict_connected_sheets

    while retries > 0:
        # Check if the connection is already cached
        if f"{bookName} : {sheetName}" in dict_connected_sheets:
            Worksheet = dict_connected_sheets[f"{bookName} : {sheetName}"]
            print_logger(
                f"Using cached connection to {bookName} : {sheetName}", level="debug"
            )
            return Worksheet

        try:
            # Open a new connection and cache it
            Workbook = get_book(bookName)
            Worksheet = Workbook.worksheet_by_title(sheetName)
            dict_connected_sheets[f"{bookName} : {sheetName}"] = Worksheet
            print_logger(
                f"Opening new connection to {bookName} : {sheetName}", level="debug"
            )
            return Worksheet

        except Exception as e:
            retries -= 1
            if retries > 0:
                print_logger(
                    f"Error: {e}. Retrying {retries} more time(s).",
                    level="warning",
                )

    # Raise exception when retries are exhausted
    raise Exception(
        f"Failed to get the sheet {sheetName} from book {bookName} after {retries} retries."
    )


def get_book_sheet_df(
    bookName: str,
    sheetName: str,
    start: Optional[str] = None,  # Allows None or str
    end: Optional[str] = None,  # Allows None or str
    index_column: Optional[int] = None,  # Allows None or int
    value_render: pygsheets.ValueRenderOption = pygsheets.ValueRenderOption.FORMATTED_VALUE,
    numerize: bool = True,
    max_retries: int = 3,
) -> pd.DataFrame:
    """
    Returns a pandas DataFrame object from a Google Sheet using the sheet name and the spreadsheet name.
    If a cached connection exists, it will be used instead of creating a new one.

    Args:
        bookName (str): The name of the Google Sheet.
        sheetName (str): The name of the sheet within the Google Sheet.
        start (Optional[str]): The top left cell of the range to retrieve data from (default is None).
        end (Optional[str]): The bottom right cell of the range to retrieve data from (default is None).
        index_column (Optional[int]): The index of the column to use as the DataFrame index (default is None).
        value_render (ValueRenderOption): The value render option to use (default is FORMATTED_VALUE).
        numerize (bool): Whether to convert numeric values to float (default is True).
        max_retries (int): The maximum number of retries in case of failure (default is 3).

    Returns:
        pandas.DataFrame: A DataFrame object with data from the Google Sheet.

    Raises:
        Exception: If the maximum number of retries is exceeded.
    """

    while max_retries > 0:
        try:
            worksheet = get_book_sheet(bookName, sheetName, max_retries)

            df = worksheet.get_as_df(
                start=start,
                end=end,
                index_column=index_column,
                value_render=value_render,
                numerize=numerize,
            )

            # If get_as_df returns False, return an empty DataFrame
            if df is False:
                raise Exception("Failed to get the sheet as a DataFrame, not linked")

            return df
        except Exception as e:
            max_retries -= 1
            if max_retries > 0:
                print_logger(
                    f"Error: {e}. Retrying {max_retries} more time(s).", level="error"
                )

    raise Exception(
        f"Failed to get the sheet {sheetName} from book {bookName} after {max_retries} retries."
    )


def get_book_sheet_values(
    bookName,
    sheetName,
    start=None,
    end=None,
):
    """
    Returns a list of lists of values from a Google Sheet using
        the sheet name and the spreadsheet name.
    If a cached connection exists, it will be used instead of creating a new one.

    Parameters:
    -----------
    bookName: str, the name of the Google Sheet.
    sheetName: str, the name of the sheet within the Google Sheet.
    start: str, the top left cell of the range to retrieve data from (default is None).
    end: str, the bottom right cell of the range to retrieve data from (default is None)

    Returns:
    -----------
    a list of lists of values.
    """

    worksheet = get_book_sheet(bookName, sheetName)

    values = worksheet.get_values(start=start, end=end)

    return values


def get_book_sheet_from_id_name(id, sheetName, retries=3):
    """
    Returns a Worksheet object from a Google Sheet using
        the spreadsheet ID and the sheet name.
    Utilizes a cached connection if one exists.

    Args:
        id (str): The ID of the Google spreadsheet.
        sheetName (str): The name of the sheet within the Google spreadsheet.
        retries (int, optional): The maximum number of retries
            in case of failure. Defaults to 3.

    Returns:
        Worksheet: A Worksheet object from the specified Google Sheet.
    """
    global dict_connected_sheets

    retries_left = retries

    while retries_left > 0:
        if f"{id} : {sheetName}" in dict_connected_sheets.keys():
            Worksheet = dict_connected_sheets[f"{id} : {sheetName}"]
            print_logger(
                f"Using cached connection to {id} : {sheetName}", level="debug"
            )
            return Worksheet
        else:
            try:
                Workbook = get_book_from_id(id)
                Worksheet = Workbook.worksheet_by_title(sheetName)
                dict_connected_sheets[f"{id} : {sheetName}"] = Worksheet
                print_logger(
                    f"Opening new connection to {id} : {sheetName}", level="debug"
                )
                return Worksheet
            except Exception as e:
                retries_left -= 1
                if retries_left > 0:
                    print_logger(
                        f"Error: {e}. Retrying {retries_left} more time(s).",
                        level="warning",
                    )
                else:
                    raise e


def get_book_sheet_df_from_id_name(
    id,
    sheetName,
    start=None,
    end=None,
    index_column=None,
    value_render="FORMATTED_VALUE",
    numerize=True,
    retries=3,
):
    try:
        worksheet = get_book_sheet_from_id_name(id, sheetName)

        df = worksheet.get_as_df(
            start=start,
            end=end,
            index_column=index_column,
            value_render=value_render,
            numerize=numerize,
        )

    except Exception as e:
        if retries == 0:
            print_logger(
                "Error getting sheet from id after max retries: "
                f"{id}, sheetName: {sheetName}, error: {e}",
                level="error",
            )
            raise Exception(
                "Error getting sheet from id after max retries: "
                f"{id}, sheetName: {sheetName}, error: {e}"
            )
        else:
            print_logger(
                f"Error getting sheet from id: {id}, sheetName: {sheetName}, "
                f"retrying in 5 seconds, error: {e}",
                level="error",
            )
            time.sleep(5)
            return get_book_sheet_df_from_id_name(
                id,
                sheetName,
                start=start,
                end=end,
                index_column=index_column,
                value_render=value_render,
                numerize=numerize,
                retries=retries - 1,
            )

    return df


def get_book_sheet_values_from_id_name(
    id,
    sheetName,
    start=None,
    end=None,
    include_tailing_empty=True,
):
    worksheet = get_book_sheet_from_id_name(id, sheetName)

    values = worksheet.get_values(
        start=start,
        end=end,
        include_tailing_empty=include_tailing_empty,
    )

    return values


def WriteToSheets(  # noqa: C901
    bookName,
    sheetName,
    df,
    indexes=False,
    set_note=None,
    retries=3,
):
    """
    Writes a dataframe to a Google Sheet, creating the sheet if it does not exist.
    Optionally sets a note on the sheet.

    Args:
        bookName (str): The name of the Google spreadsheet.
        sheetName (str): The name of the sheet within the Google spreadsheet.
        df (DataFrame): The dataframe to write to the sheet.
        indexes (bool): Whether to write the index column to the sheet.
        set_note (str or None): The note to set on the sheet. Use None for no note, "DT"
            for date/time, or a string for a custom note.
        retries (int): The number of times to retry if the connection fails.

    Returns:
        None
    """

    # global dict_connected_books
    # global dict_connected_sheets
    df = df.copy()

    start_time = datetime.datetime.now()
    print_logger(
        f"Writing to Google Sheet: {bookName} - {sheetName} with size {df.shape}"
    )
    if isinstance(df, pd.Series):
        print_logger(
            "# Found a series when writing to sheets, converting to dataframe #",
            level="warning",
        )
        df = df.reset_index()

    for i in range(retries):
        try:
            Workbook = get_book(bookName)
            # get available sheets
            ls_sheets = Workbook.worksheets()
            ls_sheet_names = [sheet.title for sheet in ls_sheets]
            if sheetName not in ls_sheet_names:
                print_logger(
                    f"Sheet {sheetName} not found in book {bookName}, creating new sheet",
                    level="warning",
                )
                Workbook.add_worksheet(sheetName)
            try:
                Worksheet = get_book_sheet(bookName, sheetName)
            except Exception as e:
                print_logger(
                    f"Sheet {sheetName} not found in book {bookName}, creating new sheet because {e}",
                    level="warning",
                )
                Workbook.add_worksheet(sheetName)
                Worksheet = get_book_sheet(bookName, sheetName)

            if not indexes:
                Worksheet.set_dataframe(df, (1, 1), fit=True, nan="")
            else:
                Worksheet.set_dataframe(df, (1, 1), fit=True, nan="", copy_index=True)
            try:
                if set_note is not None:
                    if set_note == "DT":
                        Worksheet.cell((1, 1)).note = "Data updated at: " + str(
                            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        )
                    else:
                        Worksheet.cell((1, 1)).note = set_note
            except Exception as e:
                print_logger(
                    f"Failed to set note when writing, error: {e}, trying 1 more time",
                    level="warning",
                )
                try:
                    if set_note is not None:
                        if set_note == "DT":
                            Worksheet.cell((1, 1)).note = "Data updated at: " + str(
                                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            )
                        else:
                            Worksheet.cell((1, 1)).note = set_note
                except Exception:
                    pass
                pass

            print_logger(
                f"Finished writing to Google Sheet: "
                f"{bookName} - {sheetName} with size {df.shape}, "
                f"after {datetime.datetime.now() - start_time}\n"
                f"Link: https://docs.google.com/spreadsheets/d/{Workbook.id}"
            )

            return
        except Exception as e:
            print_logger(
                (
                    f"Failed to write to sheets with name {bookName} and "
                    f"sheet name {sheetName} and df of size {df.shape}, error: {e}"
                ),
                level="warning",
            )
            print_logger(
                f"Retrying {i+1} of {retries} times after {i * 20} seconds",
                level="warning",
            )
            time.sleep(i * 20)
            print_logger("Retrying now", level="warning")
            pass

    print_logger(f"Failed to write to sheet after {retries} retries", level="warning")
    raise Exception(
        (
            f"Failed to write to sheets with name {bookName} "
            f" and sheet name {sheetName} and df of size {df.shape}"
        )
    )


def ClearSheet(book_name, sheet_name, start_range, end_range):
    """
    Clears a specified range of cells on a sheet.

    Args:
        book_name (str): The name of the Google spreadsheet.
        sheet_name (str): The name of the sheet within the Google spreadsheet.
        start_range (str): The start range of the cells to clear, in the format "A1".
        end_range (str): The end range of the cells to clear, in the format "A1".

    Returns:
        None
    """

    Worksheet = get_book_sheet(book_name, sheet_name)
    Worksheet.clear(start_range, end_range)


def clear_range_of_sheet_obj(sheet_obj, start, end, retries=3):
    """
    Clears a specified range of cells on a sheet.

    Args:
        sheet_obj: The sheet object to write to.
        start (str): The start range of the cells to clear, in the format "A1".
        end (str): The end range of the cells to clear, in the format "A1".

    Returns:
        None
    """

    for i in range(retries):
        try:
            sheet_obj.clear(start, end)
            return
        except Exception as e:
            print_logger(f"Failed to clear range, error: {e}", level="warning")
            print_logger(
                f"Retrying {i+1} of {retries} times after {i * 20} seconds",
                level="warning",
            )
            time.sleep(i * 10)
            print_logger("Retrying now", level="warning")
            pass

    print_logger(f"Failed to clear range after {retries} retries", level="warning")
    raise Exception(f"Failed to clear range after {retries} retries")


def clear_formatting_of_range_of_sheet_obj(sheet_obj, start, end, retries=3):
    """
    Clears the formatting of a specified range of cells on a sheet.

    Args:
        sheet_obj: The sheet object to write to.
        start (str): The start range of the cells to clear, in the format "A1".
        end (str): The end range of the cells to clear, in the format "A1".

    Returns:
        None
    """

    for i in range(retries):
        try:
            sheet_obj.clear(start, end, fields="userEnteredFormat")
            return
        except Exception as e:
            print_logger(
                f"Failed to clear formatting of range, error: {e}", level="warning"
            )
            print_logger(
                f"Retrying {i+1} of {retries} times after {i * 20} seconds",
                level="warning",
            )
            time.sleep(i * 10)
            print_logger("Retrying now", level="warning")
            pass

    print_logger(
        f"Failed to clear formatting of range after {retries} retries", level="warning"
    )
    raise Exception(f"Failed to clear formatting of range after {retries} retries")


def clear_formatting_of_book_sheet_range(book_name, sheet_name, start, end, retries=3):
    """
    Clears the formatting of a specified range of cells on a sheet.

    Args:
        book_name (str): The name of the Google spreadsheet.
        sheet_name (str): The name of the sheet within the Google spreadsheet.
        start (str): The start range of the cells to clear, in the format "A1".
        end (str): The end range of the cells to clear, in the format "A1".

    Returns:
        None
    """

    Worksheet = get_book_sheet(book_name, sheet_name)
    clear_formatting_of_range_of_sheet_obj(Worksheet, start, end, retries)


def write_df_to_range_of_sheet_obj(
    sheet_obj,
    df,
    start,
    fit,
    nan="",
    copy_head=False,
    retries=3,
):
    """
    Writes a DataFrame to a specified range on a sheet.

    Args:
        sheet_obj: The sheet object to write to.
        df (DataFrame): The DataFrame to write to the sheet.
        start (str): The start range of the cells to clear, in the format "A1".
        fit (bool): Whether to fit the DataFrame to the range specified.
        nan: The value to use for NaN values in the DataFrame.
        copy_head (bool): Whether to copy the header of the DataFrame to the sheet.

    Returns:
        None
    """

    for i in range(retries):
        try:
            sheet_obj.set_dataframe(
                df=df, start=start, fit=fit, nan=nan, copy_head=copy_head
            )
            return
        except Exception as e:
            print_logger(
                (
                    f"Failed to write to range with error: {e}, "
                    f"retrying {i+1} of {retries} times"
                ),
                level="warning",
            )
            time.sleep(i * 10)
            pass

    print_logger(f"Failed to write to range after {retries} retries", level="warning")
    raise Exception("Failed to write to range")


# %%
# Entire Sheet Operations #


def copy_sheet_book_to_book(source_book, ls_source_sheets, ls_dest_books):
    Workbook_src = gc.open(source_book)
    src_book_id = Workbook_src.id

    for dest_book in ls_dest_books:
        for source_sheet in ls_source_sheets:
            sheet_src = Workbook_src.worksheet_by_title(source_sheet)
            src_sheet_id = sheet_src.id
            src_tup = (src_book_id, src_sheet_id)

            Workbook_dest = gc.open(dest_book)

            try:
                Workbook_dest.del_worksheet(
                    Workbook_dest.worksheet_by_title(source_sheet)
                )
            except Exception:
                pass

            Workbook_dest.add_worksheet(source_sheet, src_tuple=src_tup)


def remove_sheet_from_book(book_name, sheet_name):
    Workbook = get_book(book_name)
    try:
        Workbook.del_worksheet(Workbook.worksheet_by_title(sheet_name))
    except Exception as e:
        print_logger(
            f"Failed to remove sheet from book {book_name} with sheet name {sheet_name}, error: {e}",
            level="warning",
        )


# %%
# Auth and gets #


def get_book_from_file_name(file_name):  # need to remove, aliased to new one for now
    book_from_file_name = get_book(file_name)
    return book_from_file_name


def get_df_from_sheet_id(
    id, sheet_name, start_range, end_range, include_tailing_empty=False, retry=True
):
    try:
        data_from_book = get_book_sheet_from_id_name(id, sheet_name).get_as_df(
            start=start_range,
            end=end_range,
            include_tailing_empty=include_tailing_empty,
        )
        return data_from_book
    except Exception as e:
        if retry:
            print_logger(
                f"Failed to get df from sheet id {id}, "
                f"sheet_name: {sheet_name}, error: {e}, retrying",
                level="warning",
            )
            return get_df_from_sheet_id(
                id,
                sheet_name,
                start_range,
                end_range,
                include_tailing_empty,
                retry=False,
            )
        else:
            error_message = (
                f"Failed to get df even after retry from sheet id {id}, "
                f"sheet_name: {sheet_name}, error: {e}"
            )
            print_logger(error_message, level="warning")
            raise Exception(error_message)


def get_df_from_file_name(
    file_name, sheet_name, start_range, end_range, include_tailing_empty=False
):
    book_from_file_name = get_book_from_file_name(file_name)
    sheet_from_book = book_from_file_name.worksheet_by_title(sheet_name)
    data_from_book = sheet_from_book.get_as_df(
        start=start_range, end=end_range, include_tailing_empty=include_tailing_empty
    )
    return data_from_book


def get_df_and_id_from_file_name(
    file_name, sheet_name, start_range, end_range, include_tailing_empty=False
):
    book_from_file_name = get_book_from_file_name(file_name)
    sheet_id = book_from_file_name.id
    sheet_from_book = book_from_file_name.worksheet_by_title(sheet_name)
    data_from_book = sheet_from_book.get_as_df(
        start=start_range, end=end_range, include_tailing_empty=include_tailing_empty
    )
    return data_from_book, sheet_id


def copy_formulas_range_to_range(
    book_name, copy_sheet_name, copy_range, paste_sheet_name, paste_range_string
):
    copy_sheet = get_book_sheet(book_name, copy_sheet_name)
    paste_sheet = get_book_sheet(book_name, paste_sheet_name)
    paste_sheet.update_values(
        paste_range_string,
        copy_sheet.get_values(
            start=copy_range[0],
            end=copy_range[1],
            returnas="matrix",
            include_tailing_empty=True,
            include_tailing_empty_rows=True,
            value_render="FORMULA",
        ),
    )


def get_sheet_link(sheet_id):
    if (sheet_id == "") or (sheet_id is None) or (len(sheet_id) != 44):
        return ""
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}"


def get_sheet_link_formula(sheet_id):
    sheet_link = get_sheet_link(sheet_id)
    if sheet_link == "":
        return ""
    return f'=hyperlink("{sheet_link}","Link")'


def convert_tab_name_to_hyperlink(book_obj, tab_name, link_text):
    if tab_name == "":
        return ""
    ss_id = book_obj.id
    sheet_id = book_obj.worksheet_by_title(tab_name).id

    hyperlink = (
        "=HYPERLINK("
        f'"https://docs.google.com/spreadsheets/d/{ss_id}/edit#gid={sheet_id}",'
        f'"{link_text}")'
    )
    return hyperlink


# %%
# Permission Management #


def get_editors_from_spreadsheet(sheet_id, print_output=True):
    book = get_book_from_id(sheet_id)
    spreadsheet_name = book.title
    permissions = book.permissions
    editor_emails = []
    for permission in permissions:
        # if email address esixts, and role is not writer, skip
        if ("emailAddress" not in permission) or (permission["role"] != "writer"):
            continue
        editor_emails.append(permission["emailAddress"])
    if print_output:
        pprint_ls(editor_emails, f"{spreadsheet_name} Editor Emails: ")
    return editor_emails


def check_for_editor(sheet_id, email):
    editor_emails = get_editors_from_spreadsheet(sheet_id, print_output=False)
    is_editor = email in editor_emails
    print_logger(f"{email} is editor: {is_editor}")
    return is_editor


def share_to_email(sheet_id, email, role="writer"):
    book = get_book_from_id(sheet_id)
    book.share(
        email,
        role=role,
    )


def share_list_sheets_to_email(sheet_id_list, email, role="writer", test_mode=True):
    df_statuses = pd.DataFrame(columns=["sheet_id", "sheet_name", "status"])
    for sheet_id in sheet_id_list:
        # get sheet name from dict_hardcoded_book_ids values
        sheet_name = list(dict_hardcoded_book_ids.keys())[
            list(dict_hardcoded_book_ids.values()).index(sheet_id)
        ]
        status = ""
        try:
            if check_for_editor(sheet_id, email):
                status = "Already Editor"
            elif test_mode:
                status = "Would Have Shared"
            else:
                share_to_email(sheet_id, email, role=role)
                status = "Shared"
        except Exception as e:
            print_logger(f"Failed to share {sheet_id} to {email}.", level="error")
            print_logger(e)
            status = "Failed"
        df_statuses = df_statuses.append(
            {
                "sheet_id": sheet_id,
                "sheet_name": sheet_name,
                "status": status,
            },
            ignore_index=True,
        )

    pprint_df(df_statuses)
    print_logger("Failed Sheets:", level="error")
    pprint_df(df_statuses[df_statuses["status"] == "Failed"])


# %%
