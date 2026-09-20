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
    viewer, package, app_list, argv = vnc_connect.viewer_plan("darwin")
    assert viewer == vnc_connect.MAC_VIEWER
    assert (package, app_list) == ("tigervnc", "app_lists/Brewfile")
    assert argv == ["brew", "install", "--cask", "tigervnc"]


def test_windows_takes_the_choco_list():
    viewer, package, app_list, argv = vnc_connect.viewer_plan("windows")
    assert viewer == "vncviewer"
    assert (package, app_list) == ("tigervnc", "app_lists/windows_apps_personal_choco.txt")
    assert argv == ["choco", "install", "tigervnc", "-y"]


def test_the_install_is_one_package_not_the_whole_app_list():
    """Typing vncpi4 asks for a viewer, not for every pending app on the machine."""
    for key in ("darwin", "windows"):
        argv = vnc_connect.viewer_plan(key)[3]
        assert "tigervnc" in argv
        assert not any("install_mac_apps" in part or "chocolatey.ps1" in part for part in argv)


def test_linux_names_the_viewer_the_way_its_own_distro_does(monkeypatch):
    """Debian ships tigervnc-viewer, Fedora ships tigervnc; the lists differ too."""
    monkeypatch.setattr(vnc_connect.shutil, "which", lambda name: "/usr/bin/apt-get" if name == "apt-get" else None)
    package, app_list, argv = vnc_connect.linux_plan()
    assert (package, app_list) == ("tigervnc-viewer", "app_lists/linux_apps.txt")
    assert argv[:3] == ["sudo", "apt-get", "install"]
    monkeypatch.setattr(vnc_connect.shutil, "which", lambda name: "/usr/bin/dnf" if name == "dnf" else None)
    package, app_list, argv = vnc_connect.linux_plan()
    assert (package, app_list) == ("tigervnc", "app_lists/linux_apps_dnf.txt")
    monkeypatch.setattr(vnc_connect.shutil, "which", lambda name: None)
    assert vnc_connect.linux_plan() == (None, None, None)


# %%
# The app list stays authoritative #


def test_the_shipped_app_lists_declare_the_viewer():
    """If this fails the alias cannot install anything, which is the point of the guard."""
    assert vnc_connect.declared_in_app_list("tigervnc", "app_lists/Brewfile")
    assert vnc_connect.declared_in_app_list("tigervnc", "app_lists/windows_apps_personal_choco.txt")
    assert vnc_connect.declared_in_app_list("tigervnc-viewer", "app_lists/linux_apps.txt")


def test_a_package_no_app_list_names_is_refused(monkeypatch, capsys):
    """Installing something the lists do not name is exactly the drift they exist to stop."""
    monkeypatch.setattr(vnc_connect, "find_viewer", lambda viewer: None)
    monkeypatch.setattr(vnc_connect, "declared_in_app_list", lambda package, app_list: False)
    monkeypatch.setattr(vnc_connect.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(vnc_connect, "ask_yes_no", lambda q: pytest.fail("prompted for an undeclared package"))
    assert vnc_connect.connect("host", platform_token="darwin", run=lambda argv: 0) == 1
    assert "not named in" in capsys.readouterr().out


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


def test_a_missing_viewer_offers_just_the_viewer_then_launches(monkeypatch, capsys):
    """Install the one package the list names, then connect."""
    state = {"installed": False}
    monkeypatch.setattr(vnc_connect, "find_viewer", lambda viewer: "/bin/vncviewer" if state["installed"] else None)
    monkeypatch.setattr(vnc_connect.sys.stdin, "isatty", lambda: True)
    calls = []

    def run(argv):
        calls.append(argv)
        state["installed"] = True
        return 0

    assert vnc_connect.connect("host", platform_token="darwin", run=run, ask=lambda q: True) == 0
    assert "app_lists/Brewfile" in capsys.readouterr().out
    assert calls[0] == ["brew", "install", "--cask", "tigervnc"]
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
