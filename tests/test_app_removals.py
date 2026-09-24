# %%
# Imports #

import os

import config_test_utils  # noqa F401
import pytest
import yaml

from src import app_removals

# %%
# Helpers #


def write_removals(directory, entries, name="app_removals.yaml"):
    os.makedirs(str(directory), exist_ok=True)
    path = os.path.join(str(directory), name)
    with open(path, "w", encoding="utf-8") as file_handle:
        yaml.safe_dump(entries, file_handle)
    return path


def write_list(directory, name, lines):
    os.makedirs(str(directory), exist_ok=True)
    path = os.path.join(str(directory), name)
    with open(path, "w", encoding="utf-8") as file_handle:
        file_handle.write("\n".join(lines) + "\n")
    return path


def fake_run(responses):
    """A run_capture stand-in: maps the first argv token to (code, output)."""

    def run(argv):
        if not argv:
            return None, ""
        return responses.get(argv[0], (None, ""))

    return run


CASK_ENTRY = {"name": "retired_cask", "manager": "cask", "package": "vnc-viewer"}


def pair(found):
    """The two outcomes most tests look at."""
    return found.removable, found.protected


@pytest.fixture(autouse=True)
def no_machine_state(monkeypatch):
    """No test may read this machine's context app lists or its real winget."""
    monkeypatch.setattr(app_removals.app_lists, "discover_app_lists", lambda: [])
    monkeypatch.setattr(app_removals, "duplicate_groups", lambda **kwargs: [])


# %%
# Loading #


def test_entries_load_with_their_source_file(tmp_path):
    path = write_removals(tmp_path, [CASK_ENTRY])
    entries = app_removals.load_app_removals([path])
    assert entries[0]["package"] == "vnc-viewer"
    assert entries[0]["_file"] == path


def test_a_missing_required_key_is_a_hard_error(tmp_path):
    path = write_removals(tmp_path, [{"name": "no_package", "manager": "cask"}])
    with pytest.raises(ValueError, match="missing 'package'"):
        app_removals.load_app_removals([path])


def test_an_unknown_manager_is_a_hard_error(tmp_path):
    path = write_removals(tmp_path, [{"name": "bad", "manager": "snap", "package": "x"}])
    with pytest.raises(ValueError, match="Unknown manager"):
        app_removals.load_app_removals([path])


def test_a_duplicate_name_across_files_is_a_hard_error(tmp_path):
    first = write_removals(tmp_path / "a", [CASK_ENTRY])
    second = write_removals(tmp_path / "b", [CASK_ENTRY])
    with pytest.raises(ValueError, match="Duplicate app removal entry name"):
        app_removals.load_app_removals([first, second])


