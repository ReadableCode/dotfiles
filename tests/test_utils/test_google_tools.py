# %%
# Imports #

import config_test_utils  # noqa F401
import pandas as pd
from src.utils.display_tools import pprint_df
from src.utils.google_tools import get_book_sheet_df

# %%
# Tests #


def test_get_book_sheet_df():
    df = get_book_sheet_df("TestApp", "TestApp")
    pprint_df(df.head(20))
    assert isinstance(df, pd.DataFrame)


# %%
# Main #

if __name__ == "__main__":
    test_get_book_sheet_df()


# %%
