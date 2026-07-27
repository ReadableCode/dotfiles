# %%
# Imports #

import argparse
import sys
import textwrap
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

# Grid-view block background per attendance state - the FALLBACK for sources
# with no ``color:`` configured. A configured source color always wins: every
# calendar keeps its own color, attendance lives in the badge, and conflicts
# tag on a ‼ instead of repainting the block. Organizer is purple rather than
# the badge's magenta - ANSI magenta renders pink-red in many themes and
# would read as an error.
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
    if len(label) > width:
        return label[: max(width - 1, 0)] + "…"[: min(width, 1)]
    return label.ljust(width)


def _event_block_style(event):
    if event["response"] == "declined":
        return "dim strike"
    color = event.get("source_color") or RESPONSE_BLOCK_COLORS[event["response"]]
    # black text and borders on every block - the calm "inverse" of the pastel
    # source colors; conflicts keep the calendar's color and alarm via ‼ + bold
    return f"{'bold ' if event['conflict'] else ''}black on {color}"


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
    (event, is_label_row, is_last_row). The label lands on the event's first
    VISIBLE row, so an overnight meeting clamped to this day still gets its
    title; the last row draws the block's bottom border.
    """
    placed, lane_count = assign_lanes(day_events)
    cells = {}
    for event, lane in placed:
        span = _event_slot_span(event, day_anchor, slot_minutes, total_slots, tz)
        if span is None:
            continue
        for slot in range(span[0], span[1] + 1):
            cells[(slot, lane)] = (event, slot - span[0], span[1] - span[0] + 1)
    return cells, lane_count


def _lane_widths(column_width, lane_count):
    """Split a column between overlap lanes, keeping a 1-char gap between lanes."""
    usable = max(lane_count, column_width - (lane_count - 1))
    base = max(1, usable // lane_count)
    widths = [base] * lane_count
    widths[-1] += usable - base * lane_count
    return widths


def _event_label_lines(event, width, tz):
    """The block's text, word-wrapped to its lane width."""
    badge = ("‼" if event["conflict"] else "") + RESPONSE_BADGES[event["response"]][0]
    prefix = event.get("label_prefix", "")
    full = f"{badge}{event['start'].astimezone(tz):%H:%M} {prefix}{event['title']}"
    return textwrap.wrap(full, max(width, 1)) or [""]


def _cell_style(event, underline):
    style = Style.parse(_event_block_style(event) + (" underline" if underline else ""))
    if event.get("_click_id") is not None:  # click a block -> the detail screen
        style += Style(meta={"@click": f"app.show_event({event['_click_id']})"})
    return style


def _append_column_cells(text, cells, lane_widths, slot, fill, fill_style, tz):
    for lane, lane_width in enumerate(lane_widths):
        if lane:  # the gap that keeps side-by-side blocks visually apart
            text.append(fill if fill != " " else " ", style=fill_style)
        entry = cells.get((slot, lane))
        if entry is None:
            text.append(fill * lane_width, style=fill_style)
            continue
        event, row, total = entry
        if total > 1 and row == total - 1:
            # the last row of a multi-row block is its bottom border: ▁ sits at
            # the cell's floor (underline doesn't), so stacked blocks can't bleed
            text.append("▎" + "▁" * (lane_width - 1), style=_cell_style(event, underline=False))
            continue
        body_rows = total - 1 if total > 1 else 1
        lines = _event_label_lines(event, lane_width - 1, tz)
        label = lines[row] if row < len(lines) else ""
        if row == body_rows - 1 and len(lines) > body_rows:
            label += "…"  # more text than block rows; _pad turns this into a trailing ellipsis
        # ▎ is the block's left border - same-color neighbours stay two cards;
        # single-row blocks keep underline as their only possible bottom edge
        text.append("▎" + _pad(label, lane_width - 1), style=_cell_style(event, underline=(total == 1)))