def test_a_removals_file_must_be_a_list(tmp_path):
    path = os.path.join(str(tmp_path), "app_removals.yaml")
    os.makedirs(str(tmp_path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        file_handle.write("name: not-a-list\n")
    with pytest.raises(ValueError, match="must be a YAML list"):
        app_removals.load_app_removals([path])


# %%
# Candidates #


def test_an_installed_listed_app_is_removable(tmp_path):
    write_list(tmp_path, "Brewfile", [])
    removable, protected = pair(
        app_removals.candidates(
            [dict(CASK_ENTRY)],
            system="Darwin",
            hostname="ENVY",
            lists_dir=str(tmp_path),
            overlay_paths=[],
            run=fake_run({"brew": (0, "vnc-viewer\nslack\n")}),
        )
    )
    assert [entry["package"] for entry in removable] == ["vnc-viewer"]
    assert protected == []


def test_an_app_list_still_naming_the_package_wins(tmp_path):
    """The whole point of the guard: re-adding a package beats a stale removal line."""
    write_list(tmp_path, "Brewfile", ['cask "vnc-viewer"'])
    removable, protected = pair(
        app_removals.candidates(
            [dict(CASK_ENTRY)],
            system="Darwin",
            hostname="ENVY",
            lists_dir=str(tmp_path),
            overlay_paths=[],
            run=fake_run({"brew": (0, "vnc-viewer\n")}),
        )
    )
    assert removable == []
    assert [entry["name"] for entry in protected] == ["retired_cask"]


def test_a_package_that_is_not_installed_is_not_offered(tmp_path):
    write_list(tmp_path, "Brewfile", [])
    removable, _ = pair(
        app_removals.candidates(
            [dict(CASK_ENTRY)],
            system="Darwin",
            hostname="ENVY",
            lists_dir=str(tmp_path),
            overlay_paths=[],
            run=fake_run({"brew": (0, "slack\n")}),
        )
    )
    assert removable == []


def test_entries_for_another_platform_are_skipped(tmp_path):
    write_list(tmp_path, "Brewfile", [])
    removable, protected = pair(
        app_removals.candidates(
            [dict(CASK_ENTRY)],
            system="Linux",
            hostname="NUKBUNTU",
            lists_dir=str(tmp_path),
            overlay_paths=[],
            run=fake_run({"brew": (0, "vnc-viewer\n")}),
        )
    )
    assert (removable, protected) == ([], [])


def test_the_hosts_filter_gates_an_entry(tmp_path):
    write_list(tmp_path, "Brewfile", [])
    entry = dict(CASK_ENTRY, hosts=["MacBookProM5"])
    responses = fake_run({"brew": (0, "vnc-viewer\n")})
    on_envy, _ = pair(
        app_removals.candidates(
            [entry], system="Darwin", hostname="ENVY", lists_dir=str(tmp_path), overlay_paths=[], run=responses
        )
    )
    on_macbook, _ = pair(
        app_removals.candidates(
            [entry], system="Darwin", hostname="MACBOOKPROM5", lists_dir=str(tmp_path), overlay_paths=[], run=responses
        )
    )
    assert on_envy == []
    assert [e["package"] for e in on_macbook] == ["vnc-viewer"]


def test_a_manager_that_is_not_installed_offers_nothing(tmp_path):
    """A box with no flatpak has no flatpak removals; that is not a failure."""
    write_list(tmp_path, "linux_apps_flatpak.txt", [])
    entry = {"name": "gone", "manager": "flatpak", "package": "com.example.App"}
    removable, _ = pair(
        app_removals.candidates(
            [entry], system="Linux", hostname="NUKBUNTU", lists_dir=str(tmp_path), overlay_paths=[], run=fake_run({})
        )
    )
    assert removable == []


def test_choco_output_is_split_on_its_separator(tmp_path):
    write_list(tmp_path, "windows_apps_personal_choco.txt", [])
    entry = {"name": "gone", "manager": "choco", "package": "vnc-viewer"}
    removable, _ = pair(
        app_removals.candidates(
            [entry],
            system="Windows",
            hostname="RYZENWHITE",
            lists_dir=str(tmp_path),
            overlay_paths=[],
            run=fake_run({"choco": (0, "vnc-viewer|8.5.0\ntightvnc|2.8.88\n")}),
        )
    )
    assert [e["package"] for e in removable] == ["vnc-viewer"]


def test_winget_presence_is_asked_per_id(tmp_path):
    """winget list is fixed-width columns, so presence is an exit code, not parsed text."""
    write_list(tmp_path, "windows_apps_personal_winget.txt", [])
    entry = {"name": "gone", "manager": "winget", "package": "RealVNC.VNC-Connect"}
    removable, _ = pair(
        app_removals.candidates(
            [entry],
            system="Windows",
            hostname="RYZENWHITE",
            lists_dir=str(tmp_path),
            overlay_paths=[],
            run=fake_run({"winget": (0, "")}),
        )
    )
    assert [e["package"] for e in removable] == ["RealVNC.VNC-Connect"]


def test_installed_lookup_is_case_insensitive(tmp_path):
    write_list(tmp_path, "windows_apps_personal_choco.txt", [])
    entry = {"name": "gone", "manager": "choco", "package": "VNC-Viewer"}
    removable, _ = pair(
        app_removals.candidates(
            [entry],
            system="Windows",
            hostname="RYZENWHITE",
            lists_dir=str(tmp_path),
            overlay_paths=[],
            run=fake_run({"choco": (0, "vnc-viewer|8.5.0\n")}),
        )
    )
    assert [e["package"] for e in removable] == ["VNC-Viewer"]


# %%
# Removal #


def test_remove_builds_the_managers_uninstall_command():
    seen = {}

    class Result:
        returncode = 0

    def run(argv):
        seen["argv"] = argv
        return Result()

    assert app_removals.remove_package(dict(CASK_ENTRY), run=run)
    assert seen["argv"] == ["brew", "uninstall", "--cask", "vnc-viewer"]


def test_remove_reports_failure_when_the_manager_exits_non_zero():
    class Result:
        returncode = 1

    assert not app_removals.remove_package(dict(CASK_ENTRY), run=lambda argv: Result())


def test_apt_removal_simulates_before_it_asks(capsys):
    entry = {"name": "gone", "manager": "apt", "package": "realvnc-vnc-server"}
    app_removals.show_simulation(entry, run=fake_run({"apt-get": (0, "Remv realvnc-vnc-server\n")}))
    assert "Remv realvnc-vnc-server" in capsys.readouterr().out


def test_a_manager_with_no_dry_run_says_so(capsys):
    app_removals.show_simulation(dict(CASK_ENTRY), run=fake_run({}))
    assert "no dry run" in capsys.readouterr().out


# %%
# Run #


def test_run_removes_nothing_without_a_terminal(tmp_path, monkeypatch, capsys):
    """An unattended run reports and stops; nothing is uninstalled without an answer."""
    monkeypatch.setattr(app_removals.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(
        app_removals, "candidates", lambda *a, **k: app_removals.Candidates(removable=[dict(CASK_ENTRY)], protected=[])
    )
    monkeypatch.setattr(app_removals, "remove_package", lambda *a, **k: pytest.fail("removed without a terminal"))
    assert app_removals.run(entries=[dict(CASK_ENTRY)]) == 0
    assert "stdin is not a terminal" in capsys.readouterr().out


def test_run_is_quiet_and_clean_when_nothing_is_installed(capsys, monkeypatch):
    monkeypatch.setattr(app_removals, "candidates", lambda *a, **k: app_removals.Candidates(removable=[], protected=[]))
    assert app_removals.run(entries=[dict(CASK_ENTRY)]) == 0
    assert "No listed apps to remove are installed" in capsys.readouterr().out


def test_run_announces_a_package_an_app_list_protects(capsys, monkeypatch):
    monkeypatch.setattr(
        app_removals, "candidates", lambda *a, **k: app_removals.Candidates(removable=[], protected=[dict(CASK_ENTRY)])
    )
    app_removals.run(entries=[dict(CASK_ENTRY)])
    assert "an app list still names it" in capsys.readouterr().out


def test_list_only_reports_without_prompting(capsys, monkeypatch):
    monkeypatch.setattr(
        app_removals, "candidates", lambda *a, **k: app_removals.Candidates(removable=[dict(CASK_ENTRY)], protected=[])
    )
    monkeypatch.setattr(app_removals, "prompt_yes_no_quit", lambda *a: pytest.fail("prompted during --list"))
    assert app_removals.run(list_only=True, entries=[dict(CASK_ENTRY)]) == 0
    assert "listed for removal" in capsys.readouterr().out


def test_declining_keeps_the_package(monkeypatch):
    monkeypatch.setattr(
        app_removals, "candidates", lambda *a, **k: app_removals.Candidates(removable=[dict(CASK_ENTRY)], protected=[])
    )
    monkeypatch.setattr(app_removals.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(app_removals, "show_simulation", lambda *a, **k: None)
    monkeypatch.setattr(app_removals, "package_present", lambda *a, **k: True)
    monkeypatch.setattr(app_removals, "prompt_yes_no_quit", lambda question: "n")
    monkeypatch.setattr(app_removals, "remove_package", lambda *a, **k: pytest.fail("removed after declining"))
    assert app_removals.run(entries=[dict(CASK_ENTRY)]) == 0


def test_quit_stops_before_the_remaining_apps(monkeypatch):
    first = dict(CASK_ENTRY)
    second = {"name": "other", "manager": "cask", "package": "realvnc-connect-viewer"}
    monkeypatch.setattr(
        app_removals, "candidates", lambda *a, **k: app_removals.Candidates(removable=[first, second], protected=[])
    )
    monkeypatch.setattr(app_removals.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(app_removals, "show_simulation", lambda *a, **k: None)
    monkeypatch.setattr(app_removals, "package_present", lambda *a, **k: True)
    monkeypatch.setattr(app_removals, "prompt_yes_no_quit", lambda question: "q")
    monkeypatch.setattr(app_removals, "remove_package", lambda *a, **k: pytest.fail("removed after quitting"))
    assert app_removals.run(entries=[first, second]) == 0


def test_a_failed_removal_is_a_non_zero_exit(monkeypatch):
    monkeypatch.setattr(
        app_removals, "candidates", lambda *a, **k: app_removals.Candidates(removable=[dict(CASK_ENTRY)], protected=[])
    )
    monkeypatch.setattr(app_removals.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(app_removals, "show_simulation", lambda *a, **k: None)
    monkeypatch.setattr(app_removals, "package_present", lambda *a, **k: True)
    monkeypatch.setattr(app_removals, "remove_package", lambda *a, **k: False)
    assert app_removals.run(assume_yes=True, entries=[dict(CASK_ENTRY)]) == 1


# %%
# The shipped file #


def test_the_repos_own_app_removals_file_parses():
    """app_removals.yaml is loaded on every myupdater, so a typo in it must fail here first."""
    path = os.path.join(app_removals.REPO_ROOT, "app_removals.yaml")
    entries = app_removals.load_app_removals([path])
    assert entries, "app_removals.yaml should not be empty while RealVNC is still being retired"
    for entry in entries:
        assert app_removals.manager_for(entry["manager"])


# %%


# %%
# One uninstall taking another entry's package #


def test_a_package_an_earlier_removal_took_is_skipped_not_failed(monkeypatch, capsys):
    """
    homebrew lists `vnc-viewer` and `realvnc-connect-viewer` separately but they
    are one cask (the old name is an alias of the renamed one), so uninstalling
    either empties both. The second entry must skip, not try and fail.
    """
    first = {"name": "renamed", "manager": "cask", "package": "realvnc-connect-viewer"}
    second = dict(CASK_ENTRY)
    gone = set()

    monkeypatch.setattr(
        app_removals, "candidates", lambda *a, **k: app_removals.Candidates(removable=[first, second], protected=[])
    )
    monkeypatch.setattr(app_removals.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(app_removals, "show_simulation", lambda *a, **k: None)
    monkeypatch.setattr(app_removals, "prompt_yes_no_quit", lambda question: "y")
    # both names vanish together, which is what brew actually does
    monkeypatch.setattr(app_removals, "package_present", lambda entry, *a, **k: not gone)

    def remove(entry, **kwargs):
        gone.add(entry["package"])
        return True

    monkeypatch.setattr(app_removals, "remove_package", remove)

    assert app_removals.run(entries=[first, second]) == 0
    output = capsys.readouterr().out
    assert "already gone" in output
    assert gone == {"realvnc-connect-viewer"}


def test_presence_is_rechecked_without_the_cache_before_removing(monkeypatch):
    """The removal loop must not reuse the set collected before the first uninstall."""
    calls = []

    def fake_present(entry, cache=None, **kwargs):
        calls.append(cache)
        return True

    monkeypatch.setattr(
        app_removals, "candidates", lambda *a, **k: app_removals.Candidates(removable=[dict(CASK_ENTRY)], protected=[])
    )
    monkeypatch.setattr(app_removals.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(app_removals, "show_simulation", lambda *a, **k: None)
    monkeypatch.setattr(app_removals, "prompt_yes_no_quit", lambda question: "n")
    monkeypatch.setattr(app_removals, "package_present", fake_present)

    app_removals.run(entries=[dict(CASK_ENTRY)])
    assert calls == [None], "the pre-removal check must pass no cache"


def test_package_present_reuses_a_cache_when_given_one():
    queries = []

    def run(argv):
        queries.append(argv)
        return 0, "vnc-viewer\n"

    cache: dict = {}
    entry = dict(CASK_ENTRY)
    assert app_removals.package_present(entry, cache, run=run)
    assert app_removals.package_present(entry, cache, run=run)
    assert len(queries) == 1


def test_package_present_without_a_cache_asks_every_time():
    queries = []

    def run(argv):
        queries.append(argv)
        return 0, "vnc-viewer\n"

    entry = dict(CASK_ENTRY)
    app_removals.package_present(entry, run=run)
    app_removals.package_present(entry, run=run)
    assert len(queries) == 2


# %%
# Windows capabilities and replaced_by #

CAPABILITY_ENTRY = {
    "name": "inbox_sshd",
    "manager": "capability",
    "package": "OpenSSH.Server~~~~0.0.1.0",
    "replaced_by": "winget:Microsoft.OpenSSH.Preview",
}


def windows_run(capabilities=(0, "OpenSSH.Server~~~~0.0.1.0\n"), winget_code=0):
    """Answers the capability query and the per-id winget presence check."""

    def run(argv):
        if argv[0] == "powershell":
            return capabilities
        if argv[0] == "winget":
            return winget_code, ""
        return None, ""

    return run


def test_a_capability_is_removable_once_its_replacement_is_installed(tmp_path):
    found = app_removals.candidates(
        [dict(CAPABILITY_ENTRY)],
        system="Windows",
        hostname="RYZENWHITE",
        lists_dir=str(tmp_path),
        overlay_paths=[],
        run=windows_run(),
    )
    assert [entry["name"] for entry in found.removable] == ["inbox_sshd"]


def test_a_capability_waits_while_its_replacement_is_missing(tmp_path):
    """Removing the in-box sshd from a box with no other ssh server would lock it out."""
    found = app_removals.candidates(
        [dict(CAPABILITY_ENTRY)],
        system="Windows",
        hostname="SHELLY",
        lists_dir=str(tmp_path),
        overlay_paths=[],
        run=windows_run(winget_code=1),
    )
    assert found.removable == []
    assert [entry["name"] for entry in found.waiting] == ["inbox_sshd"]


def test_a_capability_query_that_fails_is_reported_not_absent(tmp_path):
    """Listing capabilities needs an elevated shell; a failure must not read as 'not installed'."""
    found = app_removals.candidates(
        [dict(CAPABILITY_ENTRY)],
        system="Windows",
        hostname="RYZENWHITE",
        lists_dir=str(tmp_path),
        overlay_paths=[],
        run=windows_run(capabilities=(1, "Access is denied")),
    )
    assert [entry["name"] for entry in found.unknown] == ["inbox_sshd"]


def test_unknown_presence_makes_the_run_fail(monkeypatch, capsys):
    monkeypatch.setattr(
        app_removals, "candidates", lambda *a, **k: app_removals.Candidates(unknown=[dict(CAPABILITY_ENTRY)])
    )
    assert app_removals.run(list_only=True, entries=[dict(CAPABILITY_ENTRY)], system="Windows") == 1
    assert "could not ask capability" in capsys.readouterr().out


def test_replaced_by_must_name_a_manager_and_package(tmp_path):
    path = write_removals(tmp_path, [dict(CAPABILITY_ENTRY, replaced_by="Microsoft.OpenSSH.Preview")])
    with pytest.raises(ValueError, match="manager:package"):
        app_removals.load_app_removals([path])


def test_replaced_by_rejects_an_unknown_manager(tmp_path):
    path = write_removals(tmp_path, [dict(CAPABILITY_ENTRY, replaced_by="scoop:openssh")])
    with pytest.raises(ValueError, match="Unknown manager"):
        app_removals.load_app_removals([path])


# %%
# Duplicate installs #

REAL_DUPLICATE_GROUPS = app_removals.duplicate_groups

WINGET_LIST = (
    "   - \r   \\ \r"
    "Name                  Id                        Version    Available Source\n"
    "---------------------------------------------------------------------------\n"
    "OpenSSH               Microsoft.OpenSSH.Preview 10.0.0.0             winget\n"
    "Slack                 SlackTechnologies.Slack   4.52.162             winget\n"
    "Slack                 SlackTechnologies.Slack   4.51.191.0           winget\n"
    "Notepad++ (64-bit x64) Notepad++.Notepad++      8.7        8.8       winget\n"
)


def test_winget_list_is_cut_at_the_header_columns():
    rows = app_removals.parse_winget_list(WINGET_LIST)
    assert rows[0] == app_removals.Install("OpenSSH", "Microsoft.OpenSSH.Preview", "10.0.0.0")
    assert [row.version for row in rows if row.id == "SlackTechnologies.Slack"] == ["4.52.162", "4.51.191.0"]


def test_winget_list_without_a_header_has_no_rows():
    assert app_removals.parse_winget_list("No installed package found matching input criteria.") == []


def test_trailing_zero_versions_compare_equal():
    assert app_removals.version_key("4.51.191.0") == app_removals.version_key("4.51.191")
    assert app_removals.version_key("10.0.0.0") == "10"


def duplicate_run(choco="slack|4.51.191\n"):
    def run(argv):
        if argv[:2] == ["winget", "list"]:
            return 0, WINGET_LIST
        if argv[0] == "choco":
            return 0, choco
        return None, ""

    return run


def test_the_choco_owned_copy_is_kept_and_the_other_offered(tmp_path):
    write_list(tmp_path, "windows_apps_personal_choco.txt", ["slack"])
    groups = REAL_DUPLICATE_GROUPS(run=duplicate_run(), lists_dir=str(tmp_path), overlay_paths=[])
    assert [group.id for group in groups] == ["SlackTechnologies.Slack"]
    group = groups[0]
    assert group.owned_by == "choco:slack"
    assert group.owner.version == "4.51.191.0"
    assert [row.version for row, _ in group.offers] == ["4.52.162"]


def test_a_context_app_list_can_own_the_copy(tmp_path):
    overlay = tmp_path / "acme_app_lists.yaml"
    overlay.write_text("choco: [slack]\n")
    groups = REAL_DUPLICATE_GROUPS(run=duplicate_run(), lists_dir=str(tmp_path), overlay_paths=[str(overlay)])
    assert groups[0].owned_by == "choco:slack"


def test_an_app_no_list_names_is_flagged_and_left_alone(tmp_path):
    groups = REAL_DUPLICATE_GROUPS(run=duplicate_run(), lists_dir=str(tmp_path), overlay_paths=[])
    assert groups[0].owner is None
    assert "no app list names" in groups[0].reason


def test_a_winget_listed_duplicate_is_flagged_not_guessed(tmp_path):
    """Both rows answer to the winget id, so which one winget installed cannot be told."""
    write_list(tmp_path, "windows_apps_personal_winget.txt", ["SlackTechnologies.Slack"])
    groups = REAL_DUPLICATE_GROUPS(run=duplicate_run(choco=""), lists_dir=str(tmp_path), overlay_paths=[])
    assert groups[0].owner is None
    assert "which one winget installed" in groups[0].reason


def test_a_choco_version_matching_no_row_names_no_owner(tmp_path):
    write_list(tmp_path, "windows_apps_personal_choco.txt", ["slack"])
    groups = REAL_DUPLICATE_GROUPS(run=duplicate_run(choco="slack|4.40.0\n"), lists_dir=str(tmp_path), overlay_paths=[])
    assert groups[0].owner is None
    assert "matches no copy" in groups[0].reason


def owned_group():
    keep = app_removals.Install("Slack", "SlackTechnologies.Slack", "4.51.191.0")
    extra = app_removals.Install("Slack", "SlackTechnologies.Slack", "4.52.162")
    return app_removals.DuplicateGroup(
        id=keep.id,
        rows=[extra, keep],
        owner=keep,
        owned_by="choco:slack",
        listed=True,
        offers=[(extra, app_removals.winget_uninstall(keep.id, extra.version))],
    )


def test_an_extra_copy_is_removed_by_id_and_version():
    group = owned_group()
    [(row, argv)] = group.offers
    assert row.version == "4.52.162"
    assert argv[:2] == ["winget", "uninstall"]
    assert argv[-4:] == ["--id", "SlackTechnologies.Slack", "--version", "4.52.162"]


def test_run_offers_the_extra_copy_on_windows(monkeypatch, capsys):
    removed = []
    monkeypatch.setattr(app_removals, "duplicate_groups", lambda **kwargs: [owned_group()])
    monkeypatch.setattr(app_removals.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(app_removals, "prompt_yes_no_quit", lambda question: "y")
    monkeypatch.setattr(app_removals, "remove_duplicate", lambda argv: removed.append(argv[-1]) or True)
    assert app_removals.run(entries=[], system="Windows") == 0
    assert removed == ["4.52.162"]
    assert "Installed more than once" in capsys.readouterr().out


def test_list_only_reports_duplicates_without_offering(monkeypatch, capsys):
    monkeypatch.setattr(app_removals, "duplicate_groups", lambda **kwargs: [owned_group()])
    monkeypatch.setattr(app_removals, "prompt_yes_no_quit", lambda *a: pytest.fail("prompted during --list"))
    assert app_removals.run(list_only=True, entries=[], system="Windows") == 0
    assert "extra" in capsys.readouterr().out


def test_duplicates_are_not_looked_for_off_windows(monkeypatch):
    monkeypatch.setattr(app_removals, "duplicate_groups", lambda **kwargs: pytest.fail("asked winget on a mac"))
    assert app_removals.run(entries=[], system="Darwin") == 0


def test_an_app_on_both_lists_is_a_conflict_not_an_offer(tmp_path):
    """choco's claude and winget's Anthropic.Claude are both the repo's; removing either fights installmissing."""
    write_list(tmp_path, "windows_apps_personal_choco.txt", ["slack"])
    write_list(tmp_path, "windows_apps_personal_winget.txt", ["SlackTechnologies.Slack"])
    groups = REAL_DUPLICATE_GROUPS(run=duplicate_run(), lists_dir=str(tmp_path), overlay_paths=[])
    assert groups[0].owner is None
    assert groups[0].listed
    assert "two app lists install it" in groups[0].reason


def test_unlisted_duplicates_collapse_to_one_line(capsys):
    framework = app_removals.Install("VCLibs", "Microsoft.VCLibs.14", "14.0.1")
    unlisted = app_removals.DuplicateGroup(id=framework.id, rows=[framework, framework], reason="no app list")
    app_removals.report_duplicates([owned_group(), unlisted])
    output = capsys.readouterr().out
    assert "SlackTechnologies.Slack" in output
    assert "Microsoft.VCLibs.14" not in output
    assert "1 more ids are installed more than once" in output


def test_show_all_lists_the_unlisted_duplicates(capsys):
    framework = app_removals.Install("VCLibs", "Microsoft.VCLibs.14", "14.0.1")
    unlisted = app_removals.DuplicateGroup(id=framework.id, rows=[framework, framework], reason="no app list")
    app_removals.report_duplicates([unlisted], show_all=True)
    assert "Microsoft.VCLibs.14" in capsys.readouterr().out


def test_an_app_the_winget_list_owns_offers_chocos_leftover_to_choco(tmp_path):
    """Moved from choco to winget: the copy choco installed goes, and choco removes its own."""
    write_list(tmp_path, "windows_apps_personal_winget.txt", ["SlackTechnologies.Slack"])
    groups = REAL_DUPLICATE_GROUPS(run=duplicate_run(), lists_dir=str(tmp_path), overlay_paths=[])
    group = groups[0]
    assert group.owned_by == "winget:SlackTechnologies.Slack"
    assert group.owner.version == "4.52.162"
    [(row, argv)] = group.offers
    assert row.version == "4.51.191.0"
    assert argv == ["choco", "uninstall", "slack", "-y"]


def test_the_owner_is_the_listed_choco_package_even_when_its_copy_is_older(tmp_path):
    """myupdater upgrades before it removes, so the choco copy is current by the time this runs."""
    write_list(tmp_path, "windows_apps_personal_choco.txt", ["slack"])
    groups = REAL_DUPLICATE_GROUPS(run=duplicate_run(), lists_dir=str(tmp_path), overlay_paths=[])
    assert groups[0].owner.version == "4.51.191.0"


# %%
# after: scripts #


def test_after_resolves_relative_to_the_removals_files_repo(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "fix.ps1").write_text("exit 0\n")
    path = write_removals(tmp_path, [dict(CAPABILITY_ENTRY, after="scripts/fix.ps1")])
    [entry] = app_removals.load_app_removals([path])
    argv = app_removals.after_argv(entry)
    assert argv[:2] == ["powershell", "-NoProfile"]
    assert argv[-1] == os.path.join(str(tmp_path), "scripts", "fix.ps1")


def test_a_shell_after_script_runs_with_bash(tmp_path):
    (tmp_path / "fix.sh").write_text("exit 0\n")
    path = write_removals(tmp_path, [dict(CASK_ENTRY, after="fix.sh")])
    [entry] = app_removals.load_app_removals([path])
    assert app_removals.after_argv(entry)[0] == "bash"


def test_a_missing_after_script_fails_at_load(tmp_path):
    path = write_removals(tmp_path, [dict(CAPABILITY_ENTRY, after="scripts/nope.ps1")])
    with pytest.raises(ValueError, match="not found"):
        app_removals.load_app_removals([path])


def test_an_after_script_with_no_runner_fails_at_load(tmp_path):
    (tmp_path / "fix.py").write_text("")
    path = write_removals(tmp_path, [dict(CAPABILITY_ENTRY, after="fix.py")])
    with pytest.raises(ValueError, match=".ps1 or .sh"):
        app_removals.load_app_removals([path])


def test_after_runs_once_the_removal_succeeded(monkeypatch):
    ran = []
    entry = dict(CAPABILITY_ENTRY, after="scripts/repair_sshd.ps1", _file=app_removals.REPO_ROOT + "/app_removals.yaml")
    monkeypatch.setattr(app_removals, "candidates", lambda *a, **k: app_removals.Candidates(removable=[entry]))
    monkeypatch.setattr(app_removals.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(app_removals, "show_simulation", lambda *a, **k: None)
    monkeypatch.setattr(app_removals, "package_present", lambda *a, **k: True)
    monkeypatch.setattr(app_removals, "remove_package", lambda *a, **k: True)
    monkeypatch.setattr(app_removals, "run_after", lambda e: ran.append(e["name"]) or True)
    assert app_removals.run(assume_yes=True, entries=[entry], system="Darwin") == 0
    assert ran == ["inbox_sshd"]


def test_a_failed_after_script_fails_the_run(monkeypatch, capsys):
    entry = dict(CAPABILITY_ENTRY, after="scripts/repair_sshd.ps1")
    monkeypatch.setattr(app_removals, "candidates", lambda *a, **k: app_removals.Candidates(removable=[entry]))
    monkeypatch.setattr(app_removals, "show_simulation", lambda *a, **k: None)
    monkeypatch.setattr(app_removals, "package_present", lambda *a, **k: True)
    monkeypatch.setattr(app_removals, "remove_package", lambda *a, **k: True)
    monkeypatch.setattr(app_removals, "run_after", lambda e: False)
    assert app_removals.run(assume_yes=True, entries=[entry], system="Darwin") == 1
    assert "FAILED: scripts/repair_sshd.ps1" in capsys.readouterr().out


def test_after_is_skipped_when_the_removal_is_declined(monkeypatch):
    entry = dict(CAPABILITY_ENTRY, after="scripts/repair_sshd.ps1")
    monkeypatch.setattr(app_removals, "candidates", lambda *a, **k: app_removals.Candidates(removable=[entry]))
    monkeypatch.setattr(app_removals.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(app_removals, "show_simulation", lambda *a, **k: None)
    monkeypatch.setattr(app_removals, "package_present", lambda *a, **k: True)
    monkeypatch.setattr(app_removals, "prompt_yes_no_quit", lambda question: "n")
    monkeypatch.setattr(app_removals, "run_after", lambda e: pytest.fail("ran after: without a removal"))
    assert app_removals.run(entries=[entry], system="Darwin") == 0
