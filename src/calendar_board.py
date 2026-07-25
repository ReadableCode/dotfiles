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
    assign_lanes,
    events_for_day,
    fetch_source,
    grid_hour_range,
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

# Grid-view block background per attendance state; conflicts override to
# red, so organizer blocks are purple rather than the badge's magenta -
# ANSI magenta renders pink-red in many themes and would masquerade as a
# conflict.
RESPONSE_BLOCK_COLORS = {
    "organizer": "purple",
    "accepted": "green",
    "tentative": "yellow",
    "needs_action": "cyan",
}

GRID_GUTTER = 6         # "07:00 " time-axis column
GRID_SLOT_CHOICES = (30, 15, 60)  # minutes per grid row, cycled by the zoom key


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
# Grid rendering #
#
# The Google-Calendar-style day view: a shared vertical time axis on the
# left, one column per source, events drawn as colored blocks positioned and
# sized by time - so a cross-client double booking is visible as two blocks
# sitting at the same height, before the ‼ flag even registers. Overlapping
# events WITHIN a source split into side-by-side lanes, like the web UIs do.


def _pad(label, width):
    return label[:width].ljust(width)


def _event_block_style(event):
    if event["conflict"]:
        return "bold white on red"
    if event["response"] == "declined":
        return "dim strike"
    return f"black on {RESPONSE_BLOCK_COLORS[event['response']]}"