def _pack_grid_columns(columns_data, day, start_hour, slot_minutes, total_slots, tz, now):
    """Per column: its lane-packed cells and its own now-rule slot (columns may show different days)."""
    packed, now_slots = [], []
    for column in columns_data:
        column_day = column.get("day", day)
        anchor = datetime(column_day.year, column_day.month, column_day.day, start_hour)
        anchor = anchor.replace(tzinfo=tz) if tz else anchor.astimezone()
        packed.append(
            _column_cells(column["events"] if column["ok"] else [], anchor, slot_minutes, total_slots, tz)
        )
        now_slot = None
        if now is not None:
            offset = (now.astimezone(tz) - anchor).total_seconds() / 60
            if 0 <= offset < total_slots * slot_minutes:
                now_slot = int(offset // slot_minutes)
        now_slots.append(now_slot)
    return packed, now_slots


def grid_renderable(columns_data, day, width, tz=None, slot_minutes=30, now=None, full_day=False):
    """
    The whole grid as one rich Text. columns_data is a list of dicts per
    column - {name, color, summary, ok, error, events} - with ``events``
    already sliced to the column's day and conflict-marked. A column may carry
    its own ``day`` (the multi-day views); otherwise all show ``day``. ``now``
    (an aware datetime) draws the current-time rule on today's column.
    full_day covers 00-24 (the TUI scrolls); otherwise the working-day span
    widened to fit the events (compact --once printing).
    """
    if not columns_data:
        return Text("no sources", style="dim")
    # no_wrap: a row wider than the widget must crop, never soft-wrap - one
    # wrapped row shifts every hour line below it off its events
    text = Text(no_wrap=True)
    count = len(columns_data)
    column_width = max(8, (width - GRID_GUTTER - count) // count)
    if full_day:
        start_hour, end_hour = 0, 24
    else:
        all_events = [event for column in columns_data if column["ok"] for event in column["events"]]
        start_hour, end_hour = grid_hour_range(all_events, day, tz)
    total_slots = (end_hour - start_hour) * 60 // slot_minutes
    packed, now_slots = _pack_grid_columns(columns_data, day, start_hour, slot_minutes, total_slots, tz, now)

    _append_grid_header(text, columns_data, column_width, width)
    for slot in range(total_slots):
        text.append("\n")
        minutes = start_hour * 60 + slot * slot_minutes
        on_hour = minutes % 60 == 0
        # the hour line is the row's BOTTOM edge (underline), so it sits on the
        # boundary between hours and a block starting on the hour begins right
        # below its line instead of straddling it
        hour_below = (minutes + slot_minutes) % 60 == 0
        label = f"{minutes // 60:02d}:00" if on_hour else ""
        gutter_now = any(slot == now_slot for now_slot in now_slots)
        text.append(_pad(label, GRID_GUTTER), style="bold red" if gutter_now else "dim")
        for (cells, lane_count), now_slot in zip(packed, now_slots):
            if slot == now_slot:
                fill, fill_style = "─", "red"
            elif hour_below:
                fill, fill_style = " ", "dim underline"
            else:
                fill, fill_style = " ", ""
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
    # status row only when there's something to say (an error, or a summary)
    if any(not column["ok"] or column["summary"] for column in columns_data):
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
                label = f"{badge} {event.get('label_prefix', '')}{event['title']}"
                # same card look (and click behavior) as the timed blocks
                text.append("▎" + _pad(label, column_width - 1), style=_cell_style(event, underline=True))
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


def _refresh_stale_columns(columns, days):
    for column in columns:
        column.refresh_if_stale(days)


MIN_GRID_COLUMN_WIDTH = 8  # narrower and the grid's lines wrap into garbage


def _next_choice(choices, current):
    return choices[(choices.index(current) + 1) % len(choices)]


def event_detail_text(event, tz=None):
    """The detail screen's body: everything the APIs kept about one event."""
    details = event.get("details") or {}
    text = Text()
    badge, badge_style, badge_label = RESPONSE_BADGES[event["response"]]
    text.append(event["title"] + "\n", style="bold")
    if event["all_day"]:
        last = (event["end"] - timedelta(days=1)).date()
        span = f"all day {event['start'].date()}" + (f" → {last}" if last > event["start"].date() else "")
    else:
        start, end = event["start"].astimezone(tz), event["end"].astimezone(tz)
        span = f"{start:%A %Y-%m-%d %H:%M} → {end:%H:%M}" + ("" if start.date() == end.date() else f" ({end.date()})")
    text.append(span + "\n", style="dim")
    text.append(f"\n{badge} {badge_label}", style=badge_style)
    if event["conflict"]:
        text.append("   ‼ overlaps another meeting", style="bold red")
    text.append("\n")
    rows = [("calendar", event.get("calendar", "")), ("source", event.get("source", ""))]
    rows += [("location", details.get("location", "")), ("organizer", details.get("organizer", ""))]
    for label, value in rows:
        if value:
            text.append(f"\n{label:<10}", style="dim")
            text.append(str(value))
    attendees = details.get("attendees") or []
    if attendees:
        text.append(f"\n\nattendees ({len(attendees)})", style="dim")
        for who, response in attendees:
            attendee_badge, attendee_style, _ = RESPONSE_BADGES.get(response, RESPONSE_BADGES["needs_action"])
            text.append(f"\n  {attendee_badge} ", style=attendee_style)
            text.append(who)
    if details.get("description"):
        text.append("\n\n")
        text.append(details["description"], style="dim")
    if details.get("link"):
        text.append("\n\n")
        text.append(details["link"], style=f"underline link {details['link']}")
    return text


def build_event_detail_screen():
    """Construct the event-detail modal class lazily (same reason as build_app)."""
    from textual.binding import Binding
    from textual.containers import VerticalScroll
    from textual.screen import ModalScreen
    from textual.widgets import Static

    class EventDetail(ModalScreen):
        """One event's full details; escape (or another click) goes back to the board."""

        BINDINGS = [Binding("escape", "app.pop_screen", "back to board")]

        def __init__(self, event):
            super().__init__()
            self.event = event

        def compose(self):
            with VerticalScroll(id="event-detail"):
                yield Static(event_detail_text(self.event), markup=False)

        def on_click(self, event):
            # click outside the card -> back to the board (inside it, scroll/select freely)
            if not self.query_one("#event-detail").region.contains(event.screen_x, event.screen_y):
                self.app.pop_screen()

    return EventDetail


def span_min_width(span, source_count):
    """Terminal columns a span needs before its grid wraps unreadably."""
    count = source_count if span == 1 else span
    return GRID_GUTTER + max(1, count) * (1 + MIN_GRID_COLUMN_WIDTH)


def sources_legend(columns):
    """Legend fragment mapping each source's initial-letter tag and color back to its name."""
    text = Text()
    for column in columns:
        text.append("   ", style="dim")
        text.append(
            f"{source_initial(column.source['name'])}·{column.source['name']}",
            style=f"bold {column.source.get('color') or 'white'}",
        )
    return text


def _page_step(day_span):
    """What one ←/→ press moves: the days on screen, or a whole week in the week views."""
    return day_span if day_span in (1, 3) else 7


def _grid_width(app):
    """
    The width the grid Static actually gets: the scroll view's inner area
    minus its scrollbar. content_size still includes the scrollbar, and
    rendering to it makes every row 2 cells too wide - the rows then
    soft-wrap, shifting each hour line below the wrap off its events.
    """
    return app.query_one("#grid-view").scrollable_content_region.width


def _span_fits(app, span, source_count):
    width = _grid_width(app)
    return span == 1 or width >= span_min_width(span, source_count)


def _next_fitting_span(app, source_count):
    """The next span choice the terminal can draw (1 always fits, so this terminates)."""
    span = _next_choice(DAY_SPAN_CHOICES, app.day_span)
    while not _span_fits(app, span, source_count):
        span = _next_choice(DAY_SPAN_CHOICES, span)
    return span


def _app_set_span(app, span, source_count, columns):
    if not _span_fits(app, span, source_count):
        needed = span_min_width(span, source_count)
        app.notify(f"{span}-day view needs a {needed}-column terminal", severity="warning")
        return
    app.day_span = span
    _refresh_stale_columns(columns, span_days(app.view_date, span))
    app.render_day()


def _shrink_span_to_fit(app, source_count):
    """Drop to the widest span the terminal can draw (resize protection); 1 always fits."""
    width = _grid_width(app)
    span = app.day_span
    while width > 0 and span > 1 and width < span_min_width(span, source_count):
        span = max(choice for choice in DAY_SPAN_CHOICES if choice < span)
    if span != app.day_span:
        app.day_span = span
        app.notify(f"terminal too narrow - dropped to the {span}-day view", severity="warning")


def _app_render_day(app, columns):
    """Re-render both views for the app's viewed span (see day_slices for the conflict pass)."""
    per_column = day_slices(columns, app.view_date)  # agenda stays single-day
    _show_agenda(per_column)
    _shrink_span_to_fit(app, len(columns))
    days = span_days(app.view_date, app.day_span)
    legend = legend_text()
    if len(days) == 1:
        columns_data = columns_grid_data(per_column)
        app.sub_title = app.view_date.strftime("%A %Y-%m-%d")
    else:
        columns_data = multi_day_grid_data(columns, days)
        app.sub_title = f"{days[0].strftime('%a %Y-%m-%d')} → {days[-1].strftime('%a %Y-%m-%d')}"
        legend.append_text(sources_legend(columns))  # map block colors/tags back to sources
    app.query_one(".legend").update(legend)
    # every rendered event gets an id into the app's click registry, so a
    # click on its block can pull up the detail screen
    app._click_events = []
    for column_data in columns_data:
        for event in column_data["events"]:
            event["_click_id"] = len(app._click_events)
            app._click_events.append(event)
    _app_render_grid(app, columns_data)


def _app_render_grid(app, columns_data):
    # pre-layout width may be 0: rendered too wide once, on_resize fixes it
    renderable = grid_renderable(
        columns_data,
        app.view_date,
        max(_grid_width(app), 40),
        slot_minutes=app.slot_minutes,
        now=datetime.now().astimezone(),
        full_day=True,  # the TUI shows 00-24 and scrolls; --once stays compact
    )
    app.query_one("#grid").update(renderable)
    # re-position only when the view actually changed - never yank a manually
    # scrolled grid just because a background poll finished
    scroll_key = (app.view_date, app.day_span, app.slot_minutes)
    if getattr(app, "_scroll_key", None) != scroll_key:
        app._scroll_key = scroll_key
        app.call_after_refresh(_app_scroll_grid, app, columns_data)


def _app_scroll_grid(app, columns_data):
    """Land the scroll like Google Calendar: an hour above now on today, else 07:00."""
    days = span_days(app.view_date, app.day_span)
    hour = max(datetime.now().hour - 1, 0) if date.today() in days else 7
    banner_rows = max((len(_all_day(column)) for column in columns_data), default=0)
    status_row = int(any(not column["ok"] or column["summary"] for column in columns_data))
    header_rows = 1 + status_row + banner_rows + 1  # names, optional status, banners, rule
    app.query_one("#grid-view").scroll_to(y=header_rows + hour * 60 // app.slot_minutes, animate=False)


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
            # stamp the source color so blocks keep their calendar's color in
            # the single-day view too (copies - the cache stays unstamped)
            "events": [dict(event, source_color=column.source.get("color")) for event in day_events],
        }
        for column, day_events in per_column
    ]


DAY_SPAN_CHOICES = (1, 3, 5, 7)  # like Google Calendar: day / 3-day / work week / week


def span_days(view_date, day_span):
    """
    The dates a span shows: 1 = the viewed day, 3 = it plus the next two,
    5 = the Mon-Fri work week containing it, 7 = its Sun-Sat week.
    """
    if day_span == 5:
        monday = view_date - timedelta(days=view_date.weekday())
        return [monday + timedelta(days=offset) for offset in range(5)]
    if day_span == 7:
        sunday = view_date - timedelta(days=(view_date.weekday() + 1) % 7)
        return [sunday + timedelta(days=offset) for offset in range(7)]
    return [view_date + timedelta(days=offset) for offset in range(day_span)]


def source_initial(name):
    """The single letter that tags a source's events in the merged multi-day columns."""
    return name[0].upper() if name else "?"


def multi_day_grid_data(columns, days):
    """
    grid_renderable's columns_data for the multi-day views: one column per
    DAY, every source's events merged into it (source told apart by block
    color and an initial-letter tag - the legend line maps both back to the
    source), conflicts marked per day across sources. Today's header lights up.
    """
    data = []
    for day in days:
        merged = [
            dict(
                event,
                source_color=column.source.get("color"),
                label_prefix=f"{source_initial(column.source['name'])}·",
            )
            for column in columns
            if column.ok
            for event in events_for_day(column.events, day)
        ]
        mark_conflicts(merged)
        data.append(
            {
                "name": day.strftime("%a %m/%d"),
                "color": "reverse" if day == date.today() else "white",
                "summary": "",
                "ok": True,
                "error": "",
                "events": merged,
                "day": day,
            }
        )
    return data


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

        def refresh_if_stale(self, days):
            covered = bool(self.window) and self.window[0] <= days[0] and days[-1] <= self.window[1]
            if not covered:
                self.refresh_source()  # re-window around the new span; renders when done

        def show(self, day_events):
            if self.ok:
                self.query_one(".column-output", Static).update(day_renderable(day_events))

        def refresh_source(self):
            # anchor on the span's first day so week views (which may start
            # days before view_date) always land inside the fetched window
            first = span_days(self.app.view_date, self.app.day_span)[0]
            window = (first - timedelta(days=WINDOW_BEFORE_DAYS), first + timedelta(days=WINDOW_AFTER_DAYS))
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


class _BoardActions:
    """
    The board's key/click actions, as a plain module-level mixin (no textual
    imports needed) so the lazily-built app class stays under the flake8
    complexity ceiling. ``SOURCE_COUNT`` and ``DETAIL_SCREEN`` are stamped on
    the concrete class by build_app; SourceColumn widgets are found via the
    string selector.
    """

    def render_day(self):
        """Re-render both views for the viewed span (see day_slices for the conflict pass)."""
        _app_render_day(self, list(self.query("SourceColumn")))

    def action_toggle_view(self):
        self.view_mode = {"grid": "agenda", "agenda": "grid"}[self.view_mode]
        self.query_one("#grid-view").set_class(self.view_mode != "grid", "hidden")
        self.query_one("#columns").set_class(self.view_mode != "agenda", "hidden")
        self.render_day()

    def action_zoom(self):
        self.slot_minutes = _next_choice(GRID_SLOT_CHOICES, self.slot_minutes)
        self.render_day()

    def action_shift_day(self, delta):
        self._go_to(self.view_date + timedelta(days=delta))

    def action_shift_page(self, direction):
        self._go_to(self.view_date + timedelta(days=direction * _page_step(self.day_span)))

    def action_cycle_span(self):
        self.action_set_span(_next_fitting_span(self, self.SOURCE_COUNT))

    def action_set_span(self, span):
        _app_set_span(self, span, self.SOURCE_COUNT, self.query("SourceColumn"))

    def action_today(self):
        self._go_to(date.today())

    def action_show_event(self, index):
        events = getattr(self, "_click_events", [])
        if 0 <= index < len(events):
            self.push_screen(self.DETAIL_SCREEN(events[index]))

    def _go_to(self, day):
        self.view_date = day
        _refresh_stale_columns(self.query("SourceColumn"), span_days(day, self.day_span))
        self.render_day()

    def action_refresh_all(self):
        _refresh_all_columns(self.query("SourceColumn"))


def build_grid_view():
    """Construct the grid container class lazily (same reason as build_app)."""
    from textual.containers import VerticalScroll

    class GridView(VerticalScroll):
        """Grid container; re-renders on ITS resize - the app never sees one for the initial layout."""

        def on_resize(self, event):
            self.app.render_day()

    return GridView


def build_app(sources, start_date):
    """
    Construct the Textual app class lazily so --once/--auth (and the unit
    tests) never need textual imported at module import time.
    """
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal
    from textual.widgets import Footer, Header, Static

    SourceColumn = build_source_column()
    GridView = build_grid_view()
    EventDetail = build_event_detail_screen()

    class CalendarBoardApp(_BoardActions, App):
        TITLE = "calendar board"
        BINDINGS = [
            # priority=True keeps the day-navigation arrows working (and visible in
            # the footer) even while the scrollable grid has focus - VerticalScroll
            # binds the same keys for scrolling, which would otherwise mask these.
            Binding("left", "shift_page(-1)", "prev", key_display="←", priority=True),
            Binding("right", "shift_page(1)", "next", key_display="→", priority=True),
            Binding("shift+left", "shift_day(-7)", "-week", key_display="⇧←", priority=True),
            Binding("shift+right", "shift_day(7)", "+week", key_display="⇧→", priority=True),
            Binding("t", "today", "today"),
            Binding("d", "cycle_span", "1/3/5/7 days"),
            Binding("1", "set_span(1)", "1 day", show=False),
            Binding("3", "set_span(3)", "3 days", show=False),
            Binding("5", "set_span(5)", "work week", show=False),
            Binding("7", "set_span(7)", "week", show=False),
            Binding("v", "toggle_view", "grid/agenda"),
            Binding("z", "zoom", "zoom 30/15/60"),
            Binding("r", "refresh_all", "refresh all"),
            Binding("q", "quit", "quit"),
        ]
        CSS = """
        /* stable gutter: the scrollbar's 2 cells are reserved even while the
           grid is short (loading), so _grid_width never changes under us when
           content growth pops the scrollbar in */
        #grid-view { height: 1fr; padding: 0 1; scrollbar-gutter: stable; }
        /* blocks carry @click meta; without this Textual repaints them in the
           theme's link colors (white-ish text). Keep the blocks' own colors,
           and signal clickability on hover instead. */
        #grid {
            link-color: black;
            link-background: initial;
            link-style: none;
            link-style-hover: bold reverse;
        }
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
        EventDetail { align: center middle; }
        #event-detail {
            width: 70%;
            max-width: 100;
            max-height: 80%;
            height: auto;
            border: round $accent;
            background: $surface;
            padding: 1 2;
        }
        """

        def __init__(self):
            super().__init__()
            self.view_date = start_date
            self.view_mode = "grid"
            self.slot_minutes = GRID_SLOT_CHOICES[0]
            self.day_span = DAY_SPAN_CHOICES[0]

        def on_mount(self):
            self.query_one("#grid-view").focus()  # so up/down scroll the full-day grid

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with GridView(id="grid-view"):
                yield Static("loading…", markup=False, id="grid")
            with Horizontal(id="columns", classes="hidden"):
                for source in sources:
                    yield SourceColumn(source)
            yield Static(legend_text(), classes="legend")
            yield Footer()

    CalendarBoardApp.SOURCE_COUNT = len(sources)
    CalendarBoardApp.DETAIL_SCREEN = EventDetail
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
