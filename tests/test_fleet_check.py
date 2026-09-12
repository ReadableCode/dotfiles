"""Unit tests for src/fleet_check.py, the one read-only question asked of every inventory host."""

import json
import os

import config_test_utils  # noqa F401
import pytest
from src import fleet_check


class FakeRun:
    """Stands in for subprocess.run, recording the argv it was handed."""

    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        return self


HOSTS = [
    {"host": "EliteDesk", "os": "linux", "command": "ssh jason@192.168.86.179"},
    {"host": "Envy", "os": "macos", "command": "ssh jason@192.168.86.131"},
    {"host": "Shelly", "os": "windows", "command": "ssh jason@192.168.86.50"},
    {"host": "GalaxyTab", "os": "android", "command": "ssh -p 8022 u0@tab"},
    {"host": "Jumped", "os": "linux", "command": "ssh -J jason@192.0.2.1:2222 svc@192.0.2.9"},
]


# ---------------------------------------------------------------- which hosts


def test_load_hosts_skips_this_machine_and_anything_without_a_shell():
    run = FakeRun(stdout=json.dumps(HOSTS))
    hosts = fleet_check.load_hosts("/g", local_hostname="ENVY.LOCAL", run=run)
    assert [h["host"] for h in hosts] == ["EliteDesk", "Jumped", "Shelly"]
    assert run.calls[0][1].endswith(os.path.join("dotfiles", "src", "ssh_aliases.py"))


def test_load_hosts_raises_when_the_generator_fails():
    with pytest.raises(RuntimeError):
        fleet_check.load_hosts("/g", local_hostname="envy", run=FakeRun(stderr="boom", returncode=1))


# ---------------------------------------------------------------- how it asks


def test_remote_command_uses_each_shell_its_own_way():
    assert fleet_check.remote_command("linux", "gitpullall --check") == "$SHELL -ic 'gitpullall --check' 2>&1"
    assert fleet_check.remote_command("windows", "x") == 'powershell -NoLogo -Command "x"'


def test_ssh_argv_keeps_the_hosts_own_options_and_adds_batch_mode():
    argv = fleet_check.ssh_argv(HOSTS[4], "gitpullall --check")
    assert argv[:4] == ["ssh", "-J", "jason@192.0.2.1:2222", "-o"]
    assert "BatchMode=yes" in argv and "ConnectTimeout=8" in argv
    assert argv[-2] == "svc@192.0.2.9"  # the target stays last before the question
    assert argv[-1].startswith("$SHELL -ic")


@pytest.mark.parametrize(
    "code, output, status",
    [
        (0, "all ok", "ok"),
        (1, "2 behind", "drift"),
        (255, "ssh: connect timed out", "unreachable"),
        (127, "", "no command"),
        (0, "", "ok"),
        (2, "boom", "failed"),
    ],
)
def test_classify(code, output, status):
    assert fleet_check.classify(code, output) == status


def test_classify_reads_a_missing_command_out_of_the_output():
    assert fleet_check.classify(2, "bash: line 1: gitpullall: command not found") == "no command"


# ---------------------------------------------------------------- the rows


def test_ask_reports_the_last_line_and_writes_a_log():
    written = {}

    def log(host_name, text):
        written[host_name] = text
        return "/l"

    run = FakeRun(stdout="checking\n2 repos behind\n", returncode=1)
    row = fleet_check.ask(HOSTS[0], "gitpullall --check", run=run, log=log)
    assert row == {"host": "EliteDesk", "os": "linux", "status": "drift", "last": "2 repos behind", "log": "/l"}
    assert "2 repos behind" in written["EliteDesk"]


def test_ask_survives_an_ssh_that_cannot_start():
    def explode(argv, **kwargs):
        raise OSError("no ssh binary")

    row = fleet_check.ask(HOSTS[0], "x", run=explode, log=lambda h, t: "")
    assert row["status"] == "unreachable" and "no ssh" in row["last"]


def test_ask_all_asks_every_host():
    run = FakeRun(stdout="ok")
    rows = fleet_check.ask_all(HOSTS[:3], "x", run=run, log=lambda h, t: "")
    assert sorted(row["host"] for row in rows) == ["EliteDesk", "Envy", "Shelly"]


def test_render_aligns_and_stays_plain_without_color():
    rows = [
        {"host": "EliteDesk", "os": "linux", "status": "ok", "last": "", "log": ""},
        {"host": "Shelly", "os": "windows", "status": "drift", "last": "2 links stale", "log": ""},
    ]
    text = fleet_check.render(rows, False)
    assert "  EliteDesk  linux    ok" in text
    assert "  Shelly     windows  drift        2 links stale" in text


def test_render_says_so_when_there_is_nobody_to_ask():
    assert "no other ssh-reachable hosts" in fleet_check.render([], False)


# ---------------------------------------------------------------- the command line


def test_help_is_the_page(capsys):
    with pytest.raises(SystemExit) as exited:
        fleet_check.main(["--help"], environ={})
    assert exited.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("❯ fleet_check\n")
    assert "\n// what happens\n" in out


def test_default_question_is_the_read_only_one():
    assert fleet_check.parse_args([]).command == "gitpullall --check"
    assert "--check" in fleet_check.DEFAULT_COMMAND
