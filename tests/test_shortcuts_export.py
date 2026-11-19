import plistlib
import sqlite3

from src import shortcuts_export


def make_db(path, shortcuts):
    """A minimal Shortcuts library: name -> list of actions."""
    con = sqlite3.connect(path)
    con.executescript(
        """
        create table ZSHORTCUT (Z_PK integer primary key, ZNAME varchar, ZWORKFLOWID varchar, ZACTIONS integer,
            ZICON integer, ZTOMBSTONED integer, ZCONFLICTOF integer, ZHIDDENFROMLIBRARYANDSYNC integer,
            ZINPUTCLASSESDATA blob, ZOUTPUTCLASSESDATA blob, ZIMPORTQUESTIONSDATA blob, ZNOINPUTBEHAVIORDATA blob,
            ZHASSHORTCUTINPUTVARIABLES integer, ZMINIMUMCLIENTVERSION varchar, ZLASTMIGRATEDCLIENTVERSION varchar);
        create table ZSHORTCUTACTIONS (Z_PK integer primary key, ZDATA blob);
        create table ZSHORTCUTICON (Z_PK integer primary key, ZBACKGROUNDCOLORVALUE integer, ZGLYPHNUMBER integer);
        """
    )
    for pk, (name, actions, tombstoned) in enumerate(shortcuts, start=1):
        con.execute(
            "insert into ZSHORTCUTACTIONS values (?, ?)", (pk, plistlib.dumps(actions, fmt=plistlib.FMT_BINARY))
        )
        con.execute("insert into ZSHORTCUTICON values (?, ?, ?)", (pk, -1, 61440))
        con.execute(
            "insert into ZSHORTCUT values (?, ?, ?, ?, ?, ?, null, 0, ?, null, null, null, 0, '1106', '4046')",
            (pk, name, f"id-{pk}", pk, pk, tombstoned, plistlib.dumps(["WFStringContentItem"])),
        )
    con.commit()
    con.close()


def test_slugify_and_unique_names():
    assert shortcuts_export.slugify("Wake Up!") == "wake_up"
    assert shortcuts_export.file_names(["A b", "a-b", "C"]) == ["a_b.plist", "a_b_2.plist", "c.plist"]


def test_export_writes_live_shortcuts_and_prunes_stale(tmp_path):
    db = tmp_path / "lib.sqlite"
    action = {"WFWorkflowActionIdentifier": "is.workflow.actions.comment", "WFWorkflowActionParameters": {}}
    make_db(db, [("Wake Up", [action], 0), ("Gone", [], 1)])
    out = tmp_path / "out"
    out.mkdir()
    (out / "old_one.plist").write_bytes(b"x")
    (out / "notes.md").write_text("kept")

    assert shortcuts_export.export(str(out), str(db)) == ["wake_up.plist"]

    workflow = plistlib.loads((out / "wake_up.plist").read_bytes())
    assert workflow["WFWorkflowActions"] == [action]
    assert workflow["WFWorkflowInputContentItemClasses"] == ["WFStringContentItem"]
    assert workflow["WFWorkflowIcon"] == {"WFWorkflowIconStartColor": 0xFFFFFFFF, "WFWorkflowIconGlyphNumber": 61440}
    assert workflow["WFWorkflowMinimumClientVersion"] == 1106
    assert not (out / "old_one.plist").exists()
    assert (out / "notes.md").exists()
