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
# App lists #


def test_app_list_drops_comments_and_blanks(tmp_path):
    path = write_list(tmp_path, "linux_apps.txt", ["# header", "", "tmux", "btop # inline note", "  "])
    assert app_removals.read_app_list(path) == ["tmux", "btop"]


def test_brewfile_separates_formulae_from_casks(tmp_path):
    path = write_list(tmp_path, "Brewfile", ['brew "tmux"', 'cask "slack"', '# cask "commented"'])
    assert app_removals.read_brewfile(path, "brew") == ["tmux"]
    assert app_removals.read_brewfile(path, "cask") == ["slack"]


def test_wanted_packages_reads_only_this_managers_lists(tmp_path):
    write_list(tmp_path, "Brewfile", ['brew "tmux"', 'cask "slack"'])
    write_list(tmp_path, "linux_apps.txt", ["btop"])
    assert app_removals.wanted_packages(app_removals.MANAGERS["cask"], str(tmp_path)) == {"slack"}
    assert app_removals.wanted_packages(app_removals.MANAGERS["apt"], str(tmp_path)) == {"btop"}


def test_a_missing_app_list_is_not_an_error(tmp_path):
    assert app_removals.wanted_packages(app_removals.MANAGERS["apt"], str(tmp_path)) == set()


# %%
# Candidates #


def test_an_installed_listed_app_is_removable(tmp_path):
    write_list(tmp_path, "Brewfile", [])
    removable, protected = app_removals.candidates(
        [dict(CASK_ENTRY)],
        system="Darwin",
        hostname="ENVY",
        app_lists=str(tmp_path),
        run=fake_run({"brew": (0, "vnc-viewer\nslack\n")}),
    )
    assert [entry["package"] for entry in removable] == ["vnc-viewer"]
    assert protected == []


def test_an_app_list_still_naming_the_package_wins(tmp_path):
    """The whole point of the guard: re-adding a package beats a stale removal line."""
    write_list(tmp_path, "Brewfile", ['cask "vnc-viewer"'])
    removable, protected = app_removals.candidates(
        [dict(CASK_ENTRY)],
        system="Darwin",
        hostname="ENVY",
        app_lists=str(tmp_path),
        run=fake_run({"brew": (0, "vnc-viewer\n")}),
    )
    assert removable == []
    assert [entry["name"] for entry in protected] == ["retired_cask"]


def test_a_package_that_is_not_installed_is_not_offered(tmp_path):
    write_list(tmp_path, "Brewfile", [])
    removable, _ = app_removals.candidates(
        [dict(CASK_ENTRY)],
        system="Darwin",
        hostname="ENVY",
        app_lists=str(tmp_path),
        run=fake_run({"brew": (0, "slack\n")}),
    )
    assert removable == []


def test_entries_for_another_platform_are_skipped(tmp_path):
    write_list(tmp_path, "Brewfile", [])
    removable, protected = app_removals.candidates(
        [dict(CASK_ENTRY)],
        system="Linux",
        hostname="NUKBUNTU",
        app_lists=str(tmp_path),
        run=fake_run({"brew": (0, "vnc-viewer\n")}),
    )
    assert (removable, protected) == ([], [])


def test_the_hosts_filter_gates_an_entry(tmp_path):
    write_list(tmp_path, "Brewfile", [])
    entry = dict(CASK_ENTRY, hosts=["MacBookProM5"])
    responses = fake_run({"brew": (0, "vnc-viewer\n")})
    on_envy, _ = app_removals.candidates(
        [entry], system="Darwin", hostname="ENVY", app_lists=str(tmp_path), run=responses
    )
    on_macbook, _ = app_removals.candidates(
        [entry], system="Darwin", hostname="MACBOOKPROM5", app_lists=str(tmp_path), run=responses
    )
    assert on_envy == []
    assert [e["package"] for e in on_macbook] == ["vnc-viewer"]


def test_a_manager_that_is_not_installed_offers_nothing(tmp_path):
    """A box with no flatpak has no flatpak removals; that is not a failure."""
    write_list(tmp_path, "linux_apps_flatpak.txt", [])
    entry = {"name": "gone", "manager": "flatpak", "package": "com.example.App"}
    removable, _ = app_removals.candidates(
        [entry], system="Linux", hostname="NUKBUNTU", app_lists=str(tmp_path), run=fake_run({})
    )
    assert removable == []


def test_choco_output_is_split_on_its_separator(tmp_path):
    write_list(tmp_path, "windows_apps_personal_choco.txt", [])
    entry = {"name": "gone", "manager": "choco", "package": "vnc-viewer"}
    removable, _ = app_removals.candidates(
        [entry],
        system="Windows",
        hostname="RYZENWHITE",
        app_lists=str(tmp_path),
        run=fake_run({"choco": (0, "vnc-viewer|8.5.0\ntightvnc|2.8.88\n")}),
    )
    assert [e["package"] for e in removable] == ["vnc-viewer"]


