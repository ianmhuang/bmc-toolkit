"""Locks that let several Sessions share one Library.

A multi-file operation (storing an original, extracting, writing
``tables.json``, cloning a Code Tree) holds ``.lock`` in the directory it
writes. The file is created with ``O_EXCL`` and holds, for people to read,
the pid, host, command and start time of the holder.

Liveness is the file's mtime, never the pid: a daemon thread touches the
file every ``HEARTBEAT_SECONDS`` while the lock is held, and a lock untouched
for ``STALE_SECONDS`` is stale and may be taken over. Pids mean nothing
across Windows and WSL and are reused after a reboot.

Readers take no lock; when a version is not current they call
:func:`wait_while_locked` and try again. Standard library only.

Windows refuses to remove, rename or exclusively create a file another
process has open, even for a moment (a waiter reading the holder), with a
``PermissionError``; every such step here retries briefly instead of
failing, and a release that still cannot remove the file leaves it to age
out as stale rather than raise over the command's own result.
"""

import json
import os
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

LOCK_NAME = ".lock"
TAKEOVER_NAME = ".lock.takeover"  # whoever creates it may remove a stale .lock
HEARTBEAT_SECONDS = 30.0  # how often a holder touches its lock
STALE_SECONDS = 300.0  # untouched this long: the holder is presumed dead
POLL_SECONDS = 0.2  # how often a waiter looks again
DEFAULT_WAIT = 60  # seconds a command waits before exiting busy
RELEASE_RETRIES = 100  # unlink attempts on release, RETRY_PAUSE apart
RETRY_PAUSE = 0.05
MAX_MISSES = 20  # a lock file that keeps vanishing between two looks


@dataclass(frozen=True)
class Holder:
    """What a lock file says about its holder, plus how long ago it was touched."""

    path: Path
    pid: int | None
    host: str
    command: str
    started: str
    age: float  # seconds since the last heartbeat

    @property
    def stale(self) -> bool:
        return self.age > STALE_SECONDS

    def describe(self) -> str:
        pid = "?" if self.pid is None else str(self.pid)
        return f"pid {pid} on host {self.host} ({self.command}, since {self.started})"


class Busy(Exception):
    """A live lock is in the way after the wait ran out."""

    def __init__(self, holder: Holder):
        self.holder = holder
        super().__init__(
            f"busy: {holder.path} is held by {holder.describe()}; retry with --wait"
        )


def read_holder(path: Path) -> Holder | None:
    """The holder recorded in a lock file, or None when there is no file.

    A file that cannot be parsed still counts as a lock (its mtime decides
    whether it is live); its fields read as unknown.
    """
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    pid = data.get("pid")
    return Holder(
        path=path,
        pid=pid if isinstance(pid, int) else None,
        host=str(data.get("host", "?")),
        command=str(data.get("command", "?")),
        started=str(data.get("started", "?")),
        age=max(0.0, time.time() - mtime),
    )


def locks_under(root: Path) -> list[Holder]:
    """Every lock in a Library: the root (``notes record``), version
    directories and Code Tree repositories."""
    found = []
    if (root / LOCK_NAME).is_file():
        found.append(root / LOCK_NAME)
    specs = root / "specs"
    if specs.is_dir():
        found += sorted(specs.glob("*/*/*/" + LOCK_NAME))
    code = root / "code"
    if code.is_dir():
        found += sorted(code.glob("*/" + LOCK_NAME))
    holders = [read_holder(p) for p in found]
    return [h for h in holders if h is not None]


def live_holder(directory: Path) -> Holder | None:
    """The live holder of ``directory``'s lock, or None (no lock, or stale)."""
    holder = read_holder(Path(directory) / LOCK_NAME)
    if holder is None or holder.stale:
        return None
    return holder


def wait_while_locked(directory: Path, wait: float) -> Holder | None:
    """Wait up to ``wait`` seconds for a live lock on ``directory`` to go
    away; returns the holder still in the way, or None when the way is clear."""
    deadline = time.monotonic() + max(0.0, wait)
    while True:
        holder = live_holder(directory)
        if holder is None:
            return None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return holder
        time.sleep(min(POLL_SECONDS, remaining))


def _unlink_retrying(path: Path) -> str:
    """Remove ``path``, riding out Windows sharing violations: ``removed``,
    ``missing`` (someone else did), or ``stuck`` after RELEASE_RETRIES."""
    for attempt in range(RELEASE_RETRIES):
        try:
            path.unlink()
        except FileNotFoundError:
            return "missing"
        except PermissionError:
            if attempt == RELEASE_RETRIES - 1:
                return "stuck"
            time.sleep(RETRY_PAUSE)
        else:
            return "removed"
    return "stuck"


