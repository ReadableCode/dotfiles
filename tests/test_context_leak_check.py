"""context_leak_check derives each context's identifiers from its own repo and refuses them elsewhere."""

import json
import os
import subprocess

import pytest

from src import context_leak_check as leak


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def git_repo(path, files):
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "-C", path, "init", "-q"], check=True)
    for name, text in files.items():
        write(os.path.join(path, name), text)
    subprocess.run(["git", "-C", path, "add", "-A"], check=True)
    return path


@pytest.fixture
def constellation(tmp_path):
    parent = str(tmp_path)
    write(
        os.path.join(parent, "personal_credentials", "personal_repos.yaml"),
        "defaults:\n  org: mine\nrepos:\n  - name: blog\n",
    )
    git_repo(os.path.join(parent, "personal_credentials"), {"notes.md": "acme and bravo both fine here"})
    write(
        os.path.join(parent, "acme_credentials", "acme_repos.yaml"),
        "defaults:\n  org: acmeorg\nrepos:\n  - name: acme-app\n  - name: shared-tool\n    org: mine\n",
    )
    write(
        os.path.join(parent, "acme_credentials", "acme_hosts.json"),
        json.dumps({"hosts": [{"name": "ACME-LAP-01", "hostname": "10.9.9.9", "aliases": ["sshacme"]}]}),
    )
    write(
        os.path.join(parent, "acme_credentials", "acme.env"),
        "JIRA_PROJECT=ACM\n"
        "JIRA_BASE_URL=https://acmeco.atlassian.net\n"
        "SECRET_ACCOUNT=abc123secret\n"
        "GOOGLE_TOKEN_URL=https://oauth2.googleapis.com/token\n",
    )
    write(os.path.join(parent, "acme_credentials", "ssh", "acme.conf"), "Host acmegw 10.9.9.1\n    User svc\n")
    write(os.path.join(parent, "acme_credentials", "acme_identifiers.txt"), "Acme Widgets\n")
    git_repo(os.path.join(parent, "acme_credentials"), {"README.md": "acme only"})
    write(os.path.join(parent, "acme_dev", "acme_dev_manifest.yaml"), "- name: x\n  per_context_repo: acme\n")
    git_repo(os.path.join(parent, "acme_dev"), {"docs/a.md": "talks about acme-app"})
    write(os.path.join(parent, "bravo_credentials", "bravo_repos.yaml"), "repos:\n  - name: bravo-site\n")
    git_repo(os.path.join(parent, "bravo_credentials"), {"README.md": "bravo only"})
    git_repo(os.path.join(parent, "dotfiles"), {"docs/x.md": "uses the acme placeholder\n"})
    return parent


def test_identifiers_come_from_each_context_s_own_repo(constellation):
    contexts = leak.derive_contexts(constellation)
    assert set(contexts) == {"acme", "bravo"}
    acme = contexts["acme"]["identifiers"]
    # token variants, repo names, non-personal orgs, hosts, ticket prefix, the identifier file, the dev repo
    for expected in [
        "acme",
        "acme_credentials",
        "acme-app",
        "acmeorg",
        "ACME-LAP-01",
        "10.9.9.9",
        "ACM-",
        "Acme Widgets",
        "acme_dev",
        "acme-dev",
        "sshacme",
        "acmegw",
        "acmeco.atlassian.net",
    ]:
        assert expected in acme, expected
    assert "abc123secret" not in acme  # env VALUES are never identifiers, only URL hostnames
    assert "oauth2.googleapis.com" not in acme  # third-party service hosts identify nobody
    assert "mine" not in acme  # the personal org appears in client repos files and is not a client identifier
    assert "shared-tool" in acme
    assert contexts["acme"]["repos"] == ["acme_credentials", "acme_dev"]
    # the client's own checkouts are owned (their identifiers are theirs) but not scanned by default
    assert {"acme-app", "shared-tool", "acme_credentials", "acme_dev"} <= contexts["acme"]["owned"]


