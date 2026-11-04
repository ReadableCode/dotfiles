# %%
# Imports #

import functools

from mcp.server.mcpserver.exceptions import ToolError

# %%
# Variables #

# Failures a server raises on purpose - an account not configured, a store the
# OS will not open, a refused write. The SDK passes only its own ToolError's
# message through to the model and shows a bare "Error executing tool <name>"
# for any other exception type, so these are re-raised as ToolError to carry
# their reason through.
ANTICIPATED_ERRORS = (ValueError, PermissionError, FileNotFoundError, RuntimeError)

# %%
# Functions #


def tool_decorator(server):
    """
    A ``tool(description)`` decorator for ``server`` that registers the function
    the way ``server.tool(description=...)`` does, with every anticipated error
    re-raised as ``ToolError`` so its text reaches the model. ``functools.wraps``
    keeps the signature the SDK reads for the tool's argument schema.
    """

    def tool(description):
        def register(function):
            @functools.wraps(function)
            def wrapped(*args, **kwargs):
                try:
                    return function(*args, **kwargs)
                except ANTICIPATED_ERRORS as error:
                    raise ToolError(str(error)) from error

            return server.tool(description=description)(wrapped)

        return register

    return tool


__all__ = ["ANTICIPATED_ERRORS", "ToolError", "tool_decorator"]

# %%
