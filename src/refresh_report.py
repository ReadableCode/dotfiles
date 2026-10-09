"""The closing status page of refresh_machine.py, and the file the steps feed it from.

Every step of gitpullall and myupdater keeps the real terminal (its prompts,
colours and progress reach the person running it, and a package manager
behaves as it does when run by hand), so nothing here reads a step's output.
Instead each tool appends one tab-separated line per thing it did to the file
``$REFRESH_REPORT`` names, and refresh_machine.py draws the page from that file
after the last step. A tool run on its own, with the variable unset, writes
nothing and behaves exactly as before.

Line format: ``kind<TAB>name<TAB>detail``. The kinds, by the tool that writes them:

- refresh_machine.py: ``step`` (name: the step title, detail: ``ok|failed <seconds> <family>``),
  ``pull.pulled`` (detail ``old -> new (n commits, m files)``), ``pull.current``, ``pull.wip``,
  ``pull.failed``, ``pull.auth``, ``pull.dirty``, and for ``--check`` ``pull.behind`` / ``pull.problem``.
- scripts/my_updater.sh and my_updater.ps1: ``package.upgraded`` (name ``manager:package``,
  detail ``old -> new``), ``package.failed`` (detail: why), ``package.log`` (detail: the log path).
- clone_repos.py: ``clone.cloned``, ``clone.failed``.
- sync_python_envs.py: ``env.synced``, ``env.failed``.
- deploy_configs.py: ``deploy.changed`` (detail ``<action> <destination>``), ``deploy.skipped``,
  ``deploy.count`` (name ``already deployed`` or ``not applicable``, detail: the number),
  ``prune.removed``, ``prune.skipped``.
- app_removals.py and the app installers: ``app.removed``, ``app.remove-failed``,
  ``app.installed``, ``app.install-failed`` (name ``manager:package``).

A detail may hold ``old -> new``; the page draws that as an arrow. Stdlib-only,
like refresh_machine.py: a bare python3 must run the page before uv exists.
"""

import os
import re
import shutil
import sys

import terminal_style

REPORT_ENV = "REFRESH_REPORT"
ARROW = " -> "
GLYPH = {"ok": "●", "warn": "▲", "fail": "✖", "info": "·"}
ROLE = {"ok": "green", "warn": "amber", "fail": "red", "info": "muted"}
STEP_DETAIL = re.compile(r"^(ok|failed|drift)\s+([\d.]+)\s*(\S*)$")
MAX_NAME = 30


def record(kind, name, detail="", environ=None):
    """Append one line to the run's report, or nothing when no refresh run is in progress."""
    path = (os.environ if environ is None else environ).get(REPORT_ENV)
    if not path:
        return
    cells = (str(part).replace("\t", " ").replace("\r", " ").replace("\n", " ") for part in (kind, name, detail))
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("\t".join(cells) + "\n")


def read(path):
    """Every ``(kind, name, detail)`` in the report, in the order written; [] when there is no file."""
    if not path or not os.path.exists(path):
        return []
    lines = []
    with open(path, encoding="utf-8-sig") as handle:
        for raw in handle:
            text = raw.rstrip("\r\n")
            if not text.strip():
                continue
            kind, _, rest = text.partition("\t")
            name, _, detail = rest.partition("\t")
            lines.append((kind.strip(), name.strip(), detail.strip()))
    return lines


def of(lines, kind):
    """The ``(name, detail)`` pairs of one kind."""
    return [(name, detail) for found, name, detail in lines if found == kind]


def count(lines, kind):
    return sum(1 for found, _, _ in lines if found == kind)


def step_detail(status, seconds, family):
    return f"{status} {seconds:.1f} {family}"


def steps_of(lines):
    """``(title, status, seconds, family)`` per recorded step, the pull first when it restarted the run."""
    steps = []
    for title, detail in of(lines, "step"):
        match = STEP_DETAIL.match(detail)
        if not match:
            continue
        steps.append((title, match.group(1), float(match.group(2)), match.group(3)))
    return steps


