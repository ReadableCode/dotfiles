# %%
# Imports #

import re

import config_test_utils  # noqa F401
from src.utils.date_tools import (
    all_days_list,
    all_days_list_dashed_desc,
    all_weeks_list,
    df_days,
    df_scm_weeks,
    df_weeks,
    get_current_time_in_timezone,
    ls_days_slashed_no_pad,
)
from src.utils.display_tools import pprint_df, pprint_ls, print_logger

# %%
# Variables #

dict_columns_to_regex_test = {
    "dashed_pad_desc": {"format": "YYYY-MM-DD", "regex": r"^\d{4}-\d{2}-\d{2}$"},
    "slashed_nopad": {"format": "M/D/YYYY", "regex": r"^\d{1,2}/\d{1,2}/\d{4}$"},
    "week": {"format": "D", "regex": r"^\d{1,2}$"},
    "Week": {"format": "2021-W01", "regex": r"^\d{4}-W\d{2}$"},
    "WeekNum": {"format": "D", "regex": r"^\d{1,2}$"},
    "WeekAbbrev": {"format": "W01", "regex": r"^W\d{2}$"},
    "WeekString": {"format": "2021-W01", "regex": r"^\d{4}-W\d{2}$"},
    "slashed_pad_desc": {"format": "2021/01/01", "regex": r"^\d{4}/\d{2}/\d{2}$"},
    "slashed_pad": {"format": "01/01/2021", "regex": r"^\d{2}/\d{2}/\d{4}$"},
    "WeekDay": {"format": "1", "regex": r"^\d{1}$"},
    "WeekDayName": {"format": "Monday", "regex": r"^[A-Za-z]{6,9}$"},
    "WeekDayNumDashName": {"format": "5 - Friday", "regex": r"^\d{1} - [A-Za-z]{6,9}$"},
    "SCMWeekDayNumDashName": {
        "format": "2 - Friday",
        "regex": r"^\d{1} - [A-Za-z]{6,9}$",
    },
    "Year": {"format": "2021", "regex": r"^\d{4}$"},
    "Start Date": {"format": "M/D/YYYY", "regex": r"^\d{1,2}/\d{1,2}/\d{4}$"},
    "End Date": {"format": "M/D/YYYY", "regex": r"^\d{1,2}/\d{1,2}/\d{4}$"},
    "Thursday Meeting for Week": {
        "format": "M/D/YYYY",
        "regex": r"^\d{1,2}/\d{1,2}/\d{4}$",
    },
    "RosterForWeekBegin": {
        "format": "2020-12-21",
        "regex": r"^\d{4}-\d{2}-\d{2}$",
    },
    "RosterForWeekBeginSlashedNoPad": {
        "format": "M/D/YY",
        "regex": r"^\d{1,2}/\d{1,2}/\d{2}$",
    },
    "RosterForWeekBeginSlashedNoPadFullYear": {
        "format": "M/D/YYYY",
        "regex": r"^\d{1,2}/\d{1,2}/\d{4}$",
    },
    "SCM_Weekday": {
        "format": "Wednesday - 1",
        "regex": r"^[A-Za-z]{6,9}(?: - \d{1})?$",
    },
    "Week_Start_Date": {
        "format": "1/7/2021",
        "regex": r"^\d{1,2}/\d{1,2}/\d{4}$",
    },
    "Week_Start_Modifier": {"format": "-1", "regex": r"^-?\d+$"},
    "Week_SCM_Weekday": {
        "format": "2021-W01 - Wednesday - 1",
        "regex": r"^\d{4}-W\d{2} - [A-Za-z]{6,9}(?: - \d{1})?$",
    },
}


# %%
# Test Dataframes #


