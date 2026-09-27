# google_mcp: anticipated errors reach the model as a bare "Error executing tool"

    found:  2026-09-26
    status: open
    verify: grep -c "ToolError" src/google_mcp.py   # 0 means still open

`src/google_mcp.py` and `src/utils/googlemcp_tools.py` report expected
failures with `raise ValueError(...)`: 22 of them, including the two hints
most likely to fire:

    src/google_mcp.py:124: raise ValueError(f"no {gtools.plural(label)} configured - see docs/setup_google_mcp.md")
    src/google_mcp.py:126: raise ValueError(f"several {gtools.plural(label)} configured ({available}) - pass {label}= to pick one")

## Evidence

The MCP SDK in dotfiles' venv
(`.venv/lib/python3.10/site-packages/mcp/server/mcpserver/tools/base.py`) only
passes a message through for its own `ToolError`:

    except (ToolError, ResourceError) as exc:
        raise ToolError(f"Error executing tool {self.name}: {exc}") from exc
    except Exception as exc:
        # A crash: the exception's own text stays on the server.
        raise UnexpectedToolError(f"Error executing tool {self.name}") from exc

Seen on the new mac server before it was fixed there on 2026-09-26: a refused
call returned exactly `Error executing tool messages_list_chats` with no
reason, and after re-raising as `ToolError` it returned `Error executing tool
messages_list_chats: no messages configured for this context - see
docs/setup_mac_mcp.md`. The Google server has the same shape, so on a
multi-mailbox context Claude sees a failure without the "pass mailbox=" hint
and has to guess.

## fix

Use the wrapper `src/mac_mcp.py` already has: a `tool(description)` decorator
that re-raises `ValueError` (and the other anticipated types) as
`mcp.server.mcpserver.exceptions.ToolError`, then replace every
`@server.tool(` in `src/google_mcp.py` with `@tool(`. Move the wrapper into a
shared module (for example `src/utils/mcpserver_tools.py`) so both servers use
one copy. Add the test `test_anticipated_failures_reach_the_model_with_their_reason`
from `tests/test_mac_mcp.py` to `tests/test_google_mcp.py`.

## blast radius

Tool results for failing calls gain their reason text; successful calls and
tool schemas are unchanged (`functools.wraps` keeps the signature the SDK reads,
as `test_wrapped_tools_keep_their_argument_schema` checks for the mac server).
The server stops logging these as crashes with tracebacks.

## not doing yet

Out of scope for the mac server work that found it. The shared-module move
touches both servers and wants its own commit.
