import os
import stat
import subprocess

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "install_mac_apps.sh")

FAKE_BREW = """#!/bin/bash
echo "$*" >> "$BREW_LOG"
"""


def run_install_phase(tmp_path, planned):
    """Run the installer's install phase (APP_PHASE=install) against a fake brew that logs each call."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    brew = bin_dir / "brew"
    brew.write_text(FAKE_BREW)
    brew.chmod(brew.stat().st_mode | stat.S_IEXEC)
    brewfile = tmp_path / "Brewfile"
    brewfile.write_text("")
    plan = tmp_path / "plan.tsv"
    plan.write_text("".join(f"brew\t{name}\n" for name in planned))
    log = tmp_path / "brew.log"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "APP_PHASE": "install",
        "APP_PLAN": str(plan),
        "BREW_LOG": str(log),
    }
    subprocess.run(["bash", SCRIPT, str(brewfile)], env=env, check=True, capture_output=True, text=True)
    return log.read_text().splitlines()


def test_a_tap_formula_is_tapped_and_trusted_alone_before_it_installs(tmp_path):
    calls = run_install_phase(tmp_path, ["jq", "acme/tools/widget", "tmux"])
    assert calls == [
        "tap acme/tools",
        "trust --formula acme/tools/widget",
        "install acme/tools/widget",
        "install jq tmux",
    ]


def test_plain_formulae_install_in_one_call_with_nothing_trusted(tmp_path):
    assert run_install_phase(tmp_path, ["jq", "tmux"]) == ["install jq tmux"]