def _event_slot_span(event, day_anchor, slot_minutes, total_slots, tz):
    """The [first, last] grid rows an event covers, or None when fully outside the range."""
    start_minutes = (event["start"].astimezone(tz) - day_anchor).total_seconds() / 60
    end_minutes = (event["end"].astimezone(tz) - day_anchor).total_seconds() / 60
    if end_minutes <= 0 or start_minutes >= total_slots * slot_minutes:
        return None
    first = max(0, int(start_minutes // slot_minutes))
    last = min(total_slots - 1, max(first, int(-(-end_minutes // slot_minutes)) - 1))
    return first, last


def _column_cells(day_events, day_anchor, slot_minutes, total_slots, tz):
    """
    Pack one source's timed day events into grid cells: (slot, lane) ->
    (event, is_label_row). The label lands on the event's first VISIBLE row,
    so an overnight meeting clamped to this day still gets its title.
    """
    placed, lane_count = assign_lanes(day_events)
    cells = {}
    for event, lane in placed:
        span = _event_slot_span(event, day_anchor, slot_minutes, total_slots, tz)
        if span is None:
            continue
        for slot in range(span[0], span[1] + 1):
            cells[(slot, lane)] = (event, slot == span[0])
    return cells, lane_count


def _lane_widths(column_width, lane_count):
    base = max(1, column_width // lane_count)
    widths = [base] * lane_count
    widths[-1] += column_width - base * lane_count
    return widths


def _append_column_cells(text, cells, lane_widths, slot, fill, fill_style, tz):
    for lane, lane_width in enumerate(lane_widths):
        entry = cells.get((slot, lane))
        if entry is None:
            text.append(fill * lane_width, style=fill_style)
            continue
        event, is_label = entry
        if is_label:
            badge = RESPONSE_BADGES[event["response"]][0]
            label = f"{badge}{event['start'].astimezone(tz):%H:%M} {event['title']}"
        else:
            label = ""
        text.append(_pad(label, lane_width), style=_event_block_style(event))


def grid_renderable(columns_data, day, width, tz=None, slot_minutes=30, now=None):
    """
    The whole day grid as one rich Text. columns_data is a list of dicts per
    source - {name, color, summary, ok, error, events} - with ``events``
    already sliced to the day and conflict-marked across sources. ``now``
    (an aware datetime) draws the current-time rule when it falls on this day.
    """
    if not columns_data:
        return Text("no sources", style="dim")
    count = len(columns_data)
    column_width = max(8, (width - GRID_GUTTER - count) // count)
    all_events = [event for column in columns_data if column["ok"] for event in column["events"]]
    start_hour, end_hour = grid_hour_range(all_events, day, tz)
    total_slots = (end_hour - start_hour) * 60 // slot_minutes
    day_anchor = datetime(day.year, day.month, day.day, start_hour)
    day_anchor = day_anchor.replace(tzinfo=tz) if tz else day_anchor.astimezone()
    now_slot = None
    if now is not None:
        offset = (now.astimezone(tz) - day_anchor).total_seconds() / 60
        if 0 <= offset < total_slots * slot_minutes:
            now_slot = int(offset // slot_minutes)

    text = Text()
    _append_grid_header(text, columns_data, column_width, width)
    packed = [
        _column_cells(column["events"] if column["ok"] else [], day_anchor, slot_minutes, total_slots, tz)
        for column in columns_data
    ]
    for slot in range(total_slots):
        text.append("\n")
        minutes = start_hour * 60 + slot * slot_minutes
        on_hour = minutes % 60 == 0
        label = f"{minutes // 60:02d}:00" if on_hour else ""
        text.append(_pad(label, GRID_GUTTER), style="bold red" if slot == now_slot else "dim")
        if slot == now_slot:
            fill, fill_style = "─", "red"
        elif on_hour:
            fill, fill_style = "╌", "dim"
        else:
            fill, fill_style = " ", ""
        for (cells, lane_count), column in zip(packed, columns_data):
            text.append(fill if fill != " " else " ", style=fill_style)
            _append_column_cells(
                text, cells, _lane_widths(column_width, lane_count), slot, fill, fill_style, tz
            )
    return text


def _append_grid_header(text, columns_data, column_width, width):
    """Source names in their colors, a status/summary line, all-day banner rows, and a rule."""
    text.append(" " * GRID_GUTTER)
    for column in columns_data:
        text.append(" ")
        text.append(_pad(column["name"], column_width), style=f"bold {column.get('color') or 'white'}")
    text.append("\n")
    text.append(" " * GRID_GUTTER)
    for column in columns_data:
        text.append(" ")
        status = column["summary"] if column["ok"] else (column["error"] or "error")
        text.append(_pad(status, column_width), style="dim" if column["ok"] else "red")
    banner_rows = max((len(_all_day(column)) for column in columns_data), default=0)
    for row in range(banner_rows):
        text.append("\n")
        text.append(_pad("", GRID_GUTTER))
        for column in columns_data:
            text.append(" ")
            banner = _all_day(column)
            if row < len(banner):
                event = banner[row]
                badge = RESPONSE_BADGES[event["response"]][0]
                text.append(_pad(f"{badge} {event['title']}", column_width), style=_event_block_style(event))
            else:
                text.append(" " * column_width)
    text.append("\n")
    text.append("─" * width, style="dim")


def _all_day(column):
    return [event for event in column["events"] if event["all_day"]] if column["ok"] else []


def day_slices(columns, view_date):
    """
    (column, day_events) pairs for the viewed day with conflicts marked on
    the COMBINED slice, so a meeting in one source lights up when it collides
    with a meeting in another - the whole point of the side-by-side layout.
    """
    per_column = [
        (column, events_for_day(column.events, view_date) if column.ok else []) for column in columns
    ]
    mark_conflicts([event for _, day_events in per_column for event in day_events])
    return per_column


def _show_agenda(per_column):
    for column, day_events in per_column:
        column.show(day_events)


def _refresh_stale_columns(columns, day):
    for column in columns:
        column.refresh_if_stale(day)


def _refresh_all_columns(columns):
    for column in columns:
        column.refresh_source()


def columns_grid_data(per_column):
    """grid_renderable's columns_data, from (SourceColumn, day_events) pairs."""
    return [
        {
            "name": column.source["name"],
            "color": column.source.get("color"),
            "summary": column.summary,
            "ok": column.ok,
            "error": column.error,
            "events": day_events,
        }
        for column, day_events in per_column
    ]


# %%
# TUI #


# The widget-state helpers below live at module level (taking the widget as
# their first argument, found via string selectors so textual stays a lazy
# import) to keep the class factories under the flake8 complexity ceiling.


def _column_begin_refresh(column):
    """Flip a column's footer into the fetching state (pulsing bar)."""
    column.deadline = None
    column.fired = time.monotonic()
    column.query_one("ProgressBar").total = None  # indeterminate pulse while the worker runs
    column.query_one(".column-countdown").update("refreshing…")


def _column_store(column, result, window):
    """Absorb one fetch result into the column and re-render the board."""
    column.ok = result.ok
    column.summary = result.summary
    column.error = result.error
    column.set_class(not result.ok, "error")
    state = result.summary or ("ok" if result.ok else "error")
    column.border_subtitle = f"{state} · {time.strftime('%H:%M:%S')}"
    if result.ok:
        column.events = result.events
        column.window = window
    else:
        column.query_one(".column-output").update(Text(result.error, style="red"))
    # anchor the countdown to fetch start, same as the status board
    column.deadline = column.fired + column.source["interval"]
    bar = column.query_one("ProgressBar")
    bar.total = column.source["interval"]
    bar.progress = 0
    column.app.render_day()


def _column_tick(column):
    """Advance the footer's next-poll countdown once a second."""
    if column.deadline is None:
        return  # fetch in flight - bar is pulsing
    remaining = max(0, column.deadline - time.monotonic())
    interval = column.source["interval"]
    column.query_one("ProgressBar").progress = interval - remaining
    minutes, seconds = divmod(int(remaining), 60)
    column.query_one(".column-countdown").update(f"next in {minutes}m{seconds:02d}s")


def _apply_column_color(column):
    if column.source.get("color"):
        column.styles.border = ("round", column.source["color"])


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
            self.summary = ""
            self.error = "loading…"
            self.deadline = None  # monotonic time of the next scheduled poll; None = fetching

        def compose(self) -> ComposeResult:
            yield Static("loading…", markup=False, classes="column-output")
            with Horizontal(classes="column-footer"):
                yield ProgressBar(total=None, show_eta=False, show_percentage=False)
                yield Label("refreshing…", classes="column-countdown")

        def on_mount(self):
            _apply_column_color(self)
            self.refresh_source()
            self.set_interval(self.source["interval"], self.refresh_source)
            self.set_interval(1.0, lambda: _column_tick(self))

        def refresh_if_stale(self, day):
            covered = bool(self.window) and self.window[0] <= day <= self.window[1]
            if not covered:
                self.refresh_source()  # re-window around the new day; renders when done

        def show(self, day_events):
            if self.ok:
                self.query_one(".column-output", Static).update(day_renderable(day_events))

        def refresh_source(self):
            view = self.app.view_date
            window = (view - timedelta(days=WINDOW_BEFORE_DAYS), view + timedelta(days=WINDOW_AFTER_DAYS))
            _column_begin_refresh(self)
            self.run_worker(
                lambda: self._fetch(window), thread=True, group=self.source["name"], exclusive=True
            )

        def _fetch(self, window):
            result = fetch_source(
                self.source, local_midnight(window[0]), local_midnight(window[1] + timedelta(days=1))
            )
            self.app.call_from_thread(_column_store, self, result, window)

    return SourceColumn


def build_app(sources, start_date):
    """
    Construct the Textual app class lazily so --once/--auth (and the unit
    tests) never need textual imported at module import time.
    """
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, VerticalScroll
    from textual.widgets import Footer, Header, Static

    SourceColumn = build_source_column()

    class GridView(VerticalScroll):
        """Grid container; re-renders on ITS resize - the app never sees one for the initial layout."""

        def on_resize(self, event):
            self.app.render_day()

    class CalendarBoardApp(App):
        TITLE = "calendar board"
        BINDINGS = [
            ("q", "quit", "quit"),
            ("r", "refresh_all", "refresh all"),
            ("left", "shift_day(-1)", "prev day"),
            ("right", "shift_day(1)", "next day"),
            ("t", "today", "today"),
            ("v", "toggle_view", "grid/agenda"),
            ("z", "zoom", "zoom"),
        ]
        CSS = """
        #grid-view { height: 1fr; padding: 0 1; }
        #columns { height: 1fr; }
        .hidden { display: none; }
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
            self.view_mode = "grid"
            self.slot_minutes = GRID_SLOT_CHOICES[0]

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with GridView(id="grid-view"):
                yield Static("loading…", markup=False, id="grid")
            with Horizontal(id="columns", classes="hidden"):
                for source in sources:
                    yield SourceColumn(source)
            yield Static(legend_text(), classes="legend")
            yield Footer()

        def render_day(self):
            """Re-render both views for the viewed day (see day_slices for the conflict pass)."""
            per_column = day_slices(list(self.query(SourceColumn)), self.view_date)
            _show_agenda(per_column)
            self._render_grid(per_column)
            self.sub_title = self.view_date.strftime("%A %Y-%m-%d")

        def _render_grid(self, per_column):
            # pre-layout width may be 0: rendered too wide once, on_resize fixes it
            width = max(self.query_one("#grid-view").content_size.width, 40)
            renderable = grid_renderable(
                columns_grid_data(per_column),
                self.view_date,
                width,
                slot_minutes=self.slot_minutes,
                now=datetime.now().astimezone(),
            )
            self.query_one("#grid", Static).update(renderable)

        def action_toggle_view(self):
            self.view_mode = {"grid": "agenda", "agenda": "grid"}[self.view_mode]
            self.query_one("#grid-view").set_class(self.view_mode != "grid", "hidden")
            self.query_one("#columns").set_class(self.view_mode != "agenda", "hidden")
            self.render_day()

        def action_zoom(self):
            choices = list(GRID_SLOT_CHOICES)
            self.slot_minutes = choices[(choices.index(self.slot_minutes) + 1) % len(choices)]
            self.render_day()

        def action_shift_day(self, delta):
            self._go_to(self.view_date + timedelta(days=delta))

        def action_today(self):
            self._go_to(date.today())

        def _go_to(self, day):
            self.view_date = day
            _refresh_stale_columns(self.query(SourceColumn), day)
            self.render_day()

        def action_refresh_all(self):
            _refresh_all_columns(self.query(SourceColumn))

    return CalendarBoardApp


# %%
# Main #


def run_once(sources, start_day, days, grid=False):
    """Fetch every source once and print a static agenda or grid per day (sanity check / headless use)."""
    console = Console()
    window_start = local_midnight(start_day)
    window_end = local_midnight(start_day + timedelta(days=days))
    results = [(source, fetch_source(source, window_start, window_end)) for source in sources]
    for offset in range(days):
        day = start_day + timedelta(days=offset)
        console.rule(f"[bold]{day.strftime('%A %Y-%m-%d')}[/bold]")
        per_source = [
            (source, result, events_for_day(result.events, day) if result.ok else [])
            for source, result in results
        ]
        mark_conflicts([event for _, _, day_events in per_source for event in day_events])
        if grid:
            columns_data = [
                {
                    "name": source["name"],
                    "color": source.get("color"),
                    "summary": result.summary,
                    "ok": result.ok,
                    "error": result.error,
                    "events": day_events,
                }
                for source, result, day_events in per_source
            ]
            console.print(grid_renderable(columns_data, day, console.width, now=datetime.now().astimezone()))
            console.print()
            continue
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
    parser.add_argument("--grid", action="store_true", help="print the time grid instead of the agenda in --once mode")
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
        return run_once(sources, start_day, max(args.days, 1), grid=args.grid)
    app_class = build_app(sources, start_day)
    app_class().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())


# %%
