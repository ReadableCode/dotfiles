# %%
# Imports #

import config_test_utils  # noqa F401
import pytest

from src import vnc_connect

# %%
# Platform resolution #


def test_platform_key_maps_the_usual_tokens():
    assert vnc_connect.platform_key("darwin") == "darwin"
    assert vnc_connect.platform_key("win32") == "windows"
    assert vnc_connect.platform_key("linux") == "linux"


def test_macos_uses_the_in_bundle_path():
    """The cask installs an .app, so there is nothing named vncviewer on PATH."""
    viewer, installer, app_list = vnc_connect.viewer_plan("darwin")
    assert viewer == vnc_connect.MAC_VIEWER
    assert installer == "scripts/install_mac_apps.sh"
    assert app_list == "app_lists/Brewfile"


def test_windows_takes_the_choco_list():
    viewer, installer, app_list = vnc_connect.viewer_plan("windows")
    assert viewer == "vncviewer"
    assert "chocolatey" in installer
    assert app_list == "app_lists/windows_apps_personal_choco.txt"


def test_linux_picks_the_installer_for_the_package_manager_present(monkeypatch):
    """Fedora and Debian keep separate lists; the wrong one reports everything missing."""
    monkeypatch.setattr(vnc_connect.shutil, "which", lambda name: "/usr/bin/apt-get" if name == "apt-get" else None)
    assert vnc_connect.linux_installer() == ("scripts/install_linux_apps.sh", "app_lists/linux_apps.txt")
    monkeypatch.setattr(vnc_connect.shutil, "which", lambda name: "/usr/bin/dnf" if name == "dnf" else None)
    assert vnc_connect.linux_installer() == ("scripts/install_linux_apps_dnf.sh", "app_lists/linux_apps_dnf.txt")
    monkeypatch.setattr(vnc_connect.shutil, "which", lambda name: None)
    assert vnc_connect.linux_installer() == (None, None)


# %%
# Connecting #


def test_the_port_is_doubled_so_it_is_not_read_as_a_display(monkeypatch):
    """TigerVNC reads host:5900 as display 5900; only host::5900 means the port."""
    seen = {}
    monkeypatch.setattr(vnc_connect, "find_viewer", lambda viewer: "/bin/vncviewer")
    vnc_connect.connect("10.0.0.5", 5901, platform_token="linux", run=lambda argv: seen.update(argv=argv) or 0)
    assert seen["argv"] == ["/bin/vncviewer", "10.0.0.5::5901"]


def test_an_installed_viewer_is_launched_without_prompting(monkeypatch):
    monkeypatch.setattr(vnc_connect, "find_viewer", lambda viewer: "/bin/vncviewer")
    monkeypatch.setattr(vnc_connect, "ask_yes_no", lambda q: pytest.fail("prompted with the viewer present"))
    assert vnc_connect.connect("host", platform_token="linux", run=lambda argv: 0) == 0


# %%
# The install offer #


def test_a_missing_viewer_offers_the_installer_then_launches(monkeypatch, capsys):
    """The whole point: say which list names it and offer the repo's own installer."""
    state = {"installed": False}
    monkeypatch.setattr(vnc_connect, "find_viewer", lambda viewer: "/bin/vncviewer" if state["installed"] else None)
    monkeypatch.setattr(vnc_connect.sys.stdin, "isatty", lambda: True)
    calls = []

    def run(argv):
        calls.append(argv)
        state["installed"] = True
        return 0

    assert vnc_connect.connect("host", platform_token="darwin", run=run, ask=lambda q: True) == 0
    out = capsys.readouterr().out
    assert "app_lists/Brewfile" in out and "scripts/install_mac_apps.sh" in out
    assert "install_mac_apps.sh" in " ".join(calls[0])
    assert calls[1][1] == "host::5900", "must launch once the viewer exists"


def test_declining_the_offer_does_not_launch(monkeypatch):
    monkeypatch.setattr(vnc_connect, "find_viewer", lambda viewer: None)
    monkeypatch.setattr(vnc_connect.sys.stdin, "isatty", lambda: True)
    assert vnc_connect.connect("host", platform_token="linux", run=lambda argv: 0, ask=lambda q: False) == 1


def test_nothing_is_offered_without_a_terminal(monkeypatch, capsys):
    """A script calling an alias must not hang on a prompt."""
    monkeypatch.setattr(vnc_connect, "find_viewer", lambda viewer: None)
    # an installer must be found, or the no-installer message short-circuits first
    monkeypatch.setattr(vnc_connect.shutil, "which", lambda name: "/usr/bin/apt-get" if name == "apt-get" else None)
    monkeypatch.setattr(vnc_connect.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(vnc_connect, "ask_yes_no", lambda q: pytest.fail("prompted without a terminal"))
    assert vnc_connect.connect("host", platform_token="linux", run=lambda argv: 0) == 1
    assert "Not running on a terminal" in capsys.readouterr().out


def test_a_linux_box_with_no_known_package_manager_says_so(monkeypatch, capsys):
    monkeypatch.setattr(vnc_connect, "find_viewer", lambda viewer: None)
    monkeypatch.setattr(vnc_connect.shutil, "which", lambda name: None)
    assert vnc_connect.connect("host", platform_token="linux", run=lambda argv: 0) == 1
    assert "install TigerVNC by hand" in capsys.readouterr().out


# %%
