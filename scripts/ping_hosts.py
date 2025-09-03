# %%
# Imports #


import asyncio
import platform
import time

import config_scripts  # noqa: F401
import pandas as pd
from src.utils.display_tools import pprint_df

# %%

HOSTS = {
    # Workstations
    "ryzenwhite": {
        "username": "jason",
        "hostname": "192.168.86.94",
        "ips": ["192.168.86.94"],
        "category": "Workstations",
    },
    "spectre": {
        "username": "jason",
        "hostname": "Spectre",
        "ips": ["Spectre"],
        "category": "Workstations",
    },
    "zephyrus": {
        "username": "jason",
        "hostname": "JasonZephyrus",
        "ips": ["JasonZephyrus"],
        "category": "Workstations",
    },
    "mac": {
        "username": "jason",
        "hostname": "MacbookPro12",
        "ips": ["MacbookPro12"],
        "category": "Workstations",
    },
    # Upstairs Rack
    "elite": {
        "username": "jason",
        "hostname": "192.168.86.179",
        "ips": ["192.168.86.179"],
        "category": "Upstairs Rack",
    },
    "nuk": {
        "username": "jason",
        "hostname": "nukbuntu",
        "ips": ["nukbuntu"],
        "category": "Upstairs Rack",
    },
    "opti": {
        "username": "jason",
        "hostname": "Optiplex9020",
        "ips": ["Optiplex9020"],
        "category": "Upstairs Rack",
    },
    "pav5": {
        "username": "jason",
        "hostname": "Pavilioni5",
        "ips": ["Pavilioni5"],
        "category": "Upstairs Rack",
    },
    # Servers
    "behemoth": {
        "username": "root",
        "hostname": "192.168.86.31",
        "ips": ["192.168.86.31"],
        "category": "Servers",
    },
    # Appliances
    "pi4": {
        "username": "pi",
        "hostname": "raspberrypi4",
        "ips": ["raspberrypi4"],
        "category": "Appliances",
    },
    "pi4a": {
        "username": "pi",
        "hostname": "raspberrypi4a",
        "ips": ["raspberrypi4a"],
        "category": "Appliances",
    },
    "pi3": {
        "username": "pi",
        "hostname": "raspberrypi3",
        "ips": ["raspberrypi3"],
        "category": "Appliances",
    },
    "pi3a": {
        "username": "pi",
        "hostname": "raspberrypi3a",
        "ips": ["raspberrypi3a"],
        "category": "Appliances",
    },
    "pi0": {
        "username": "pi",
        "hostname": "raspberrypi0",
        "ips": ["raspberrypi0"],
        "category": "Appliances",
    },
    # Rebeca
    "shelly": {
        "username": "rebeca",
        "hostname": "Shelly",
        "ips": ["Shelly"],
        "category": "Rebeca",
    },
    # HelloFresh
    "hello": {
        "username": "jason",
        "hostname": "192.168.86.4",
        "ips": ["192.168.86.4"],
        "category": "HelloFresh",
    },
    "hellowin": {
        "username": r"HELLOFRESH\16937827583938060798",
        "hostname": "HelloFreshWindows",
        "ips": ["HelloFreshWindows"],
        "category": "HelloFresh",
    },
    # Fourteen Foods
    "ff14": {
        "username": "jason.christiansen",
        "hostname": "192.168.86.126",
        "ips": ["192.168.86.126"],
        "category": "Fourteen Foods",
    },
    # Android
    "tabs7p": {
        "username": "u0_a1053",
        "hostname": "GalaxyTabS7P",
        "ips": ["GalaxyTabS7P"],
        "category": "Android",
    },
}


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


async def stream_ping_df(hosts: dict = HOSTS, timeout_s: float = 1.0):
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


def ping_all_now(hosts: dict = HOSTS, timeout_s: float = 1.0):
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
    final_df = ping_all_now(timeout_s=1.0)

# %%