def test_a_short_identifier_counts_only_when_listed_by_hand(constellation):
    write(os.path.join(constellation, "acme_credentials", "acme_identifiers.txt"), "Acme Widgets\nAW\n")
    write(
        os.path.join(constellation, "bravo_credentials", "bravo_repos.yaml"),
        "repos:\n  - name: bravo-site\n  - name: bv\n",
    )
    contexts = leak.derive_contexts(constellation)
    assert "AW" in contexts["acme"]["identifiers"]  # a hand-listed abbreviation is meant
    assert "bv" not in contexts["bravo"]["identifiers"]  # a short derived name is too noisy to match on
    dotfiles = git_repo(
        os.path.join(constellation, "dotfiles"),
        {"notes.md": "the AW numbers\n", "ok.md": "a bv raw value, aw_points = []\n"},
    )
    hits = leak.scan_repo(dotfiles, contexts)
    assert [(h[0], h[3]) for h in hits if h[0] in ("notes.md", "ok.md")] == [("notes.md", "AW")]


def test_rules_depend_on_which_repo_is_scanned(constellation):
    contexts = leak.derive_contexts(constellation)
    assert leak.forbidden_for(os.path.join(constellation, "personal_credentials"), contexts) == {}
    assert leak.forbidden_for(os.path.join(constellation, "personal_dev"), contexts) == {}
    assert set(leak.forbidden_for(os.path.join(constellation, "acme_dev"), contexts)) == {"bravo"}
    assert set(leak.forbidden_for(os.path.join(constellation, "acme_credentials"), contexts)) == {"bravo"}
    assert set(leak.forbidden_for(os.path.join(constellation, "dotfiles"), contexts)) == {"acme", "bravo"}
    assert set(leak.forbidden_for(os.path.join(constellation, "blog"), contexts)) == {"acme", "bravo"}
    assert set(leak.forbidden_for(os.path.join(constellation, "acme-app"), contexts)) == {"bravo"}


def test_a_worktree_is_named_after_the_checkout_it_belongs_to(constellation, tmp_path_factory):
    contexts = leak.derive_contexts(constellation)
    main = os.path.join(constellation, "acme-app")
    git_repo(main, {"README.md": "acme app\n"})
    worktree = str(tmp_path_factory.mktemp("worktrees") / "t3code-abc123")
    subprocess.run(["git", "-C", main, "worktree", "add", "-q", worktree], check=True)
    assert leak.checkout_name(worktree) == "acme-app"
    assert set(leak.forbidden_for(worktree, contexts)) == {"bravo"}


def test_scan_flags_the_other_context_and_the_public_repo_but_not_the_owner(constellation):
    contexts = leak.derive_contexts(constellation)
    # acme's own dev repo naming acme is fine
    assert leak.scan_repo(os.path.join(constellation, "acme_dev"), contexts) == []
    # dotfiles naming acme is not - even though its text calls it a placeholder
    hits = leak.scan_repo(os.path.join(constellation, "dotfiles"), contexts)
    assert [(h[0], h[2], h[3]) for h in hits] == [("docs/x.md", "acme", "acme")]
    # a bravo identifier inside acme's context is the cross-context case
    write(os.path.join(constellation, "acme_dev", "docs/b.md"), "mirror what bravo-site does\n")
    subprocess.run(["git", "-C", os.path.join(constellation, "acme_dev"), "add", "-A"], check=True)
    hits = leak.scan_repo(os.path.join(constellation, "acme_dev"), contexts)
    # both the repo name and the bare token match on that line (the token's boundary allows the hyphen)
    assert sorted((h[0], h[2], h[3]) for h in hits) == [
        ("docs/b.md", "bravo", "bravo"),
        ("docs/b.md", "bravo", "bravo-site"),
    ]


