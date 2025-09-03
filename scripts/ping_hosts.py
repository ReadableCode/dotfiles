# %%
# Imports #


import asyncio
import json
import os
import platform
import time

import pandas as pd
from config_scripts import parent_dir  # noqa: F401
from src.utils.display_tools import pprint_df

# %%
# Functions #


def _ping_cmd(target: str, timeout_s: float = 1.0):
    is_win = platform.system().lower().startswith("win")
    if is_win:
        # Windows: -n count, -w timeout(ms)
        return ["ping", "-n", "1", "-w", str(int(timeout_s * 1000)), target]
    else:
        # Linux/macOS: -c count, -W timeout(s)
        return ["ping", "-c", "1", "-W", str(int(timeout_s)), target]


async def _ping_one(name: str, meta: dict, target: str, timeout_s: float):
    t0 = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            *_ping_cmd(target, timeout_s),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        rc = await proc.wait()
        ok = rc == 0
    except Exception:
        ok = False
    dt = time.time() - t0
    return {
        "alias": name,
        "category": meta["category"],
        "username": meta["username"],
        "hostname": meta["hostname"],
        "target": target,
        "reachable": ok,
        "elapsed_s": round(dt, 3),
        "ts": pd.Timestamp.utcnow(),
    }


async def stream_ping_df(hosts, timeout_s: float = 1.0):
    """
    Async generator: yields a pandas.DataFrame that grows in real time
    as hosts finish pinging.
    """
    tasks = []
    for name, meta in hosts.items():
        for target in meta["ips"]:
            tasks.append(_ping_one(name, meta, target, timeout_s))

    results = []
    for coro in asyncio.as_completed(tasks):
        row = await coro
        results.append(row)
        yield pd.DataFrame(results).sort_values(
            ["category", "alias", "target"]
        ).reset_index(drop=True)


def ping_all_now(hosts, timeout_s: float = 1.0):
    """
    Convenience wrapper for synchronous scripts: iterates the stream and
    prints the DataFrame each time a result arrives. Returns the final DataFrame.
    """

    async def _run():
        latest = None
        async for df in stream_ping_df(hosts, timeout_s):
            print("\n--- update ---")
            pprint_df(df)
            latest = df
        return latest

    return asyncio.run(_run())


# %%
# Main #


if __name__ == "__main__":
    with open(os.path.join(parent_dir, "hosts.json"), "r") as f:
        HOSTS = json.load(f)

    final_df = ping_all_now(hosts=HOSTS, timeout_s=1.0)

# %%