# %%
# Text helpers #


def elapsed(seconds):
    seconds = int(round(seconds))
    if seconds < 1:
        return "<1s"
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def fit(text, width):
    """Text no wider than ``width``, cut with an ellipsis; never negative."""
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)] + "…"


def plural(number, word, plural_word=None):
    return f"{number} {word if number == 1 else (plural_word or word + 's')}"


def arrow(detail):
    """``old -> new`` drawn as ``old → new``; anything else as it is."""
    return detail.replace(ARROW, " → ")


def join(parts):
    """Summary fragments two spaces apart, the empty ones dropped."""
    return "  ".join(part for part in parts if part)


def terminal_size(stream=None):
    stream = sys.stdout if stream is None else stream
    try:
        if not stream.isatty():
            return 100, 40
        size = shutil.get_terminal_size((100, 40))
        return min(max(size.columns, 60), 140), max(size.lines, 24)
    except (OSError, ValueError, AttributeError):
        return 100, 40


# %%
# Step results #


def family_summary(family, lines, check):
    """One line of what a step's family did, from its report lines; "" when it recorded nothing."""
    if family == "pull":
        if check:
            behind = count(lines, "pull.behind")
            problems = count(lines, "pull.problem")
            return join([f"{behind} behind" if behind else "", f"{problems} not checked" if problems else ""])
        pulled, current = count(lines, "pull.pulled"), count(lines, "pull.current")
        wip, failed = count(lines, "pull.wip"), count(lines, "pull.failed") + count(lines, "pull.auth")
        total = pulled + current + wip + failed
        return join(
            [
                plural(total, "repo") if total else "",
                f"{pulled} pulled" if pulled else "",
                f"{current} current" if current else "",
                f"{wip} wip protected" if wip else "",
                f"{failed} not pulled" if failed else "",
            ]
        )
    if family == "package":
        upgraded, failed = count(lines, "package.upgraded"), count(lines, "package.failed")
        return join([f"{upgraded} upgraded" if upgraded else "", f"{failed} failed" if failed else ""])
    if family == "clone":
        cloned, failed = count(lines, "clone.cloned"), count(lines, "clone.failed")
        return join([f"{cloned} cloned" if cloned else "", f"{failed} failed" if failed else ""])
    if family == "env":
        synced, failed = count(lines, "env.synced"), count(lines, "env.failed")
        return join([plural(synced, "project") + " synced" if synced else "", f"{failed} failed" if failed else ""])
    if family == "deploy":
        changed, skipped = count(lines, "deploy.changed"), count(lines, "deploy.skipped")
        already = dict(of(lines, "deploy.count")).get("already deployed", "")
        return join(
            [
                f"{changed} changed" if changed else "",
                f"{already} already deployed" if already else "",
                f"{skipped} skipped" if skipped else "",
            ]
        )
    if family == "prune":
        removed, skipped = count(lines, "prune.removed"), count(lines, "prune.skipped")
        return join([f"{removed} removed" if removed else "", f"{skipped} skipped" if skipped else ""])
    if family == "remove":
        removed, failed = count(lines, "app.removed"), count(lines, "app.remove-failed")
        return join([f"{removed} removed" if removed else "", f"{failed} failed" if failed else ""])
    if family == "install":
        installed, failed = count(lines, "app.installed"), count(lines, "app.install-failed")
        return join([f"{installed} installed" if installed else "", f"{failed} failed" if failed else ""])
    return ""


def step_rows(lines, check):
    """``(state, title, result, seconds)`` per step for the steps table."""
    rows = []
    for title, status, seconds, family in steps_of(lines):
        summary = family_summary(family, lines, check)
        if status == "ok":
            state, result = "ok", summary or ("no change" if check else "ok")
        elif check:
            state, result = "warn", summary or "drift"
        else:
            state, result = "fail", summary or "failed"
        if status == "ok" and (count(lines, "pull.wip") or count(lines, "pull.failed") or count(lines, "pull.auth")):
            state = "warn" if family == "pull" else state
        rows.append((state, title, result, seconds))
    return rows


