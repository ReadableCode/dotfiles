# %%
# Imports #

import os
import platform

# %%
# Functions #


def get_uppercase_hostname():
    HOSTNAME = os.getenv("HOSTNAME")

    if HOSTNAME is None:
        system_platform = platform.system().upper()
        if system_platform == "WINDOWS":
            try:
                HOSTNAME = os.environ["COMPUTERNAME"].upper()
            except KeyError:
                HOSTNAME = os.environ["HOSTNAME"].upper()
        else:
            try:
                import socket

                HOSTNAME = socket.gethostname().upper()
            except KeyError:
                pass  # Handle other platforms if needed

    return HOSTNAME


# %%
