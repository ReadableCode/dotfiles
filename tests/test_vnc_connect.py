# %%
# Imports #

import json

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
    viewer, package, argv = vnc_connect.viewer_plan("darwin")
    assert viewer == vnc_connect.MAC_VIEWER
    assert package == "tigervnc"
    assert argv == ["brew", "install", "--cask", "tigervnc"]


def test_windows_takes_the_choco_package():
    viewer, package, argv = vnc_connect.viewer_plan("windows")
    assert viewer == "vncviewer"
    assert package == "tigervnc"
    assert argv == ["choco", "install", "tigervnc", "-y"]


def test_the_install_is_one_package_not_the_whole_app_list():
    """Typing vncpi4 asks for a viewer, not for every pending app on the machine."""
    for key in ("darwin", "windows"):
        argv = vnc_connect.viewer_plan(key)[2]
        assert "tigervnc" in argv
        assert not any("install_mac_apps" in part or "chocolatey.ps1" in part for part in argv)


def test_linux_names_the_viewer_the_way_its_own_distro_does(monkeypatch):
    """Debian ships tigervnc-viewer, Fedora ships tigervnc."""
    monkeypatch.setattr(vnc_connect.shutil, "which", lambda name: "/usr/bin/apt-get" if name == "apt-get" else None)
    package, argv = vnc_connect.linux_plan()
    assert package == "tigervnc-viewer"
    assert argv[:3] == ["sudo", "apt-get", "install"]
    monkeypatch.setattr(vnc_connect.shutil, "which", lambda name: "/usr/bin/dnf" if name == "dnf" else None)
    package, argv = vnc_connect.linux_plan()
    assert package == "tigervnc"
    monkeypatch.setattr(vnc_connect.shutil, "which", lambda name: None)
    assert vnc_connect.linux_plan() == (None, None)


def test_the_app_lists_are_not_consulted(monkeypatch):
    """A typed alias may install its viewer whether or not a list names it; the lists gate refreshes only."""
    assert not hasattr(vnc_connect, "declared_in_app_list")
    monkeypatch.setattr(vnc_connect, "find_viewer", lambda viewer: None)
    monkeypatch.setattr(vnc_connect.sys.stdin, "isatty", lambda: True)
    asked = []
    monkeypatch.setattr(vnc_connect, "ask_yes_no", lambda q: asked.append(q) or False)
    assert vnc_connect.connect("host", platform_token="darwin", run=lambda argv: 0) == 1
    assert asked == ["Install brew install --cask tigervnc now? [y/N] "]


# %%
# Connecting #


def test_the_port_is_doubled_so_it_is_not_read_as_a_display(monkeypatch):
    """TigerVNC reads host:5900 as display 5900; only host::5900 means the port."""
    seen = {}
    monkeypatch.setattr(vnc_connect, "find_viewer", lambda viewer: "/bin/vncviewer")
    vnc_connect.connect("10.0.0.5", 5901, platform_token="linux", run=lambda argv: seen.update(argv=argv) or 0)
    assert seen["argv"][0] == "/bin/vncviewer"
    assert seen["argv"][-1] == "10.0.0.5::5901"


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
    assert "not installed on this machine" in capsys.readouterr().out
    assert calls[0] == ["brew", "install", "--cask", "tigervnc"]
    assert calls[1][-1] == "host::5900", "must launch once the viewer exists"


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


# %%
# Viewer arguments #


def test_remote_resize_is_turned_off(monkeypatch):
    """
    wayvnc drives a headless Pi whose output cannot be resized, so the viewer's
    default RemoteResize logs "SetDesktopSize failed: 4" on every window change
    for the whole session. Nothing is lost by disabling it.
    """
    seen = {}
    monkeypatch.setattr(vnc_connect, "find_viewer", lambda viewer: "/bin/vncviewer")
    vnc_connect.connect("host", platform_token="linux", run=lambda argv: seen.update(argv=argv) or 0)
    assert "-RemoteResize=0" in seen["argv"]
    assert seen["argv"].index("-RemoteResize=0") < seen["argv"].index("host::5900")


# %%
# RDP #


def write_rdp_inventory(root, password="s3cret", block=None):
    """A personal_credentials repo holding one rdp host and the env file with its password."""
    credentials = root / "personal_credentials"
    credentials.mkdir()
    remote_desktop = block or {
        "protocol": "rdp",
        "port": 3390,
        "user": "jason",
        "password_env": "LAPTOP_RDP_PASSWORD",
        "env_file": "personal.env",
        "fingerprint": "sha256:AA:BB",
    }
    host = {"name": "Laptop", "hostname": "10.0.0.9", "os": "linux", "remote_desktop": remote_desktop}
    (credentials / "personal_hosts.json").write_text(json.dumps({"hosts": [host]}))
    (credentials / "personal.env").write_text(f"LAPTOP_RDP_PASSWORD={password}\n")
    return str(root)


