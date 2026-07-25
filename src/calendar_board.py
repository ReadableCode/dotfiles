# %%
# Imports #

import argparse
import sys
import time
from datetime import date, datetime, timedelta

from config import grandparent_dir, parent_dir
from rich.console import Console
from rich.style import Style
from rich.text import Text
from utils.calendarboard_tools import (
    events_for_day,
    fetch_source,
    load_sources,
    mark_conflicts,
    run_google_auth,
    run_outlook_auth,
)

# %%
# Variables #

REPO_ROOT = parent_dir
CREDENTIALS_ROOT = grandparent_dir

# Each source fetches this window around the viewed day, so day-to-day
# navigation is instant from cache; stepping outside it triggers a refetch.
WINDOW_BEFORE_DAYS = 1
WINDOW_AFTER_DAYS = 13

# Badge / style / legend label per normalized attendance state - the visual
# answer to "did I accept this or am I merely invited?".
RESPONSE_BADGES = {
    "organizer": ("★", "bold magenta", "you organize"),
    "accepted": ("✓", "bold green", "accepted"),
    "tentative": ("~", "bold yellow", "tentative"),
    "needs_action": ("?", "bold cyan", "invited - not responded"),
    "declined": ("✗", "dim", "declined"),
}


# %%
# Rendering #


def legend_text():
    """One-line key for the badges, shown at the bottom of the board."""
    text = Text()
    entries = [(badge, style, label) for badge, style, label in RESPONSE_BADGES.values()]
    entries.append(("‼", "bold red", "overlaps another meeting"))
    for index, (badge, style, label) in enumerate(entries):
        if index:
            text.append("   ", style="dim")
        text.append(badge, style=style)
        text.append(f" {label}", style="dim")
    return text


def local_midnight(day):
    """Aware datetime at this machine's local midnight of a calendar date."""
    return datetime(day.year, day.month, day.day).astimezone()


def day_renderable(day_events, tz=None):
    """
    One source's agenda for one day as a rich Text: badge, local time range,
    title, and the calendar it came from - declined events struck through and
    dimmed, cross-source conflicts flagged loudly on the time itself.
    """
    if not day_events:
        return Text("no events", style="dim")
    text = Text()
    for index, event in enumerate(day_events):
        if index:
            text.append("\n")
        badge, badge_style, _ = RESPONSE_BADGES[event["response"]]
        declined = event["response"] == "declined"
        text.append(f"{badge} ", style=badge_style)
        if event["all_day"]:
            time_str = "all day"
        else:
            start_local = event["start"].astimezone(tz)
            end_local = event["end"].astimezone(tz)
            time_str = f"{start_local:%H:%M}–{end_local:%H:%M}"
        if event["conflict"]:
            text.append("‼ ", style="bold red")
            text.append(time_str, style="bold red")
        else:
            text.append(time_str, style="dim" if declined else "bold")
        text.append("  ")
        text.append(event["title"], style=Style(dim=True, strike=True) if declined else Style())
        text.append(f"\n    {event['calendar']}", style="dim")
    return text


# %%
# TUI #