def test_df_days():
    pprint_df(df_days.head(10))
    # assert all items in format defined for column
    for column_name in df_days.columns:
        if column_name in dict_columns_to_regex_test.keys():
            date_format_description = dict_columns_to_regex_test[column_name]["format"]
            date_format_regex = re.compile(
                dict_columns_to_regex_test[column_name]["regex"]
            )
            first_val_in_col = df_days[column_name].iloc[0]
            print_logger(
                f"Testing column {column_name} which has values "
                f"like {first_val_in_col} matches format {date_format_description}"
            )
            for date_string in df_days[column_name]:
                if isinstance(date_string, int):
                    date_string = str(date_string)
                assert date_format_regex.match(
                    date_string
                ), f"{date_string} does not match format {date_format_description}"


def test_df_weeks():
    pprint_df(df_weeks.head(10))
    # assert all items in format defined for column
    for column_name in df_weeks.columns:
        if column_name in dict_columns_to_regex_test.keys():
            date_format_description = dict_columns_to_regex_test[column_name]["format"]
            date_format_regex = re.compile(
                dict_columns_to_regex_test[column_name]["regex"]
            )
            first_val_in_col = df_weeks[column_name].iloc[0]
            print_logger(
                f"Testing column {column_name} which has values "
                f"like {first_val_in_col} matches format {date_format_description}"
            )
            for date_string in df_weeks[column_name]:
                if isinstance(date_string, int):
                    date_string = str(date_string)
                assert date_format_regex.match(
                    date_string
                ), f"{date_string} does not match format {date_format_description}"


def test_df_scm_weeks():
    pprint_df(df_scm_weeks.head(10))
    # assert all items in format defined for column
    for column_name in df_scm_weeks.columns:
        if column_name in dict_columns_to_regex_test.keys():
            date_format_description = dict_columns_to_regex_test[column_name]["format"]
            date_format_regex = re.compile(
                dict_columns_to_regex_test[column_name]["regex"]
            )
            first_val_in_col = df_scm_weeks[column_name].iloc[0]
            print_logger(
                f"Testing column {column_name} which has values "
                f"like {first_val_in_col} matches format {date_format_description}"
            )
            for date_string in df_scm_weeks[column_name]:
                if isinstance(date_string, int):
                    date_string = str(date_string)
                assert date_format_regex.match(
                    date_string
                ), f"{date_string} does not match format {date_format_description}"


# %%
# Test Lists #


def test_all_days_list():
    pprint_ls(all_days_list)

    # regex assert all items in format '2021-01-01' without converting to date
    date_format_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    for date_string in all_days_list:
        assert date_format_pattern.match(
            date_string
        ), f"{date_string} does not match format YYYY-MM-DD"


def test_ls_days_slashed_no_pad():
    pprint_ls(ls_days_slashed_no_pad)

    # regex assert all items in format '1/1/2021' without converting to date
    date_format_pattern = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")

    for date_string in ls_days_slashed_no_pad:
        assert date_format_pattern.match(
            date_string
        ), f"{date_string} does not match format M/D/YYYY"


def test_all_days_list_dashed_desc():
    pprint_ls(all_days_list_dashed_desc)

    # regex assert all items in format '2021-01-01' without converting to date
    date_format_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    for date_string in all_days_list_dashed_desc:
        assert date_format_pattern.match(
            date_string
        ), f"{date_string} does not match format YYYY-MM-DD"


def test_all_weeks_list():
    pprint_ls(all_weeks_list)

    # regex assert all items in format '2021-W01' without converting to date
    date_format_pattern = re.compile(r"^\d{4}-W\d{2}$")

    for date_string in all_weeks_list:
        assert date_format_pattern.match(
            date_string
        ), f"{date_string} does not match format YYYY-MM-DD"


def test_get_current_time_in_timezone():
    current_datetime = get_current_time_in_timezone()
    print(current_datetime)
    assert current_datetime is not None


# %%
# Main #

if __name__ == "__main__":
    test_df_days()
    test_df_weeks()
    test_df_scm_weeks()
    test_all_days_list()
    test_ls_days_slashed_no_pad()
    test_all_days_list_dashed_desc()
    test_all_weeks_list()
    test_get_current_time_in_timezone()

    print_logger("All tests passed!")


# %%
