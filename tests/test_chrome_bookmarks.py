# %%
# Imports #

import os

import config_test_utils  # noqa F401
from src import chrome_bookmarks

# %%
# Helpers #


def url(name, href):
    return {"type": "url", "name": name, "url": href, "date_added": "13265679455000000"}


def folder(name, children):
    return {"type": "folder", "name": name, "children": children, "date_added": "13265679455000000"}


def sync_duplicated_tree():
    # The shape Chrome Sync leaves after a device reconnects: every top-level
    # folder twice, with an addition made inside one copy only.
    first = folder("Self-Hosted", [folder("Behemoth", [url("Plex", "http://a/plex")])])
    second = folder(
        "Self-Hosted",
        [folder("Behemoth", [url("Plex", "http://a/plex")]), folder("Nukbuntu", [url("Kuma", "http://b/kuma")])],
    )
    loose = url("Plex", "https://app.plex.tv/desktop#")
    return {
        "checksum": "abc",
        "sync_metadata": "xyz",
        "version": 1,
        "roots": {
            "bookmark_bar": folder("Bookmarks Bar", [first, second, loose, dict(loose)]),
            "other": folder("Other Bookmarks", []),
            "synced": folder("Mobile Bookmarks", []),
        },
    }


# %%
# Tests #


def test_merge_children_collapses_same_name_folders_and_keeps_additions():
    report = []
    merged = chrome_bookmarks.merge_children(sync_duplicated_tree()["roots"]["bookmark_bar"]["children"], "", report)

    assert [c["name"] for c in merged] == ["Self-Hosted", "Plex"]
    self_hosted = merged[0]["children"]
    assert [c["name"] for c in self_hosted] == ["Behemoth", "Nukbuntu"]
    assert [c["url"] for c in self_hosted[0]["children"]] == ["http://a/plex"]
    assert "merged folder /Self-Hosted" in report
    assert "dropped duplicate /Plex" in report


def test_merge_children_keeps_same_url_in_different_folders():
    # A url that legitimately lives in two folders (Our Cash under Household
    # and under My Hosted Apps) is not a duplicate.
    merged = chrome_bookmarks.merge_children(
        [folder("A", [url("x", "http://x")]), folder("B", [url("x", "http://x")])]
    )
    assert [c["children"][0]["url"] for c in merged] == ["http://x", "http://x"]


def test_dedupe_bookmarks_drops_live_file_metadata():
    tree = sync_duplicated_tree()
    tree["roots"]["bookmark_bar"]["guid"] = "g1"
    tree["roots"]["bookmark_bar"]["children"][0]["id"] = "5"
    tree["roots"]["bookmark_bar"]["children"][0]["children"][0]["children"][0]["date_last_used"] = "9"
    deduped = chrome_bookmarks.dedupe_bookmarks(tree)
    assert set(deduped) == {"roots", "version"}
    assert set(deduped["roots"]) == {"bookmark_bar", "other", "synced"}
    bar = deduped["roots"]["bookmark_bar"]
    assert set(bar) == {"children", "date_added", "name", "type"}
    assert set(bar["children"][0]) == {"children", "date_added", "name", "type"}
    assert set(bar["children"][0]["children"][0]["children"][0]) == {"date_added", "name", "type", "url"}


def test_html_escapes_apostrophes_the_way_chrome_decodes_them(tmp_path):
    tree = {
        "version": 1,
        "roots": {
            "bookmark_bar": folder("Bookmarks Bar", [url("Charlie's Site & co", 'http://x/?q="a"&b=<c>')]),
            "other": folder("Other Bookmarks", [url("Loose", "http://loose")]),
        },
    }
    out = tmp_path / "bookmarks.html"
    chrome_bookmarks.export_bookmarks_as_html(tree, str(out))
    text = out.read_text(encoding="utf-8")

    assert "&#x27;" not in text
    assert ">Charlie's Site &amp; co</A>" in text
    assert 'HREF="http://x/?q=&quot;a&quot;&amp;b=&lt;c&gt;"' in text
    assert 'PERSONAL_TOOLBAR_FOLDER="true">Bookmarks Bar</H3>' in text
    assert text.index(">Loose</A>") > text.index("</DL><p>")


def test_write_outputs_writes_both_files(tmp_path):
    chrome_bookmarks.write_outputs(sync_duplicated_tree(), str(tmp_path))
    assert (tmp_path / "personal_bookmarks.json").exists()
    assert (tmp_path / "personal_bookmarks.html").exists()


def test_check_drift_says_so_and_passes_when_there_is_no_repo_copy(tmp_path, capsys):
    # personal_credentials not cloned, or bookmarks never exported.
    missing = tmp_path / "personal_bookmarks.json"

    assert chrome_bookmarks.check_drift(sync_duplicated_tree(), str(missing)) == 0
    assert "nothing to compare against" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


def test_check_drift_passes_when_the_repo_copy_matches(tmp_path, capsys):
    chrome_bookmarks.write_outputs(sync_duplicated_tree(), str(tmp_path))
    repo_json = tmp_path / "personal_bookmarks.json"
    before = repo_json.read_text(encoding="utf-8")

    assert chrome_bookmarks.check_drift(sync_duplicated_tree(), str(repo_json)) == 0
    assert "match" in capsys.readouterr().out
    assert repo_json.read_text(encoding="utf-8") == before


def test_check_drift_exits_one_and_shows_the_lines_that_differ(tmp_path, capsys):
    chrome_bookmarks.write_outputs(sync_duplicated_tree(), str(tmp_path))
    repo_json = tmp_path / "personal_bookmarks.json"
    live = sync_duplicated_tree()
    live["roots"]["other"]["children"].append(url("Added Since", "http://added"))

    assert chrome_bookmarks.check_drift(live, str(repo_json)) == 1
    out = capsys.readouterr().out
    assert "differ" in out
    assert "Added Since" in out


def test_check_drift_prints_at_most_the_preview_and_never_writes_to_the_repo(tmp_path, capsys):
    chrome_bookmarks.write_outputs(sync_duplicated_tree(), str(tmp_path))
    repo_json = tmp_path / "personal_bookmarks.json"
    repo_html = tmp_path / "personal_bookmarks.html"
    stamps = {p.name: p.stat().st_mtime_ns for p in (repo_json, repo_html)}
    live = sync_duplicated_tree()
    live["roots"]["other"]["children"] = [url(f"New {i}", f"http://new/{i}") for i in range(40)]

    assert chrome_bookmarks.check_drift(live, str(repo_json)) == 1
    out = capsys.readouterr().out
    diff_lines = [line for line in out.splitlines() if line.startswith(("+", "-", "@@"))]
    assert len(diff_lines) <= chrome_bookmarks.DIFF_PREVIEW_LINES
    assert "more diff lines" in out
    assert sorted(p.name for p in tmp_path.iterdir()) == ["personal_bookmarks.html", "personal_bookmarks.json"]
    assert {p.name: p.stat().st_mtime_ns for p in (repo_json, repo_html)} == stamps


def test_repo_json_path_is_the_committed_copy_in_personal_credentials():
    path = chrome_bookmarks.get_repo_json_path()
    assert path.endswith(os.path.join("personal_credentials", "bookmarks", "personal_bookmarks.json"))
