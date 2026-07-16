# %%
# Imports #

import argparse
import platform
import subprocess
import sys
import time
import webbrowser

from config import grandparent_dir, parent_dir
from rich.console import Console
from rich.style import Style
from rich.text import Text
from readable_utils.host_tools import get_uppercase_hostname
from utils.statusboard_tools import fetch_panel, load_panels

# %%
# Variables #

REPO_ROOT = parent_dir
CREDENTIALS_ROOT = grandparent_dir

# Panel `browser:` values -> platform-specific launch names. Anything not in
# this table is passed through as the app/binary name verbatim.
BROWSER_APPS = {
    "edge": {"Darwin": "Microsoft Edge", "Windows": "msedge", "Linux": "microsoft-edge"},
    "chrome": {"Darwin": "Google Chrome", "Windows": "chrome", "Linux": "google-chrome"},
    "firefox": {"Darwin": "Firefox", "Windows": "firefox", "Linux": "firefox"},
    "safari": {"Darwin": "Safari"},
}


# %%
# Browser launching #


def browser_open_argv(browser, url, system=None):
    """
    The argv that opens url in the named browser on this platform, or None
    when no browser is named (caller falls back to the OS default handler).
    """
    if not browser:
        return None
    system = system or platform.system()
    app = BROWSER_APPS.get(browser.lower(), {}).get(system, browser)
    if system == "Darwin":
        return ["open", "-a", app, url]
    if system == "Windows":
        # `start` resolves app-execution aliases like msedge/chrome
        return ["cmd", "/c", "start", "", app, url]
    return [app, url]


def open_link(url, browser=None):
    """Open url in the panel's configured browser, or the OS default when none is set."""
    argv = browser_open_argv(browser, url)
    if argv is None:
        webbrowser.open(url)
        return
    subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# %%
# Rendering #


def legend_text():
    """One-line key for the PR badge symbols, shown at the bottom of the board."""
    text = Text()
    for index, (badge, style, label) in enumerate([
        ("✏", "bold red", "unsubmitted draft"),
        ("●", "bold cyan", "needs your review"),
        ("✋", "bold yellow", "waiting on author"),
        ("💬", "dim", "you commented"),
        ("⬆", "bold magenta", "your PR"),
        ("◌", "dim", "draft, parked"),
    ]):
        if index:
            text.append("   ", style="dim")
        text.append(badge, style=style)
        text.append(f" {label}", style="dim")
    return text


def result_renderable(result, browser=None, tui=False):
    """
    Turn a PanelResult into a rich renderable (used by both the TUI and --once).

    Link rows render differently per mode: --once emits plain OSC 8 hyperlinks
    (the terminal handles clicks), but inside the TUI Textual captures the
    mouse, so rows carry an @click action meta that routes through
    app.action_open_link - which is also what honors the panel's browser.
    """
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
        if row.get("badge"):
            text.append(f"{row['badge']} ", style=row.get("badge_style", ""))
        dim = bool(row.get("dim"))
        if tui:
            style = Style(
                bold=not dim, dim=dim, underline=True,
                meta={"@click": f"app.open_link({row['url']!r}, {browser!r})"},
            )
        else:
            style = Style(bold=not dim, dim=dim, link=row["url"])
        text.append(row["text"], style=style)
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
            renderable = result_renderable(result, browser=self.panel.get("browser"), tui=True)
            self.query_one(".panel-output", Static).update(renderable)
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
        .legend { height: 1; padding: 0 2; }
        """

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with VerticalScroll():
                for panel in panels:
                    yield Panel(panel)
            yield Static(legend_text(), classes="legend")
            yield Footer()

        def action_refresh_all(self):
            for widget in self.query(Panel):
                widget.refresh_panel()

        def action_open_link(self, url, browser=None):
            open_link(url, browser)

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
    console.print(legend_text())
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