def test_ticket_prefix_needs_a_number_and_words_need_boundaries(constellation):
    contexts = leak.derive_contexts(constellation)
    repo = os.path.join(constellation, "dotfiles")
    write(os.path.join(repo, "docs/x.md"), "ACM-12 is a ticket, ACMe is a word, unacme is not, acme-app is\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    idents = sorted(h[3] for h in leak.scan_repo(repo, contexts))
    assert idents == ["ACM-", "acme", "acme-app"]


def test_staged_mode_sees_only_the_index(constellation):
    contexts = leak.derive_contexts(constellation)
    repo = os.path.join(constellation, "dotfiles")
    write(os.path.join(repo, "docs/x.md"), "clean now\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    write(os.path.join(repo, "docs/x.md"), "acme back in the worktree only\n")
    assert leak.scan_repo(repo, contexts, staged=True) == []
    assert leak.scan_repo(repo, contexts, staged=False) != []


def test_main_exit_codes(constellation, capsys):
    assert leak.main(["--parent", constellation]) == 1  # dotfiles names acme
    assert "context-leak: FAILED" in capsys.readouterr().out
    write(os.path.join(constellation, "dotfiles", "docs/x.md"), "clean\n")
    subprocess.run(["git", "-C", os.path.join(constellation, "dotfiles"), "add", "-A"], check=True)
    assert leak.main(["--parent", constellation]) == 0
    assert "context-leak: clean" in capsys.readouterr().out


def test_a_bang_line_drops_a_derived_name_that_is_an_ordinary_word(constellation):
    write(
        os.path.join(constellation, "bravo_credentials", "bravo_identifiers.txt"),
        "# bravo is also an ordinary word\n!Bravo\n",
    )
    contexts = leak.derive_contexts(constellation)
    assert "bravo" not in contexts["bravo"]["identifiers"]
    assert "bravo_credentials" in contexts["bravo"]["identifiers"]  # only the exact name goes
    assert "!Bravo" not in contexts["bravo"]["identifiers"]


def test_message_mode_scans_the_commit_message_without_its_comments(constellation, tmp_path, capsys):
    message = write(
        str(tmp_path / "COMMIT_EDITMSG"),
        "fix the report\n\n# acme in a comment is not recorded\n"
        "# ------------------------ >8 ------------------------\nacme below the scissors\n",
    )
    dotfiles = os.path.join(constellation, "dotfiles")
    assert leak.main(["--parent", constellation, "--repo", dotfiles, "--message", message]) == 0
    write(message, "fix the Acme Widgets report\n")
    assert leak.main(["--parent", constellation, "--repo", dotfiles, "--message", message]) == 1
    assert "commit message:1: [acme] 'Acme Widgets'" in capsys.readouterr().out
    owner = os.path.join(constellation, "acme_dev")
    assert leak.main(["--parent", constellation, "--repo", owner, "--message", message]) == 0


def test_message_mode_needs_a_repo(constellation, tmp_path):
    message = write(str(tmp_path / "COMMIT_EDITMSG"), "anything\n")
    with pytest.raises(SystemExit):
        leak.main(["--parent", constellation, "--message", message])


def test_binary_files_are_skipped_in_both_modes(constellation):
    contexts = leak.derive_contexts(constellation)
    repo = os.path.join(constellation, "dotfiles")
    with open(os.path.join(repo, "logo.png"), "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n\0\0\0acme\n")
    write(os.path.join(repo, "docs/x.md"), "clean\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    assert leak.scan_repo(repo, contexts, staged=True) == []
    assert leak.scan_repo(repo, contexts, staged=False) == []


def test_outgoing_text_follows_the_target_repo_s_rules(constellation):
    fields = {"title": "port the Acme Widgets report"}
    assert leak.outgoing_hits(fields, repo="mine/blog", parent=constellation)
    assert leak.outgoing_hits(fields, repo="acmeorg/acme-app", parent=constellation) == []
    assert leak.outgoing_hits(fields, repo="acmeorg/undeclared", parent=constellation) == []  # the context's own org
    assert leak.outgoing_hits(fields, ticket="ACM-12", parent=constellation) == []  # its own ticket prefix
    assert leak.outgoing_hits(fields, ticket="ZZZ-12", parent=constellation)  # an unclaimed key fails closed