def test_rdp_target_reads_the_record_and_its_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("LAPTOP_RDP_PASSWORD", raising=False)
    root = write_rdp_inventory(tmp_path)
    assert vnc_connect.rdp_target("laptop", root) == ("10.0.0.9", 3390, "jason", "s3cret", "sha256:AA:BB")


def test_rdp_target_refuses_a_host_without_an_rdp_block(tmp_path):
    root = write_rdp_inventory(tmp_path, block={"protocol": "spice"})
    with pytest.raises(ValueError, match="no rdp remote_desktop block"):
        vnc_connect.rdp_target("Laptop", root)


def test_rdp_arguments_are_one_per_line_and_end_with_an_empty_line():
    """FreeRDP's /args-from:stdin reads a line per argument and stops at an empty one."""
    text = vnc_connect.rdp_arguments("10.0.0.9", 3389, "jason", "pw with space", "sha256:AA:BB")
    lines = text.split("\n")
    assert lines[:4] == ["/v:10.0.0.9:3389", "/u:jason", "/p:pw with space", "/cert:fingerprint:sha256:AA:BB"]
    assert text.endswith("\n\n")


def test_connect_rdp_keeps_the_password_off_the_command_line(tmp_path, monkeypatch):
    monkeypatch.delenv("LAPTOP_RDP_PASSWORD", raising=False)
    root = write_rdp_inventory(tmp_path)
    monkeypatch.setattr(vnc_connect, "find_viewer", lambda viewer: "/bin/sdl-freerdp")
    seen = {}

    def run(argv, text):
        seen.update(argv=argv, text=text)
        return 0

    assert vnc_connect.connect_rdp("Laptop", platform_token="linux", run=run, root=root) == 0
    assert seen["argv"] == ["/bin/sdl-freerdp", "/args-from:stdin"]
    assert "/p:s3cret" in seen["text"].split("\n")
    assert not any("s3cret" in part for part in seen["argv"])


def test_debian_freerdp_is_found_under_its_suffixed_name(monkeypatch):
    monkeypatch.setattr(
        vnc_connect, "find_viewer", lambda viewer: "/usr/bin/sdl-freerdp3" if viewer == "sdl-freerdp3" else None
    )
    assert vnc_connect.find_any_viewer(list(vnc_connect.RDP_VIEWERS)) == "/usr/bin/sdl-freerdp3"


def test_rdp_install_plans_name_one_package_per_platform(monkeypatch):
    assert vnc_connect.rdp_plan("darwin")[1:] == ("freerdp", ["brew", "install", "freerdp"])
    viewers, package, argv = vnc_connect.rdp_plan("windows")
    assert viewers == [vnc_connect.WINDOWS_RDP_VIEWER]
    assert argv[1:] == ["-S", "--noconfirm", "mingw-w64-ucrt-x86_64-freerdp"]
    monkeypatch.setattr(vnc_connect.shutil, "which", lambda name: "/usr/bin/apt-get" if name == "apt-get" else None)
    assert vnc_connect.rdp_plan("linux")[1] == "freerdp3-sdl"
    monkeypatch.setattr(vnc_connect.shutil, "which", lambda name: "/usr/bin/dnf" if name == "dnf" else None)
    assert vnc_connect.rdp_plan("linux")[1] == "freerdp"


def test_a_missing_freerdp_is_offered_then_launched(tmp_path, monkeypatch):
    monkeypatch.delenv("LAPTOP_RDP_PASSWORD", raising=False)
    root = write_rdp_inventory(tmp_path)
    state = {"installed": False}
    monkeypatch.setattr(vnc_connect, "find_viewer", lambda viewer: "/opt/sdl-freerdp" if state["installed"] else None)
    monkeypatch.setattr(vnc_connect.sys.stdin, "isatty", lambda: True)
    installs = []

    def install(argv):
        installs.append(argv)
        state["installed"] = True
        return 0

    launched = []
    code = vnc_connect.connect_rdp(
        "Laptop",
        "darwin",
        run=lambda argv, text: launched.append(argv) or 0,
        install=install,
        ask=lambda q: True,
        root=root,
    )
    assert code == 0
    assert installs == [["brew", "install", "freerdp"]]
    assert launched == [["/opt/sdl-freerdp", "/args-from:stdin"]]


def test_main_routes_rdp_to_freerdp(monkeypatch):
    seen = {}
    monkeypatch.setattr(vnc_connect, "connect_rdp", lambda name, platform: seen.update(name=name) or 0)
    assert vnc_connect.main(["--rdp", "Laptop"]) == 0
    assert seen == {"name": "Laptop"}
