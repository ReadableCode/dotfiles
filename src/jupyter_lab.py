#!/usr/bin/env python3
"""Run JupyterLab on one checkout for one T3 thread, and stop it when that thread is done.

    python3 ~/GitHub/dotfiles/src/jupyter_lab.py start     # from inside the checkout
    python3 ~/GitHub/dotfiles/src/jupyter_lab.py status
    python3 ~/GitHub/dotfiles/src/jupyter_lab.py stop

``start`` launches ``jupyter lab`` through ``uv run`` in the checkout's own project environment,
with ``jupyterlab`` and ``jupytext`` layered on for that run only (``--with``), so nothing is added
to the project and nothing is installed globally. A notebook needs nothing else from Jupyter: a
package the cells import belongs in the project's own dependencies. A checkout with a
``uv.lock`` runs ``--frozen`` (starting Jupyter never rewrites a lock); one without runs
``--no-project`` (it never creates a lock or a ``.venv`` there).

- **Port.** The first free port from 8888 up, and ``--ServerApp.port_retries=0`` so the server
  fails instead of drifting to another port behind the URL it was given. One server per
  checkout: a second ``start`` in the same checkout prints the running server's URL.
- **Login.** A fresh token per server, passed on the command line along with an empty password,
  so a password left in ``~/.jupyter/jupyter_server_config.json`` never applies. The printed
  ``/lab?token=...`` URL logs a browser in; auth stays on for everything else on the machine.
- **Checkpoints** go to ``~/.cache/jupyter_lab/checkpoints/<key>/`` (``FileCheckpoints.root_dir``),
  never ``.ipynb_checkpoints/`` inside the checkout, so a worktree never holds untracked files
  because Jupyter saved.
- **Lifetime.** The server belongs to the T3 thread that started it: the thread is found from
  ``CLAUDE_CODE_SESSION_ID`` through ``t3_state.thread_for_session`` (or ``--thread``). A detached
  supervisor (``serve``, its own session, so it outlives the Claude turn) runs the server and
  polls T3's state every 15 seconds, and stops it once the thread is settled or deleted or the
  checkout is gone. Settling does not stop it yet while the thread's session stays ``ready``
  (``backlog/jupyter-lab-ignores-settle-while-session-ready.md``). ``init_worktree.teardown``
  (``/remove_worktree``, ``/sweep_worktrees``) calls ``stop_for`` before deleting a worktree, so
  nothing is left serving a removed directory.

State lives in ``~/.cache/jupyter_lab/<key>.json`` (checkout, port, token, thread, supervisor
pid), the server's output in ``<key>.log`` beside it, where ``<key>`` is a hash of the checkout
path. Saving a ``.py`` back without a YAML header or cell metadata needs a jupytext config
(``py:percent``, both metadata filters ``-all``) in the repo or in ``~/.config/jupytext/``; none is
deployed (see ``docs/repo_jupyter_lab.md``).

POSIX only (process groups). Stdlib-only, like its siblings: a bare ``python3`` runs it before
any venv exists. Not wrapped by a command and not deployed anywhere: run it by hand.
"""

import argparse
import hashlib
import json
import os
import secrets
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import t3_state  # noqa: E402

STATE_DIR = os.path.expanduser("~/.cache/jupyter_lab")
FIRST_PORT = 8888
LAST_PORT = 8987
TOOLS = ("jupyterlab", "jupytext")
POLL_SECONDS = 15
# The first start on a machine downloads jupyterlab into uv's cache.
START_TIMEOUT = 180
STOP_TIMEOUT = 15


# ---------------------------------------------------------------- state files


def checkout_root(path):
    """The checkout containing path (its git top level), or path itself outside git."""
    try:
        top = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=path, text=True, stderr=subprocess.DEVNULL
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return os.path.realpath(path)
    return os.path.realpath(top.strip())


def state_key(checkout):
    return hashlib.sha1(checkout.encode("utf-8")).hexdigest()[:12]


def state_file(checkout, state_dir=None):
    return os.path.join(state_dir or STATE_DIR, state_key(checkout) + ".json")


