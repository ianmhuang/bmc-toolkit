"""The lock module: creation, heartbeat, staleness, busy, and listing
(AC-1 to AC-4 at the module level; the CLI paths are in test_lock_cli.py)."""

import json
import os
import socket
import threading
import time

import pytest

from bmc_toolkit.spec import lock as lock_mod
from bmc_toolkit.spec.lock import Busy, Lock, read_holder


def backdate(path, seconds):
    old = time.time() - seconds
    os.utime(path, (old, old))


def fake_lock(directory, pid=4242, host="elsewhere", command="extract X 1", age=0):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / lock_mod.LOCK_NAME
    path.write_text(
        json.dumps(
            {
                "pid": pid,
                "host": host,
                "command": command,
                "started": "2026-09-05T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    if age:
        backdate(path, age)
    return path


# ----------------------------------------------------------------- AC-1


def test_lock_file_records_the_holder_and_goes_away(tmp_path):
    vdir = tmp_path / "v"
    with Lock(vdir, "extract DSP0236 1.3.3", wait=0) as lock:
        assert lock.held
        data = json.loads(lock.path.read_text(encoding="utf-8"))
        assert data["pid"] == os.getpid()
        assert data["host"] == socket.gethostname()
        assert data["command"] == "extract DSP0236 1.3.3"
        assert data["started"].endswith("+00:00")
    assert not lock.path.exists()
    assert not lock.held


def test_lock_goes_away_when_the_body_raises(tmp_path):
    vdir = tmp_path / "v"
    with pytest.raises(RuntimeError):
        with Lock(vdir, "extract", wait=0):
            raise RuntimeError("boom")
    assert not (vdir / ".lock").exists()


def test_lock_creates_the_directory_it_guards(tmp_path):
    vdir = tmp_path / "a" / "b"
    with Lock(vdir, "fetch", wait=0):
        assert vdir.is_dir()


# ----------------------------------------------------------------- AC-2


def test_heartbeat_refreshes_the_mtime(tmp_path):
    vdir = tmp_path / "v"
    with Lock(vdir, "extract", wait=0, heartbeat=0.05) as lock:
        backdate(lock.path, 1000)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if read_holder(lock.path).age < 100:
                break
            time.sleep(0.02)
        assert read_holder(lock.path).age < 100


def test_staleness_is_mtime_not_pid(tmp_path):
    path = fake_lock(tmp_path / "v", pid=os.getpid())  # our own live pid
    assert not read_holder(path).stale
    backdate(path, lock_mod.STALE_SECONDS + 1)
    assert read_holder(path).stale
    assert read_holder(path).pid == os.getpid()


# ----------------------------------------------------------------- AC-3


def test_live_lock_raises_busy_after_the_wait(tmp_path):
    vdir = tmp_path / "v"
    fake_lock(vdir)
    started = time.monotonic()
    with pytest.raises(Busy) as info:
        Lock(vdir, "extract", wait=0.3).acquire()
    assert time.monotonic() - started >= 0.25
    message = str(info.value)
    assert message.startswith(
        f"busy: {vdir / '.lock'} is held by pid 4242 on host elsewhere "
    )
    assert "(extract X 1, since 2026-09-05T00:00:00+00:00)" in message
    assert message.endswith("; retry with --wait")
    assert (vdir / ".lock").read_text(encoding="utf-8")  # untouched


def test_wait_zero_returns_at_once(tmp_path):
    vdir = tmp_path / "v"
    fake_lock(vdir)
    started = time.monotonic()
    with pytest.raises(Busy):
        Lock(vdir, "extract", wait=0).acquire()
    assert time.monotonic() - started < 1


def test_a_lock_released_during_the_wait_is_acquired(tmp_path):
    vdir = tmp_path / "v"
    first = Lock(vdir, "first", wait=0).acquire()
    threading.Timer(0.3, first.release).start()
    with Lock(vdir, "second", wait=5) as second:
        assert json.loads(second.path.read_text("utf-8"))["command"] == "second"


def test_wait_while_locked_reports_the_holder_or_the_clear_way(tmp_path):
    vdir = tmp_path / "v"
    assert lock_mod.wait_while_locked(vdir, 0) is None  # no lock at all
    fake_lock(vdir)
    holder = lock_mod.wait_while_locked(vdir, 0)
    assert holder is not None and holder.pid == 4242
    fake_lock(vdir, age=lock_mod.STALE_SECONDS + 1)
    assert lock_mod.wait_while_locked(vdir, 0) is None  # stale: not in the way
    first = Lock(vdir, "first", wait=0).acquire()
    threading.Timer(0.3, first.release).start()
    assert lock_mod.wait_while_locked(vdir, 5) is None


# ----------------------------------------------------------------- AC-4


def test_stale_lock_is_taken_over_and_reported(tmp_path):
    vdir = tmp_path / "v"
    fake_lock(vdir, age=lock_mod.STALE_SECONDS + 1)
    seen = []
    started = time.monotonic()
    with Lock(vdir, "extract", wait=0, on_takeover=seen.append) as lock:
        assert time.monotonic() - started < 1
        assert json.loads(lock.path.read_text("utf-8"))["pid"] == os.getpid()
    assert [h.pid for h in seen] == [4242]
    assert seen[0].describe() == (
        "pid 4242 on host elsewhere (extract X 1, since 2026-09-05T00:00:00+00:00)"
    )


def test_unparsable_lock_file_still_counts_by_its_mtime(tmp_path):
    vdir = tmp_path / "v"
    vdir.mkdir()
    path = vdir / ".lock"
    path.write_bytes(b"\x00garbage")
    holder = read_holder(path)
    assert holder.pid is None and holder.host == "?" and not holder.stale
    assert holder.describe().startswith("pid ? on host ? (?, since ?)")
    with pytest.raises(Busy):
        Lock(vdir, "x", wait=0).acquire()
    backdate(path, lock_mod.STALE_SECONDS + 1)
    with Lock(vdir, "x", wait=0):
        pass


# -------------------------------------------------------------- listing


def test_locks_under_finds_version_and_repository_locks(tmp_path):
    root = tmp_path / "lib"
    a = fake_lock(root / "specs" / "mctp" / "DSP0236" / "1.3.3", command="extract")
    b = fake_lock(
        root / "code" / "bmcweb", command="clone", age=lock_mod.STALE_SECONDS + 1
    )
    (root / "specs" / "mctp" / "DSP0236" / ".lock").write_text("wrong depth", "utf-8")
    holders = lock_mod.locks_under(root)
    assert [h.path for h in holders] == [a, b]
    assert [h.stale for h in holders] == [False, True]
    assert lock_mod.locks_under(tmp_path / "nowhere") == []
