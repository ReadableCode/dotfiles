"""Unit tests for src/refresh_machine.py, the one implementation of pullrepos, gitpullall and myupdater."""

import io
import os

import config_test_utils  # noqa F401
import pytest
from src import refresh_machine, terminal_style


def make_git_dir(tmp_path):
    os.makedirs(tmp_path / "dotfiles" / ".git")
    return str(tmp_path)


def titles(steps):
    return [step.title for step in steps]


# ---------------------------------------------------------------- where it runs


def test_resolve_git_dir_prefers_the_exported_git_dir(tmp_path):
    git_dir = make_git_dir(tmp_path)
    assert refresh_machine.resolve_git_dir({"gitDir": git_dir + "/"}, "/elsewhere/dotfiles/src/x.py") == git_dir


def test_resolve_git_dir_falls_back_to_this_checkouts_parent(tmp_path):
    git_dir = make_git_dir(tmp_path)
    script = os.path.join(git_dir, "dotfiles", "src", "refresh_machine.py")
    assert refresh_machine.resolve_git_dir({}, script) == git_dir


def test_resolve_git_dir_refuses_a_directory_without_dotfiles(tmp_path):
    assert refresh_machine.resolve_git_dir({"gitDir": str(tmp_path)}) is None


@pytest.mark.parametrize(
    "system, machine, suffix",
    [
        ("Darwin", "arm64", "git_puller_mac_arm"),
        ("Darwin", "x86_64", "git_puller_mac_x86"),
        ("Linux", "aarch64", "git_puller_arm"),
        ("Linux", "x86_64", "git_puller"),
        ("Windows", "AMD64", "git_puller.exe"),
    ],
)
def test_git_puller_binary_per_platform(system, machine, suffix):
    assert os.path.basename(refresh_machine.git_puller_binary("/g", system, machine)) == suffix


# ---------------------------------------------------------------- which steps


def test_default_steps_in_order(tmp_path):
    steps = refresh_machine.build_steps(make_git_dir(tmp_path), "Darwin", "arm64", which=lambda name: None)
    assert titles(steps) == [
        "pulling every repo",
        "checking for repos to clone",
        "syncing python environments",
        "deploying configs",
        "pruning removed configs",
    ]
    assert steps[-1].argv[-3:] == [os.path.join(tmp_path, "dotfiles", "src", "deploy_configs.py"), "prune", "--apply"]


def test_packages_run_between_the_pull_and_the_clone(tmp_path):
    steps = refresh_machine.build_steps(make_git_dir(tmp_path), "Linux", "x86_64", packages=True, which=lambda n: None)
    assert titles(steps)[:3] == ["pulling every repo", "updating os packages", "checking for repos to clone"]
    assert steps[1].argv == ["bash", os.path.join(tmp_path, "dotfiles", "scripts", "my_updater.sh")]


def test_pull_only_is_just_the_pull(tmp_path):
    assert titles(refresh_machine.build_steps(make_git_dir(tmp_path), "Darwin", "arm64", pull_only=True)) == [
        "pulling every repo"
    ]


def test_windows_uses_powershell_for_packages_and_adds_autohotkey(tmp_path):
    git_dir = make_git_dir(tmp_path)
    os.makedirs(tmp_path / "dotfiles" / "scripts")
    (tmp_path / "dotfiles" / "scripts" / "ensure_autohotkey_v2.ps1").write_text("", encoding="utf-8")
    steps = refresh_machine.build_steps(git_dir, "Windows", "AMD64", packages=True, which=lambda n: "C:/pwsh.exe")
    assert steps[1].argv[0] == "C:/pwsh.exe" and steps[1].argv[-1].endswith("my_updater.ps1")
    assert titles(steps)[-1] == "checking autohotkey"
    assert steps[-1].argv[-2:] == ["-AutoFix", "-Full"]


# ---------------------------------------------------------------- running them


def test_execute_keeps_going_after_a_failure_and_reports_it():
    steps = [
        refresh_machine.Step("pulling every repo", ["puller"], pull=True),
        refresh_machine.Step("deploying configs", ["deploy"]),
        refresh_machine.Step("pruning removed configs", ["prune"]),
    ]
    ran = []

    def run(argv):
        ran.append(argv[0])
        return 2 if argv[0] == "deploy" else 0

    out = io.StringIO()
    failed = refresh_machine.execute(steps, out, False, run=run, pull=lambda argv, o: (0, 0), which=lambda n: "x")
    assert failed == ["deploying configs"]
    assert ran == ["deploy", "prune"]
    assert "failed with exit code 2" in out.getvalue()


def test_execute_warns_about_unpulled_repos_without_failing():
    steps = [refresh_machine.Step("pulling every repo", ["puller"], pull=True)]
    out = io.StringIO()
    failed = refresh_machine.execute(steps, out, False, pull=lambda argv, o: (0, 3))
    assert failed == []
    assert "3 repo(s) could not be pulled" in out.getvalue()


