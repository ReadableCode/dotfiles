"""Unit tests for src/jupyter_lab.py — ports, the server command, state files and when a server stops."""

import os
import socket
import sqlite3
import subprocess

import config_test_utils  # noqa F401
import pytest

from src import jupyter_lab

# ---------------------------------------------------------------- helpers


def a_state(tmp_path, **overrides):
    state = {
        "checkout": str(tmp_path / "repo"),
        "port": 8888,
        "token": "abc123",
        "thread": "thread-1",
        "checkpoints": str(tmp_path / "state" / "checkpoints" / "k"),
        "log": str(tmp_path / "state" / "k.log"),
        "started": "",
        "pid": 4242,
    }
    state.update(overrides)
    return state


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    path = str(tmp_path / "state")
    monkeypatch.setattr(jupyter_lab, "STATE_DIR", path)
    return path


# ---------------------------------------------------------------- checkout and state files


def test_checkout_root_is_the_git_top_level(tmp_path):
    subprocess.check_call(["git", "init", "-q", str(tmp_path / "repo")])
    os.makedirs(tmp_path / "repo" / "sub")
    assert jupyter_lab.checkout_root(str(tmp_path / "repo" / "sub")) == os.path.realpath(tmp_path / "repo")


def test_checkout_root_outside_git_is_the_path_itself(tmp_path):
    assert jupyter_lab.checkout_root(str(tmp_path)) == os.path.realpath(tmp_path)


def test_state_is_private_and_round_trips(tmp_path, state_dir):
    state = a_state(tmp_path)
    path = jupyter_lab.state_file(state["checkout"])
    assert os.path.dirname(path) == state_dir
    jupyter_lab.write_state(path, state)
    assert jupyter_lab.read_state(path) == state
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"


def test_servers_prunes_a_state_file_whose_supervisor_is_gone(tmp_path, state_dir, monkeypatch):
    live, dead = a_state(tmp_path, pid=1), a_state(tmp_path, checkout=str(tmp_path / "other"), pid=2)
    for state in (live, dead):
        jupyter_lab.write_state(jupyter_lab.state_file(state["checkout"]), state)
    monkeypatch.setattr(jupyter_lab, "is_alive", lambda pid: pid == 1)
    assert jupyter_lab.servers() == [live]
    assert not os.path.exists(jupyter_lab.state_file(dead["checkout"]))
    assert jupyter_lab.server_for(live["checkout"]) == live


def test_servers_without_a_state_dir_is_empty(state_dir):
    assert jupyter_lab.servers() == []


def test_is_alive_never_trusts_a_recycled_pid():
    """Our own pid is alive but is not a supervisor, so a state file naming it is stale."""
    assert jupyter_lab.is_alive(os.getpid()) is False
    assert jupyter_lab.is_alive(None) is False


# ---------------------------------------------------------------- ports and the command


def test_free_port_skips_claimed_and_listening_ports():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        assert jupyter_lab.free_port({port + 1}, first=port, last=port + 2) == port + 2


def test_a_port_left_in_time_wait_by_a_stopped_server_is_free():
    """The server side closes first, so its port sits in TIME_WAIT after the listener is gone."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port))
    accepted, _ = listener.accept()
    accepted.close()
    client.recv(1)
    client.close()
    listener.close()
    assert jupyter_lab.port_in_use(port) is False


def test_free_port_raises_when_the_range_is_full():
    with pytest.raises(RuntimeError):
        jupyter_lab.free_port({9000}, first=9000, last=9000)


def test_command_runs_frozen_in_a_uv_project(tmp_path):
    os.makedirs(tmp_path / "repo")
    (tmp_path / "repo" / "uv.lock").write_text("", encoding="utf-8")
    command = jupyter_lab.jupyter_command(a_state(tmp_path))
    assert command[:7] == ["uv", "run", "--frozen", "--with", "jupyterlab", "--with", "jupytext"]
    assert "--port" in command and command[command.index("--port") + 1] == "8888"
    assert "--ServerApp.port_retries=0" in command
    assert "--IdentityProvider.token=abc123" in command
    assert "--ServerApp.password=" in command and "--PasswordIdentityProvider.hashed_password=" in command
    assert f"--ServerApp.root_dir={tmp_path / 'repo'}" in command
    assert f"--FileCheckpoints.root_dir={tmp_path / 'state' / 'checkpoints' / 'k'}" in command


def test_command_never_creates_a_lock_outside_a_uv_project(tmp_path):
    os.makedirs(tmp_path / "repo")
    assert jupyter_lab.jupyter_command(a_state(tmp_path))[:3] == ["uv", "run", "--no-project"]


def test_command_adds_only_the_jupyter_tools(tmp_path):
    """A notebook's own imports come from the project; nothing else is layered on."""
    command = jupyter_lab.jupyter_command(a_state(tmp_path))
    withs = [command[i + 1] for i, arg in enumerate(command) if arg == "--with"]
    assert withs == ["jupyterlab", "jupytext"]