def remove_stale_lock(
    path: Path, on_takeover: Callable[[Holder], None] | None = None
) -> str:
    """Remove the lock at ``path`` if it is stale, so that no process ever
    removes a fresh one; the one protocol both ``Lock.acquire`` and ``prune``
    use.

    Only the process that created ``.lock.takeover`` (O_EXCL) beside it may
    remove the lock, and it re-reads the lock inside that section: while the
    stale file exists nobody can create a fresh one (O_EXCL fails), and only
    this section removes it, so what it removes is what it read. A takeover
    file older than STALE_SECONDS (its owner died inside the section) is
    removed like a stale lock.

    Returns ``removed`` (``on_takeover`` was called with the old holder),
    ``gone`` (no lock there any more), ``fresh`` (the lock is live: someone
    took it over), ``busy`` (another process is inside the section right
    now) or ``stuck`` (the file could not be removed).
    """
    gate = path.with_name(TAKEOVER_NAME)
    for _attempt in range(3):
        try:
            fd = os.open(gate, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError:
            other = read_holder(gate)
            if other is not None and other.stale:
                _unlink_retrying(gate)
                continue  # the section's owner died: try the gate again
            return "busy"
        break
    else:
        return "busy"
    os.close(fd)
    try:
        current = read_holder(path)
        if current is None:
            return "gone"
        if not current.stale:
            return "fresh"
        outcome = _unlink_retrying(path)
        if outcome == "missing":
            return "gone"  # vanished between the re-read and the unlink
        if outcome == "stuck":
            return "stuck"
        if on_takeover is not None:
            on_takeover(current)
        return "removed"
    finally:
        _unlink_retrying(gate)


def _unknown_holder(path: Path) -> Holder:
    """For a lock file that vanished or could not be read at the deadline."""
    return Holder(path=path, pid=None, host="?", command="?", started="?", age=0.0)


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class Lock:
    """Hold ``<directory>/.lock`` for the duration of a ``with`` block.

    ``acquire`` waits up to ``wait`` seconds for a live lock, takes over a
    stale one (calling ``on_takeover`` with the old holder), and raises
    :class:`Busy` when the wait runs out.
    """

    def __init__(
        self,
        directory: Path,
        command: str,
        *,
        wait: float = DEFAULT_WAIT,
        heartbeat: float | None = None,
        on_takeover: Callable[[Holder], None] | None = None,
        on_leftover: Callable[[Path], None] | None = None,
    ):
        self.directory = Path(directory)
        self.path = self.directory / LOCK_NAME
        self.command = command
        self.wait = wait
        self.heartbeat = HEARTBEAT_SECONDS if heartbeat is None else heartbeat
        self.on_takeover = on_takeover
        self.on_leftover = on_leftover
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._created_dir = False
        self.held = False

    def acquire(self) -> "Lock":
        self._created_dir = not self.directory.exists()
        self.directory.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + max(0.0, self.wait)
        misses = 0  # the file was there for os.open but gone for read_holder
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileNotFoundError:
                # The directory went away (a releasing Session removed it
                # because it was empty): make it again.
                self.directory.mkdir(parents=True, exist_ok=True)
                continue
            except (FileExistsError, PermissionError):
                # Held, or (Windows) being created, read or removed right now.
                holder = read_holder(self.path)
                if holder is None:
                    misses += 1
                    if misses > MAX_MISSES:
                        raise Busy(_unknown_holder(self.path)) from None
                    time.sleep(RETRY_PAUSE)
                    continue
                misses = 0
                if holder.stale:
                    if self._take_over():
                        continue  # progress was made: try the create again
                    # Another Session is mid take-over (its gate is fresh) or
                    # has just won: keep trying, but not past the deadline.
                    current = read_holder(self.path)
                    if time.monotonic() < deadline or current is None:
                        continue
                    raise Busy(current) from None  # whoever holds it now
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Busy(holder) from None
                time.sleep(min(POLL_SECONDS, remaining))
                continue
            record = {
                "pid": os.getpid(),
                "host": socket.gethostname(),
                "command": self.command,
                "started": _now_iso(),
            }
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                json.dump(record, fh, indent=4, sort_keys=True)
                fh.write("\n")
            self.held = True
            self._stop.clear()
            self._thread = threading.Thread(target=self._beat, daemon=True)
            self._thread.start()
            return self

    def _take_over(self) -> bool:
        """Try to remove the stale lock through :func:`remove_stale_lock`.
        True when the create can be tried again at once (the lock was removed
        or is gone), False when it is fresh, stuck, or another Session is
        inside the take-over section (a short pause, then the caller decides
        by its deadline)."""
        outcome = remove_stale_lock(self.path, self.on_takeover)
        if outcome in ("removed", "gone"):
            return True
        if outcome == "busy":
            time.sleep(RETRY_PAUSE)
        return False

    def _beat(self) -> None:
        while not self._stop.wait(self.heartbeat):
            try:
                os.utime(self.path, None)
            except OSError:
                pass  # the file is gone or unreachable: nothing to do

    def release(self) -> None:
        if not self.held:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        self.held = False
        if _unlink_retrying(self.path) == "stuck":
            # A waiter keeps it open: it ages out as stale.
            if self.on_leftover is not None:
                self.on_leftover(self.path)
            return
        if self._created_dir:
            try:
                os.rmdir(self.directory)  # only when nothing was written
            except OSError:
                pass

    def __enter__(self) -> "Lock":
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()
