import os
import shutil
import subprocess

LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "app_install_lib.sh")

# Stands in for an installer script: the caller-defined functions the library
# calls, with installs that fail for any name in $BAD and log every call.
# src/app_lists.py is stubbed too: $LIST is what --packages names, and this
# machine ignores nothing.
CALLER = """
source "$LIB"
app_lists_py() {
    case "$1" in
        --packages) cat "$LIST" ;;
        --ignored) cat > /dev/null ;;
        *) return 1 ;;
    esac
}
list_installed() { :; }
list_available() { printf '%s\\n' $AVAILABLE; }
install_apps() {
    echo "install $*" >> "$LOG"
    for app in "$@"; do
        case " $BAD " in *" $app "*) return 1 ;; esac
    done
}
install_from_list "apt" apt
"""


def run(tmp_path, phase, listed=(), planned=(), available="", bad=""):
    script = tmp_path / "caller.sh"
    # LF endings, as the installers write their own files; bash reads a CR as part of the name
    script.write_text(CALLER, newline="\n")
    app_list = tmp_path / "apps.txt"
    app_list.write_text("".join(f"{name}\n" for name in listed), newline="\n")
    plan = tmp_path / "plan.tsv"
    plan.write_text("".join(f"apt\t{name}\n" for name in planned), newline="\n")
    log = tmp_path / "calls.log"
    env = {
        **os.environ,
        "LIB": LIB.replace(os.sep, "/"),
        "LIST": str(app_list).replace(os.sep, "/"),
        "APP_PHASE": phase,
        "APP_PLAN": str(plan).replace(os.sep, "/"),
        "LOG": str(log).replace(os.sep, "/"),
        "AVAILABLE": available,
        "BAD": bad,
        "ASSUME_YES": "1",
    }
    env.pop("REFRESH_REPORT", None)
    # the bash on PATH: on Windows a bare "bash" is System32's WSL launcher
    done = subprocess.run(
        [shutil.which("bash"), str(script).replace(os.sep, "/")], env=env, capture_output=True, text=True
    )
    calls = log.read_text().splitlines() if log.exists() else []
    return done, calls, plan.read_text().splitlines()


def test_a_package_the_sources_lack_is_reported_and_never_queued(tmp_path):
    done, _, plan = run(tmp_path, "ask", listed=["fzf", "fastfetch", "ripgrep"], available="fzf ripgrep")
    assert done.returncode == 0, done.stderr
    assert "not offered (1):\n  fastfetch" in done.stdout
    assert plan == ["apt\tfzf", "apt\tripgrep"]


def test_a_failed_batch_retries_each_package_and_fails_only_for_the_bad_one(tmp_path):
    done, calls, _ = run(tmp_path, "install", planned=["fzf", "nosuch", "ripgrep"], bad="nosuch")
    assert done.returncode == 1
    assert calls == ["install fzf nosuch ripgrep", "install fzf", "install nosuch", "install ripgrep"]


def test_a_good_batch_installs_in_one_call(tmp_path):
    done, calls, _ = run(tmp_path, "install", planned=["fzf", "ripgrep"])
    assert done.returncode == 0
    assert calls == ["install fzf ripgrep"]
