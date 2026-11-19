# %%
# Imports #

import argparse
import os
import plistlib
import re
import sqlite3
import subprocess
import sys

# %%
# Variables #

DB_PATH = os.path.expanduser("~/Library/Shortcuts/Shortcuts.sqlite")
DEFAULT_OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "personal_credentials", "shortcuts"
)
# Used when a shortcut has no icon row: the Shortcuts app's own default glyph and colour.
DEFAULT_ICON = {"WFWorkflowIconStartColor": 4282601983, "WFWorkflowIconGlyphNumber": 59511}
QUERY = """
select s.ZNAME, s.ZWORKFLOWID, a.ZDATA, s.ZINPUTCLASSESDATA, s.ZOUTPUTCLASSESDATA,
       s.ZIMPORTQUESTIONSDATA, s.ZNOINPUTBEHAVIORDATA, s.ZHASSHORTCUTINPUTVARIABLES,
       s.ZMINIMUMCLIENTVERSION, s.ZLASTMIGRATEDCLIENTVERSION,
       i.ZBACKGROUNDCOLORVALUE, i.ZGLYPHNUMBER
from ZSHORTCUT s
left join ZSHORTCUTACTIONS a on a.Z_PK = s.ZACTIONS
left join ZSHORTCUTICON i on i.Z_PK = s.ZICON
where s.ZTOMBSTONED = 0 and s.ZCONFLICTOF is null and coalesce(s.ZHIDDENFROMLIBRARYANDSYNC, 0) = 0
order by s.ZNAME
"""


# %%
# Functions #


def load_blob(blob, default):
    """A stored property list, or default when the column is empty."""
    if not blob:
        return default
    return plistlib.loads(blob)


def slugify(name):
    """A file name for a shortcut: lowercase, words joined by underscores."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "unnamed"


def build_workflow(row):
    """The same top-level dict a .shortcut file holds, built from one database row."""
    (_, _, actions, in_classes, out_classes, questions, no_input, has_input_vars, min_ver, client_ver, color, glyph) = (
        row
    )
    icon = dict(DEFAULT_ICON)
    if color is not None:
        icon["WFWorkflowIconStartColor"] = color & 0xFFFFFFFF
    if glyph is not None:
        icon["WFWorkflowIconGlyphNumber"] = glyph
    workflow = {
        "WFWorkflowActions": load_blob(actions, []),
        "WFWorkflowClientVersion": client_ver or "",
        "WFWorkflowHasShortcutInputVariables": bool(has_input_vars),
        "WFWorkflowIcon": icon,
        "WFWorkflowImportQuestions": load_blob(questions, []),
        "WFWorkflowInputContentItemClasses": load_blob(in_classes, []),
        "WFWorkflowMinimumClientVersion": int(min_ver) if min_ver and str(min_ver).isdigit() else 900,
        "WFWorkflowMinimumClientVersionString": str(min_ver or "900"),
        "WFWorkflowOutputContentItemClasses": load_blob(out_classes, []),
        "WFWorkflowTypes": [],
    }
    no_input_behavior = load_blob(no_input, None)
    if no_input_behavior is not None:
        workflow["WFWorkflowNoInputBehavior"] = no_input_behavior
    return workflow


def read_shortcuts(db_path=DB_PATH):
    """(name, workflow dict) for every shortcut in the library, read-only."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(QUERY).fetchall()
    finally:
        con.close()
    return [(row[0], build_workflow(row)) for row in rows]


def file_names(names):
    """One unique .plist name per shortcut, in input order; a repeated slug gets _2, _3."""
    seen = {}
    result = []
    for name in names:
        slug = slugify(name)
        seen[slug] = seen.get(slug, 0) + 1
        result.append(f"{slug}.plist" if seen[slug] == 1 else f"{slug}_{seen[slug]}.plist")
    return result


def export(out_dir, db_path=DB_PATH):
    """Write one XML plist per shortcut; remove plists for shortcuts no longer in the library."""
    shortcuts = read_shortcuts(db_path)
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for (name, workflow), fname in zip(shortcuts, file_names([n for n, _ in shortcuts])):
        path = os.path.join(out_dir, fname)
        with open(path, "wb") as f:
            plistlib.dump(workflow, f, fmt=plistlib.FMT_XML, sort_keys=True)
        written.append(fname)
        print(f"wrote {fname}  ({name})")
    for fname in sorted(os.listdir(out_dir)):
        if fname.endswith(".plist") and fname not in written:
            os.remove(os.path.join(out_dir, fname))
            print(f"removed {fname}  (no longer in the library)")
    return written


def sign(plist_path, out_path):
    """Make an importable .shortcut from an exported plist with the system `shortcuts sign`."""
    with open(plist_path, "rb") as f:
        workflow = plistlib.load(f)
    # `shortcuts sign` refuses an input whose name does not end in .shortcut.
    unsigned = re.sub(r"(\.shortcut)?$", ".unsigned.shortcut", out_path, count=1)
    with open(unsigned, "wb") as f:
        plistlib.dump(workflow, f, fmt=plistlib.FMT_BINARY)
    try:
        subprocess.run(["shortcuts", "sign", "--mode", "anyone", "--input", unsigned, "--output", out_path], check=True)
    finally:
        os.remove(unsigned)
    print(f"signed {out_path}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Export every Shortcuts.app shortcut on this Mac to one XML plist each (read-only on the library)."
    )
    parser.add_argument(
        "--out-dir", default=DEFAULT_OUT_DIR, help="where the plists go (default: personal_credentials/shortcuts)"
    )
    parser.add_argument("--db", default=DB_PATH, help="the Shortcuts library database")
    parser.add_argument(
        "--sign", nargs=2, metavar=("PLIST", "OUT"), help="sign one exported plist into an importable .shortcut"
    )
    args, _ = parser.parse_known_args(argv)
    if sys.platform != "darwin":
        print("Shortcuts exists only on macOS")
        return 1
    if args.sign:
        sign(*args.sign)
        return 0
    export(os.path.normpath(args.out_dir), args.db)
    return 0


# %%
# Main #

if __name__ == "__main__":
    main()

# %%
