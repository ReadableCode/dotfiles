"""context_leak_check derives each client's identifiers from its own repo and refuses them elsewhere."""

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
    write(os.path.join(parent, "personal_credentials", "personal_repos.yaml"), "defaults:\n  org: mine\nrepos:\n  - name: blog\n")
    git_repo(os.path.join(parent, "personal_credentials"), {"notes.md": "acme and bravo both fine here"})
    write(os.path.join(parent, "acme_credentials", "acme_repos.yaml"),
          "defaults:\n  org: acmeorg\nrepos:\n  - name: acme-app\n  - name: shared-tool\n    org: mine\n")
    write(os.path.join(parent, "acme_credentials", "acme_hosts.json"),
          json.dumps({"hosts": [{"name": "ACME-LAP-01", "hostname": "10.9.9.9"}]}))
    write(os.path.join(parent, "acme_credentials", "acme.env"), "JIRA_PROJECT=ACM\n")
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
    for expected in ["acme", "acme_credentials", "acme-app", "acmeorg", "ACME-LAP-01", "10.9.9.9", "ACM-", "Acme Widgets", "acme_dev", "acme-dev"]:
        assert expected in acme, expected
    assert "mine" not in acme  # the personal org appears in client repos files and is not a client identifier
    assert "shared-tool" in acme
    assert contexts["acme"]["repos"] == ["acme_credentials", "acme_dev"]
    # the client's own checkouts are owned (their identifiers are theirs) but not scanned by default
    assert {"acme-app", "shared-tool", "acme_credentials", "acme_dev"} <= contexts["acme"]["owned"]


def test_rules_depend_on_which_repo_is_scanned(constellation):
    contexts = leak.derive_contexts(constellation)
    assert leak.forbidden_for(os.path.join(constellation, "personal_credentials"), contexts) == {}
    assert leak.forbidden_for(os.path.join(constellation, "personal_dev"), contexts) == {}
    assert set(leak.forbidden_for(os.path.join(constellation, "acme_dev"), contexts)) == {"bravo"}
    assert set(leak.forbidden_for(os.path.join(constellation, "acme_credentials"), contexts)) == {"bravo"}
    assert set(leak.forbidden_for(os.path.join(constellation, "dotfiles"), contexts)) == {"acme", "bravo"}
    assert set(leak.forbidden_for(os.path.join(constellation, "blog"), contexts)) == {"acme", "bravo"}
    assert set(leak.forbidden_for(os.path.join(constellation, "acme-app"), contexts)) == {"bravo"}


def test_scan_flags_the_other_context_and_the_public_repo_but_not_the_owner(constellation):
    contexts = leak.derive_contexts(constellation)
    # acme's own dev repo naming acme is fine
    assert leak.scan_repo(os.path.join(constellation, "acme_dev"), contexts) == []
    # dotfiles naming acme is not - even though its text calls it a placeholder
    hits = leak.scan_repo(os.path.join(constellation, "dotfiles"), contexts)
    assert [(h[0], h[2], h[3]) for h in hits] == [("docs/x.md", "acme", "acme")]
    # a bravo identifier inside acme's context is the cross-client case
    write(os.path.join(constellation, "acme_dev", "docs/b.md"), "mirror what bravo-site does\n")
    subprocess.run(["git", "-C", os.path.join(constellation, "acme_dev"), "add", "-A"], check=True)
    hits = leak.scan_repo(os.path.join(constellation, "acme_dev"), contexts)
    # both the repo name and the bare token match on that line (the token's boundary allows the hyphen)
    assert sorted((h[0], h[2], h[3]) for h in hits) == [("docs/b.md", "bravo", "bravo"), ("docs/b.md", "bravo", "bravo-site")]


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
