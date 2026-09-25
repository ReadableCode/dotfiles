# %%
# Imports #

import os

import config_test_utils  # noqa F401
import pytest

from src import app_lists

# %%
# Helpers #


@pytest.fixture(autouse=True)
def own_ignore_file(tmp_path, monkeypatch):
    """No test may read or write this machine's real ~/.dotfiles_ignored_apps."""
    path = str(tmp_path / "ignored_apps")
    monkeypatch.setattr(app_lists, "IGNORE_FILE", path)
    return path


def write(directory, name, text):
    path = os.path.join(str(directory), name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


# %%
# Dotfiles app lists #


def test_app_list_drops_comments_and_blanks(tmp_path):
    path = write(tmp_path, "linux_apps.txt", "# header\n\ntmux\nbtop # inline note\n  \n")
    assert app_lists.read_app_list(path) == ["tmux", "btop"]


def test_brewfile_separates_formulae_from_casks(tmp_path):
    path = write(tmp_path, "Brewfile", 'brew "tmux"\ncask "firefox"\n# cask "commented"\n')
    assert app_lists.read_brewfile(path, "brew") == ["tmux"]
    assert app_lists.read_brewfile(path, "cask") == ["firefox"]


def test_base_packages_reads_only_this_managers_lists(tmp_path):
    write(tmp_path, "Brewfile", 'brew "tmux"\ncask "firefox"\n')
    write(tmp_path, "linux_apps.txt", "btop\n")
    assert app_lists.base_packages("cask", str(tmp_path)) == {"firefox"}
    assert app_lists.base_packages("apt", str(tmp_path)) == {"btop"}


def test_a_missing_app_list_is_not_an_error(tmp_path):
    assert app_lists.base_packages("apt", str(tmp_path)) == set()


# %%
# Context app lists #


def test_overlay_names_come_back_per_manager_without_repeats(tmp_path):
    first = write(tmp_path, "acme_app_lists.yaml", "choco: [awscli, slack]\ncask: [slack]\n")
    second = write(tmp_path, "other_app_lists.yaml", "choco: [slack, teams]\n")
    assert app_lists.overlay_packages("choco", [first, second]) == ["awscli", "slack", "teams"]
    assert app_lists.overlay_packages("cask", [first, second]) == ["slack"]
    assert app_lists.overlay_packages("apt", [first, second]) == []


def test_the_same_name_in_two_contexts_is_offered_once_whatever_its_case(tmp_path):
    first = write(tmp_path, "acme_app_lists.yaml", "winget: [T3Tools.T3Code]\nchoco: [claude]\n")
    second = write(tmp_path, "personal_app_lists.yaml", "winget: [t3tools.t3code, Foo.Bar]\nchoco: [claude]\n")
    assert app_lists.overlay_packages("winget", [first, second]) == ["T3Tools.T3Code", "Foo.Bar"]
    assert app_lists.overlay_packages("choco", [first, second]) == ["claude"]


def test_wanted_packages_is_the_union_of_both_sources(tmp_path):
    write(tmp_path, "windows_apps_personal_choco.txt", "7zip\n")
    overlay = write(tmp_path, "acme_app_lists.yaml", "choco: [slack]\n")
    assert app_lists.wanted_packages("choco", str(tmp_path), [overlay]) == {"7zip", "slack"}


def test_an_unknown_manager_is_a_hard_error(tmp_path):
    path = write(tmp_path, "acme_app_lists.yaml", "chocolatey: [slack]\n")
    with pytest.raises(ValueError, match="Unknown manager 'chocolatey'"):
        app_lists.load_overlay([path])


def test_a_manager_must_map_to_a_list_of_names(tmp_path):
    path = write(tmp_path, "acme_app_lists.yaml", "choco: slack\n")
    with pytest.raises(ValueError, match="must be a list of package names"):
        app_lists.load_overlay([path])


def test_the_file_must_be_a_mapping(tmp_path):
    path = write(tmp_path, "acme_app_lists.yaml", "- slack\n")
    with pytest.raises(ValueError, match="must be a mapping"):
        app_lists.load_overlay([path])


def test_an_empty_file_adds_nothing(tmp_path):
    path = write(tmp_path, "acme_app_lists.yaml", "")
    assert app_lists.load_overlay([path]) == {}


def test_discovery_reads_only_member_overlays(tmp_path, monkeypatch):
    member = tmp_path / "acme_credentials"
    other = tmp_path / "globex_credentials"
    for repo in (member, other):
        repo.mkdir()
    write(member, "acme_app_lists.yaml", "choco: [slack]\n")
    write(other, "globex_app_lists.yaml", "choco: [teams]\n")
    monkeypatch.setattr(app_lists, "member_overlay_dirs", lambda: ([str(member)], [(str(other), "globex")]))
    assert app_lists.discover_app_lists() == [os.path.join(str(member), "acme_app_lists.yaml")]


def test_the_cli_prints_one_overlay_name_per_line(tmp_path, monkeypatch, capsys):
    overlay = write(tmp_path, "acme_app_lists.yaml", "choco: [awscli, slack]\n")
    monkeypatch.setattr(app_lists, "discover_app_lists", lambda: [overlay])
    assert app_lists.main(["--overlay", "choco"]) == 0
    assert capsys.readouterr().out.splitlines() == ["awscli", "slack"]


def test_every_base_list_the_resolver_names_exists():
    """A renamed or deleted app list must not silently drop out of the protection set."""
    for manager, filenames in app_lists.BASE_LISTS.items():
        for filename in filenames:
            assert os.path.exists(os.path.join(app_lists.APP_LISTS, filename)), f"{manager}: {filename}"


# %%
# Missing apps #


def fake_run(responses):
    def run(argv):
        return responses.get(argv[0], (None, ""))

    return run


def test_missing_lists_what_the_manager_does_not_report(tmp_path):
    write(tmp_path, "windows_apps_personal_choco.txt", "7zip\nfirefox\n")
    overlay = write(tmp_path, "acme_app_lists.yaml", "choco: [dbeaver]\n")
    missing, _, unanswered, _ = app_lists.missing_packages(
        which=lambda name: name == "choco",
        run=fake_run({"choco": (0, "7zip|24.0\n")}),
        app_lists=str(tmp_path),
        overlay_paths=[overlay],
    )
    assert missing == ["choco:dbeaver", "choco:firefox"]
    assert unanswered == []


def test_missing_skips_managers_this_machine_does_not_have(tmp_path):
    write(tmp_path, "windows_apps_personal_choco.txt", "7zip\n")
    missing, _, unanswered, _ = app_lists.missing_packages(
        which=lambda name: None, run=fake_run({}), app_lists=str(tmp_path), overlay_paths=[]
    )
    assert (missing, unanswered) == ([], [])


def test_a_manager_that_cannot_answer_is_reported(tmp_path):
    write(tmp_path, "windows_apps_personal_choco.txt", "7zip\n")
    missing, _, unanswered, _ = app_lists.missing_packages(
        which=lambda name: name == "choco", run=fake_run({"choco": (1, "")}), app_lists=str(tmp_path), overlay_paths=[]
    )
    assert unanswered == ["choco"]


def test_missing_reads_winget_ids_from_its_list(tmp_path):
    write(tmp_path, "windows_apps_personal_winget.txt", "T3Tools.T3Code\nMicrosoft.OpenSSH.Preview\n")
    listing = (
        "Name     Id                        Version  Source\n"
        "-------------------------------------------------\n"
        "OpenSSH  Microsoft.OpenSSH.Preview 10.0.0.0 winget\n"
    )
    missing, _, _, _ = app_lists.missing_packages(
        which=lambda name: name == "winget",
        run=fake_run({"winget": (0, listing)}),
        app_lists=str(tmp_path),
        overlay_paths=[],
    )
    assert missing == ["winget:T3Tools.T3Code"]


def test_a_versioned_formula_counts_as_installed(tmp_path):
    write(tmp_path, "Brewfile", 'brew "python"\nbrew "tmux"\n')
    missing, _, _, _ = app_lists.missing_packages(
        which=lambda name: name == "brew",
        run=fake_run({"brew": (0, "python@3.14\n")}),
        app_lists=str(tmp_path),
        overlay_paths=[],
    )
    assert "brew:python" not in missing
    assert "brew:tmux" in missing


def test_wsl_reads_the_wsl_apt_list():
    assert app_lists.installer_lists("apt", release="5.15.167.4-microsoft-standard-WSL2") == ("linux_apps_wsl.txt",)
    assert app_lists.installer_lists("apt", release="6.8.0-45-generic") == ("linux_apps.txt",)


def test_a_choco_app_installed_another_way_is_elsewhere_not_missing(tmp_path):
    write(tmp_path, "windows_apps_personal_choco.txt", "tailscale\ndbeaver\n")
    listing = (
        "Name       Id                  Version  Source\n"
        "---------------------------------------------\n"
        "Tailscale  Tailscale.Tailscale 1.90.0   winget\n"
    )
    missing, elsewhere, _, _ = app_lists.missing_packages(
        which=lambda name: name in ("choco", "winget"),
        run=fake_run({"choco": (0, ""), "winget": (0, listing)}),
        app_lists=str(tmp_path),
        overlay_paths=[],
    )
    assert missing == ["choco:dbeaver"]
    assert elsewhere == ["choco:tailscale"]


# %%
# Ignored on this machine #


def test_recording_creates_the_file_with_its_header(own_ignore_file):
    assert app_lists.record_ignored("brew", ["docker", "colima"]) == ["brew:docker", "brew:colima"]
    text = open(own_ignore_file, encoding="utf-8").read()
    assert text.startswith("# Apps this machine was offered and turned down")
    assert "Delete a line to be offered that app again." in text
    assert text.rstrip().splitlines()[-2:] == ["brew:docker", "brew:colima"]


def test_recording_twice_adds_nothing_new(own_ignore_file):
    app_lists.record_ignored("brew", ["docker"])
    assert app_lists.record_ignored("brew", ["Docker", "colima"]) == ["brew:colima"]


def test_ignored_is_per_manager_and_case_insensitive(own_ignore_file):
    app_lists.record_ignored("cask", ["DBeaver-Community"])
    assert app_lists.ignored_packages("cask", ["dbeaver-community", "slack"]) == ["dbeaver-community"]
    assert app_lists.ignored_packages("choco", ["dbeaver-community"]) == []


def test_a_missing_file_ignores_nothing():
    assert app_lists.read_ignored() == set()


def test_an_ignored_app_is_not_reported_missing(tmp_path, own_ignore_file):
    write(tmp_path, "Brewfile", 'brew "docker"\nbrew "tmux"\n')
    app_lists.record_ignored("brew", ["docker"])
    missing, _, _, ignored = app_lists.missing_packages(
        which=lambda name: name == "brew",
        run=fake_run({"brew": (0, "")}),
        app_lists=str(tmp_path),
        overlay_paths=[],
    )
    assert missing == ["brew:tmux"]
    assert ignored == ["brew:docker"]


def test_the_cli_filters_stdin_through_the_ignore_file(own_ignore_file, monkeypatch, capsys):
    import io

    app_lists.record_ignored("choco", ["dbeaver"])
    monkeypatch.setattr(app_lists.sys, "stdin", io.StringIO("dbeaver\nslack\n"))
    assert app_lists.main(["--ignored", "choco"]) == 0
    assert capsys.readouterr().out.splitlines() == ["dbeaver"]


def test_the_cli_records_and_prints_the_lines_it_added(own_ignore_file, capsys):
    assert app_lists.main(["--ignore", "cask", "docker", "dbeaver-community"]) == 0
    assert capsys.readouterr().out.splitlines() == ["cask:docker", "cask:dbeaver-community"]


def test_the_cli_rejects_an_unknown_manager_to_ignore_for():
    with pytest.raises(SystemExit):
        app_lists.main(["--ignore", "snap", "slack"])
