# %%
# Imports #

import calendar
import datetime
import os
import sys

import pandas as pd
from pytz import timezone

# append grandparent
if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config_utils import file_dir
from utils.google_tools import get_book_sheet_df

# %%
# Functions #


def get_datetime_format_string(format):
    """
    Returns a datetime format string based on a more readable format string.

    Args:
        format (str): The format option, which can be one of the following:
            - "%Y%m%d%H%M%S" or "number"
            - "%Y%m%d" or "YYYYMMDD"
            - "%H%M%S" or "HHMMSS" or "time_number"
            - "%Y-%m-%d %H:%M:%S" or "readable"
            - "%Y-%m-%d" or "YYYY-MM-DD"
            - "%H:%M" or "hour_mins"
            - "%A" or "Weekday"

    Returns:
        str: The corresponding datetime format string.
    """
    if format == "%Y%m%d%H%M%S" or format == "number":
        return "%Y%m%d%H%M%S"
    elif format == "%Y%m%d" or format == "YYYYMMDD":
        return "%Y%m%d"
    elif format == "%H%M%S" or format == "HHMMSS" or format == "time_number":
        return "%H%M%S"
    elif format == "%Y-%m-%d %H:%M:%S" or format == "readable":
        return "%Y-%m-%d %H:%M:%S"
    elif format == "%Y-%m-%d" or format == "YYYY-MM-DD":
        return "%Y-%m-%d"
    elif format == "%H:%M" or format == "hour_mins":
        return "%H:%M"
    elif format == "%A" or format == "Weekday":
        return "%A"
    else:
        print("Invalid format string")
        return format


def get_current_datetime(format="%Y%m%d%H%M%S"):
    """
    Returns the current datetime in the specified format string.

    Args:
        format (str): The format option for the datetime string
            which can be one of the following:
            - "%Y%m%d%H%M%S" or "number"
            - "%Y%m%d" or "YYYYMMDD"
            - "%H%M%S" or "HHMMSS" or "time_number"
            - "%Y-%m-%d %H:%M:%S" or "readable"
            - "%Y-%m-%d" or "YYYY-MM-DD"
            - "%H:%M" or "hour_mins"
            - "%A" or "Weekday"

    Returns:
        str: The current datetime formatted according to the string passed in.
    """
    return datetime.datetime.now().strftime(get_datetime_format_string(format))


# Custom date parsing function
def parse_mixed_date(date_str):
    # List of allowed date formats
    formats = ["%m/%d/%Y", "%Y-%m-%d"]

    # Try each format
    for fmt in formats:
        try:
            return datetime.datetime.strptime(date_str, fmt).strftime("%m/%d/%Y")
        except ValueError:
            pass

    # Handle Excel serial date format
    try:
        # Check if date_str is a number
        serial_date = int(date_str)
        # Excel serial date base (Windows default)
        base_date = datetime.datetime(1899, 12, 30)
        parsed_date = base_date + datetime.timedelta(days=serial_date)
        return parsed_date.strftime("%m/%d/%Y")
    except ValueError:
        pass

    # If all formats fail, print an error message
    print(f"Error: {date_str} does not match allowed formats.")
    return None


# %%
# Define Variables #

currentDT = get_current_datetime(get_datetime_format_string("number"))
current_date_time_readable = get_current_datetime(
    get_datetime_format_string("readable")
)


# %%
# Get Date Data #


df_days = pd.read_csv(
    os.path.join(file_dir, "df_days.csv"),
)

df_weeks = pd.read_csv(
    os.path.join(file_dir, "df_weeks.csv"),
)

df_scm_weeks = pd.read_csv(
    os.path.join(file_dir, "df_scm_weeks.csv"),
)


def build_date_csvs_from_sheets():
    df_days = get_book_sheet_df(
        "Weeks",
        "Days",
        start="A1",
        end="K",
    )
    df_days.to_csv(
        os.path.join(file_dir, "df_days.csv"),
        index=False,
    )

    df_weeks = get_book_sheet_df(
        "Weeks",
        "ImportableWeeks",
        start="A1",
        end="J",
    )
    df_weeks.to_csv(
        os.path.join(file_dir, "df_weeks.csv"),
        index=False,
    )

    df_scm_weeks = get_book_sheet_df(
        "Weeks",
        "SCM_Week_Days",
    )
    df_scm_weeks.to_csv(
        os.path.join(file_dir, "df_scm_weeks.csv"),
        index=False,
    )


