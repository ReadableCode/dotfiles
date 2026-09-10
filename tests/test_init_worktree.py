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


# ---------------------------------------------------------------- leaving


def with_remote(main, worktree, tmp_path):
    """Give the fixture a bare origin and push the worktree's branch to it with an upstream."""
    bare = str(tmp_path / "origin.git")
    git(["init", "-q", "--bare", bare], str(tmp_path))
    git(["remote", "add", "origin", bare], main)
    git(["push", "-q", "-u", "origin", "feature/ACME-2482-thing"], worktree)


def test_remove_refuses_uncommitted_tracked_changes_and_untracked_files(repos, tmp_path, capsys):
    repo_parent, main, worktree = repos
    with_remote(main, worktree, tmp_path)
    write(os.path.join(worktree, "uv.lock"), "changed\n")
    write(os.path.join(worktree, "new_file.py"), "x = 1\n")
    assert init_worktree.main(["--worktree", worktree, "--remove", "--hostname", "envy"]) == 1
    out = capsys.readouterr().out
    assert "refusing to remove" in out and "uv.lock" in out and "new_file.py" in out
    assert os.path.isdir(worktree)


def test_remove_refuses_without_upstream_and_with_unpushed_commits(repos, tmp_path, capsys):
    repo_parent, main, worktree = repos
    write(os.path.join(worktree, "uv.lock"), "unique\n")
    git(["commit", "-q", "-am", "only here"], worktree)
    assert init_worktree.main(["--worktree", worktree, "--remove", "--hostname", "envy"]) == 1
    assert "no upstream" in capsys.readouterr().out
    git(["reset", "-q", "--hard", "HEAD~1"], worktree)
    with_remote(main, worktree, tmp_path)
    write(os.path.join(worktree, "uv.lock"), "changed\n")
    git(["commit", "-q", "-am", "local only"], worktree)
    assert init_worktree.main(["--worktree", worktree, "--remove", "--hostname", "envy"]) == 1
    assert "1 commit(s) that origin/feature/ACME-2482-thing does not" in capsys.readouterr().out
    assert os.path.isdir(worktree)


def test_remove_deletes_only_this_worktree_and_its_workspace_entry(repos, tmp_path, capsys):
    repo_parent, main, worktree = repos
    with_remote(main, worktree, tmp_path)
    write(os.path.join(repo_parent, "envy.code-workspace"), WORKSPACE)
    assert init_worktree.main(["--worktree", worktree, "--no-sync", "--hostname", "envy"]) == 0
    # ignored build output, the kind of thing that accumulates
    write(os.path.join(worktree, ".venv", "lib", "x.py"), "")
    with open(os.path.join(worktree, ".gitignore"), "a", encoding="utf-8") as file_handle:
        file_handle.write(".venv/\n")
    git(["add", ".gitignore"], worktree)
    git(["commit", "-q", "-m", "ignore the venv"], worktree)
    git(["push", "-q"], worktree)
    other = str(tmp_path / ".t3" / "worktrees" / "acme-app" / "other")
    git(["worktree", "add", "-q", "-b", "feature/ACME-9999-other", other], main)
    write(os.path.join(other, "dirty.txt"), "unsaved work in the other worktree")
    capsys.readouterr()
    assert init_worktree.main(["--worktree", worktree, "--remove", "--hostname", "envy"]) == 0
    out = capsys.readouterr().out
    assert "workspace: removed" in out
    assert "worktree:  removed" in out
    assert "feature/ACME-2482-thing left in place" in out
    assert not os.path.exists(worktree)
    assert os.path.isfile(os.path.join(other, "dirty.txt"))
    registered = subprocess.check_output(["git", "worktree", "list", "--porcelain"], cwd=main, text=True)
    assert other in registered and worktree not in registered
    assert "feature/ACME-2482-thing" in subprocess.check_output(["git", "branch"], cwd=main, text=True)
    with open(os.path.join(repo_parent, "envy.code-workspace"), encoding="utf-8") as file_handle:
        assert file_handle.read() == WORKSPACE


def test_remove_dry_run_changes_nothing(repos, tmp_path, capsys):
    repo_parent, main, worktree = repos
    with_remote(main, worktree, tmp_path)
    write(os.path.join(repo_parent, "envy.code-workspace"), WORKSPACE)
    assert init_worktree.main(["--worktree", worktree, "--no-sync", "--hostname", "envy"]) == 0
    assert init_worktree.main(["--worktree", worktree, "--remove", "--dry-run", "--hostname", "envy"]) == 0
    assert "would remove" in capsys.readouterr().out
    assert os.path.isdir(worktree)
    with open(os.path.join(repo_parent, "envy.code-workspace"), encoding="utf-8") as file_handle:
        assert "acme-app · ACME-2482" in file_handle.read()


def test_remove_refuses_a_path_that_is_not_a_worktree_of_main(repos):
    _, main, worktree = repos
    with pytest.raises(RuntimeError):
        init_worktree.remove_worktree(main, main)
    with pytest.raises(RuntimeError):
        init_worktree.remove_worktree(main, os.path.dirname(worktree))


def test_remove_settled_placeholder_worktree_and_deletes_its_branch(repos, tmp_path, capsys):
    """A placeholder worktree that never left master: no upstream, nothing unique, safe to drop with its branch."""
    repo_parent, main, worktree = repos
    placeholder = str(tmp_path / ".t3" / "worktrees" / "acme-app" / "settled")
    git(["worktree", "add", "-q", "-b", "t3code/deadbeef", placeholder], main)
    write(os.path.join(placeholder, "token.json"), "{}")  # gitignored, the kind of thing that accumulates
    assert init_worktree.main(["--worktree", placeholder, "--remove", "--hostname", "envy"]) == 0
    out = capsys.readouterr().out
    assert "worktree:  removed" in out and "t3code/deadbeef deleted (placeholder, fully on master)" in out
    assert not os.path.exists(placeholder)
    assert "t3code/deadbeef" not in subprocess.check_output(["git", "branch"], cwd=main, text=True)
    assert os.path.isdir(worktree)  # the other worktree is untouched


def test_remove_keeps_a_placeholder_branch_that_has_its_own_commits(repos, tmp_path, capsys):
    repo_parent, main, worktree = repos
    placeholder = str(tmp_path / ".t3" / "worktrees" / "acme-app" / "wip")
    git(["worktree", "add", "-q", "-b", "t3code/cafe", placeholder], main)
    write(os.path.join(placeholder, "uv.lock"), "work\n")
    git(["commit", "-q", "-am", "work on the placeholder"], placeholder)
    assert init_worktree.main(["--worktree", placeholder, "--remove", "--hostname", "envy"]) == 1
    assert "no upstream" in capsys.readouterr().out
    assert os.path.isdir(placeholder)