def read_state(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def write_state(path, state):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    os.chmod(path, 0o600)  # holds the token


def is_alive(pid):
    """True when pid is a running `jupyter_lab.py serve` supervisor (never a recycled pid)."""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    args = subprocess.run(["ps", "-p", str(pid), "-o", "args="], capture_output=True, text=True).stdout
    return "jupyter_lab.py" in args and " serve " in args


def servers(state_dir=None):
    """Every live server's state; a state file whose supervisor is gone is deleted."""
    state_dir = state_dir or STATE_DIR
    if not os.path.isdir(state_dir):
        return []
    live = []
    for name in sorted(os.listdir(state_dir)):
        path = os.path.join(state_dir, name)
        if not name.endswith(".json"):
            continue
        state = read_state(path)
        if state and is_alive(state.get("pid")):
            live.append(state)
        else:
            os.remove(path)
    return live


def server_for(checkout, state_dir=None):
    return next((state for state in servers(state_dir) if state["checkout"] == checkout), None)


def lab_url(state):
    return f"http://127.0.0.1:{state['port']}/lab?token={state['token']}"


# ---------------------------------------------------------------- launching


def port_in_use(port):
    """True when something answers on the port, or the server could not bind it.

    The bind probe sets SO_REUSEADDR like the server does, so the TIME_WAIT sockets a stopped
    server leaves behind do not push the next one to another port. The connect catches a listener
    on 0.0.0.0, which BSD lets a reuse-address bind to 127.0.0.1 coexist with.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            return True
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return True
    return False


def free_port(taken, first=FIRST_PORT, last=LAST_PORT):
    """The first port from `first` that no server here claims and nothing is using."""
    for port in range(first, last + 1):
        if port not in taken and not port_in_use(port):
            return port
    raise RuntimeError(f"no free port between {first} and {last}")


def jupyter_command(state):
    """The `uv run ... jupyter lab` argv for one server, from its state."""
    checkout = state["checkout"]
    uv = ["uv", "run", "--frozen" if os.path.isfile(os.path.join(checkout, "uv.lock")) else "--no-project"]
    for tool in TOOLS:
        uv += ["--with", tool]
    return uv + [
        "jupyter",
        "lab",
        "--no-browser",
        "--ip",
        "127.0.0.1",
        "--port",
        str(state["port"]),
        "--ServerApp.port_retries=0",
        f"--ServerApp.root_dir={checkout}",
        f"--IdentityProvider.token={state['token']}",
        "--PasswordIdentityProvider.hashed_password=",
        "--ServerApp.password=",
        f"--FileCheckpoints.root_dir={state['checkpoints']}",
    ]


def responds(state):
    """True when the server answers an authenticated status request (no proxy: it is loopback)."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = f"http://127.0.0.1:{state['port']}/api/status?token={state['token']}"
    try:
        with opener.open(url, timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def finished_reason(state, db_path=t3_state.STATE_DB):
    """Why the server should stop now, or None. A locked or missing database never stops it."""
    if not os.path.isdir(state["checkout"]):
        return "checkout removed"
    try:
        verdict = t3_state.thread_verdict(state["thread"], db_path)
    except sqlite3.Error:
        return None
    return f"thread {verdict}" if verdict in t3_state.FINISHED else None


# ---------------------------------------------------------------- commands


def start(path, thread=None, state_dir=None):
    state_dir = state_dir or STATE_DIR
    if os.name == "nt":
        print("jupyter_lab.py needs POSIX process groups; not supported on Windows")
        return 2
    checkout = checkout_root(path)
    running = server_for(checkout, state_dir)
    if running:
        print(f"already running for {checkout}\nurl: {lab_url(running)}")
        return 0
    thread = thread or t3_state.thread_for_session(os.environ.get("CLAUDE_CODE_SESSION_ID"))
    if not thread:
        print("no T3 thread owns this session, and the server's lifetime is a thread's - pass --thread <id>")
        return 2
    verdict = t3_state.thread_verdict(thread)
    if verdict in t3_state.FINISHED:
        print(f"thread {thread[:8]} is {verdict}; refusing to start a server it would stop at once")
        return 2
    if shutil.which("uv") is None:
        print("uv is not on PATH")
        return 2

    key = state_key(checkout)
    state = {
        "checkout": checkout,
        "port": free_port({server["port"] for server in servers(state_dir)}),
        "token": secrets.token_hex(24),
        "thread": thread,
        "checkpoints": os.path.join(state_dir, "checkpoints", key),
        "log": os.path.join(state_dir, key + ".log"),
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "pid": None,
    }
    path = state_file(checkout, state_dir)
    write_state(path, state)
    with open(state["log"], "w", encoding="utf-8") as log:
        supervisor = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "serve", "--state", path],
            cwd=checkout,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    state["pid"] = supervisor.pid
    write_state(path, state)

    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if supervisor.poll() is not None:
            print(f"the server exited during startup; last lines of {state['log']}:")
            with open(state["log"], encoding="utf-8", errors="replace") as log:
                print("".join(log.readlines()[-15:]), end="")
            return 1
        if responds(state):
            print(f"checkout: {checkout}\nthread:   {thread}\nport:     {state['port']}\nlog:      {state['log']}")
            print(f"url: {lab_url(state)}")
            return 0
        time.sleep(1)
    print(f"no answer on port {state['port']} after {START_TIMEOUT}s - stopping it; see {state['log']}")
    stop_for(checkout, state_dir=state_dir)
    return 1


def serve(path, db_path=t3_state.STATE_DB):
    """The supervisor: session leader of the server's process group, run detached by `start`."""
    state = read_state(path)
    stopping = []
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda number, frame: stopping.append(number))
    server = subprocess.Popen(jupyter_command(state), cwd=state["checkout"], stdin=subprocess.DEVNULL)
    print(f"supervisor {os.getpid()}: server {server.pid} on port {state['port']}", flush=True)
    next_check = time.monotonic() + POLL_SECONDS
    while server.poll() is None and not stopping:
        time.sleep(1)
        if time.monotonic() >= next_check:
            reason = finished_reason(state, db_path)
            if reason:
                print(f"stopping: {reason}", flush=True)
                break
            next_check = time.monotonic() + POLL_SECONDS
    if server.poll() is None:
        os.killpg(os.getpgrp(), signal.SIGTERM)  # uv and jupyter both; our own handler just records it
        try:
            server.wait(STOP_TIMEOUT)
        except subprocess.TimeoutExpired:
            pass
    current = read_state(path)
    if current and current.get("pid") == os.getpid():
        os.remove(path)
    if server.poll() is None:
        os.killpg(os.getpgrp(), signal.SIGKILL)  # the last act: it kills this process too
    return 0


