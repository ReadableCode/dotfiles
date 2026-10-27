"""Unit tests for src/remote_desktop_credentials.py - the keyring half of RDP Desktop Sharing."""

import json
import subprocess

import config_test_utils  # noqa F401

from src import remote_desktop_credentials as rdc

STATUS = """Overall:
\tUnit status: active
RDP:
\tStatus: enabled
\tPort: 3389
\tUsername: {user}
\tPassword: {password}
VNC:
\tStatus: disabled
\tPassword: vncpw
"""


def write_inventory(root, block=None, password="s3cret"):
    credentials = root / "personal_credentials"
    credentials.mkdir()
    remote_desktop = block or {
        "protocol": "rdp",
        "user": "jason",
        "password_env": "LAPTOP_RDP_PASSWORD",
        "env_file": "personal.env",
        "fingerprint": "sha256:AA",
    }
    hosts = [{"name": "Laptop", "os": "linux", "remote_desktop": remote_desktop}, {"name": "Desk", "os": "linux"}]
    (credentials / "personal_hosts.json").write_text(json.dumps({"hosts": hosts}))
    (credentials / "personal.env").write_text(f"LAPTOP_RDP_PASSWORD={password}\n")
    return str(root)


class FakeGrdctl:
    """Stands in for grdctl: answers status from what it holds and records set-credentials."""

    def __init__(self, user="", password=""):
        self.user, self.password = user, password
        self.calls = []

    def __call__(self, argv, env=None, input=None, capture_output=False, text=False, check=False):
        self.calls.append((argv, input, env))
        if argv[1] == "status":
            out = STATUS.format(user=self.user or "", password=self.password or "")
            return subprocess.CompletedProcess(argv, 0, stdout=out)
        if argv[0] == "systemctl":
            self.restarts = getattr(self, "restarts", 0) + 1
            return subprocess.CompletedProcess(argv, 0)
        if argv[1:3] == ["rdp", "set-credentials"]:
            self.user, self.password = argv[3], input.rstrip("\n")
            return subprocess.CompletedProcess(argv, 0)
        raise AssertionError(f"unexpected grdctl call {argv}")


def run_sync(root, grdctl, check=False, hostname="laptop", up=True):
    return rdc.sync(
        hostname,
        root,
        check=check,
        run=grdctl,
        which=lambda name: "/usr/bin/grdctl",
        environ={},
        is_listening=lambda port: up,
    )


def test_the_rdp_section_is_read_and_the_vnc_password_ignored():
    assert rdc.parse_rdp_credentials(STATUS.format(user="jason", password="pw")) == ("jason", "pw")
    assert rdc.parse_rdp_credentials(STATUS.format(user="", password="")) == (None, None)


def test_a_differing_login_is_set_with_the_password_on_stdin(tmp_path, monkeypatch):
    monkeypatch.delenv("LAPTOP_RDP_PASSWORD", raising=False)
    root = write_inventory(tmp_path)
    grdctl = FakeGrdctl()
    assert run_sync(root, grdctl) == 0
    argv, stdin, _ = grdctl.calls[1]
    assert argv == ["grdctl", "rdp", "set-credentials", "jason"]
    assert stdin == "s3cret\n"
    assert (grdctl.user, grdctl.password) == ("jason", "s3cret")


def test_a_matching_login_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.delenv("LAPTOP_RDP_PASSWORD", raising=False)
    root = write_inventory(tmp_path)
    grdctl = FakeGrdctl("jason", "s3cret")
    assert run_sync(root, grdctl) == 0
    assert [call[0][1] for call in grdctl.calls] == ["status"]


def test_check_reports_and_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("LAPTOP_RDP_PASSWORD", raising=False)
    root = write_inventory(tmp_path)
    grdctl = FakeGrdctl("jason", "old")
    assert run_sync(root, grdctl, check=True) == 0
    assert [call[0][1] for call in grdctl.calls] == ["status"]
    assert "differs" in capsys.readouterr().out


def test_a_host_without_the_block_runs_nothing(tmp_path):
    root = write_inventory(tmp_path)
    grdctl = FakeGrdctl()
    assert run_sync(root, grdctl, hostname="desk") == 0
    assert run_sync(root, grdctl, hostname="not-in-any-inventory") == 0
    assert grdctl.calls == []


def test_another_protocol_is_not_governed(tmp_path):
    root = write_inventory(tmp_path, block={"protocol": "vnc"})
    grdctl = FakeGrdctl()
    assert run_sync(root, grdctl) == 0
    assert grdctl.calls == []


def test_a_declared_host_without_grdctl_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("LAPTOP_RDP_PASSWORD", raising=False)
    root = write_inventory(tmp_path)
    assert (
        rdc.sync("laptop", root, run=FakeGrdctl(), which=lambda name: None, environ={}, is_listening=lambda p: True)
        == 1
    )
    assert "grdctl is not installed" in capsys.readouterr().out


def test_the_session_bus_is_found_over_ssh():
    assert rdc.session_environ({}, uid=1000)["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/run/user/1000/bus"
    kept = rdc.session_environ({"DBUS_SESSION_BUS_ADDRESS": "unix:path=/x"}, uid=1000)
    assert kept["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/x"


def test_a_changed_login_restarts_the_daemon(tmp_path, monkeypatch):
    monkeypatch.delenv("LAPTOP_RDP_PASSWORD", raising=False)
    root = write_inventory(tmp_path)
    grdctl = FakeGrdctl()
    assert run_sync(root, grdctl) == 0
    assert grdctl.calls[-1][0] == ["systemctl", "--user", "restart", "gnome-remote-desktop.service"]


def test_a_daemon_not_listening_is_restarted_even_with_the_login_current(tmp_path, monkeypatch):
    """The deploy's dconf update lands before the certificate links, so RDP stays off until a restart."""
    monkeypatch.delenv("LAPTOP_RDP_PASSWORD", raising=False)
    root = write_inventory(tmp_path)
    grdctl = FakeGrdctl("jason", "s3cret")
    state = {"up": False}

    def is_listening(port):
        return state["up"]

    def run(argv, **kwargs):
        if argv[0] == "systemctl":
            state["up"] = True
        return grdctl(argv, **kwargs)

    assert (
        rdc.sync("laptop", root, run=run, which=lambda n: "/usr/bin/grdctl", environ={}, is_listening=is_listening) == 0
    )
    assert [c[0][0] for c in grdctl.calls] == ["grdctl", "systemctl"]


def test_check_reports_a_daemon_not_listening_and_restarts_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("LAPTOP_RDP_PASSWORD", raising=False)
    root = write_inventory(tmp_path)
    grdctl = FakeGrdctl("jason", "s3cret")
    assert run_sync(root, grdctl, check=True, up=False) == 0
    assert [c[0][0] for c in grdctl.calls] == ["grdctl"]
    assert "would restart" in capsys.readouterr().out
