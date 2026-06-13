# %%
# Imports #

import datetime
import os
import time

import pandas as pd
from config_test_utils import data_dir, grandparent_dir
from dotenv import load_dotenv
from src.utils.display_tools import print_logger
from src.utils.gmail_tools import (
    get_attachment_from_search_string,
    get_email_addresses_from_search_string,
    get_gmail_service,
    send_email,
)

# %%
# Load Environment #

# source .env file
dotenv_path = os.path.join(grandparent_dir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

# %%
# Variables #

email_address_for_testing = os.getenv("EMAIL_ADDRESS_FOR_TESTING")


# %%
# Tests #


def test_get_gmail_service():
    gmail_service = get_gmail_service()
    assert gmail_service is not None
    print_logger(f"gmail_service: {gmail_service}")


def test_send_email():
    # generate test csv file
    test_csv_path = os.path.join(data_dir, "test_send_email.csv")
    test_df = pd.DataFrame(
        {
            "col1": [1, 2, 3],
            "col2": ["a", "b", "c"],
            "col3": ["x", "y", "z"],
        }
    )
    test_df.to_csv(test_csv_path, index=False)

    send_email(
        email_address_for_testing.split(".")[0],
        email_address_for_testing,
        [email_address_for_testing],
        "Gmail Test Python",
        "Gmail Test Python with a test email in the body.\n\nSent on: "
        + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        + "\n\ntestemail@testemail.com",
        ls_attachment_path=[test_csv_path],
    )


def test_get_email_addresses_from_search_string():
    # run the test above twice, handles running the tests out of order
    test_send_email()
    # wait for the message from the previous test to come in
    time.sleep(10)
    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    gmail_search_string = f"Gmail Test Python after:{today_date}"
    print(f" ########### Searching for: {gmail_search_string} ###########")

    email_addresses = get_email_addresses_from_search_string(
        gmail_search_string,
    )
    print(email_addresses)
    assert "testemail@testemail.com" in email_addresses


def test_get_attachment_from_search_string():
    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    gmail_search_string = f"Gmail Test Python after:{today_date}"
    print(f" ########### Searching for: {gmail_search_string} ###########")

    ls_paths_with_file_names = get_attachment_from_search_string(
        gmail_search_string,
        data_dir,
        force_download=True,
    )

    print(ls_paths_with_file_names)
    assert os.path.join(data_dir, "test_send_email.csv") in ls_paths_with_file_names


# %%
# Main #

if __name__ == "__main__":
    test_get_gmail_service()
    test_send_email()
    test_get_email_addresses_from_search_string()
    test_get_attachment_from_search_string()

# %%