# %%
# Date Lists #

all_days_list = df_days["dashed_pad_desc"].tolist()
ls_days_slashed_no_pad = df_days["slashed_nopad"].tolist()
all_days_list_dashed_desc = df_days["dashed_pad_desc"].tolist()
all_weeks_list = df_weeks["WeekString"].to_list()


# %%
# Imports to Dictionary Maps #

# from slashed_pad
dict_slashed_pad_date = dict(zip(df_days["slashed_pad"], df_days["WeekString"]))
dict_slashed_pad_to_dashed_pad_desc = dict(
    zip(df_days["slashed_pad"], df_days["dashed_pad_desc"])
)
dict_slashed_pad_to_slashed_nopad = dict(
    zip(df_days["slashed_pad"], df_days["slashed_nopad"])
)

# from slashed_nopad
dict_slashed_nopad_to_dashed_pad_desc = dict(
    zip(df_days["slashed_nopad"], df_days["dashed_pad_desc"])
)
dict_slashed_nopad_to_weekdaynumtext = dict(
    zip(df_days["slashed_nopad"], df_days["WeekDayNumDashName"])
)
dict_slashed_nopad_date = dict(zip(df_days["slashed_nopad"], df_days["WeekString"]))
dict_slashed_no_pad_to_slashed_pad = dict(
    zip(df_days["slashed_nopad"], df_days["slashed_pad"])
)

# from dict_slashed_pad_desc_date
dict_slashed_pad_desc_date = dict(
    zip(df_days["slashed_pad_desc"], df_days["WeekString"])
)

# from dashed_pad_desc
dict_dashed_pad_desc_to_weekdaynumtext = dict(
    zip(df_days["dashed_pad_desc"], df_days["WeekDayNumDashName"])
)
dict_dashed_pad_desc_to_scmweekdaynumtext = dict(
    zip(df_days["dashed_pad_desc"], df_days["SCMWeekDayNumDashName"])
)
dict_dashed_pad_desc_to_weekday = dict(
    zip(df_days["dashed_pad_desc"], df_days["WeekDayName"])
)
dict_dashed_pad_desc_to_slashed_pad = dict(
    zip(df_days["dashed_pad_desc"], df_days["slashed_pad"])
)
dict_dashed_pad_desc_date = dict(zip(df_days["dashed_pad_desc"], df_days["WeekString"]))
dict_dashed_pad_desc_to_slashed_nopad = dict(
    zip(df_days["dashed_pad_desc"], df_days["slashed_nopad"])
)

# from Week_SCM_Weekday
dict_scm_weeks = dict(
    zip(df_scm_weeks["Week_SCM_Weekday"], df_scm_weeks["dashed_pad_desc"])
)

# from WeekString
dict_mon_roster_dates = dict(
    zip(df_weeks["WeekString"], df_weeks["RosterForWeekBegin"])
)
dict_mon_roster_dates_full_year = dict(
    zip(df_weeks["WeekString"], df_weeks["RosterForWeekBeginSlashedNoPadFullYear"])
)

# from RosterForWeekBegin
dict_mon_roster_dates_inverted = dict(
    zip(df_weeks["RosterForWeekBegin"], df_weeks["WeekString"])
)


# %%
# Imports to Dictionary Maps #

dict_days = {
    "Sunday": "7 - Sunday",
    "Monday": "1 - Monday",
    "Tuesday": "2 - Tuesday",
    "Wednesday": "3 - Wednesday",
    "Thursday": "4 - Thursday",
    "Friday": "5 - Friday",
    "Saturday": "6 - Saturday",
}

dict_day_sort_order = {
    "Sunday": 1,
    "Monday": 2,
    "Tuesday": 3,
    "Wednesday": 4,
    "Thursday": 5,
    "Friday": 6,
    "Saturday": 7,
}

dict_day_abbrev_to_day = {
    "Mon": "Monday",
    "Tue": "Tuesday",
    "Wed": "Wednesday",
    "Thu": "Thursday",
    "Fri": "Friday",
    "Sat": "Saturday",
    "Sun": "Sunday",
}