# %%
# Detail sections #


def repo_rows(lines, check):
    rows = []
    if check:
        rows += [("warn", name, arrow(detail)) for name, detail in of(lines, "pull.behind")]
        rows += [("fail", name, detail) for name, detail in of(lines, "pull.problem")]
        return rows
    rows += [("ok", name, arrow(detail)) for name, detail in of(lines, "pull.pulled")]
    rows += [("warn", name, join(["wip protected", detail])) for name, detail in of(lines, "pull.wip")]
    rows += [("fail", name, join(["auth required", detail])) for name, detail in of(lines, "pull.auth")]
    rows += [("fail", name, join(["failed", detail])) for name, detail in of(lines, "pull.failed")]
    rows += [("ok", name, "cloned") for name, _ in of(lines, "clone.cloned")]
    rows += [("fail", name, join(["clone failed", detail])) for name, detail in of(lines, "clone.failed")]
    rows += [("fail", name, join(["uv sync failed", detail])) for name, detail in of(lines, "env.failed")]
    notes = []
    current = count(lines, "pull.current")
    if current:
        notes.append(f"{current} already current")
    dirty = count(lines, "pull.dirty")
    if dirty:
        notes.append(f"{dirty} with uncommitted changes")
    synced = count(lines, "env.synced")
    if synced:
        notes.append(f"{plural(synced, 'uv project')} synced")
    if notes:
        rows.append(("info", "", ", ".join(notes)))
    return rows


def package_rows(lines):
    rows = [("ok", name, arrow(detail)) for name, detail in of(lines, "package.upgraded")]
    rows += [("fail", name, detail) for name, detail in of(lines, "package.failed")]
    rows += [("info", "", "full output: " + detail) for _, detail in of(lines, "package.log")]
    return rows


def config_rows(lines):
    rows = [("ok", name, detail) for name, detail in of(lines, "deploy.changed")]
    rows += [("warn", name, join(["skipped", detail])) for name, detail in of(lines, "deploy.skipped")]
    rows += [("ok", "pruned", join([name, detail])) for name, detail in of(lines, "prune.removed")]
    rows += [("warn", "not pruned", join([name, detail])) for name, detail in of(lines, "prune.skipped")]
    counts = dict(of(lines, "deploy.count"))
    notes = [f"{counts[key]} {key}" for key in ("already deployed", "not applicable") if counts.get(key)]
    if notes:
        rows.append(("info", "", ", ".join(notes) + " here"))
    return rows


def app_rows(lines, missing, asked_missing):
    rows = [("ok", name, join(["installed", detail])) for name, detail in of(lines, "app.installed")]
    rows += [("fail", name, join(["install failed", detail])) for name, detail in of(lines, "app.install-failed")]
    rows += [("ok", name, join(["removed", detail])) for name, detail in of(lines, "app.removed")]
    rows += [("fail", name, join(["removal failed", detail])) for name, detail in of(lines, "app.remove-failed")]
    if asked_missing and missing is None:
        rows.append(("fail", "", "could not work out which listed apps are installed (app_lists.py --missing)"))
    elif missing:
        for name in missing.get("missing", []):
            rows.append(("warn", name, "listed, not installed; the next myupdater offers it again"))
        for name in missing.get("elsewhere", []):
            rows.append(("info", name, "installed, but not by the manager its list names"))
        ignored = missing.get("ignored", [])
        if ignored:
            where = (missing.get("ignore-file") or ["the ignore file"])[0]
            rows.append(("info", "", f"{plural(len(ignored), 'app')} ignored here by {where}: {', '.join(ignored)}"))
    return rows


# %%
# Drawing #


ORDER = {"fail": 0, "warn": 1, "ok": 2, "info": 3}