def build_source_column():
    """
    Construct the per-source column widget class lazily (same reason as
    build_app: --once/--auth and the unit tests never import textual).
    """
    from textual.app import ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import Label, ProgressBar, Static

    class SourceColumn(Vertical):
        """
        One calendar source: a bordered column showing the viewed day's
        agenda, refetching its event window on its own interval (sources poll
        independently - one slow API never stalls the others), with a
        real-time bar filling toward the next poll.
        """

        def __init__(self, source):
            super().__init__()
            self.source = source
            self.border_title = source["name"]
            self.events = []
            self.window = None  # (first_day, last_day) the cached events cover; None = never fetched
            self.ok = False
            self.deadline = None  # monotonic time of the next scheduled poll; None = fetching

        def compose(self) -> ComposeResult:
            yield Static("loading…", markup=False, classes="column-output")
            with Horizontal(classes="column-footer"):
                yield ProgressBar(total=None, show_eta=False, show_percentage=False)
                yield Label("refreshing…", classes="column-countdown")

        def on_mount(self):
            if self.source.get("color"):
                self.styles.border = ("round", self.source["color"])
            self.refresh_source()
            self.set_interval(self.source["interval"], self.refresh_source)
            self.set_interval(1.0, self._tick)

        def covers(self, day):
            return bool(self.window) and self.window[0] <= day <= self.window[1]

        def refresh_source(self):
            view = self.app.view_date
            window = (view - timedelta(days=WINDOW_BEFORE_DAYS), view + timedelta(days=WINDOW_AFTER_DAYS))
            self.deadline = None
            self._fired = time.monotonic()
            bar = self.query_one(ProgressBar)
            bar.total = None  # indeterminate pulse while the worker runs
            self.query_one(".column-countdown", Label).update("refreshing…")
            self.run_worker(
                lambda: self._fetch(window), thread=True, group=self.source["name"], exclusive=True
            )

        def _fetch(self, window):
            result = fetch_source(
                self.source, local_midnight(window[0]), local_midnight(window[1] + timedelta(days=1))
            )
            self.app.call_from_thread(self._store, result, window)

        def _store(self, result, window):
            self.ok = result.ok
            self.set_class(not result.ok, "error")
            state = result.summary or ("ok" if result.ok else "error")
            self.border_subtitle = f"{state} · {time.strftime('%H:%M:%S')}"
            if result.ok:
                self.events = result.events
                self.window = window
            else:
                self.query_one(".column-output", Static).update(Text(result.error, style="red"))
            # anchor the countdown to fetch start, same as the status board
            self.deadline = self._fired + self.source["interval"]
            bar = self.query_one(ProgressBar)
            bar.total = self.source["interval"]
            bar.progress = 0
            self.app.render_day()

        def show(self, day_events):
            self.query_one(".column-output", Static).update(day_renderable(day_events))

        def _tick(self):
            if self.deadline is None:
                return  # fetch in flight - bar is pulsing
            remaining = max(0, self.deadline - time.monotonic())
            interval = self.source["interval"]
            self.query_one(ProgressBar).progress = interval - remaining
            minutes, seconds = divmod(int(remaining), 60)
            self.query_one(".column-countdown", Label).update(f"next in {minutes}m{seconds:02d}s")

    return SourceColumn


def build_app(sources, start_date):
    """
    Construct the Textual app class lazily so --once/--auth (and the unit
    tests) never need textual imported at module import time.
    """
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal
    from textual.widgets import Footer, Header, Static

    SourceColumn = build_source_column()

    class CalendarBoardApp(App):
        TITLE = "calendar board"
        BINDINGS = [
            ("q", "quit", "quit"),
            ("r", "refresh_all", "refresh all"),
            ("left", "shift_day(-1)", "prev day"),
            ("right", "shift_day(1)", "next day"),
            ("t", "today", "today"),
        ]
        CSS = """
        #columns { height: 1fr; }
        SourceColumn {
            border: round $primary;
            border-title-color: $accent;
            width: 1fr;
            margin: 0 1 1 1;
            padding: 0 1;
        }
        SourceColumn.error { border: round red; }
        .column-output { height: 1fr; overflow-y: auto; }
        .column-footer { height: 1; margin-top: 1; }
        .column-footer ProgressBar { width: 1fr; }
        .column-footer Bar { width: 1fr; }
        .column-countdown { color: $text-muted; margin-left: 2; }
        .legend { height: 1; padding: 0 2; }
        """

        def __init__(self):
            super().__init__()
            self.view_date = start_date

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Horizontal(id="columns"):
                for source in sources:
                    yield SourceColumn(source)
            yield Static(legend_text(), classes="legend")
            yield Footer()

        def on_mount(self):
            self.sub_title = self.view_date.strftime("%A %Y-%m-%d")

        def render_day(self):
            """
            Re-render every column for the viewed day. Conflicts are marked on
            the COMBINED day view first, so a meeting in one source's column
            lights up when it collides with a meeting in another's - the
            whole point of standing the columns side by side.
            """
            columns = [column for column in self.query(SourceColumn) if column.ok]
            per_column = [(column, events_for_day(column.events, self.view_date)) for column in columns]
            mark_conflicts([event for _, day_events in per_column for event in day_events])
            for column, day_events in per_column:
                column.show(day_events)
            self.sub_title = self.view_date.strftime("%A %Y-%m-%d")

        def action_shift_day(self, delta):
            self._go_to(self.view_date + timedelta(days=delta))

        def action_today(self):
            self._go_to(date.today())

        def _go_to(self, day):
            self.view_date = day
            for column in self.query(SourceColumn):
                if not column.covers(day):
                    column.refresh_source()  # re-window around the new day; renders when done
            self.render_day()

        def action_refresh_all(self):
            for column in self.query(SourceColumn):
                column.refresh_source()

    return CalendarBoardApp