dict_month_numbers = {
    "TOTAL": "00",
    "January": "01",
    "February": "02",
    "March": "03",
    "April": "04",
    "May": "05",
    "June": "06",
    "July": "07",
    "August": "08",
    "September": "09",
    "October": "10",
    "November": "11",
    "December": "12",
}

today = datetime.date.today()
today_date = today.strftime("%Y-%m-%d")
WorkingWeek = dict_dashed_pad_desc_date[today_date]
WeekNum = WorkingWeek.split("-")[1].replace("W", "")
Year = WorkingWeek.split("-")[0]

all_weeks_list = []
starting_year = 2018
starting_week = 1
for i in range(600):
    all_weeks_list.append(str(starting_year) + "-W" + str(starting_week).zfill(2))
    if starting_week == 52:
        starting_week = 1
        starting_year += 1
    else:
        starting_week += 1
df_week_list = pd.DataFrame(all_weeks_list, columns=["Week"])


# %%
# Main Functions #


def get_start_end_dates_for_week(week):
    ls_dates_in_week = [
        date[0] for date in dict_dashed_pad_desc_date.items() if date[1] == week
    ]
    return ls_dates_in_week[0], ls_dates_in_week[-1]


def week_span_to_week_list(base_week, num_weeks_back, num_weeks_forward):
    """
    Returns a list of weeks from a specified base week, including a specified number of
    weeks before and after the base week.

    Args:
        base_week (str): The week to start from, in the format "YYYY-WWW"
            e.g., "2022-W01".
        num_weeks_back (int): The number of weeks to go back from the base week.
        num_weeks_forward (int): The number of weeks to go forward from the base week.

    Returns:
        list: A list of week strings in the format "YYYY-WWW".
    """
    week_list = []

    for i in range(
        all_weeks_list.index(base_week) - num_weeks_back,
        all_weeks_list.index(base_week) + num_weeks_forward + 1,
    ):
        week_list.append(all_weeks_list[i])

    return week_list


def week_range_to_week_list(start_week, end_week):
    """
    Returns a list of weeks from the base week to the end week.

    Args:
        start_week (str): The week to start from, in the format "YYYY-WWW"
            e.g., "2022-W01".
        end_week (str): The week to end at, in the same format as start_week
            e.g., "2022-W52".

    Returns:
        list: A list of week strings in the format "YYYY-WWW",
        from start_week to end_week inclusive.
    """
    week_list = []

    for i in range(
        all_weeks_list.index(start_week),
        all_weeks_list.index(end_week) + 1,
    ):
        week_list.append(all_weeks_list[i])

    return week_list


def day_span_to_day_list(base_day, num_days_back, num_days_forward):
    """
    Returns a list of days from a specified base day, including a specified number of
        days before and after the base day.

    Args:
        base_day (str): The day to start from, in the format "YYYY-MM-DD"
            e.g., "2022-01-01".
        num_days_back (int): The number of days to go back from the base day.
        num_days_forward (int): The number of days to go forward from the base day.

    Returns:
        list: A list of day strings in the format "YYYY-MM-DD".
    """
    day_list = []

    for i in range(
        all_days_list.index(base_day) - num_days_back,
        all_days_list.index(base_day) + num_days_forward + 1,
    ):
        day_list.append(all_days_list[i])

    return day_list


def day_range_to_day_list(start_day, end_day):
    """
    Returns a list of days from the start day to the end day.

    Args:
        start_day (str): The day to start from, in the format "YYYY-MM-DD"
            e.g., "2022-01-01".
        end_day (str): The day to end on, in the same format as start_day
            e.g., "2022-01-10".

    Returns:
        list: A list of day strings in the format "YYYY-MM-DD"
            from start_day to end_day inclusive.
    """
    day_list = []

    for i in range(
        all_days_list.index(start_day),
        all_days_list.index(end_day) + 1,
    ):
        day_list.append(all_days_list[i])

    return day_list


def day_span_to_day_list_no_pad(base_day, num_days_back, num_days_forward):
    """
    Returns a list of days from a specified base day, including a specified number
        of days before and after the base day, with the format "YYYY-M-D".

    Args:
        base_day (str): The day to start from, in the format "YYYY-M-D"
            e.g., "2022-1-1".
        num_days_back (int): The number of days to go back from the base day.
        num_days_forward (int): The number of days to go forward from the base day.

    Returns:
        list: A list of day strings in the format "YYYY-M-D".
    """
    day_list = []

    for i in range(
        ls_days_slashed_no_pad.index(base_day) - num_days_back,
        ls_days_slashed_no_pad.index(base_day) + num_days_forward + 1,
    ):
        day_list.append(ls_days_slashed_no_pad[i])

    return day_list


