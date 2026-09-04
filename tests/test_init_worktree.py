"""Unit tests for src/init_worktree.py — bringing a git worktree up to parity with its main checkout."""

import os
import subprocess

import config_test_utils  # noqa F401
import pytest
from src import init_worktree

# ---------------------------------------------------------------- helpers

WORKSPACE = """{
  "folders": [
    {
      "name": "──  TOOLING  ──",
      "path": "personal_credentials/vscode/groups/tooling",
    },
    {
      "name": "│ dotfiles",
      "path": "dotfiles",
    },
    {
      "name": "│ acme-app",
      "path": "acme-app",
    },
    {
      "name": "│ acme_tools",
      "path": "acme_tools",
    },
  ],
  "settings": {
    "files.exclude": {
      "**/.gitkeep": true,
    },
  },
}
"""


def git(args, cwd):
    subprocess.check_call(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def write(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        file_handle.write(content)
    return path


@pytest.fixture
def repos(tmp_path):
    """
    <tmp>/GitHub/acme-app as a main checkout with the deploy-style gitignored
    links, plus a worktree at <tmp>/.t3/worktrees/acme-app/abc. Returns
    (repo_parent, main, worktree).
    """
    repo_parent = tmp_path / "GitHub"
    main = repo_parent / "acme-app"
    creds = repo_parent / "acme_credentials"
    write(str(creds / "acme_app.env"), "SECRET=1\n")
    write(str(creds / "acme_app_claude_settings.json"), "{}\n")
    write(str(main / ".gitignore"), ".env\n.mcp.json\n.claude/\nconfiguration.json\ntoken.json\n")
    write(str(main / "uv.lock"), "")
    git(["init", "-q", "-b", "master"], str(main))
    git(["add", "."], str(main))
    git(["commit", "-q", "-m", "init"], str(main))
    os.symlink("../acme_credentials/acme_app.env", str(main / ".env"))  # relative, like the real deploy
    os.makedirs(str(main / ".claude"))
    os.symlink(str(creds / "acme_app_claude_settings.json"), str(main / ".claude" / "settings.local.json"))
    write(str(main / "token.json"), "{}")  # gitignored plain file: reported, never mirrored
    write(str(main / ".DS_Store"), "")  # noise: not even reported
    worktree = tmp_path / ".t3" / "worktrees" / "acme-app" / "abc"
    os.makedirs(str(worktree.parent))
    git(["worktree", "add", "-q", "-b", "feature/ACME-2482-thing", str(worktree)], str(main))
    return str(repo_parent), os.path.realpath(str(main)), os.path.realpath(str(worktree))


# ---------------------------------------------------------------- git discovery


def test_main_checkout_is_found_from_inside_the_worktree(repos):
    _, main, worktree = repos
    assert init_worktree.main_checkout(worktree) == main
    assert init_worktree.worktree_root(worktree) == worktree


def test_label_comes_from_the_branch_then_from_commits_ahead_of_master_else_none(repos):
    _, main, worktree = repos
    assert init_worktree.derive_label(worktree) == "ACME-2482"
    git(["checkout", "-q", "-b", "t3code/deadbeef"], worktree)
    assert init_worktree.derive_label(worktree) is None
    git(["commit", "-q", "--allow-empty", "-m", "ACME-9: from the subject"], worktree)
    assert init_worktree.derive_label(worktree) == "ACME-9"


def test_masters_own_tip_ticket_is_not_mistaken_for_the_worktrees(repos):
    """T3 cuts worktrees from master on a placeholder branch; master's last merged ticket is not ours."""
    _, main, worktree = repos
    git(["commit", "-q", "--allow-empty", "-m", "ACME-1: something already merged"], main)
    fresh = os.path.join(os.path.dirname(worktree), "fresh")
    git(["worktree", "add", "-q", "-b", "t3code/cafe", fresh, "master"], main)
    assert init_worktree.derive_label(fresh) is None


# ---------------------------------------------------------------- local-only links


def test_ignored_links_are_mirrored_with_absolute_targets_and_plain_files_are_not(repos):
    repo_parent, main, worktree = repos
    entries = init_worktree.local_only_entries(main)
    statuses = {entry[0]: init_worktree.mirror_entry(entry, worktree) for entry in entries}
    assert statuses == {".env": "linked", ".claude/settings.local.json": "linked", "token.json": "not mirrored"}
    env_link = os.path.join(worktree, ".env")
    assert os.path.islink(env_link)
    assert os.path.isabs(os.readlink(env_link))
    env_file = os.path.join(repo_parent, "acme_credentials", "acme_app.env")
    assert os.path.realpath(env_link) == os.path.realpath(env_file)
    assert not os.path.exists(os.path.join(worktree, "token.json"))


def test_second_run_is_a_no_op(repos):
    _, main, worktree = repos
    entries = init_worktree.local_only_entries(main)
    for entry in entries:
        init_worktree.mirror_entry(entry, worktree)
    assert {init_worktree.mirror_entry(entry, worktree) for entry in entries} == {"ok", "not mirrored"}


def test_existing_different_file_is_a_conflict_and_left_alone(repos):
    _, main, worktree = repos
    write(os.path.join(worktree, ".env"), "MINE=1\n")
    entry = [e for e in init_worktree.local_only_entries(main) if e[0] == ".env"][0]
    assert init_worktree.mirror_entry(entry, worktree) == "conflict"
    with open(os.path.join(worktree, ".env"), encoding="utf-8") as file_handle:
        assert file_handle.read() == "MINE=1\n"


def test_plain_file_env_is_copied(repos):
    _, main, worktree = repos
    os.remove(os.path.join(main, ".env"))
    write(os.path.join(main, ".env"), "PLAIN=1\n")
    entry = [e for e in init_worktree.local_only_entries(main) if e[0] == ".env"][0]
    assert entry[1] == "env"
    assert init_worktree.mirror_entry(entry, worktree) == "copied"
    assert not os.path.islink(os.path.join(worktree, ".env"))
    assert init_worktree.mirror_entry(entry, worktree) == "ok"


def test_dry_run_changes_nothing(repos):
    _, main, worktree = repos
    for entry in init_worktree.local_only_entries(main):
        init_worktree.mirror_entry(entry, worktree, dry_run=True)
    assert not os.path.lexists(os.path.join(worktree, ".env"))


# ---------------------------------------------------------------- workspace file


def test_folder_entry_lands_right_after_the_main_checkout_with_matching_indent():
    text, status = init_worktree.add_workspace_folder(
        WORKSPACE, "acme-app", "│ acme-app · ACME-2482", "../.t3/worktrees/acme-app/abc"
    )
    assert status == "added"
    expected = (
        '    {\n      "name": "│ acme-app",\n      "path": "acme-app",\n    },\n'
        '    {\n      "name": "│ acme-app · ACME-2482",\n      "path": "../.t3/worktrees/acme-app/abc",\n    },\n'
        '    {\n      "name": "│ acme_tools",\n'
    )
    assert expected in text


def test_adding_twice_is_idempotent_and_missing_anchor_is_reported():
    once, _ = init_worktree.add_workspace_folder(WORKSPACE, "acme-app", "x", "../wt")
    twice, status = init_worktree.add_workspace_folder(once, "acme-app", "x", "../wt")
    assert status == "present" and twice == once
    relabeled, status = init_worktree.add_workspace_folder(once, "acme-app", "│ acme-app · ACME-2", "../wt")
    assert status == "relabeled"
    assert '"name": "│ acme-app · ACME-2",\n      "path": "../wt"' in relabeled
    assert relabeled.count('"path": "../wt"') == 1
    same, status = init_worktree.add_workspace_folder(WORKSPACE, "not-here", "x", "../wt")
    assert status == "no anchor" and same == WORKSPACE


def test_remove_restores_the_original_text():
    added, _ = init_worktree.add_workspace_folder(WORKSPACE, "acme-app", "x", "../wt")
    removed, status = init_worktree.remove_workspace_folder(added, "../wt")
    assert status == "removed" and removed == WORKSPACE
    assert init_worktree.remove_workspace_folder(WORKSPACE, "../wt") == (WORKSPACE, "absent")


def test_update_workspace_uses_the_hosts_file_next_to_the_checkouts(repos):
    repo_parent, main, worktree = repos
    ws = write(os.path.join(repo_parent, "envy.code-workspace"), WORKSPACE)
    status = init_worktree.update_workspace(main, worktree, "ACME-2482", hostname="Envy.local")
    assert status.startswith("added (envy.code-workspace: ../.t3/worktrees/acme-app/abc)")
    with open(ws, encoding="utf-8") as file_handle:
        assert '"name": "│ acme-app · ACME-2482"' in file_handle.read()
    assert init_worktree.update_workspace(main, worktree, None, remove=True, hostname="envy").startswith("removed")
    with open(ws, encoding="utf-8") as file_handle:
        assert file_handle.read() == WORKSPACE


def test_update_workspace_without_a_host_file_says_so(repos):
    _, main, worktree = repos
    assert init_worktree.update_workspace(main, worktree, "x", hostname="nowhere").startswith("no workspace file")


# ---------------------------------------------------------------- cli


def test_main_refuses_the_main_checkout(repos, capsys):
    _, main, _ = repos
    assert init_worktree.main(["--worktree", main, "--no-sync", "--no-workspace"]) == 2
    assert "not a worktree" in capsys.readouterr().out


def test_main_without_a_ticket_labels_with_the_directory_and_says_so(repos, capsys):
    repo_parent, main, worktree = repos
    write(os.path.join(repo_parent, "envy.code-workspace"), WORKSPACE)
    git(["checkout", "-q", "-b", "t3code/deadbeef"], worktree)
    assert init_worktree.main(["--worktree", worktree, "--no-sync", "--hostname", "envy"]) == 0
    out = capsys.readouterr().out
    assert "no ticket in the branch" in out
    assert init_worktree.main(["--worktree", worktree, "--no-sync", "--hostname", "envy", "--label", "X-1"]) == 0
    assert "workspace: relabeled" in capsys.readouterr().out
    with open(os.path.join(repo_parent, "envy.code-workspace"), encoding="utf-8") as file_handle:
        text = file_handle.read()
    assert '"name": "│ acme-app · X-1"' in text and '"name": "│ acme-app · abc"' not in text


def test_main_end_to_end_reports_and_exits_zero(repos, capsys):
    repo_parent, main, worktree = repos
    write(os.path.join(repo_parent, "envy.code-workspace"), WORKSPACE)
    code = init_worktree.main(["--worktree", worktree, "--no-sync", "--hostname", "envy"])
    out = capsys.readouterr().out
    assert code == 0
    assert "linked       .env" in out and "not mirrored token.json" in out
    assert "workspace: added" in out
    assert os.path.islink(os.path.join(worktree, ".claude", "settings.local.json"))