# %%
# Main #


def run_once(sources, start_day, days):
    """Fetch every source once and print a static agenda per day (sanity check / headless use)."""
    console = Console()
    window_start = local_midnight(start_day)
    window_end = local_midnight(start_day + timedelta(days=days))
    results = [(source, fetch_source(source, window_start, window_end)) for source in sources]
    for offset in range(days):
        day = start_day + timedelta(days=offset)
        console.rule(f"[bold]{day.strftime('%A %Y-%m-%d')}[/bold]")
        per_source = [
            (source, result, events_for_day(result.events, day) if result.ok else None)
            for source, result in results
        ]
        mark_conflicts([event for _, _, day_events in per_source if day_events for event in day_events])
        for source, result, day_events in per_source:
            state = result.summary or ("ok" if result.ok else "error")
            console.print(f"[bold]{source['name']}[/bold] · {state}", style="green" if result.ok else "red")
            console.print(Text(result.error, style="red") if not result.ok else day_renderable(day_events))
            console.print()
    console.print(legend_text())
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Long-lived TUI calendar board showing each configured calendar source (Google, "
        "Outlook/Microsoft Graph) side by side per day; sources come from "
        "<context>_calendarboard.yaml configs discovered in sibling *_credentials repos."
    )
    parser.add_argument("--once", action="store_true", help="fetch every source once, print, and exit (no TUI)")
    parser.add_argument("--date", default=None, help="start/view date as YYYY-MM-DD (default: today)")
    parser.add_argument("--days", type=int, default=1, help="days to print in --once mode (default 1)")
    parser.add_argument(
        "--auth",
        metavar="SOURCE",
        default=None,
        help="run the one-time interactive OAuth flow for the named source and print its refresh token",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="load only this calendarboard config file, skipping discovery (for testing)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    sources, config_paths = load_sources(CREDENTIALS_ROOT, REPO_ROOT, config_path=args.config)
    if not sources:
        print(
            "No calendarboard sources found - add a <context>_calendarboard.yaml to a sibling "
            "*_credentials repo (see docs/setup_calendar_board.md)"
        )
        return 1
    if args.auth:
        by_name = {source["name"]: source for source in sources}
        if args.auth not in by_name:
            print(f"Unknown source '{args.auth}' (configured: {', '.join(by_name)})")
            return 1
        source = by_name[args.auth]
        runner = run_google_auth if source["type"] == "google_calendar" else run_outlook_auth
        return runner(source)
    start_day = date.fromisoformat(args.date) if args.date else date.today()
    print(f"configs: {', '.join(config_paths)}")
    if args.once:
        return run_once(sources, start_day, max(args.days, 1))
    app_class = build_app(sources, start_day)
    app_class().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())


# %%