def getDiffWeek(base_week, num_weeks_diff):
    """
    Returns the week a specified number of weeks away from the base week.

    Args:
        base_week (str): The week to start from, in the format "YYYY-WWW"
            e.g., "2022-W01".
        num_weeks_diff (int): The number of weeks to go forward (positive value)
            or backward (negative value) from the base week.

    Returns:
        str: A week in the format "YYYY-WWW", representing the week num_weeks_diff
            away from base_week.
    """
    base_week_index = all_weeks_list.index(base_week)
    outputWeek = all_weeks_list[base_week_index + num_weeks_diff]
    return outputWeek


def getDiffDay(base_day, num_days_diff):
    """
    Returns the day a specified number of days away from the base day.

    Args:
        base_day (str): The day to start from, in the format "YYYY-MM-DD"
            e.g., "2022-01-01".
        num_days_diff (int): The number of days to go forward (positive value) or
            backward (negative value) from the base day.

    Returns:
        str: A day in the format "YYYY-MM-DD"
            representing the day num_days_diff away from base_day.
    """
    base_day_index = all_days_list.index(base_day)
    outputDay = all_days_list[base_day_index + num_days_diff]
    return outputDay


def get_weeks_out_from_week(weekMade, weekRegards):
    """
    Returns the number of weeks between two specified weeks.

    Args:
        weekMade (str): The starting week, in the format "YYYY-WWW", e.g., "2022-W01".
        weekRegards (str): The ending week, in the same format as weekMade
            e.g., "2022-W52".

    Returns:
        int: The number of weeks between weekMade and weekRegards.
    """
    weeksOut = all_weeks_list.index(weekRegards) - all_weeks_list.index(weekMade)
    return weeksOut


def floatHourToTime(fh):
    """
    Converts a float hour value to a time tuple in the format of:
        (hours, minutes, seconds).

    Args:
        fh (float): The float hour to convert.

    Returns:
        tuple: A time represented as a tuple in the format (hours, minutes, seconds).
    """
    hours, hourSeconds = divmod(fh, 1)
    minutes, seconds = divmod(hourSeconds * 60, 1)
    return (
        int(hours),
        int(minutes),
        int(seconds * 60),
    )


def convert_week(convert_week):
    """
    Converts a week from the Sanders format ('2242') to the standard ISO format:
        ('2022-W42').

    Args:
        convert_week (str): The week to convert, in Sanders format
            (e.g., '2242' representing the 42nd week of 2022).

    Returns:
        str: The converted week in the standard ISO format (e.g., '2022-W42').
    """
    WeekString = "20" + convert_week[0:2] + "-W" + convert_week[2:4]
    return WeekString


def fix_weeks(df):
    """
    Fixes the weeks in a DataFrame, converting from the Sanders format:
        ('2242') to the standard ISO format ('2022-W42').

    Args:
        df (DataFrame): The DataFrame with weeks in the Sanders format to be fixed.

    Returns:
        DataFrame: The DataFrame with weeks converted to the standard ISO format.
    """
    df["WeekString"] = df["WeekString"].apply(convert_week)
    return df


def get_today_date(format_string="YYYY-MM-DD"):
    """
    Returns the current date in the format specified by the format_string.

    Args:
        format_string (str): The format to return the date in. Currently
            the only option is "YYYY-MM-DD".

    Returns:
        str: The current date in the format specified by format_string.
    """
    dict_formats = {"YYYY-MM-DD": "%Y-%m-%d"}
    today = datetime.date.today()
    return today.strftime(dict_formats[format_string])


def excel_date_to_datetime(excel_date):
    """
    Converts an Excel date to a datetime object.

    Args:
        excel_date (int): The Excel date to convert.

    Returns:
        datetime: The converted datetime object.
    """
    dt = datetime.datetime.fromordinal(
        datetime.datetime(1900, 1, 1).toordinal() + int(excel_date) - 2
    )
    hour, minute, second = floatHourToTime(excel_date % 1)
    dt = dt.replace(hour=hour, minute=minute, second=second)
    return dt


