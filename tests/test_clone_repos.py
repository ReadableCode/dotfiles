# %%
# Imports #

import os

import config_test_utils  # noqa F401
import pytest
import yaml
from src import clone_repos

# %%
# Helpers #


def write_repos_config(directory, context, data):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{context}_repos.yaml")
    with open(path, "w", encoding="utf-8") as file_handle:
        yaml.safe_dump(data, file_handle)
    return path


def write_inventory(directory, context, names):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{context}_hosts.json")
    with open(path, "w", encoding="utf-8") as file_handle:
        file_handle.write('{"hosts": [' + ", ".join(f'{{"name": "{name}"}}' for name in names) + "]}\n")
    return path


@pytest.fixture
def git_dir(tmp_path, monkeypatch):
    """A fake gitDir whose only overlay repo is acme_credentials."""
    root = tmp_path / "GitHub"
    os.makedirs(str(root / "acme_credentials"))
    monkeypatch.setattr(clone_repos, "GIT_DIR", str(root))
    return root


# %%
# Host filters #


def test_no_filters_offers_everywhere():
    assert clone_repos.entry_matches_host({"name": "x"}, "ANYBOX")


def test_hosts_allow_list_matches_short_name_case_insensitively():
    entry = {"name": "x", "hosts": ["Envy", "RyzenWhite"]}
    assert clone_repos.entry_matches_host(entry, "ENVY.LOCAL")
    assert clone_repos.entry_matches_host(entry, "ryzenwhite")
    assert not clone_repos.entry_matches_host(entry, "ELITEDESK")


def test_exclude_hosts_blocks_a_machine_that_would_otherwise_match():
    # the elitedesk case: it holds the credentials repo only because the git
    # origin lives there, so it must never be offered that context's repos
    entry = {"name": "x", "exclude_hosts": ["ELITEDESK"]}
    assert not clone_repos.entry_matches_host(entry, "elitedesk.local")
    assert clone_repos.entry_matches_host(entry, "ENVY")
    assert clone_repos.entry_matches_host(entry, "ACME-LAPTOP")


def test_exclude_hosts_wins_over_an_allow_list():
    entry = {"name": "x", "hosts": ["ENVY", "ELITEDESK"], "exclude_hosts": ["ELITEDESK"]}
    assert clone_repos.entry_matches_host(entry, "ENVY")
    assert not clone_repos.entry_matches_host(entry, "ELITEDESK")


# %%
# Validation #


def test_invalid_filter_shapes_are_rejected():
    for field in ("hosts", "exclude_hosts"):
        for bad in ("ENVY", [5], {"host": "ENVY"}):
            with pytest.raises(ValueError, match=field):
                clone_repos.validate_entry({"name": "x", "provider": "github", "org": "o", field: bad}, "cfg.yaml")


def test_unknown_hosts_name_fails_loudly(git_dir):
    write_inventory(str(git_dir / "acme_credentials"), "acme", ["ACMEBOX"])
    write_repos_config(
        str(git_dir / "acme_credentials"),
        "acme",
        {"defaults": {"provider": "github", "org": "acme"}, "repos": [{"name": "widget", "hosts": ["NOSUCHBOX"]}]},
    )
    with pytest.raises(ValueError, match="NOSUCHBOX"):
        clone_repos.load_repo_entries()


def test_unknown_exclude_hosts_name_loads_fine(git_dir):
    """
    A block list names machines of ANOTHER context, which the reading machine's
    inventories know nothing about. Validating it would make a client-only
    machine fail to load the config at all - the opposite of what the block
    list is for.
    """
    write_inventory(str(git_dir / "acme_credentials"), "acme", ["ACMEBOX"])
    write_repos_config(
        str(git_dir / "acme_credentials"),
        "acme",
        {
            "defaults": {"provider": "github", "org": "acme", "exclude_hosts": ["SOMEONE-ELSES-BOX"]},
            "repos": [{"name": "widget"}],
        },
    )
    entries = clone_repos.load_repo_entries()
    assert entries[0]["exclude_hosts"] == ["SOMEONE-ELSES-BOX"]
    assert not clone_repos.entry_matches_host(entries[0], "SOMEONE-ELSES-BOX")
    assert clone_repos.entry_matches_host(entries[0], "ACMEBOX")


def test_defaults_supply_the_block_list_to_every_entry(git_dir):
    write_repos_config(
        str(git_dir / "acme_credentials"),
        "acme",
        {
            "defaults": {"provider": "github", "org": "acme", "exclude_hosts": ["ELITEDESK"]},
            "repos": [{"name": "one"}, {"name": "two", "exclude_hosts": []}],
        },
    )
    entries = {entry["name"]: entry for entry in clone_repos.load_repo_entries()}
    assert not clone_repos.entry_matches_host(entries["one"], "ELITEDESK")
    # an entry can opt back in by overriding the default with an empty list
    assert clone_repos.entry_matches_host(entries["two"], "ELITEDESK")


# %%
# The real configs #


def test_real_repo_configs_load_and_keep_client_repos_off_the_origin_host():
    """Whatever the client configs say, elitedesk must never be offered their repos."""
    entries = clone_repos.load_repo_entries()
    if not entries:
        pytest.skip("no <context>_repos.yaml present on this machine")
    for entry in entries:
        if entry["_context"] in ("dotfiles", "personal"):
            continue
        assert not clone_repos.entry_matches_host(entry, "ELITEDESK"), (
            f"{entry['_context']} repo {entry['name']} would be offered on elitedesk, which holds git "
            "origins under ~/GitHub and must never hold client working repos"
        )
