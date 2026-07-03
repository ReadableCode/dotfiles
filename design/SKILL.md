---
name: terminal-navy
description: Apply the readablecode "terminal navy" house design system (navy surfaces, monospace type, green prompt accent, amber highlights, // section headers) when building or restyling any web UI, page, dashboard, or chart. Use whenever styling frontend work so it matches site.tinkernet.me and load-log.
---

# terminal-navy design system

Read `STYLE.md` in this skill's directory for the complete spec: color tokens,
typography, component patterns (terminal window, stat pills, `//` headers,
prompt brand), and chart rules including the validated two-series palette.
`tokens.css` has the same values as CSS custom properties ready to copy into a
project. `previews/*.html` are self-contained reference renderings of each
piece — open one when unsure how a component should look.

Hard rules that must survive any adaptation:

- Monospace everywhere (`ui-monospace, "SF Mono", "Cascadia Mono", Menlo,
  Consolas, monospace`); lowercase headings and labels (initialisms keep case).
- Navy surfaces: page `#0d1420`, cards `#121b2a`; 1px hairline borders
  `rgba(148,148,163,0.16)`-family per tokens; 8px radius; no shadows.
- Green is the accent (`#2ea043` fills, `#56d364` text glyphs like `❯` and
  `//`); amber (`#b8860b` / `#e3b341`) is the highlight, never a second theme.
- Charts: single series green; two series amber+green exactly as specced
  (CVD-validated); GitHub-dark ramp for activity heatmaps.