def extract_use_weeks():
    """
    Extracts the use weeks from the database, which include 12 weeks back and
        12 weeks forward from the current week.

    Returns:
        DataFrame: A DataFrame containing the use weeks.
    """
    ls_use_weeks = week_span_to_week_list(WorkingWeek, 12, 12)
    df_use_weeks = pd.DataFrame(ls_use_weeks, columns=["Week"])
    return df_use_weeks


def date_string_to_excel_date(date_string):
    """
    Converts a date from the format "YYYY-MM-DD" to an Excel date.

    Args:
        date_string (str): The date to convert, in the format "YYYY-MM-DD".

    Returns:
        int: The converted Excel date.
    """
    dt = datetime.datetime.strptime(date_string, "%Y-%m-%d")
    dt = (dt - datetime.datetime(1900, 1, 1)).days + 2
    return dt


def excel_date_to_date_string(excel_date):
    """
    Converts an Excel date to a date in the format "YYYY-MM-DD".

    Args:
        excel_date (int): The Excel date to convert.

    Returns:
        str: The converted date in the format "YYYY-MM-DD".
    """
    dt = datetime.datetime.fromordinal(
        datetime.datetime(1900, 1, 1).toordinal() + int(excel_date) - 2
    )
    hour, minute, second = floatHourToTime(excel_date % 1)
    dt = dt.replace(hour=hour, minute=minute, second=second)
    return str(dt.strftime("%Y-%m-%d"))


def convert_fix_date_to_no_pad(date):
    if date in dict_slashed_pad_to_slashed_nopad.keys():
        return dict_slashed_pad_to_slashed_nopad[date]
    elif date in dict_slashed_no_pad_to_slashed_pad.keys():
        return date
    elif date in dict_dashed_pad_desc_to_slashed_nopad.keys():
        return dict_dashed_pad_desc_to_slashed_nopad[date]
    else:
        print("Date not converted to No_Pad: ", date)
        raise ValueError


def convert_fix_date_to_pad(date):
    if isinstance(date, pd._libs.tslibs.timestamps.Timestamp):
        date = date.strftime("%Y-%m-%d")

    if " " in date:
        date = date.split(" ")[0]

    if date in dict_slashed_no_pad_to_slashed_pad.keys():
        return dict_slashed_no_pad_to_slashed_pad[date]
    elif date in dict_slashed_pad_to_slashed_nopad.keys():
        return date
    elif date in dict_dashed_pad_desc_to_slashed_pad.keys():
        return dict_dashed_pad_desc_to_slashed_pad[date]
    else:
        # try to convert to date with excel date
        try:
            date = excel_date_to_date_string(date)
            if date in dict_dashed_pad_desc_to_slashed_pad.keys():
                return dict_dashed_pad_desc_to_slashed_pad[date]
        except Exception:
            pass
        print("Date not converted to Pad: ", date)
        raise ValueError


def get_initial_accounting_period_due_date(date):
    """
    Returns the initial date based on last day of current/prior month.

    Args:
        Date (str): The date to start from, generally today, in the format "YYYY-MM-DD", e.g., "2024-01-01".

    Returns:
        Date (dt): The first day of the previous month after adding 12 days to the process date.
    """
    date_dt = datetime.datetime.strptime(date, "%Y-%m-%d")
    date_dt = datetime.timedelta(days=12) + date_dt
    current_month_number = date_dt.month
    current_year = date_dt.year
    if current_month_number == 1:
        current_year = current_year - 1
        previous_month_number = 12
    else:
        previous_month_number = current_month_number - 1
    _, last_day_of_month = calendar.monthrange(current_year, previous_month_number)
    initial_accounting_period_date = datetime.datetime(
        current_year, previous_month_number, last_day_of_month
    )
    return initial_accounting_period_date


def get_year_quarter_from_week_string(week_string):
    year = week_string.split("-")[0]
    week = week_string.split("-")[1].replace("W", "")
    quarter = (int(week) - 1) // 13 + 1
    return year, quarter


