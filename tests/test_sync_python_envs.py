# %%
# Imports #

import os

import config_test_utils  # noqa F401
import pytest
from src import sync_python_envs

# %%
# Helpers #


def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").close()


class FakeRun:
    """Stands in for subprocess.run: records each call, fails in the named projects."""

    def __init__(self, failing=()):
        self.calls = []
        self.failing = set(failing)

    def __call__(self, cmd, cwd, env, check):
        self.calls.append((cmd, cwd, env))
        return type("Result", (), {"returncode": 1 if os.path.basename(cwd) in self.failing else 0})()


# %%
# Tests #


def test_finds_repo_roots_and_immediate_subdirectories_only(tmp_path):
    touch(tmp_path / "app" / "uv.lock")
    touch(tmp_path / "monorepo" / "backend" / "uv.lock")
    touch(tmp_path / "monorepo" / "backend" / "deep" / "uv.lock")
    touch(tmp_path / "pipenv_repo" / "Pipfile")
    touch(tmp_path / "hidden_env" / ".venv" / "uv.lock")
    touch(tmp_path / "web" / "node_modules" / "uv.lock")
    touch(tmp_path / ".t3" / "uv.lock")
    touch(tmp_path / "notes.txt")
    found = [os.path.relpath(p, tmp_path) for p in sync_python_envs.find_uv_projects(str(tmp_path))]
    assert found == ["app", os.path.join("monorepo", "backend")]


def test_syncs_frozen_in_each_project_without_dotfiles_venv(tmp_path, monkeypatch):
    touch(tmp_path / "a" / "uv.lock")
    touch(tmp_path / "b" / "uv.lock")
    monkeypatch.setenv("VIRTUAL_ENV", "/elsewhere/dotfiles/.venv")
    fake = FakeRun()
    monkeypatch.setattr(sync_python_envs.subprocess, "run", fake)
    assert sync_python_envs.run(str(tmp_path)) == 0
    assert [cwd for _, cwd, _ in fake.calls] == [str(tmp_path / "a"), str(tmp_path / "b")]
    assert all(cmd == ["uv", "sync", "--frozen"] for cmd, _, _ in fake.calls)
    assert all("VIRTUAL_ENV" not in env for _, _, env in fake.calls)


def test_a_failing_project_never_stops_the_rest_and_sets_exit_code(tmp_path, monkeypatch, capsys):
    for name in ("a", "b", "c"):
        touch(tmp_path / name / "uv.lock")
    fake = FakeRun(failing={"b"})
    monkeypatch.setattr(sync_python_envs.subprocess, "run", fake)
    assert sync_python_envs.run(str(tmp_path)) == 1
    assert [os.path.basename(cwd) for _, cwd, _ in fake.calls] == ["a", "b", "c"]
    assert "failed: b" in capsys.readouterr().out


def test_list_only_never_runs_uv(tmp_path, monkeypatch, capsys):
    touch(tmp_path / "a" / "uv.lock")

    def refuse(*args, **kwargs):
        pytest.fail("--list must not run uv")

    monkeypatch.setattr(sync_python_envs.subprocess, "run", refuse)
    assert sync_python_envs.run(str(tmp_path), list_only=True) == 0
    assert "  a" in capsys.readouterr().out
