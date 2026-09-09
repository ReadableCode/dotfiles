# %%
# Imports #

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
