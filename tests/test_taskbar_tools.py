# %%
# Imports #

import os

import config_test_utils  # noqa F401
import pytest

from utils import taskbar_tools

# %%
# Helpers #


def pin(directory, name, text="lnk"):
    os.makedirs(str(directory), exist_ok=True)
    path = os.path.join(str(directory), name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


@pytest.fixture
def taskbar(tmp_path):
    """A pinned folder with two pins and one file that is not a pin."""
    pins = tmp_path / "TaskBar"
    pin(pins, "Claude.lnk", "claude")
    pin(pins, "Etcher.lnk", "etcher")
    pin(pins, "desktop.ini", "not a pin")
    return str(pins)


def saved(taskbar, tmp_path):
    values = {"Favorites": (b"\x00\x01", 3)}
    return taskbar_tools.snapshot(str(tmp_path / "saved"), directory=taskbar, read=lambda: values)


# %%
# Snapshot #


def test_a_snapshot_copies_the_pins_and_reads_the_registry_values(taskbar, tmp_path):
    snap = saved(taskbar, tmp_path)
    assert taskbar_tools.pinned(snap.directory) == ["Claude.lnk", "Etcher.lnk"]
    assert snap.values == {"Favorites": (b"\x00\x01", 3)}


def test_a_machine_with_no_pinned_folder_snapshots_nothing(tmp_path):
    snap = taskbar_tools.snapshot(str(tmp_path / "saved"), directory=str(tmp_path / "absent"), read=lambda: {})
    assert taskbar_tools.pinned(snap.directory) == []
    assert taskbar_tools.lost_pins(snap, directory=str(tmp_path / "absent")) == []


def test_nothing_is_lost_while_every_pin_is_still_there(taskbar, tmp_path):
    assert taskbar_tools.lost_pins(saved(taskbar, tmp_path), directory=taskbar) == []


def test_a_pin_the_uninstall_removed_is_lost(taskbar, tmp_path):
    snap = saved(taskbar, tmp_path)
    os.remove(os.path.join(taskbar, "Claude.lnk"))
    assert taskbar_tools.lost_pins(snap, directory=taskbar) == ["Claude.lnk"]


# %%
# Restore #


def test_a_lost_pin_comes_back_only_when_its_target_exists_again(taskbar, tmp_path):
    snap = saved(taskbar, tmp_path)
    os.remove(os.path.join(taskbar, "Claude.lnk"))
    os.remove(os.path.join(taskbar, "Etcher.lnk"))
    targets = {
        os.path.join(snap.directory, "Claude.lnk"): "C:/apps/claude.exe",
        os.path.join(snap.directory, "Etcher.lnk"): "C:/old/etcher.exe",
    }
    back, gone = taskbar_tools.restorable(
        snap,
        directory=taskbar,
        targets=lambda paths: {path: targets[path] for path in paths},
        exists=lambda target: target == "C:/apps/claude.exe",
    )
    assert back == ["Claude.lnk"]
    assert gone == ["Etcher.lnk"]


def test_a_pin_whose_target_cannot_be_read_is_not_restored(taskbar, tmp_path):
    snap = saved(taskbar, tmp_path)
    os.remove(os.path.join(taskbar, "Claude.lnk"))
    back, gone = taskbar_tools.restorable(snap, directory=taskbar, targets=lambda paths: {}, exists=lambda t: True)
    assert back == [] and gone == ["Claude.lnk"]


def test_restore_puts_back_the_pin_and_the_values_then_restarts_explorer(taskbar, tmp_path):
    snap = saved(taskbar, tmp_path)
    os.remove(os.path.join(taskbar, "Claude.lnk"))
    pin(taskbar, "Etcher.lnk", "changed since the snapshot")
    done = []
    taskbar_tools.restore(
        snap,
        ["Claude.lnk"],
        directory=taskbar,
        write=lambda values: done.append(("write", values)),
        restart=lambda: done.append(("restart",)),
    )
    assert open(os.path.join(taskbar, "Claude.lnk"), encoding="utf-8").read() == "claude"
    # a pin that was never lost is left exactly as it is
    assert open(os.path.join(taskbar, "Etcher.lnk"), encoding="utf-8").read() == "changed since the snapshot"
    assert done == [("write", {"Favorites": (b"\x00\x01", 3)}), ("restart",)]


def test_restoring_nothing_touches_nothing(taskbar, tmp_path):
    snap = saved(taskbar, tmp_path)
    taskbar_tools.restore(
        snap,
        [],
        directory=taskbar,
        write=lambda values: pytest.fail("wrote the registry"),
        restart=lambda: pytest.fail("restarted explorer"),
    )


def test_link_targets_reads_one_target_per_line():
    class Done:
        stdout = "C:\\saved\\Claude.lnk|C:\\apps\\claude.exe\nC:\\saved\\Etcher.lnk|\n"

    targets = taskbar_tools.link_targets(["C:\\saved\\Claude.lnk"], run=lambda argv, **kwargs: Done())
    assert targets == {"C:\\saved\\Claude.lnk": "C:\\apps\\claude.exe", "C:\\saved\\Etcher.lnk": ""}


# %%
# Explorer #


def test_explorer_is_left_to_come_back_by_itself():
    ran = []
    ok = taskbar_tools.restart_explorer(
        run=lambda argv, **kwargs: ran.append(argv[-1]),
        start=lambda: pytest.fail("started explorer by hand"),
        sleep=lambda seconds: None,
        running=lambda run: True,
    )
    assert ok and ran == ["Stop-Process -Name explorer -Force"]


def test_explorer_is_started_when_it_does_not_come_back():
    started = []
    ok = taskbar_tools.restart_explorer(
        run=lambda argv, **kwargs: None,
        start=lambda: started.append(True),
        wait=2.0,
        sleep=lambda seconds: None,
        running=lambda run: False,
    )
    assert not ok and started == [True]
