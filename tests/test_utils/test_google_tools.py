# %%
# Imports #

import datetime

import config_test_utils  # noqa F401
import pandas as pd
from src.utils.display_tools import pprint_df, print_logger
from src.utils.google_tools import WriteToSheets, get_book, get_book_sheet_df

# %%
# Tests #


def test_get_book_sheet_df():
    df = get_book_sheet_df("TestApp", "TestApp")
    pprint_df(df.head(20))
    assert isinstance(df, pd.DataFrame)


def test_write_to_sheets():
    current_datetime_string = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # create dataframe
    df = pd.DataFrame(
        {
            "A": [1, 2, 3, 4],
            "B": [5, 6, 7, 8],
            "C": [9, 10, 11, 12],
            "Datetime": [
                current_datetime_string,
                current_datetime_string,
                current_datetime_string,
                current_datetime_string,
            ],
        }
    )
    pprint_df(df)

    # write to sheets
    WriteToSheets("TestApp", "TestApp", df)

    # read from sheets
    df = get_book_sheet_df("TestApp", "TestApp")
    # Convert both the current_datetime_string and the Datetime column values to datetime objects
    sheet_datetimes = [
        datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
        for dt in df["Datetime"].values.tolist()
    ]
    current_datetime_parsed = datetime.datetime.strptime(
        current_datetime_string, "%Y-%m-%d %H:%M:%S"
    )

    # check that datetime in dataframe columns
    assert current_datetime_parsed in sheet_datetimes


def test_create_sheet_on_workbook():
    current_datetime_string = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # create dataframe
    df = pd.DataFrame(
        {
            "A": [1, 2, 3, 4],
            "B": [5, 6, 7, 8],
            "C": [9, 10, 11, 12],
            "Datetime": [
                current_datetime_string,
                current_datetime_string,
                current_datetime_string,
                current_datetime_string,
            ],
        }
    )
    pprint_df(df)

    sheet_name = f"Temp_Date_Tab_{current_datetime_string}"

    WriteToSheets("TestApp", sheet_name, df)

    # read it back
    df = get_book_sheet_df("TestApp", sheet_name)

    # Convert both the current_datetime_string and the Datetime column values to datetime objects
    sheet_datetimes = [
        datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
        for dt in df["Datetime"].values.tolist()
    ]
    current_datetime_parsed = datetime.datetime.strptime(
        current_datetime_string, "%Y-%m-%d %H:%M:%S"
    )

    # check that datetime in dataframe columns
    id_datetime_there = current_datetime_parsed in sheet_datetimes

    # try and remove the test tab
    Workbook = get_book("TestApp")
    try:
        Workbook.del_worksheet(Workbook.worksheet_by_title(sheet_name))
    except Exception as e:
        print(
            f"Failed to remove sheet from book with sheet name {sheet_name}, error: {e}",
            level="warning",
        )

    assert id_datetime_there


# %%
# Main #

if __name__ == "__main__":
    test_get_book_sheet_df()
    test_write_to_sheets()
    test_create_sheet_on_workbook()

    print_logger("All tests passed!")


# %%
