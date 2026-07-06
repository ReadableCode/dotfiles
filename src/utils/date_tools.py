# %%
# Imports #

from datetime import datetime

from pytz import timezone

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
    elif (
        format == "%Y-%m-%d %H:%M:%S"
        or format == "%Y-%m-%d %H:%M:%S %Z"
        or format == "readable"
    ):
        return "%Y-%m-%d %H:%M:%S %Z"
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
    Returns the current datetime in the specified format string, always in CST timezone.

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
    cst = timezone("America/Chicago")
    now_cst = datetime.now().astimezone(cst)

    return now_cst.strftime(get_datetime_format_string(format))


# %%
# Main #

if __name__ == "__main__":
    print("Running as main")
    print(get_current_datetime("YYYYMMDD"))
    print(get_current_datetime("Weekday"))

# %%
