"""Unit tests for src/tailscale_routes.py and scripts/tailscale_subnet_router.sh - advertised subnet routes."""

import json
import os
import subprocess

import config_test_utils  # noqa F401

from src import tailscale_routes

LAN = "10.9.8.0/24"

PREFS = """{{
\t"ControlURL": "https://controlplane.tailscale.com",
\t"RouteAll": {route_all},
\t"ExitNodeID": "",
\t"AdvertiseRoutes": {routes},
\t"WantRunning": true
}}
"""


def write_inventory(root, block):
    credentials = root / "personal_credentials"
    credentials.mkdir()
    router = {"name": "Router", "os": "linux"}
    if block is not None:
        router["tailscale"] = block
    hosts = [router, {"name": "Desk", "os": "linux"}]
    (credentials / "personal_hosts.json").write_text(json.dumps({"hosts": hosts}))
    return str(root)


class Recorder:
    def __init__(self, returncode=0):
        self.calls = []
        self.returncode = returncode

    def __call__(self, argv, **_):
        self.calls.append(argv)
        return subprocess.CompletedProcess(argv, self.returncode)


# ---------------------------------------------------------------- the wrapper


def test_a_host_without_a_tailscale_block_runs_nothing(tmp_path):
    root = write_inventory(tmp_path, None)
    run = Recorder()
    assert tailscale_routes.sync("Router", root, run=run) == 0
    assert run.calls == []


def test_a_router_hands_its_routes_to_the_script(tmp_path):
    root = write_inventory(tmp_path, {"advertise_routes": [LAN, "10.9.9.0/24"]})
    run = Recorder()
    assert tailscale_routes.sync("router.local", root, run=run) == 0
    assert run.calls == [["bash", tailscale_routes.SCRIPT, f"{LAN},10.9.9.0/24"]]


def test_check_passes_check_and_drift_is_not_a_failure(tmp_path):
    root = write_inventory(tmp_path, {"advertise_routes": [LAN]})
    run = Recorder(returncode=1)
    assert tailscale_routes.sync("Router", root, check=True, run=run) == 0
    assert run.calls == [["bash", tailscale_routes.SCRIPT, "--check", LAN]]


def test_a_failed_set_is_a_failure(tmp_path):
    root = write_inventory(tmp_path, {"advertise_routes": [LAN]})
    assert tailscale_routes.sync("Router", root, run=Recorder(returncode=1)) == 1


# ---------------------------------------------------------------- the script


def fake_tailscale(tmp_path, routes, route_all):
    """A tailscale on PATH that prints the given prefs and logs every set call."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (tmp_path / "prefs.json").write_text(PREFS.format(routes=json.dumps(routes, indent="\t"), route_all=route_all))
    tool = bindir / "tailscale"
    tool.write_text(
        "#!/bin/bash\n"
        f'if [ "$1 $2" = "debug prefs" ]; then cat "{tmp_path}/prefs.json"; exit 0; fi\n'
        f'echo "$@" >> "{tmp_path}/calls"\n'
    )
    tool.chmod(0o755)
    return {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"}


def run_script(env, *args):
    script = os.path.join(os.path.dirname(tailscale_routes.SCRIPT), "tailscale_subnet_router.sh")
    return subprocess.run(["bash", script, *args], env=env, capture_output=True, text=True)


def set_calls(tmp_path):
    calls = tmp_path / "calls"
    return calls.read_text().splitlines() if calls.exists() else []


def test_matching_prefs_change_nothing_and_print_nothing(tmp_path):
    env = fake_tailscale(tmp_path, [LAN], "false")
    result = run_script(env, LAN)
    assert result.returncode == 0 and result.stdout == ""
    assert set_calls(tmp_path) == []


def test_a_missing_route_is_set_and_the_exit_node_kept(tmp_path):
    env = fake_tailscale(tmp_path, ["0.0.0.0/0", "::/0"], "false")
    result = run_script(env, LAN)
    assert result.returncode == 0
    assert set_calls(tmp_path) == [f"set --advertise-routes={LAN} --advertise-exit-node=true --accept-routes=false"]
    assert "now advertising" in result.stdout


def test_no_routes_at_all_sets_them_without_an_exit_node(tmp_path):
    env = fake_tailscale(tmp_path, None, "false")
    run_script(env, LAN)
    assert set_calls(tmp_path) == [f"set --advertise-routes={LAN} --advertise-exit-node=false --accept-routes=false"]


def test_accepting_routes_is_drift_even_with_the_route_advertised(tmp_path):
    env = fake_tailscale(tmp_path, [LAN], "true")
    run_script(env, LAN)
    assert set_calls(tmp_path) == [f"set --advertise-routes={LAN} --advertise-exit-node=false --accept-routes=false"]


def test_check_reports_drift_and_changes_nothing(tmp_path):
    env = fake_tailscale(tmp_path, ["0.0.0.0/0", "::/0"], "true")
    result = run_script(env, "--check", LAN)
    assert result.returncode == 1 and result.stdout.startswith("drift: advertise=[0.0.0.0/0,::/0] accept-routes=true")
    assert set_calls(tmp_path) == []


def test_check_reports_ok(tmp_path):
    env = fake_tailscale(tmp_path, [LAN, "0.0.0.0/0", "::/0"], "false")
    result = run_script(env, "--check", LAN)
    assert result.returncode == 0 and result.stdout.startswith("ok:")


def test_no_route_argument_is_a_usage_error(tmp_path):
    env = fake_tailscale(tmp_path, [LAN], "false")
    assert run_script(env).returncode == 2