def test_lab_url_carries_the_token(tmp_path):
    assert jupyter_lab.lab_url(a_state(tmp_path)) == "http://127.0.0.1:8888/lab?token=abc123"


# ---------------------------------------------------------------- when a server stops


def test_finished_reason_follows_the_thread(tmp_path, monkeypatch):
    os.makedirs(tmp_path / "repo")
    state = a_state(tmp_path)
    for verdict, expected in [
        ("active", None),
        ("unsettled", None),
        ("settled", "thread settled"),
        ("deleted", "thread deleted"),
        (None, None),
    ]:
        monkeypatch.setattr(jupyter_lab.t3_state, "thread_verdict", lambda thread, db, v=verdict: v)
        assert jupyter_lab.finished_reason(state) == expected


def test_finished_reason_when_the_checkout_is_gone(tmp_path):
    assert jupyter_lab.finished_reason(a_state(tmp_path)) == "checkout removed"


def test_a_locked_database_never_stops_the_server(tmp_path, monkeypatch):
    os.makedirs(tmp_path / "repo")

    def locked(thread, db):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(jupyter_lab.t3_state, "thread_verdict", locked)
    assert jupyter_lab.finished_reason(a_state(tmp_path)) is None


def test_stop_for_with_no_server(tmp_path, state_dir):
    assert jupyter_lab.stop_for(str(tmp_path / "repo")) == "none running"


def test_stop_for_dry_run_touches_nothing(tmp_path, state_dir, monkeypatch):
    state = a_state(tmp_path, checkout=os.path.realpath(tmp_path / "repo"))
    jupyter_lab.write_state(jupyter_lab.state_file(state["checkout"]), state)
    monkeypatch.setattr(jupyter_lab, "is_alive", lambda pid: True)
    monkeypatch.setattr(jupyter_lab.os, "killpg", lambda *a: pytest.fail("signalled in a dry run"))
    assert jupyter_lab.stop_for(state["checkout"], dry_run=True) == "would stop (port 8888)"
    assert os.path.exists(jupyter_lab.state_file(state["checkout"]))


def test_stop_for_signals_the_supervisor_group_and_clears_its_state(tmp_path, state_dir, monkeypatch):
    state = a_state(tmp_path, checkout=os.path.realpath(tmp_path / "repo"))
    jupyter_lab.write_state(jupyter_lab.state_file(state["checkout"]), state)
    signals, alive = [], [True]

    def killpg(pid, signum):
        signals.append((pid, signum))
        alive[0] = False

    monkeypatch.setattr(jupyter_lab, "is_alive", lambda pid: alive[0])
    monkeypatch.setattr(jupyter_lab.os, "killpg", killpg)
    assert jupyter_lab.stop_for(state["checkout"]) == "stopped (port 8888)"
    assert signals == [(4242, jupyter_lab.signal.SIGTERM)]
    assert not os.path.exists(jupyter_lab.state_file(state["checkout"]))


def test_start_refuses_without_a_thread(tmp_path, state_dir, monkeypatch, capsys):
    if os.name == "nt":
        pytest.skip("POSIX-only tool")
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    monkeypatch.setattr(jupyter_lab.t3_state, "thread_for_session", lambda session: None)
    assert jupyter_lab.start(str(tmp_path)) == 2
    assert "pass --thread" in capsys.readouterr().out


def test_start_refuses_a_finished_thread(tmp_path, state_dir, monkeypatch, capsys):
    if os.name == "nt":
        pytest.skip("POSIX-only tool")
    monkeypatch.setattr(jupyter_lab.t3_state, "thread_verdict", lambda thread: "settled")
    assert jupyter_lab.start(str(tmp_path), thread="abcdef1234") == 2
    assert "is settled" in capsys.readouterr().out