def test_execute_reports_a_missing_tool_without_running_the_step():
    steps = [refresh_machine.Step("deploying configs", ["uv", "run"], needs="uv")]
    out = io.StringIO()
    failed = refresh_machine.execute(steps, out, False, run=lambda argv: pytest.fail("ran"), which=lambda n: None)
    assert failed == ["deploying configs"]
    assert "uv is not installed" in out.getvalue()


def test_unpulled_tags_match_git_pullers_output():
    assert refresh_machine.UNPULLED.match("[AUTH REQUIRED] some_repo")
    assert not refresh_machine.UNPULLED.match("[PULLED] some_repo")


def test_summary_names_the_failed_steps():
    assert refresh_machine.summary(["deploying configs"], 5, False) == (
        "// done\n   1 of 5 steps failed: deploying configs\n"
    )
    assert refresh_machine.summary([], 5, False) == "// done\n   all 5 steps ok\n"


# ---------------------------------------------------------------- the command line


def test_help_is_the_page(capsys):
    with pytest.raises(SystemExit) as exited:
        refresh_machine.main(["--help"], environ={})
    assert exited.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("\u276f refresh_machine\n")
    assert "\n// what happens\n" in out and "\n// examples\n" in out


def test_help_page_steps_match_the_default_steps(tmp_path):
    page = terminal_style.render_page(refresh_machine.HELP_PAGE.splitlines(), False, "")
    assert page.count("\n  ") > 0
    for number in range(1, 8):
        assert f"\n   {number}  " in page


def test_packages_and_pull_only_are_exclusive():
    with pytest.raises(SystemExit):
        refresh_machine.parse_args(["--packages", "--pull-only"])


def test_main_refuses_without_a_dotfiles_checkout(tmp_path, capsys):
    assert refresh_machine.main([], environ={"gitDir": str(tmp_path)}) == 1
    assert "no dotfiles checkout" in capsys.readouterr().err


# ---------------------------------------------------------------- the check plan


def test_check_steps_are_the_read_only_twins(tmp_path):
    git_dir = make_git_dir(tmp_path)
    steps = refresh_machine.build_steps(git_dir, "Darwin", "arm64", check=True, which=lambda name: None)
    assert titles(steps) == [
        "checking every repo for upstream commits",
        "checking for repos to clone",
        "checking python environments",
        "checking deployed configs",
        "checking for configs to prune",
    ]
    assert steps[0].action is not None and steps[0].argv == []
    # the prune check is the dry run: applying would delete links
    assert steps[-1].argv[-1] == "prune" and "--apply" not in steps[-1].argv


def test_check_with_packages_asks_the_updater_for_its_own_check(tmp_path):
    git_dir = make_git_dir(tmp_path)
    steps = refresh_machine.build_steps(
        git_dir, "Linux", "x86_64", packages=True, check=True, which=lambda name: None
    )
    assert steps[1].argv == ["bash", os.path.join(git_dir, "dotfiles", "scripts", "my_updater.sh"), "--check"]


def test_check_pull_only_is_just_the_fetch(tmp_path):
    steps = refresh_machine.build_steps(make_git_dir(tmp_path), "Darwin", "arm64", pull_only=True, check=True)
    assert titles(steps) == ["checking every repo for upstream commits"]


def test_repo_dirs_skips_directories_that_are_not_checkouts(tmp_path):
    os.makedirs(tmp_path / "repo" / ".git")
    os.makedirs(tmp_path / "notes")
    assert [name for name, _ in refresh_machine.repo_dirs(str(tmp_path))] == ["repo"]


def test_fetch_check_reports_only_the_repos_behind(tmp_path):
    for name in ("alpha", "beta", "gamma"):
        os.makedirs(tmp_path / name / ".git")
    answers = {
        "alpha": ("alpha", 3, ""),
        "beta": ("beta", 0, ""),
        "gamma": ("gamma", 0, "fetch failed (offline or no remote)"),
    }
    out = io.StringIO()
    code = refresh_machine.fetch_check(str(tmp_path), out, fetch=lambda entry: answers[entry[0]])
    text = out.getvalue()
    assert code == 1
    assert "alpha: 3 commit(s) behind" in text
    assert "gamma: fetch failed" in text
    assert "beta" not in text  # a repo that is current prints nothing
    assert "checked 3 repos: 1 behind" in text


def test_fetch_check_is_quiet_and_clean_when_nothing_is_behind(tmp_path):
    os.makedirs(tmp_path / "solo" / ".git")
    out = io.StringIO()
    assert refresh_machine.fetch_check(str(tmp_path), out, fetch=lambda entry: (entry[0], 0, "")) == 0
    assert "checked 1 repos: 0 behind" in out.getvalue()


def test_execute_runs_a_python_action_step():
    steps = [refresh_machine.Step("checking every repo for upstream commits", [], action=lambda out: 1)]
    out = io.StringIO()
    assert refresh_machine.execute(steps, out, False) == ["checking every repo for upstream commits"]


def test_summary_says_drift_in_check_mode():
    assert "reported drift" in refresh_machine.summary(["checking deployed configs"], 5, False, check=True)
    assert "all 5 steps ok" in refresh_machine.summary([], 5, False, check=True)
