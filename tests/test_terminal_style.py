"""Unit tests for src/terminal_style.py, the help pages and step headers of the stdlib-only tools."""

import argparse
import re

import config_test_utils  # noqa F401
import pytest
from readable_utils import design_tokens
from src import terminal_style

PAGE = """# demo

> does a demo thing under `$gitDir`.

## what happens

1. first step
   runs `src/first.py`
2. second step

## examples

- run the demo:

`demo`
"""


def test_render_page_plain_layout():
    git_dir = terminal_style.display_git_dir("/home/me/GitHub/", home="/home/me")
    assert terminal_style.render_page(PAGE.splitlines(), False, git_dir) == (
        "❯ demo\n"
        "  does a demo thing under ~/GitHub.\n"
        "\n"
        "// what happens\n"
        "   1  first step\n"
        "      runs src/first.py\n"
        "\n"
        "   2  second step\n"
        "\n"
        "// examples\n"
        "  run the demo\n"
        "    ❯ demo\n"
    )


def test_unset_git_dir_leaves_the_placeholder():
    assert "under $gitDir." in terminal_style.render_page(PAGE.splitlines(), False, "")


def test_color_uses_24_bit_tokens_never_palette_numbers():
    out = terminal_style.render_page(PAGE.splitlines(), True, "~/GitHub")
    assert "\033[1;38;2;86;211;100m//" in out  # green-bright section slashes
    assert "\033[1;38;2;227;179;65mdemo" in out  # amber-bright command to type
    assert not re.search(r"\033\[(?:\d+;)*(?:3[0-7]|9[0-7])m", out)


def test_tokens_match_readable_utils_design_tokens():
    assert terminal_style.TOKENS == {
        "ink": design_tokens.INK,
        "ink2": design_tokens.INK_2,
        "muted": design_tokens.MUTED,
        "green": design_tokens.GREEN_BRIGHT,
        "amber": design_tokens.AMBER_BRIGHT,
        "red": design_tokens.RED,
    }


def test_section_plain():
    assert terminal_style.section("deploying configs", False) == "// deploying configs"


def test_display_git_dir_collapses_home_and_trailing_slash():
    assert terminal_style.display_git_dir("/home/me/GitHub/", home="/home/me") == "~/GitHub"
    assert terminal_style.display_git_dir("/home/meow/GitHub", home="/home/me") == "/home/meow/GitHub"
    assert terminal_style.display_git_dir("", home="/home/me") == ""


def test_add_help_page_prints_the_page_and_exits_zero(capsys, monkeypatch):
    monkeypatch.setenv("gitDir", "/somewhere/GitHub/")
    parser = argparse.ArgumentParser(add_help=False)
    terminal_style.add_help_page(parser, PAGE)
    with pytest.raises(SystemExit) as exited:
        parser.parse_args(["--help"])
    assert exited.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("❯ demo\n")
    assert "under /somewhere/GitHub." in out
