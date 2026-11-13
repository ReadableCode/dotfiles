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


@pytest.fixture(autouse=True)
def no_browser_web_apps(monkeypatch):
    """No test may read this machine's registry for the web apps a browser installed."""
    import app_removals

    monkeypatch.setattr(app_removals, "browser_web_apps", lambda: set())


def write(directory, name, text):
    path = os.path.join(str(directory), name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


BASE = "base_app_lists.yaml"
WSL = "5.15.167.4-microsoft-standard-WSL2"
NOT_WSL = "6.8.0-45-generic"


def base_file(directory):
    """Where a test's own base_app_lists.yaml lives."""
    return os.path.join(str(directory), BASE)


def fake_run(responses):
    def run(argv):
        return responses.get(argv[0], (None, ""))

    return run


# %%
# Dotfiles app lists #


def test_base_packages_reads_only_this_managers_entries(tmp_path):
    path = write(tmp_path, BASE, "brew: [tmux]\ncask: [firefox]\n# cask: [commented]\napt:\n  - btop  # inline note\n")
    assert app_lists.base_packages("brew", path) == {"tmux"}
    assert app_lists.base_packages("cask", path) == {"firefox"}
    assert app_lists.base_packages("apt", path) == {"btop"}
    assert app_lists.base_packages("dnf", path) == set()


def test_base_packages_sees_every_entry_whatever_its_gates(tmp_path):
    """The "named anywhere" question removals ask: a hosts or wsl gate never hides a name from it."""
    path = write(
        tmp_path,
        BASE,
        "apt:\n  - samba\n  - {package: tmux, wsl: true}\n  - {package: barrier, hosts: [ELITEDESK]}\n",
    )
    assert app_lists.base_packages("apt", path) == {"samba", "tmux", "barrier"}


def test_a_missing_base_app_lists_file_is_an_error(tmp_path):
    """Installing nothing because the file moved would look like a machine with nothing to install."""
    with pytest.raises(FileNotFoundError):
        app_lists.base_packages("apt", base_file(tmp_path))


def test_the_dotfiles_file_and_a_context_file_share_one_parser(tmp_path):
    base = write(tmp_path, BASE, "choco: [7zip]\n")
    overlay = write(tmp_path, "acme_app_lists.yaml", "choco: [slack, 7ZIP]\n")
    assert app_lists.machine_packages("choco", base, [overlay], hostname="X") == ["7zip", "slack"]


def test_the_installer_only_keys_are_read_but_not_managers(tmp_path):
    path = write(tmp_path, BASE, "termux: [git]\nmsys2: [tmux]\n")
    assert app_lists.machine_packages("termux", path, [], hostname="X") == ["git"]
    assert app_lists.machine_packages("msys2", path, [], hostname="X") == ["tmux"]
    assert "termux" not in app_lists.MANAGERS and "msys2" not in app_lists.MANAGERS


# %%
# The wsl flag #


def test_on_wsl_only_the_wsl_apt_entries_apply(tmp_path):
    path = write(tmp_path, BASE, "apt:\n  - samba\n  - {package: tmux, wsl: true}\n")
    assert app_lists.machine_packages("apt", path, [], hostname="X", release=WSL) == ["tmux"]


def test_off_wsl_every_apt_entry_applies(tmp_path):
    path = write(tmp_path, BASE, "apt:\n  - samba\n  - {package: tmux, wsl: true}\n")
    assert app_lists.machine_packages("apt", path, [], hostname="X", release=NOT_WSL) == ["samba", "tmux"]


def test_wsl_detection_reads_the_kernel_release():
    assert app_lists.on_wsl(WSL)
    assert app_lists.on_wsl("4.4.0-19041-Microsoft")
    assert not app_lists.on_wsl(NOT_WSL)


def test_the_wsl_gate_leaves_other_managers_alone(tmp_path):
    path = write(tmp_path, BASE, "dnf: [samba]\nbrew: [tmux]\n")
    assert app_lists.machine_packages("dnf", path, [], hostname="X", release=WSL) == ["samba"]
    assert app_lists.machine_packages("brew", path, [], hostname="X", release=WSL) == ["tmux"]


def test_a_context_apt_entry_follows_the_same_wsl_gate(tmp_path):
    base = write(tmp_path, BASE, "apt: [{package: tmux, wsl: true}]\n")
    overlay = write(tmp_path, "acme_app_lists.yaml", "apt:\n  - steam\n  - {package: unixodbc, wsl: true}\n")
    assert app_lists.machine_packages("apt", base, [overlay], hostname="X", release=WSL) == ["tmux", "unixodbc"]
    assert app_lists.overlay_packages("apt", [overlay], hostname="X", release=NOT_WSL) == ["steam", "unixodbc"]


def test_wsl_and_hosts_gate_one_entry_together(tmp_path):
    path = write(tmp_path, BASE, "apt:\n  - {package: tmux, wsl: true, hosts: [WSLBOX]}\n")
    assert app_lists.machine_packages("apt", path, [], hostname="WSLBOX", release=WSL) == ["tmux"]
    assert app_lists.machine_packages("apt", path, [], hostname="OTHER", release=WSL) == []
    assert app_lists.machine_packages("apt", path, [], hostname="WSLBOX", release=NOT_WSL) == ["tmux"]


@pytest.mark.parametrize(
    "text",
    [
        "apt:\n  - {package: tmux, wsl: false}\n",
        "apt:\n  - {package: tmux, wsl: yes please}\n",
        "brew:\n  - {package: tmux, wsl: true}\n",
    ],
)
def test_wsl_takes_true_and_only_on_apt(tmp_path, text):
    path = write(tmp_path, BASE, text)
    with pytest.raises(ValueError, match=r"wsl: true \(apt only\)"):
        app_lists.read_lists(path)


def test_missing_on_wsl_reads_only_the_wsl_entries(tmp_path):
    write(tmp_path, BASE, "apt:\n  - samba\n  - {package: tmux, wsl: true}\n  - {package: htop, wsl: true}\n")
    missing, _, _, _ = app_lists.missing_packages(
        which=lambda name: name == "apt-get",
        run=fake_run({"dpkg-query": (0, "htop\n")}),
        lists_file=base_file(tmp_path),
        overlay_paths=[],
        release=WSL,
    )
    assert missing == ["apt:tmux"]


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
    base = write(tmp_path, BASE, "choco: [7zip]\n")
    overlay = write(tmp_path, "acme_app_lists.yaml", "choco: [slack]\n")
    assert app_lists.wanted_packages("choco", base, [overlay]) == {"7zip", "slack"}


def test_a_hosts_scoped_entry_exists_only_on_those_hosts(tmp_path):
    """The same hosts gate as manifests and removals: full or short name, any case."""
    path = write(tmp_path, "acme_app_lists.yaml", "choco:\n  - slack\n  - package: tightvnc\n    hosts: [RYZENWHITE]\n")
    assert app_lists.overlay_packages("choco", [path], hostname="RYZENWHITE") == ["slack", "tightvnc"]
    assert app_lists.overlay_packages("choco", [path], hostname="ryzenwhite.lan") == ["slack", "tightvnc"]
    assert app_lists.overlay_packages("choco", [path], hostname="ULTRAPOCKET") == ["slack"]


def test_a_scoped_entry_is_not_wanted_elsewhere_so_a_removal_may_take_it(tmp_path):
    base = write(tmp_path, BASE, "choco: [7zip]\n")
    overlay = write(tmp_path, "acme_app_lists.yaml", "choco:\n  - package: tightvnc\n    hosts: [RYZENWHITE]\n")
    assert app_lists.wanted_packages("choco", base, [overlay], hostname="RYZENWHITE") == {"7zip", "tightvnc"}
    assert app_lists.wanted_packages("choco", base, [overlay], hostname="ULTRAPOCKET") == {"7zip"}


def test_a_scoped_entry_needs_a_hosts_list_and_nothing_else(tmp_path):
    for text in (
        "choco:\n  - package: tightvnc\n",
        "choco:\n  - package: tightvnc\n    hosts: []\n",
        "choco:\n  - package: tightvnc\n    hosts: [X]\n    note: y\n",
    ):
        path = write(tmp_path, "acme_app_lists.yaml", text)
        with pytest.raises(ValueError, match="non-empty hosts list"):
            app_lists.load_overlay([path], hostname="X")


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


def test_the_cli_prints_the_base_names_then_the_contexts_one_per_line(tmp_path, monkeypatch, capsys):
    base = write(tmp_path, BASE, "choco: [7zip, slack]\n")
    overlay = write(tmp_path, "acme_app_lists.yaml", "choco: [awscli, slack]\n")
    monkeypatch.setattr(app_lists, "BASE_APP_LISTS", base)
    monkeypatch.setattr(app_lists, "discover_app_lists", lambda: [overlay])
    assert app_lists.main(["--packages", "choco"]) == 0
    assert capsys.readouterr().out.splitlines() == ["7zip", "slack", "awscli"]


def test_the_cli_prints_an_installer_only_key(tmp_path, monkeypatch, capsys):
    base = write(tmp_path, BASE, "msys2: [tmux, rsync]\n")
    monkeypatch.setattr(app_lists, "BASE_APP_LISTS", base)
    monkeypatch.setattr(app_lists, "discover_app_lists", lambda: [])
    assert app_lists.main(["--packages", "msys2"]) == 0
    assert capsys.readouterr().out.splitlines() == ["tmux", "rsync"]


def test_the_committed_base_app_lists_load_with_every_key():
    """A key renamed or dropped from the file must not silently drop out of the installs and the protection set."""
    lists = app_lists.read_lists(app_lists.BASE_APP_LISTS)
    assert set(lists) == set(app_lists.LIST_KEYS)
    assert all(lists[key] for key in app_lists.LIST_KEYS)


# %%
# Missing apps #


def test_missing_lists_what_the_manager_does_not_report(tmp_path):
    write(tmp_path, BASE, "choco: [7zip, firefox]\n")
    overlay = write(tmp_path, "acme_app_lists.yaml", "choco: [dbeaver]\n")
    missing, _, unanswered, _ = app_lists.missing_packages(
        which=lambda name: name == "choco",
        run=fake_run({"choco": (0, "7zip|24.0\n")}),
        lists_file=base_file(tmp_path),
        overlay_paths=[overlay],
    )
    assert missing == ["choco:dbeaver", "choco:firefox"]
    assert unanswered == []


def test_missing_skips_managers_this_machine_does_not_have(tmp_path):
    write(tmp_path, BASE, "choco: [7zip]\n")
    missing, _, unanswered, _ = app_lists.missing_packages(
        which=lambda name: None, run=fake_run({}), lists_file=base_file(tmp_path), overlay_paths=[]
    )
    assert (missing, unanswered) == ([], [])


def test_a_manager_that_cannot_answer_is_reported(tmp_path):
    write(tmp_path, BASE, "choco: [7zip]\n")
    missing, _, unanswered, _ = app_lists.missing_packages(
        which=lambda name: name == "choco",
        run=fake_run({"choco": (1, "")}),
        lists_file=base_file(tmp_path),
        overlay_paths=[],
    )
    assert unanswered == ["choco"]


def test_missing_reads_winget_ids_from_its_list(tmp_path):
    write(tmp_path, BASE, "winget: [T3Tools.T3Code, Microsoft.OpenSSH.Preview]\n")
    listing = (
        "Name     Id                        Version  Source\n"
        "-------------------------------------------------\n"
        "OpenSSH  Microsoft.OpenSSH.Preview 10.0.0.0 winget\n"
    )
    missing, _, _, _ = app_lists.missing_packages(
        which=lambda name: name == "winget",
        run=fake_run({"winget": (0, listing)}),
        lists_file=base_file(tmp_path),
        overlay_paths=[],
    )
    assert missing == ["winget:T3Tools.T3Code"]


def test_a_versioned_formula_counts_as_installed(tmp_path):
    write(tmp_path, BASE, "brew: [python, tmux]\n")
    missing, _, _, _ = app_lists.missing_packages(
        which=lambda name: name == "brew",
        run=fake_run({"brew": (0, "python@3.14\n")}),
        lists_file=base_file(tmp_path),
        overlay_paths=[],
    )
    assert "brew:python" not in missing
    assert "brew:tmux" in missing


def test_a_tap_formula_counts_as_installed_by_its_full_name(tmp_path):
    """brew lists a tap formula as "user/repo/formula" only with --full-name."""
    write(tmp_path, BASE, "")
    overlay = write(tmp_path, "acme_app_lists.yaml", "brew: [acme/tools/widget, acme/tools/gadget]\n")

    def run(argv):
        if argv == ["brew", "list", "--formula", "--full-name"]:
            return 0, "acme/tools/widget\njq\n"
        return (0, "widget\njq\n") if argv[0] == "brew" else (None, "")

    missing, _, _, _ = app_lists.missing_packages(
        which=lambda name: name == "brew", run=run, lists_file=base_file(tmp_path), overlay_paths=[overlay]
    )
    assert missing == ["brew:acme/tools/gadget"]


def test_a_choco_app_installed_another_way_is_elsewhere_not_missing(tmp_path):
    write(tmp_path, BASE, "choco: [tailscale, dbeaver]\n")
    listing = (
        "Name       Id                  Version  Source\n"
        "---------------------------------------------\n"
        "Tailscale  Tailscale.Tailscale 1.90.0   winget\n"
    )
    missing, elsewhere, _, _ = app_lists.missing_packages(
        which=lambda name: name in ("choco", "winget"),
        run=fake_run({"choco": (0, ""), "winget": (0, listing)}),
        lists_file=base_file(tmp_path),
        overlay_paths=[],
    )
    assert missing == ["choco:dbeaver"]
    assert elsewhere == ["choco:tailscale"]


def test_the_installers_question_uses_the_same_elsewhere_answer():
    listing = (
        "Name       Id                  Version  Source\n"
        "---------------------------------------------\n"
        "Tailscale  Tailscale.Tailscale 1.90.0   winget\n"
    )
    run = fake_run({"winget": (0, listing)})
    have_winget = lambda name: name == "winget"  # noqa: E731
    assert app_lists.elsewhere_packages("choco", ["tailscale", "dbeaver"], have_winget, run) == ["tailscale"]
    assert app_lists.elsewhere_packages("winget", ["tailscale"], have_winget, run) == []
    assert app_lists.elsewhere_packages("choco", ["tailscale"], lambda name: False, run) == []


def test_a_browser_web_app_with_the_same_name_is_not_the_app(monkeypatch):
    """A Messenger web app Chrome installed made the listed messenger look installed outside choco."""
    import app_removals

    monkeypatch.setattr(app_removals, "browser_web_apps", lambda: {"0ce69ced7fa3"})
    listing = (
        "Name       Id                         Version  Source\n"
        "----------------------------------------------------\n"
        "Messenger  ARP\\User\\X64\\0ce69ced7fa3  1.0\n"
        "Tailscale  Tailscale.Tailscale        1.90.0   winget\n"
    )
    run = fake_run({"winget": (0, listing)})
    have_winget = lambda name: name == "winget"  # noqa: E731
    assert app_lists.elsewhere_packages("choco", ["messenger", "tailscale"], have_winget, run) == ["tailscale"]


WINGET_UPGRADE = (
    "Name                  Id                               Version       Available   Source\n"
    "--------------------------------------------------------------------------------------\n"
    "Barrier 2.4.0-release DebaucheeOpenSourceGroup.Barrier 2.4.0-release 2.4.0       winget\n"
    "Epic Online Services  EpicGames.EpicOnlineServices     4.2.1         4.3.1       winget\n"
    "OBS Studio            OBSProject.OBSStudio             31.0.4        32.2.2      winget\n"
    "TightVNC              GlavSoft.TightVNC                2.8.88.0      2.8.89      winget\n"
    "Git                   Git.Git                          2.56.0        2.57.0      winget\n"
    "Windows Terminal      Microsoft.WindowsTerminal        1.24.11911.0  1.25.2733.0 winget\n"
    "6 upgrades available.\n"
    "1 package(s) have version numbers that cannot be determined. Use --include-unknown to see all results.\n"
)


WINGET_LIST = (
    "Name                     Id                          Version        Source\n"
    "--------------------------------------------------------------------------\n"
    "OpenVPN 2.7.7-I001 amd64 OpenVPNTechnologies.OpenVPN 2.7.701        winget\n"
    "OpenVPN Connect          OpenVPNTechnologies.OpenVPNConnect 3.9.0   winget\n"
    "Google Chrome            Google.Chrome               154.0.8037.98  winget\n"
    "OBS Studio               OBSProject.OBSStudio        31.0.4         winget\n"
    "Parsec                   Parsec.Parsec               150-104a       winget\n"
    "Messenger                ARP\\User\\X64\\c1b3adcf     223.0.649571860\n"
)
CHOCO_OUTDATED = (
    "GoogleChrome|153.0.8010.12|155.0.8059.12|false\n"
    "messenger|205.0.564654621|205.0.564654621|false\n"
    "obs-studio|32.1.2|32.2.2|false\n"
    "openvpn|2.5.7|2.6.16.1|false\n"
    "parsec|20220429.0.0|20240209.0.0|false\n"
    "vlc|3.0.24|3.0.25|true\n"
)


def upgrade_run(choco_list="", terminal_open=False):
    """winget and choco answering as RyzenWhite did on 2026-10-02."""

    def run(argv):
        if argv[:2] == ["winget", "upgrade"]:
            return 0, WINGET_UPGRADE
        if argv[:2] == ["winget", "list"]:
            return 0, WINGET_LIST
        if argv[:2] == ["choco", "list"]:
            return 0, choco_list
        if argv[:2] == ["choco", "outdated"]:
            return 0, CHOCO_OUTDATED
        if argv[0] == "tasklist":
            return 0, '"WindowsTerminal.exe","15932","Console","2","90,000 K"\n' if terminal_open else "INFO: none\n"
        return None, ""

    return run


def winget_plan(tmp_path, listed, choco_list="", terminal_open=False, holds=None):
    write(tmp_path, BASE, "winget: [" + ", ".join(listed) + "]\n")
    return app_lists.winget_upgrades(
        run=upgrade_run(choco_list, terminal_open),
        which=lambda name: True,
        lists_file=base_file(tmp_path),
        overlay_paths=[],
        holds=holds or {},
    )


def test_winget_upgrades_only_what_a_winget_list_names(tmp_path):
    choco = "obs-studio|32.1.2\ntightvnc|2.8.88\n"
    upgrade, held = winget_plan(tmp_path, ["Git.Git"], choco)
    assert upgrade == ["Git.Git"]
    reasons = dict(held)
    assert "no winget app list names it" in reasons["EpicGames.EpicOnlineServices"]
    assert "no winget app list names it" in reasons["Microsoft.WindowsTerminal"]
    assert "choco:obs-studio" in reasons["OBSProject.OBSStudio"]
    assert "choco:tightvnc" in reasons["GlavSoft.TightVNC"]


def test_nothing_is_wingets_when_no_list_names_anything(tmp_path):
    upgrade, held = winget_plan(tmp_path, [])
    assert upgrade == []
    assert len(held) == 6


def test_a_listed_id_chocolatey_also_installed_is_a_conflict_not_an_upgrade(tmp_path):
    upgrade, held = winget_plan(tmp_path, ["GlavSoft.TightVNC"], "tightvnc|2.8.88\n")
    assert upgrade == []
    assert "drop it from one app list" in dict(held)["GlavSoft.TightVNC"]


def test_a_listed_offer_of_the_installed_release_is_left_alone(tmp_path):
    upgrade, held = winget_plan(tmp_path, ["DebaucheeOpenSourceGroup.Barrier"])
    assert upgrade == []
    assert "2.4.0-release" in dict(held)["DebaucheeOpenSourceGroup.Barrier"]


def test_winget_leaves_windows_terminal_alone_while_a_window_is_open(tmp_path):
    upgrade, _ = winget_plan(tmp_path, ["Microsoft.WindowsTerminal"])
    assert upgrade == ["Microsoft.WindowsTerminal"]
    upgrade, held = winget_plan(tmp_path, ["Microsoft.WindowsTerminal"], terminal_open=True)
    assert upgrade == []
    assert "Terminal window is open" in dict(held)["Microsoft.WindowsTerminal"]


def test_a_held_winget_id_is_left_alone_with_its_reason(tmp_path):
    upgrade, held = winget_plan(tmp_path, ["Git.Git"], holds={("winget", "git.git"): "updates itself"})
    assert upgrade == []
    assert dict(held)["Git.Git"] == "updates itself"


def test_the_winget_plan_is_the_same_asked_twice(tmp_path):
    plans = [winget_plan(tmp_path, ["Git.Git"], "tightvnc|2.8.88\n") for _ in "12"]
    assert plans[0] == plans[1]


def test_winget_upgrades_are_unknown_when_winget_cannot_run():
    assert app_lists.winget_upgrades(run=lambda argv: (None, ""), which=lambda name: True) is None


def test_choco_leaves_a_package_alone_when_the_app_is_already_past_its_offer():
    upgrade, held = app_lists.choco_upgrades(run=upgrade_run(), which=lambda name: True, holds={})
    # Chrome 154 is behind the 155 on offer and OBS 31 behind 32, so those are real upgrades;
    # Parsec's 150-104a is behind choco's date version. messenger is not outdated, vlc is pinned.
    assert upgrade == ["GoogleChrome", "obs-studio", "parsec"]
    assert [package for package, _ in held] == ["openvpn"]
    assert "2.7.701" in held[0][1] and "2.6.16.1" in held[0][1]


def test_choco_leaves_held_packages_alone_with_their_reason():
    holds = {("choco", "googlechrome"): "Chrome updates itself", ("choco", "parsec"): "Parsec updates itself"}
    upgrade, held = app_lists.choco_upgrades(run=upgrade_run(), which=lambda name: True, holds=holds)
    assert upgrade == ["obs-studio"]
    assert dict(held)["GoogleChrome"] == "Chrome updates itself"
    assert dict(held)["parsec"] == "Parsec updates itself"


def test_choco_upgrades_everything_outdated_when_winget_cannot_say_what_is_installed():
    upgrade, held = app_lists.choco_upgrades(run=upgrade_run(), which=lambda name: name == "choco", holds={})
    assert upgrade == ["GoogleChrome", "obs-studio", "openvpn", "parsec"]
    assert held == []


def test_choco_upgrades_a_variant_only_through_its_installed_wrapper():
    # ultrapocket 2026-10-15: vscode pins vscode.install to = 1.141.2, so upgrading the variant alone fails.
    def run(argv):
        if argv[:2] == ["choco", "outdated"]:
            return (
                0,
                "vscode|1.140.0|1.141.2|false\nvscode.install|1.140.0|1.142.0|false\nputty.portable|0.84|0.85|false\n",
            )
        if argv[:2] == ["choco", "list"]:
            return 0, "vscode|1.140.0\nvscode.install|1.140.0\nputty.portable|0.84\n"
        return None, ""

    upgrade, held = app_lists.choco_upgrades(run=run, which=lambda name: name == "choco", holds={})
    assert upgrade == ["vscode", "putty.portable"]
    assert held == [("vscode.install", "upgraded through vscode, which pins its version")]


def test_choco_upgrades_are_unknown_when_choco_cannot_run():
    assert app_lists.choco_upgrades(run=lambda argv: (None, ""), which=lambda name: True) is None


def test_the_committed_upgrade_holds_load_and_name_listed_packages():
    holds = app_lists.load_upgrade_holds()
    assert ("choco", "googlechrome") in holds and ("choco", "parsec") in holds
    assert all(reason for reason in holds.values())


def test_an_upgrade_hold_without_a_reason_is_refused(tmp_path):
    path = write(tmp_path, "holds.yaml", "- name: x\n  manager: choco\n  package: x\n")
    with pytest.raises(ValueError, match="lacks reason"):
        app_lists.load_upgrade_holds(path)


def test_at_or_past_compares_the_leading_numbers():
    assert app_lists.at_or_past("2.4.0-release", "2.4.0")
    assert app_lists.at_or_past("1.2.0.0", "1.2")
    assert app_lists.at_or_past("2.7.701", "2.6.16.1")
    assert not app_lists.at_or_past("2.8.88.0", "2.8.89")
    assert not app_lists.at_or_past("Unknown", "1.19.3")
    assert not app_lists.at_or_past("154.0.8037.98", "155.0.8059.12")


# %%
# Ignored on this machine #


def test_recording_creates_the_file_with_its_header(own_ignore_file):
    assert app_lists.record_ignored("brew", ["docker", "colima"]) == ["brew:docker", "brew:colima"]
    text = open(own_ignore_file, encoding="utf-8").read()
    assert text.startswith("# Apps this machine was offered and turned down")
    assert "Delete a line to be offered that app again, or run installmissing" in text
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
    write(tmp_path, BASE, "brew: [docker, tmux]\n")
    app_lists.record_ignored("brew", ["docker"])
    missing, _, _, ignored = app_lists.missing_packages(
        which=lambda name: name == "brew",
        run=fake_run({"brew": (0, "")}),
        lists_file=base_file(tmp_path),
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


def test_forgetting_takes_only_the_named_lines_out(own_ignore_file):
    app_lists.record_ignored("brew", ["docker", "colima"])
    app_lists.record_ignored("cask", ["docker"])
    assert app_lists.forget_ignored("brew", ["Docker", "never-ignored"]) == ["brew:docker"]
    assert app_lists.read_ignored() == {"brew:colima", "cask:docker"}
    # the header that explains the file survives the rewrite
    assert open(own_ignore_file, encoding="utf-8").read().startswith("# Apps this machine was offered")


def test_forgetting_without_a_file_changes_nothing(own_ignore_file):
    assert app_lists.forget_ignored("brew", ["docker"]) == []
    assert not os.path.exists(own_ignore_file)


def test_the_cli_unignores_and_prints_the_lines_it_removed(own_ignore_file, capsys):
    app_lists.record_ignored("choco", ["dbeaver", "slack"])
    assert app_lists.main(["--unignore", "choco", "dbeaver"]) == 0
    assert capsys.readouterr().out.split() == ["choco:dbeaver"]
    assert app_lists.read_ignored() == {"choco:slack"}


def test_the_cli_rejects_an_unknown_manager_to_unignore_for():
    with pytest.raises(SystemExit):
        app_lists.main(["--unignore", "snap", "slack"])


def test_the_cli_rejects_an_unknown_manager_to_ignore_for():
    with pytest.raises(SystemExit):
        app_lists.main(["--ignore", "snap", "slack"])


# %%
# What any machine gets #

# Apps a client machine must never get from a list every machine reads: they
# belong in the personal context's app list only.
PERSONAL_ONLY = ("tailscale", "angryip", "docker-desktop", "virtualbox", "nmap", "ollama")


@pytest.mark.parametrize("manager", app_lists.LIST_KEYS)
def test_no_any_machine_list_installs_a_personal_only_app(manager):
    """base_app_lists.yaml reaches every machine, client machines included, whatever an entry's gates."""
    entries = [name.lower() for name in app_lists.base_packages(manager)]
    assert not [entry for entry in entries for name in PERSONAL_ONLY if name in entry]