def get_year_quarter_from_date(date_string):
    year = date_string.split("-")[0]
    month = date_string.split("-")[1]
    quarter = str(int(month) // 4 + 1)
    return year, quarter


def get_quarter_string_from_date(date_string):
    year = date_string.split("-")[0]
    month = date_string.split("-")[1]
    quarter = str(int(month) // 4 + 1)
    return f"{year}-Q{quarter}"


def get_reporting_month_num_from_week(week):
    key = f"{week} - Thursday - 2"
    thursday_2_of_week = dict_scm_weeks[key]
    month_of_thursday_2 = thursday_2_of_week[5:7]
    return month_of_thursday_2


def get_num_weeks_in_reporting_month(year_month):
    ls_thurs_2_in_year_month = []
    for key, value in dict_scm_weeks.items():
        if "Thursday - 2" in key:
            if value[0:7] == year_month:
                ls_thurs_2_in_year_month.append(value)
    return len(ls_thurs_2_in_year_month)


def get_ls_weeks_in_reporting_month(year_month):
    """
    Returns a list of week strings in the provided month that contain "Thursday - 2".

    Args:
        year_month (str): A string representing the year and month in the form:
            "YYYY-MM", e.g., "2023-08" for August 2023.

    Returns:
        list: A list of strings for each week in the month. For example:
              ["2023-W31", "2023-W32", "2023-W33", "2023-W34", "2023-W35"].

    Example:
        If 'year_month' is "2023-08" and there are entries in dict_scm_weeks with
            "Thursday - 2" for weeks
        "2023-W31", "2023-W32", "2023-W33", "2023-W34", and "2023-W35",
            the function will return:
        ["2023-W31", "2023-W32", "2023-W33", "2023-W34", "2023-W35"].
    """
    ls_thurs_2_in_year_month = []
    for key, value in dict_scm_weeks.items():
        if "Thursday - 2" in key:
            if value[0:7] == year_month:
                ls_thurs_2_in_year_month.append(key[:8])
    return ls_thurs_2_in_year_month


def get_week_from_yearweek(yearweek):
    yearweek = str(yearweek)
    year = f"20{yearweek[:2]}"
    week = yearweek[-2:]
    week = f"{year}-W{week}"
    return week


def get_yearweek_from_week(week):
    Year = week[:4]
    Week = week[-2:]
    YearWeek = str(Year)[2:] + Week

    return YearWeek


def get_start_end_week(week):
    start_date = df_scm_weeks[
        df_scm_weeks["Week_SCM_Weekday"] == f"{week} - Thursday - 1"
    ]["dashed_pad_desc"].values[0]
    end_date = df_scm_weeks[
        df_scm_weeks["Week_SCM_Weekday"] == f"{week} - Thursday - 2"
    ]["dashed_pad_desc"].values[0]

    return start_date, end_date


def get_start_end_week_exclusive(week):
    start_date = df_scm_weeks[
        df_scm_weeks["Week_SCM_Weekday"] == f"{week} - Thursday - 1"
    ]["dashed_pad_desc"].values[0]
    end_date = df_scm_weeks[
        df_scm_weeks["Week_SCM_Weekday"] == f"{week} - Wednesday - 2"
    ]["dashed_pad_desc"].values[0]

    return start_date, end_date


def get_month_name_from_num(month_num):
    """
    Returns the name of the month corresponding to the given month number.

    Args:
        month_num (int or str): The month number, which can be an integer from 1 to 12

    Returns:
        str: The name of the month.

    Raises:
        KeyError: If the given month number is not found in the dictionary.

    """
    month_num = str(month_num)
    for month_name in dict_month_numbers:
        if dict_month_numbers[month_name] == month_num:
            return month_name


def get_current_time_in_timezone(timezone_str="US/Central"):
    return datetime.datetime.now(timezone(timezone_str))


def is_thursday_before_5pm_cst():
    # Get current UTC time
    now_cst = get_current_time_in_timezone("US/Central")

    # Get current day of the week
    day_of_week = now_cst.weekday()

    # Check if it is Thursday
    if day_of_week != 3:
        return False

    # Check if it is before 5 PM
    if now_cst.hour < 17:
        return True
    else:
        return False


# %%
# Define Functions #

if __name__ == "__main__":
    print("Running as main")
    print(get_current_datetime("YYYYMMDD"))
    print(get_current_datetime("Weekday"))

    print(excel_date_to_date_string(44924))  # should be 2022-12-29 as a string

# %%
