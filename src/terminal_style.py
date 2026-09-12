"""Terminal-navy output for the stdlib-only command-line tools in src/.

Two jobs, shared so every tool looks the same:

- ``add_help_page`` / ``render_page``: a tool's ``--help`` as a tldr-style page
  (a summary, the steps in the order they run, examples) instead of argparse's
  flag dump.
- ``section`` / ``paint``: the ``// title`` step headers and coloured status
  lines a tool prints while it runs.

A help page lives in the tool's own source (a ``HELP_PAGE`` string), never in a
shell alias: an alias only launches the tool, so ``--help`` reaches the tool.

Page format, a tldr page plus numbered steps:

    # tool_name
    > one or more summary lines
    ## what happens
    1. a step, in the order it runs
       an indented line is detail under the step above
    ## examples
    - what the example does:
    `the command to type`

Inline `code` is highlighted, and ``$gitDir`` becomes the repos directory the
shell resolved, so the page shows the real paths a tool would touch. Blank
lines in a page are ignored; the renderer owns the spacing.

Colour only on a real terminal and never when NO_COLOR is set, like
``deploy_configs.py``. The values are the style-terminal-navy tokens as 24-bit
sequences, never palette numbers (a terminal's 16 colours are whatever its
profile says). They copy ``readable_utils.design_tokens`` because these tools
run with a bare ``python3`` before any venv exists; a test keeps the two equal.
"""

import argparse
import os
import re
import sys

# readable_utils.design_tokens values, by the role each plays in terminal output
TOKENS = {
    "ink": "#dbe4f0",  # INK: names, section titles, step text, inline code
    "ink2": "#9fb0c3",  # INK_2: summaries and descriptions
    "muted": "#7d8b9e",  # MUTED: detail under a step
    "green": "#56d364",  # GREEN_BRIGHT: the prompt glyph, // and step numbers
    "amber": "#e3b341",  # AMBER_BRIGHT: the command to type, warnings
    "red": "#f87171",  # RED: failures
}

PROMPT = "❯"
STEP = re.compile(r"^(\d+)\.\s+(.*)$")
INLINE_CODE = re.compile(r"`([^`]+)`")


def use_color(stream, environ=None):
    """Colour only on a real terminal, and never when NO_COLOR is set."""
    environ = os.environ if environ is None else environ
    return stream.isatty() and "NO_COLOR" not in environ


def paint(text, role, color, bold=False):
    if not color or not text:
        return text
    hex_value = TOKENS[role]
    red, green, blue = (int(hex_value[i : i + 2], 16) for i in (1, 3, 5))
    weight = "1;" if bold else ""
    return f"\033[{weight}38;2;{red};{green};{blue}m{text}\033[0m"


def section(title, color):
    """A ``// title`` header: the slashes in bright green, the title in ink."""
    return paint("//", "green", color, bold=True) + " " + paint(title, "ink", color, bold=True)


def inline(text, role, color):
    """Prose in ``role``, each `code` span in bold ink with its backticks dropped."""
    pieces = INLINE_CODE.split(text)
    return "".join(
        paint(piece, "ink", color, bold=True) if index % 2 else paint(piece, role, color)
        for index, piece in enumerate(pieces)
    )


def display_git_dir(git_dir, home=None):
    """The repos directory as a person reads it: no trailing slash, home as ~."""
    if not git_dir:
        return ""
    path = git_dir.rstrip("/\\") or git_dir
    home = (home if home is not None else os.path.expanduser("~")).rstrip("/\\")
    if home and path.startswith(home) and path[len(home) : len(home) + 1] in ("", "/", "\\"):
        path = "~" + path[len(home) :]
    return path


def render_page(lines, color, git_dir):
    """A help page as terminal text, ending in a newline."""
    out = []
    after_header = False
    for raw in lines:
        line = raw.rstrip("\r\n")
        if git_dir:
            line = line.replace("$gitDir", git_dir)
        text = line.strip()
        if not text:
            continue
        step = STEP.match(text)
        if line.startswith("## "):
            out += ["", section(text[3:], color)]
            after_header = True
            continue
        if line.startswith("# "):
            out.append(paint(PROMPT + " ", "green", color, bold=True) + paint(text[2:], "ink", color, bold=True))
        elif line.startswith("> "):
            out.append("  " + inline(text[2:], "ink2", color))
        elif line[0].isspace():
            out.append("      " + inline(text, "muted", color))
        elif step:
            if not after_header:
                out.append("")
            number = paint(step.group(1).rjust(2), "green", color, bold=True)
            out.append(f"  {number}  " + inline(step.group(2), "ink", color))
        elif line.startswith("- "):
            if not after_header:
                out.append("")
            out.append("  " + inline(text[2:].rstrip(":"), "ink2", color))
        elif len(text) > 1 and text.startswith("`") and text.endswith("`"):
            command = paint(text[1:-1], "amber", color, bold=True)
            out.append("    " + paint(PROMPT + " ", "green", color, bold=True) + command)
        else:
            out.append("  " + inline(text, "ink2", color))
        after_header = False
    return "\n".join(out) + "\n"


def print_page(page_text, stream=None, environ=None):
    stream = sys.stdout if stream is None else stream
    environ = os.environ if environ is None else environ
    if hasattr(stream, "reconfigure"):
        # A legacy Windows console has no glyph for the prompt; never crash on it.
        stream.reconfigure(errors="replace")
    git_dir = display_git_dir(environ.get("gitDir", ""))
    stream.write(render_page(page_text.splitlines(), use_color(stream, environ), git_dir))


class _HelpPageAction(argparse.Action):
    def __init__(self, option_strings, dest, page, **kwargs):
        super().__init__(option_strings, dest, nargs=0, default=argparse.SUPPRESS, **kwargs)
        self.page = page

    def __call__(self, parser, namespace, values, option_string=None):
        print_page(self.page)
        parser.exit()


def add_help_page(parser, page_text):
    """Give ``parser`` (built with ``add_help=False``) a -h/--help that prints the page."""
    parser.add_argument(
        "-h", "--help", action=_HelpPageAction, page=page_text, help="show what this does, step by step"
    )