def test_winget_presence_is_asked_per_id(tmp_path):
    """winget list is fixed-width columns, so presence is an exit code, not parsed text."""
    write_list(tmp_path, "windows_apps_personal_winget.txt", [])
    entry = {"name": "gone", "manager": "winget", "package": "RealVNC.VNC-Connect"}
    removable, _ = app_removals.candidates(
        [entry],
        system="Windows",
        hostname="RYZENWHITE",
        app_lists=str(tmp_path),
        run=fake_run({"winget": (0, "")}),
    )
    assert [e["package"] for e in removable] == ["RealVNC.VNC-Connect"]


def test_installed_lookup_is_case_insensitive(tmp_path):
    write_list(tmp_path, "windows_apps_personal_choco.txt", [])
    entry = {"name": "gone", "manager": "choco", "package": "VNC-Viewer"}
    removable, _ = app_removals.candidates(
        [entry],
        system="Windows",
        hostname="RYZENWHITE",
        app_lists=str(tmp_path),
        run=fake_run({"choco": (0, "vnc-viewer|8.5.0\n")}),
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
    monkeypatch.setattr(app_removals, "candidates", lambda *a, **k: ([dict(CASK_ENTRY)], []))
    monkeypatch.setattr(app_removals, "remove_package", lambda *a, **k: pytest.fail("removed without a terminal"))
    assert app_removals.run(entries=[dict(CASK_ENTRY)]) == 0
    assert "stdin is not a terminal" in capsys.readouterr().out


def test_run_is_quiet_and_clean_when_nothing_is_installed(capsys, monkeypatch):
    monkeypatch.setattr(app_removals, "candidates", lambda *a, **k: ([], []))
    assert app_removals.run(entries=[dict(CASK_ENTRY)]) == 0
    assert "No listed apps to remove are installed" in capsys.readouterr().out


def test_run_announces_a_package_an_app_list_protects(capsys, monkeypatch):
    monkeypatch.setattr(app_removals, "candidates", lambda *a, **k: ([], [dict(CASK_ENTRY)]))
    app_removals.run(entries=[dict(CASK_ENTRY)])
    assert "an app list still names it" in capsys.readouterr().out


def test_list_only_reports_without_prompting(capsys, monkeypatch):
    monkeypatch.setattr(app_removals, "candidates", lambda *a, **k: ([dict(CASK_ENTRY)], []))
    monkeypatch.setattr(app_removals, "prompt_yes_no_quit", lambda *a: pytest.fail("prompted during --list"))
    assert app_removals.run(list_only=True, entries=[dict(CASK_ENTRY)]) == 0
    assert "listed for removal" in capsys.readouterr().out


def test_declining_keeps_the_package(monkeypatch):
    monkeypatch.setattr(app_removals, "candidates", lambda *a, **k: ([dict(CASK_ENTRY)], []))
    monkeypatch.setattr(app_removals.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(app_removals, "show_simulation", lambda *a, **k: None)
    monkeypatch.setattr(app_removals, "package_present", lambda *a, **k: True)
    monkeypatch.setattr(app_removals, "prompt_yes_no_quit", lambda question: "n")
    monkeypatch.setattr(app_removals, "remove_package", lambda *a, **k: pytest.fail("removed after declining"))
    assert app_removals.run(entries=[dict(CASK_ENTRY)]) == 0


def test_quit_stops_before_the_remaining_apps(monkeypatch):
    first = dict(CASK_ENTRY)
    second = {"name": "other", "manager": "cask", "package": "realvnc-connect-viewer"}
    monkeypatch.setattr(app_removals, "candidates", lambda *a, **k: ([first, second], []))
    monkeypatch.setattr(app_removals.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(app_removals, "show_simulation", lambda *a, **k: None)
    monkeypatch.setattr(app_removals, "package_present", lambda *a, **k: True)
    monkeypatch.setattr(app_removals, "prompt_yes_no_quit", lambda question: "q")
    monkeypatch.setattr(app_removals, "remove_package", lambda *a, **k: pytest.fail("removed after quitting"))
    assert app_removals.run(entries=[first, second]) == 0


def test_a_failed_removal_is_a_non_zero_exit(monkeypatch):
    monkeypatch.setattr(app_removals, "candidates", lambda *a, **k: ([dict(CASK_ENTRY)], []))
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

    monkeypatch.setattr(app_removals, "candidates", lambda *a, **k: ([first, second], []))
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

    monkeypatch.setattr(app_removals, "candidates", lambda *a, **k: ([dict(CASK_ENTRY)], []))
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
