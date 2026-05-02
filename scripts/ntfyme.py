#!/usr/bin/env python3
"""ntfyme: run a command, send a ntfy notification when it exits.

Reads NTFY_URL, NTFY_TOPIC, NTFY_USERNAME, NTFY_PASSWORD from <dotfiles>/.env
(or the process env). CLI flags override env vars.

Stdlib only, except for an optional `truststore` import — when installed it
makes Python use the OS-native trust store (Schannel on Windows, SecureTransport
on macOS), which is the only reliable way to pick up corporate / self-hosted CAs
on Windows. Falls back gracefully when not present.
"""

import argparse
import base64
import collections
import os
import shlex
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

DOTFILES_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = DOTFILES_ROOT / ".env"
DEFAULT_TAIL_LINES = 10
LONG_RUN_SECONDS = 600


def load_env_file(path: Path) -> None:
    """Parse KEY=VALUE lines into os.environ. Existing env vars win."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s"


def send_notification(
    server, topic, title, body, priority, tags, username=None, password=None
):
    """POST to ntfy. Never raise — notify failure must not break the user's workflow."""
    url = f"{server.rstrip('/')}/{topic}"
    headers = {
        "Title": title,
        "Priority": str(priority),
        "Tags": ",".join(tags),
    }
    if username and password:
        creds = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {creds}"
    req = urllib.request.Request(
        url,
        data=body.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except (urllib.error.URLError, OSError) as e:
        print(f"[ntfyme] notification failed: {e}", file=sys.stderr)


def run_command(cmd, tail_lines):
    """Run cmd, stream stdout/stderr live, capture last N stderr lines, forward signals."""
    tail = collections.deque(maxlen=tail_lines) if tail_lines else None
    proc = subprocess.Popen(
        cmd,
        stdout=sys.stdout,
        stderr=subprocess.PIPE,
        bufsize=1,
        text=True,
    )

    def forward(sig, _frame):
        try:
            proc.send_signal(sig)
        except ProcessLookupError:
            pass

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, forward)

    start = time.monotonic()
    assert proc.stderr is not None
    for line in proc.stderr:
        sys.stderr.write(line)
        if tail is not None:
            tail.append(line.rstrip("\n"))
    proc.wait()
    duration = time.monotonic() - start
    return proc.returncode, duration, list(tail) if tail else []


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="ntfyme",
        description="Run a command and send a ntfy notification when it exits.",
        usage="ntfyme [options] [--] COMMAND [ARGS...]",
    )
    parser.add_argument("--title", help="Override the notification title")
    parser.add_argument("--topic", help="ntfy topic (overrides NTFY_TOPIC)")
    parser.add_argument("--server", help="ntfy server (overrides NTFY_URL)")
    parser.add_argument(
        "--tail",
        type=int,
        default=DEFAULT_TAIL_LINES,
        help=f"include last N stderr lines on failure (default {DEFAULT_TAIL_LINES}, 0 to disable)",
    )
    parser.add_argument(
        "--min-duration",
        type=float,
        default=0.0,
        help="skip notification if command finished faster than this many seconds",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def main() -> int:
    load_env_file(ENV_FILE)
    args = parse_args(sys.argv[1:])

    cmd = args.command
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print(
            "ntfyme: no command given. Usage: ntfyme [options] [--] CMD [ARGS...]",
            file=sys.stderr,
        )
        return 2

    topic = args.topic or os.environ.get("NTFYME_TOPIC")
    server = args.server or os.environ.get("NTFY_URL")
    username = os.environ.get("NTFY_USERNAME")
    password = os.environ.get("NTFY_PASSWORD")
    if not topic:
        print(
            f"ntfyme: NTFY_TOPIC not set in {ENV_FILE} or env (or pass --topic)",
            file=sys.stderr,
        )
        return 2
    if not server:
        print(
            f"ntfyme: NTFY_URL not set in {ENV_FILE} or env (or pass --server)",
            file=sys.stderr,
        )
        return 2

    exit_code, duration, tail = run_command(cmd, args.tail)

    if duration < args.min_duration:
        return exit_code

    hostname = socket.gethostname().split(".")[0]
    cmd_str = shlex.join(cmd)
    title = args.title or f"[{hostname}] {cmd_str}"

    if exit_code == 0:
        priority, tags, status = "default", ["white_check_mark"], "succeeded"
    else:
        priority, tags, status = "high", ["x"], f"failed (exit {exit_code})"
    if duration >= LONG_RUN_SECONDS:
        tags.append("hourglass")

    body = [f"{status} in {format_duration(duration)}"]
    if exit_code != 0 and tail:
        body += ["", "--- stderr tail ---", *tail]
    send_notification(
        server,
        topic,
        title,
        "\n".join(body),
        priority,
        tags,
        username=username,
        password=password,
    )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