def stop_for(checkout, dry_run=False, state_dir=None):
    """Stop the server serving exactly this checkout, if there is one. Returns a status word."""
    state = server_for(os.path.realpath(checkout), state_dir)
    if state is None:
        return "none running"
    if dry_run:
        return f"would stop (port {state['port']})"
    os.killpg(state["pid"], signal.SIGTERM)
    deadline = time.monotonic() + STOP_TIMEOUT + 5
    while is_alive(state["pid"]) and time.monotonic() < deadline:
        time.sleep(0.5)
    if is_alive(state["pid"]):
        os.killpg(state["pid"], signal.SIGKILL)
    path = state_file(state["checkout"], state_dir)
    if os.path.exists(path):
        os.remove(path)
    return f"stopped (port {state['port']})"


def status(state_dir=None):
    live = servers(state_dir)
    if not live:
        print("no JupyterLab servers running")
    for state in live:
        verdict = t3_state.thread_verdict(state["thread"]) or "unknown"
        print(f"port {state['port']}  thread {state['thread'][:8]} ({verdict})  {state['checkout']}")
        print(f"  {lab_url(state)}")
    return 0


# ---------------------------------------------------------------- main


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    start_parser = commands.add_parser("start", help="start a server for this checkout and print its URL")
    start_parser.add_argument("--path", default=os.getcwd(), help="path inside the checkout (default: cwd)")
    start_parser.add_argument("--thread", help="T3 thread id that owns the server (default: this session's)")
    stop_parser = commands.add_parser("stop", help="stop this checkout's server")
    stop_parser.add_argument("--path", default=os.getcwd(), help="path inside the checkout (default: cwd)")
    commands.add_parser("status", help="list the running servers")
    serve_parser = commands.add_parser("serve", help=argparse.SUPPRESS)
    serve_parser.add_argument("--state", required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.command == "start":
        return start(args.path, thread=args.thread)
    if args.command == "stop":
        checkout = checkout_root(args.path)
        print(f"{checkout}: {stop_for(checkout)}")
        return 0
    if args.command == "status":
        return status()
    return serve(args.state)


if __name__ == "__main__":
    sys.exit(main())
