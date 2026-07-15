# %%
# Imports #

import argparse
import sys
import time

from config import grandparent_dir, parent_dir
from rich.console import Console
from rich.text import Text
from utils.host_tools import get_uppercase_hostname
from utils.statusboard_tools import fetch_panel, load_panels

# %%
# Variables #

REPO_ROOT = parent_dir
CREDENTIALS_ROOT = grandparent_dir


# %%
# Rendering #


def result_renderable(result):
    """Turn a PanelResult into a rich renderable (used by both the TUI and --once)."""
    if not result.ok:
        return Text(result.body, style="red")
    if result.kind == "ansi":
        return Text.from_ansi(result.body) if result.body else Text("(no output)", style="dim")
    if not result.body:
        return Text("nothing awaiting review 🎉", style="green")
    text = Text()
    for index, row in enumerate(result.body):
        if index:
            text.append("\n")
        text.append(row["text"], style=f"bold link {row['url']}")
        if row.get("meta"):
            text.append(f"\n    {row['meta']}", style="dim")
    return text


# %%
# TUI #


def build_app(panels, local_hostname):
    """
    Construct the Textual app class lazily so --once (and the unit tests)
    never need textual imported at module import time.
    """
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.widgets import Footer, Header, Label, ProgressBar, Static

    class Panel(Vertical):
        """
        One board panel: bordered output area that refetches itself on its own
        interval (panels poll independently), with a real-time bar at the
        bottom filling toward the next poll - indeterminate while a fetch is
        actually in flight.
        """

        def __init__(self, panel):
            super().__init__()
            self.panel = panel
            self.border_title = panel["name"]
            self.deadline = None  # monotonic time of the next scheduled poll; None = fetching

        def compose(self) -> ComposeResult:
            yield Static("loading…", markup=False, classes="panel-output")
            with Horizontal(classes="panel-footer"):
                yield ProgressBar(total=None, show_eta=False, show_percentage=False)
                yield Label("refreshing…", classes="panel-countdown")

        def on_mount(self):
            self.refresh_panel()
            self.set_interval(self.panel["interval"], self.refresh_panel)
            self.set_interval(1.0, self._tick)

        def refresh_panel(self):
            self.deadline = None
            self._fired = time.monotonic()
            bar = self.query_one(ProgressBar)
            bar.total = None  # indeterminate pulse while the worker runs
            self.query_one(".panel-countdown", Label).update("refreshing…")
            self.run_worker(self._fetch, thread=True, group=self.panel["name"], exclusive=True)

        def _fetch(self):
            result = fetch_panel(self.panel, CREDENTIALS_ROOT, local_hostname)
            self.app.call_from_thread(self._show, result)

        def _show(self, result):
            self.set_class(not result.ok, "error")
            state = result.summary or ("ok" if result.ok else "error")
            self.border_subtitle = f"{state} · {time.strftime('%H:%M:%S')}"
            self.query_one(".panel-output", Static).update(result_renderable(result))
            # the poll timer fires one interval after the previous FIRE, not
            # after completion - anchor the countdown to fetch start so the
            # bar reaches full just as the timer actually fires
            self.deadline = self._fired + self.panel["interval"]
            bar = self.query_one(ProgressBar)
            bar.total = self.panel["interval"]
            bar.progress = 0

        def _tick(self):
            if self.deadline is None:
                return  # fetch in flight - bar is pulsing
            remaining = max(0, self.deadline - time.monotonic())
            interval = self.panel["interval"]
            self.query_one(ProgressBar).progress = interval - remaining
            minutes, seconds = divmod(int(remaining), 60)
            self.query_one(".panel-countdown", Label).update(f"next in {minutes}m{seconds:02d}s")

    class StatusBoardApp(App):
        TITLE = "status board"
        BINDINGS = [("q", "quit", "quit"), ("r", "refresh_all", "refresh all")]
        CSS = """
        Panel {
            border: round $primary;
            border-title-color: $accent;
            height: auto;
            max-height: 30;
            margin: 0 1 1 1;
            padding: 0 1;
        }
        Panel.error { border: round red; }
        .panel-output { height: auto; max-height: 26; overflow-y: auto; }
        .panel-footer { height: 1; margin-top: 1; }
        .panel-footer ProgressBar { width: 1fr; }
        .panel-footer Bar { width: 1fr; }
        .panel-countdown { color: $text-muted; margin-left: 2; }
        """

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with VerticalScroll():
                for panel in panels:
                    yield Panel(panel)
            yield Footer()

        def action_refresh_all(self):
            for widget in self.query(Panel):
                widget.refresh_panel()

    return StatusBoardApp


# %%
# Main #


def run_once(panels, local_hostname):
    """Fetch every panel sequentially and print a static board (sanity check / headless use)."""
    console = Console()
    for panel in panels:
        result = fetch_panel(panel, CREDENTIALS_ROOT, local_hostname)
        state = result.summary or ("ok" if result.ok else "error")
        console.rule(f"[bold]{panel['name']}[/bold] · {state}", style="green" if result.ok else "red")
        console.print(result_renderable(result))
        console.print()
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Long-lived TUI status board; panels come from <context>_statusboard.yaml "
        "configs discovered in sibling *_credentials repos (plus an optional "
        "statusboard.yaml in this repo)."
    )
    parser.add_argument("--once", action="store_true", help="fetch every panel once, print, and exit (no TUI)")
    parser.add_argument(
        "--config",
        default=None,
        help="load only this statusboard config file, skipping discovery (for testing)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    panels, config_paths = load_panels(CREDENTIALS_ROOT, REPO_ROOT, config_path=args.config)
    if not panels:
        print(
            "No statusboard panels found - add a <context>_statusboard.yaml to a sibling "
            "*_credentials repo (see docs/setup_status_board.md)"
        )
        return 1
    local_hostname = get_uppercase_hostname() or ""
    print(f"configs: {', '.join(config_paths)}")
    if args.once:
        return run_once(panels, local_hostname)
    app_class = build_app(panels, local_hostname)
    app_class().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())


# %%
