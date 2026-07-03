# readablecode design system — "terminal navy"

The house style shared by the readablecode portfolio site (site.tinkernet.me),
Load Log, and future projects: navy terminal surfaces, monospace type, a green
prompt accent, amber highlights, and `// section` headers.

This file is the source of truth. `tokens.css` carries the same values as CSS
custom properties; `previews/*.html` are self-contained renderings of the core
pieces. A live reference implementation (Streamlit + Altair) is
`backend/src/web/app.py` + `backend/.streamlit/config.toml` in the load-log repo.

## Tokens

| Role | Token | Value |
|---|---|---|
| Page background | `--bg` | `#0d1420` |
| Card / panel surface | `--surface` | `#121b2a` |
| Raised surface (terminal title bar) | `--surface-2` | `#182333` |
| Hairline border | `--border` | `rgba(148, 163, 184, 0.16)` |
| Primary text | `--ink` | `#dbe4f0` |
| Secondary text | `--ink-2` | `#9fb0c3` |
| Muted text (labels, captions, axes) | `--muted` | `#7d8b9e` |
| Chart gridline | `--grid` | `#1c2739` |
| Chart axis / domain | `--axis` | `#2a3850` |
| Accent green (buttons, primary series) | `--green` | `#2ea043` |
| Bright green (text accents: prompt `❯`, `//`, links, dots) | `--green-bright` | `#56d364` |
| Amber (second chart series) | `--amber` | `#b8860b` |
| Bright amber (text highlights, today-ring) | `--amber-bright` | `#e3b341` |
| Terminal dots | — | red `#f87171` · yellow `#fbbf24` · green `#34d399` |
| Heatmap empty cell | — | `#161b22` |
| Heatmap activity ramp (GitHub dark) | — | `#0e4429` → `#006d32` → `#26a641` → `#39d353` |

Corner radius: **8px** for cards/tiles/forms, **10px** for terminal windows.
Borders are always the 1px hairline `--border` — no shadows.

## Typography

- Everything is monospace: `ui-monospace, "SF Mono", "Cascadia Mono", Menlo,
  Consolas, monospace`. No serif or sans anywhere, including headings and
  numbers.
- Headings and UI labels are **lowercase** ("day volume", "workouts");
  initialisms keep their case ("1RM").
- Numbers that align in columns use `font-variant-numeric: tabular-nums`.

## Signature components

**Section header** — `//` in bright green + lowercase title, hairline rule
below:

```html
<h2><span style="color: var(--green-bright)">//</span> section name</h2>
```

**Prompt brand** — `❯` in bright green before the app name: `❯ load-log`.

**Stat pill / tile** — `--surface` card, hairline border, 8px radius; label row
starts with a 7px bright-green dot with a soft glow
(`box-shadow: 0 0 6px rgba(86,211,100,.65)`); big tabular-nums value with a
muted unit suffix; muted sub-line. Red dot (`#f87171`) for error/timeout
states.

**Terminal window** — title bar on `--surface-2` with three 11px dots
(red/yellow/green) + muted `user@host: ~` title; body on `--surface` with
1.8 line-height; `❯` prompt lines; amber `<span class="hl">` for the word the
user should act on.

**Buttons** — primary: solid `--green` with dark-navy-readable text; secondary:
`--surface` + hairline border. 8px radius.

## Chart rules (see the dataviz notes in load-log's app.py)

- Transparent chart background; axis labels `--muted`, axis titles `--ink-2`,
  grid `--grid`, domain/ticks `--axis`; monospace font.
- Single-series charts use `--green` (`#2ea043`); area fills fade from
  `#2ea04355` to transparent.
- Two-series charts pair amber `#b8860b` with green `#2ea043` — this exact
  pair is validated colorblind-safe on `--bg` (worst CVD ΔE 14.2, both ≥3:1
  contrast). Keep a visible legend and different mark shapes (dots vs line)
  as secondary encoding. Do not add a third series color without re-validating.
- Activity heatmaps use the GitHub-dark green ramp on `#161b22` empty cells,
  cell strokes in `--bg`, and an `--amber-bright` ring for "today".

## Applying this in a new project

Copy `tokens.css` (or the table above) and paste this into the project's
CLAUDE.md:

> UI follows the readablecode "terminal navy" design system (see
> ReadableCode/load-log `design/STYLE.md`, or the "readablecode design system"
> Claude Design project): navy surfaces (bg `#0d1420`, cards `#121b2a`),
> monospace type everywhere, lowercase labels, `//` section headers with the
> slashes in `#56d364`, green accent `#2ea043` / bright `#56d364`, amber
> highlights `#b8860b` / bright `#e3b341`, hairline borders
> `rgba(148,163,184,.16)`, 8px radius, no shadows. Charts: green primary
> series, amber+green for two series, GitHub-dark heatmap ramp.