def ordered(rows):
    """Failures first, then warnings, then what went fine, then the notes; each group in its written order."""
    return sorted(rows, key=lambda row: ORDER[row[0]])


def budget_rows(sections, available):
    """
    Cap each section so the page fits. A cut drops the plain ok rows, never a
    failure, a warning or the closing note, and says how many rows are above in
    the log.
    """
    sections = [(title, ordered(rows)) for title, rows in sections]
    total = sum(len(rows) for _, rows in sections)
    if total <= available or not sections:
        return sections
    fitted = []
    for title, rows in sections:
        share = max(3, int(available * len(rows) / total))
        if len(rows) > share:
            notes = [row for row in rows if row[0] == "info"]
            keep = [row for row in rows if row[0] != "info"][: max(1, share - 1 - len(notes))]
            dropped = len(rows) - len(keep) - len(notes)
            rows = keep + [("info", "", f"… {dropped} more, above in the log")] + notes
        fitted.append((title, rows))
    return fitted


def draw_row(state, name, text, width, name_width, color, right=""):
    paint = terminal_style.paint
    glyph = paint(GLYPH[state], ROLE[state], color, bold=state != "info")
    name_role = "ink" if state in ("ok", "warn", "fail") else "muted"
    text_role = {"ok": "ink2", "warn": "amber", "fail": "red", "info": "muted"}[state]
    room = width - 2 - name_width - 2 - (len(right) + 2 if right else 0)
    body = fit(text, room)
    line = f"{glyph} {paint(fit(name, name_width).ljust(name_width), name_role, color)}  "
    line += paint(body.ljust(room) if right else body, text_role, color)
    if right:
        line += "  " + paint(right, "muted", color)
    return line.rstrip()


def draw_section(title, rows, width, color, trailer=""):
    paint = terminal_style.paint
    header = terminal_style.section(title, color)
    if trailer:
        pad = max(1, width - len("// " + title) - len(trailer))
        header += " " * pad + paint(trailer, "muted", color)
    name_width = min(MAX_NAME, max([len(name) for _, name, *_ in rows] + [4]))
    lines = ["", header, paint("─" * width, "rule", color)]
    for row in rows:
        state, name, text = row[:3]
        right = row[3] if len(row) > 3 else ""
        lines.append(draw_row(state, name, text, width, name_width, color, right))
    return lines


def render(lines, command, host, started, seconds, color, check=False, missing=None, asked_missing=False, size=None):
    """The whole page as text ending in a newline; ``size`` is ``(columns, lines)``."""
    paint = terminal_style.paint
    width, height = size or terminal_size()
    steps = step_rows(lines, check)
    ok = sum(1 for state, *_ in steps if state == "ok")
    failed = sum(1 for state, *_ in steps if state == "fail")
    warned = sum(1 for state, *_ in steps if state == "warn")
    title = paint(terminal_style.PROMPT + " ", "green", color, bold=True) + paint(command, "ink", color, bold=True)
    meta = paint(f"  {host} · {started} · {elapsed(seconds)}", "muted", color)
    out = [title + meta]

    trailer = join(
        [f"{ok} ok" if ok else "", f"{warned} drift" if check and warned else "", f"{failed} failed" if failed else ""]
    )
    rows = [(state, title_, result, elapsed(secs)) for state, title_, result, secs in steps]
    out += draw_section("steps", rows or [("info", "", "no steps ran")], width, color, trailer)

    sections = [
        ("repos", repo_rows(lines, check)),
        ("packages", package_rows(lines)),
        ("configs", config_rows(lines)),
        ("apps", app_rows(lines, missing, asked_missing)),
    ]
    sections = [(title_, rows) for title_, rows in sections if rows]
    available = height - len(out) - 3 * len(sections) - 2
    for title_, rows in budget_rows(sections, max(available, 3 * len(sections))):
        out += draw_section(title_, rows, width, color)
    return "\n".join(out) + "\n"
