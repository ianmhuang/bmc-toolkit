"""Review acceptance tests for M13 (Sessions sharing one Library): the lock
a writing command holds (AC-1), its heartbeat and staleness (AC-2), the
busy path and --wait (AC-3), stale take-over (AC-4), readers waiting for an
extraction (AC-5), fetch re-evaluating after a wait (AC-6), the tables.json
merge (AC-7) and atomic single-file writes (AC-8).

Black-box through the CLI wherever the AC allows; the lock file is inspected
from inside a scripted download (the scripted client accepts a callable)
rather than through the lock module. Tests that need a real extraction skip
without pypdfium2; the table test also needs pdfplumber.
"""

import json
import os
import shutil
import socket
import threading
import time

import pytest

from bmc_toolkit.spec import lock as lock_mod
from bmc_toolkit.spec import render as render_mod
from bmc_toolkit.spec.cli import main
from bmc_toolkit.spec.library import Library
from tests.conftest import PDF_BYTES, ok

URL_133 = "https://example.test/DSP0236_1.3.3.pdf"
URL_132 = "https://example.test/DSP0236_1.3.2.pdf"
STARTED = "2026-09-05T00:00:00+00:00"


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def backdate(path, seconds):
    old = time.time() - seconds
    os.utime(path, (old, old))


def other_lock(vdir, command="extract DSP0236 1.3.3", pid=4242, age=0):
    """A lock file as another Session would leave it."""
    vdir.mkdir(parents=True, exist_ok=True)
    path = vdir / ".lock"
    path.write_text(
        json.dumps(
            {"pid": pid, "host": "elsewhere", "command": command, "started": STARTED}
        ),
        encoding="utf-8",
    )
    if age:
        backdate(path, age)
    return path


def hold_from_thread(vdir, seconds, body=None, command="other session"):
    """Hold ``vdir``'s lock from another thread for ``seconds``; ``body`` runs
    while the lock is held (what the other Session writes)."""
    ready = threading.Event()

    def holder():
        with lock_mod.Lock(vdir, command, wait=0):
            ready.set()
            if body is not None:
                body()
            time.sleep(seconds)

    thread = threading.Thread(target=holder, daemon=True)
    thread.start()
    assert ready.wait(5)
    return thread


def busy_line(vdir, command="extract DSP0236 1.3.3", pid=4242):
    return (
        f"busy: {vdir / '.lock'} is held by pid {pid} on host elsewhere "
        f"({command}, since {STARTED}); retry with --wait"
    )


@pytest.fixture
def vdir(library):
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


@pytest.fixture
def stored(catalog_file, library, scripted, capsys, vdir):
    """DSP0236 1.3.3 held (a fake PDF), not extracted."""
    scripted.responses[URL_133] = ok(PDF_BYTES)
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    scripted.calls.clear()
    return vdir


def extracted_version(catalog_file, library, scripted, tmp_path, capsys):
    """A one-page PDF fetched and extracted; skips without pypdfium2."""
    pytest.importorskip("pypdfium2")
    from tests import pdfgen

    pdf = pdfgen.write_pdf(
        tmp_path / "one.pdf", [pdfgen.plain_page(["1 Intro", "needle here"])]
    )
    scripted.responses[URL_133] = ok(pdf.read_bytes())
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    scripted.calls.clear()
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


# ----------------------------------------------------------------- AC-1


def test_fetch_holds_a_lock_while_it_writes_and_removes_it_after(
    catalog_file, scripted, capsys, vdir
):
    seen = {}

    def download():
        # The download runs inside the lock: the file is there, with the
        # holder record AC-1 names, and its holder is this process.
        path = vdir / ".lock"
        seen["exists"] = path.is_file()
        seen["record"] = json.loads(path.read_text(encoding="utf-8"))
        return ok(PDF_BYTES)

    scripted.responses[URL_133] = download
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    assert seen["exists"]
    record = seen["record"]
    assert record["pid"] == os.getpid()
    assert record["host"] == socket.gethostname()
    assert record["command"] == "fetch DSP0236 1.3.3"
    # ISO 8601 UTC: date, time and an explicit +00:00 offset
    assert record["started"].endswith("+00:00") and "T" in record["started"]
    assert not (vdir / ".lock").exists()
    assert (vdir / "meta.json").is_file() and (vdir / "original.pdf").is_file()


def test_lock_goes_away_when_the_download_fails(catalog_file, scripted, capsys, vdir):
    scripted.responses[URL_133] = OSError("no route")
    code, out = run(
        capsys, "--wait", "5", "fetch", "DSP0236", catalog_file=catalog_file
    )
    assert code == 2, out
    assert not (vdir / ".lock").exists()
    # nothing was written for this version: no half-made directory either
    assert not vdir.exists()


def test_add_holds_the_lock_of_the_version_directory(
    catalog_file, library, tmp_path, capsys, monkeypatch, vdir
):
    src = tmp_path / "mine.pdf"
    src.write_bytes(PDF_BYTES)
    seen = {}
    real_copy = shutil.copyfile

    def spying_copy(a, b, *args, **kwargs):
        seen["lock"] = (vdir / ".lock").is_file()
        return real_copy(a, b, *args, **kwargs)

    monkeypatch.setattr(shutil, "copyfile", spying_copy)
    code, out = run(
        capsys,
        "add",
        str(src),
        "--document",
        "DSP0236",
        "--version",
        "1.3.3",
        catalog_file=catalog_file,
    )
    assert code == 0, out
    assert seen["lock"] is True
    assert not (vdir / ".lock").exists()


def test_clone_meets_a_live_lock_on_the_repository_directory(
    catalog_file, library, capsys
):
    # The lock for a clone lives at code/<repo>/.lock (AC-1); a live one
    # stops the clone before any git or network activity (AC-3).
    rdir = library.root / "code" / "bmcweb"
    other_lock(rdir, command="clone bmcweb main", pid=7)
    code, out = run(capsys, "--wait", "0", "clone", "bmcweb", catalog_file=catalog_file)
    assert code == 3, out
    assert busy_line(rdir, command="clone bmcweb main", pid=7) in out.splitlines()
    assert sorted(p.name for p in rdir.iterdir()) == [".lock"]


# ----------------------------------------------------------------- AC-2


def test_heartbeat_refreshes_the_lock_mtime_at_the_module_interval(
    catalog_file, scripted, capsys, monkeypatch, vdir
):
    monkeypatch.setattr(lock_mod, "HEARTBEAT_SECONDS", 0.05)
    seen = {}

    def download():
        path = vdir / ".lock"
        backdate(path, 1000)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if time.time() - path.stat().st_mtime < 100:
                break
            time.sleep(0.02)
        seen["age"] = time.time() - path.stat().st_mtime
        return ok(PDF_BYTES)

    scripted.responses[URL_133] = download
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    assert seen["age"] < 100  # touched by the heartbeat while held


def test_liveness_is_the_mtime_never_the_pid(catalog_file, scripted, capsys, vdir):
    # A lock recorded by a pid that is very much alive (ours), but untouched
    # for longer than the stale age, is stale and taken over.
    other_lock(vdir, pid=os.getpid(), age=lock_mod.STALE_SECONDS + 1)
    scripted.responses[URL_133] = ok(PDF_BYTES)
    code, out = run(
        capsys, "--wait", "0", "fetch", "DSP0236", catalog_file=catalog_file
    )
    assert code == 0, out
    assert f"note: took over a stale lock from pid {os.getpid()} on host " in out
    # ... and a fresh lock recorded by a pid that does not exist is live
    other_lock(vdir, pid=4242)
    code, out = run(
        capsys, "--wait", "0", "extract", "DSP0236", catalog_file=catalog_file
    )
    assert code == 3, out
    assert (vdir / ".lock").is_file()


def test_a_lock_touched_just_under_the_stale_age_is_still_live(
    stored, catalog_file, capsys
):
    other_lock(stored, age=lock_mod.STALE_SECONDS - 5)
    code, out = run(
        capsys, "--wait", "0", "extract", "DSP0236", catalog_file=catalog_file
    )
    assert code == 3, out


# ----------------------------------------------------------------- AC-3


def test_busy_line_and_exit_3_without_writing(stored, catalog_file, capsys):
    other_lock(stored)
    before = sorted(p.name for p in stored.iterdir())
    code, out = run(
        capsys, "--wait", "0", "extract", "DSP0236", catalog_file=catalog_file
    )
    assert code == 3
    assert out.strip() == busy_line(stored)
    assert sorted(p.name for p in stored.iterdir()) == before


def test_add_on_a_locked_new_version_writes_nothing(
    catalog_file, library, tmp_path, capsys
):
    src = tmp_path / "mine.pdf"
    src.write_bytes(PDF_BYTES)
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.2"
    other_lock(vdir, command="add DSP0236 1.3.2")
    code, out = run(
        capsys,
        "--wait",
        "0",
        "add",
        str(src),
        "--document",
        "DSP0236",
        "--version",
        "1.3.2",
        catalog_file=catalog_file,
    )
    assert code == 3
    assert out.strip() == busy_line(vdir, command="add DSP0236 1.3.2")
    assert sorted(p.name for p in vdir.iterdir()) == [".lock"]


def test_wait_polls_and_gives_up_after_the_wait(stored, catalog_file, capsys):
    hold_from_thread(stored, 3)
    started = time.monotonic()
    code, out = run(
        capsys, "--wait", "0.5", "extract", "DSP0236", catalog_file=catalog_file
    )
    elapsed = time.monotonic() - started
    assert code == 3, out
    assert out.startswith(f"busy: {stored / '.lock'} is held by pid {os.getpid()} ")
    assert 0.5 <= elapsed < 2.5


def test_wait_long_enough_acquires_after_the_holder_leaves(
    catalog_file, library, tmp_path, capsys, vdir
):
    src = tmp_path / "mine.pdf"
    src.write_bytes(PDF_BYTES)
    hold_from_thread(vdir, 0.6)
    started = time.monotonic()
    code, out = run(
        capsys,
        "--wait",
        "10",
        "add",
        str(src),
        "--document",
        "DSP0236",
        "--version",
        "1.3.3",
        catalog_file=catalog_file,
    )
    assert code == 0, out
    assert time.monotonic() - started >= 0.5
    assert out.startswith("added DSP0236 1.3.3 as Drop-in")
    assert not (vdir / ".lock").exists()


def test_default_wait_is_60_and_negative_is_refused(catalog_file, capsys):
    assert lock_mod.DEFAULT_WAIT == 60
    code, out = run(capsys, "--wait", "-0.5", "library", catalog_file=catalog_file)
    assert code == 2
    assert out.strip() == "--wait takes a number of seconds, 0 or more"
    code, out = run(capsys, "--wait", "0", "library", catalog_file=catalog_file)
    assert code == 0


def test_extract_all_reports_busy_in_the_summary_and_exits_3(
    stored, catalog_file, capsys
):
    other_lock(stored)
    code, out = run(
        capsys, "--wait", "0", "extract", "--all", catalog_file=catalog_file
    )
    assert code == 3
    lines = out.splitlines()
    assert lines[0] == busy_line(stored)
    assert lines[-1] == "summary: extracted 0, skipped 0, failed 0, busy 1"


# ----------------------------------------------------------------- AC-4


def test_stale_lock_is_taken_over_with_a_note_and_no_wait(
    stored, catalog_file, scripted, capsys
):
    other_lock(stored, age=lock_mod.STALE_SECONDS + 1)
    scripted.responses[URL_133] = ok(PDF_BYTES)
    started = time.monotonic()
    code, out = run(
        capsys, "--wait", "30", "fetch", "DSP0236", catalog_file=catalog_file
    )
    assert time.monotonic() - started < 5
    assert code == 0, out
    assert (
        "note: took over a stale lock from pid 4242 on host elsewhere "
        f"(extract DSP0236 1.3.3, since {STARTED})"
    ) in out.splitlines()
    assert not (stored / ".lock").exists()


def test_stale_lock_over_a_half_written_extraction_is_redone(
    catalog_file, library, scripted, tmp_path, capsys
):
    # A crashed Session left extract.txt but no extract.json (the meta is
    # written last): the take-over extracts from scratch and the version
    # ends current.
    from bmc_toolkit.spec import extract as extract_mod

    vdir = extracted_version(catalog_file, library, scripted, tmp_path, capsys)
    (vdir / "extract.json").unlink()
    (vdir / "extract.txt").write_text("half", encoding="utf-8")
    other_lock(vdir, age=lock_mod.STALE_SECONDS + 1)
    code, out = run(
        capsys, "--wait", "0", "extract", "DSP0236", catalog_file=catalog_file
    )
    assert code == 0, out
    assert "note: took over a stale lock from pid 4242" in out
    assert "extracted DSP0236 1.3.3" in out
    assert extract_mod.is_current(vdir)
    assert "needle here" in (vdir / "extract.txt").read_text(encoding="utf-8")
    assert not (vdir / ".lock").exists()


def test_a_fetch_force_killed_after_the_original_is_replaced_is_redone(
    stored, catalog_file, scripted, capsys, monkeypatch
):
    # Round 2: "from scratch" for a replaced original means the old meta
    # must not survive over the new file. A fetch --force that dies after
    # the original landed but before meta.json is written leaves no
    # holding, so the next fetch downloads again instead of skipping.
    from bmc_toolkit.spec import library as library_mod

    old_meta = json.loads((stored / "meta.json").read_text(encoding="utf-8"))
    scripted.responses[URL_133] = ok(PDF_BYTES + b"\n%% second copy")

    def killed(*_args, **_kwargs):
        raise RuntimeError("killed while writing meta")

    # A separate MonkeyPatch: undoing the shared one would also undo the
    # library and scripted fixtures and send the rest of the test to the
    # real Library and network (author's fix, review round 2).
    temporary = pytest.MonkeyPatch()
    temporary.setattr(library_mod.Library, "write_meta", killed)
    with pytest.raises(RuntimeError):
        run(capsys, "fetch", "DSP0236", "--force", catalog_file=catalog_file)
    temporary.undo()
    capsys.readouterr()
    assert (stored / "original.pdf").read_bytes() == PDF_BYTES + b"\n%% second copy"
    assert not (stored / "meta.json").exists()  # no old meta over the new file
    assert not (stored / ".lock").exists()  # released although the body raised
    assert not list(stored.glob("*.part"))
    # status does not count it as a holding, and a plain fetch redoes it
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0 and "mctp\tDSP0236\t1.3.3" not in out
    scripted.responses[URL_133] = ok(PDF_BYTES + b"\n%% third copy")
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    assert "fetched DSP0236 1.3.3" in out
    meta = json.loads((stored / "meta.json").read_text(encoding="utf-8"))
    assert meta["sha256"] != old_meta["sha256"]
    assert (stored / "original.pdf").read_bytes() == PDF_BYTES + b"\n%% third copy"


def test_two_sessions_meeting_one_stale_lock_take_it_over_once(tmp_path):
    # Round 2 (F1): several Sessions that find the same stale lock at the
    # same moment must never both believe they hold it. Exactly one
    # take-over is reported, holds never overlap, and nothing is left
    # behind (no .lock, no take-over gate file).
    vdir = tmp_path / "v"
    other_lock(vdir, age=lock_mod.STALE_SECONDS + 1)
    takeovers = []
    holds = []
    gate = threading.Barrier(5)

    def session(name):
        gate.wait()
        with lock_mod.Lock(vdir, name, wait=15, on_takeover=takeovers.append):
            entered = time.monotonic()
            record = json.loads((vdir / ".lock").read_text(encoding="utf-8"))
            assert record["command"] == name  # the file is ours while we hold it
            time.sleep(0.15)
            holds.append((entered, time.monotonic(), name))

    threads = [threading.Thread(target=session, args=(f"s{i}",)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert not any(t.is_alive() for t in threads)
    assert [h.pid for h in takeovers] == [4242]
    assert len(holds) == 5
    holds.sort()
    for (_, left, _), (entered, _, _) in zip(holds, holds[1:], strict=False):
        assert left <= entered  # one holder at a time
    assert sorted(p.name for p in vdir.iterdir()) == []


def test_a_session_that_meets_a_take_over_in_progress_waits_for_the_winner(
    tmp_path,
):
    # Round 2 (F1): a gate file left by a Session mid take-over is respected
    # while fresh, and treated like a stale lock once it is old.
    vdir = tmp_path / "v"
    other_lock(vdir, age=lock_mod.STALE_SECONDS + 1)
    gate = vdir / ".lock.takeover"
    gate.write_bytes(b"")
    started = time.monotonic()
    with pytest.raises(lock_mod.Busy):
        lock_mod.Lock(vdir, "late", wait=0.4).acquire()
    assert time.monotonic() - started >= 0.3
    assert (vdir / ".lock").is_file()  # nobody removed the lock under the gate
    backdate(gate, lock_mod.STALE_SECONDS + 1)
    seen = []
    with lock_mod.Lock(vdir, "late", wait=5, on_takeover=seen.append):
        assert not gate.exists()
    assert [h.pid for h in seen] == [4242]
    assert sorted(p.name for p in vdir.iterdir()) == []


def test_a_lock_that_cannot_be_removed_is_reported_not_silent(
    stored, catalog_file, scripted, capsys, monkeypatch
):
    # Round 2 (F5): when the release cannot unlink its own lock (a Windows
    # sharing violation), the command still succeeds but says so, because
    # the user's next command will meet that lock and exit 3.
    from pathlib import Path

    lock = stored / ".lock"
    # A separate MonkeyPatch, see test_a_fetch_force_killed_after_... above
    # (author's fix, review round 2).
    temporary = pytest.MonkeyPatch()
    temporary.setattr(lock_mod, "RELEASE_RETRIES", 2)
    temporary.setattr(lock_mod, "RETRY_PAUSE", 0.01)
    real_unlink = Path.unlink

    def refusing_unlink(self, *args, **kwargs):
        if self == lock:
            raise PermissionError(13, "Access is denied")
        return real_unlink(self, *args, **kwargs)

    temporary.setattr(Path, "unlink", refusing_unlink)
    scripted.responses[URL_133] = ok(PDF_BYTES)
    code, out = run(capsys, "fetch", "DSP0236", "--force", catalog_file=catalog_file)
    temporary.undo()
    assert code == 0, out
    lines = out.splitlines()
    assert any(ln.startswith("fetched DSP0236 1.3.3") for ln in lines)
    note = [ln for ln in lines if ln.startswith("note: could not remove ")]
    assert len(note) == 1, out
    assert str(lock) in note[0] and "5 minutes" in note[0]
    assert lock.is_file()
    # the leftover is a live lock (our own pid) until it ages out
    code, out = run(
        capsys, "--wait", "0", "extract", "DSP0236", catalog_file=catalog_file
    )
    assert code == 3
    assert out.startswith(f"busy: {lock} is held by pid {os.getpid()} ")


# ----------------------------------------------------------------- AC-5


def test_readers_ignore_a_live_lock_when_the_version_is_current(
    catalog_file, library, scripted, tmp_path, capsys
):
    vdir = extracted_version(catalog_file, library, scripted, tmp_path, capsys)
    other_lock(vdir)
    for argv in (
        ["find", "DSP0236", "needle"],
        ["section", "DSP0236", "Intro"],
        ["page", "DSP0236", "1"],
    ):
        started = time.monotonic()
        code, out = run(capsys, "--wait", "30", *argv, catalog_file=catalog_file)
        assert code == 0, (argv, out)
        assert time.monotonic() - started < 5, argv
    assert (vdir / ".lock").is_file()  # never touched by a reader


def test_readers_meet_a_live_lock_on_an_unextracted_version(
    stored, catalog_file, capsys
):
    other_lock(stored)
    for argv in (
        ["find", "DSP0236", "x"],
        ["section", "DSP0236", "x"],
        ["page", "DSP0236", "1"],
        ["render", "DSP0236", "--page", "1"],
        ["table", "DSP0236", "--page", "1"],
    ):
        code, out = run(capsys, "--wait", "0", *argv, catalog_file=catalog_file)
        assert code == 3, (argv, out)
        assert out.strip() == busy_line(stored), argv
    assert sorted(p.name for p in stored.iterdir()) == [
        ".lock",
        "meta.json",
        "original.pdf",
    ]


def test_reader_after_the_wait_still_locked_exits_3(stored, catalog_file, capsys):
    hold_from_thread(stored, 3)
    started = time.monotonic()
    code, out = run(
        capsys, "--wait", "0.4", "find", "DSP0236", "x", catalog_file=catalog_file
    )
    assert code == 3, out
    assert time.monotonic() - started >= 0.4
    assert out.startswith("busy: ")


def test_reader_unlocked_and_still_not_current_gets_the_extract_hint(
    stored, catalog_file, capsys
):
    hold_from_thread(stored, 0.3)  # the other Session leaves without extracting
    code, out = run(
        capsys, "--wait", "10", "find", "DSP0236", "x", catalog_file=catalog_file
    )
    assert code == 2, out
    assert out.startswith("DSP0236 1.3.3 is not extracted")
    assert "run: bmcspec extract DSP0236" in out
    # a stale lock is not in the way either: no waiting, the same message
    other_lock(stored, age=lock_mod.STALE_SECONDS + 1)
    started = time.monotonic()
    code, out = run(
        capsys, "--wait", "30", "page", "DSP0236", "1", catalog_file=catalog_file
    )
    assert code == 2 and time.monotonic() - started < 5
    assert out.startswith("DSP0236 1.3.3 is not extracted")


def test_reader_waits_and_answers_once_the_extraction_lands(
    catalog_file, library, scripted, tmp_path, capsys
):
    vdir = extracted_version(catalog_file, library, scripted, tmp_path, capsys)
    meta = vdir / "extract.json"
    aside = tmp_path / "extract.json.aside"
    meta.rename(aside)  # in progress: no meta yet

    def finish_extraction():
        time.sleep(0.4)
        aside.rename(meta)

    hold_from_thread(vdir, 0, body=finish_extraction, command="extract DSP0236 1.3.3")
    code, out = run(
        capsys, "--wait", "10", "find", "DSP0236", "needle", catalog_file=catalog_file
    )
    assert code == 0, out
    assert "needle here" in out


def test_schema_and_registry_wait_for_the_bundle_extraction(
    catalog_file, library, scripted, capsys
):
    from tests.conftest import ZIP_BYTES

    scripted.responses["https://example.test/bundle_2026.1.zip"] = ok(
        ZIP_BYTES, "application/zip"
    )
    code, out = run(capsys, "fetch", "BUNDLE", catalog_file=catalog_file)
    assert code == 0, out
    vdir = library.specs / "mctp" / "BUNDLE" / "2026.1"
    other_lock(vdir, command="extract BUNDLE 2026.1")
    for cmd in ("schema", "registry"):
        code, out = run(capsys, "--wait", "0", cmd, "BUNDLE", catalog_file=catalog_file)
        assert code == 3, (cmd, out)
        assert out.strip() == busy_line(vdir, command="extract BUNDLE 2026.1")
    (vdir / ".lock").unlink()
    hold_from_thread(vdir, 0.3)
    code, out = run(
        capsys, "--wait", "10", "schema", "BUNDLE", catalog_file=catalog_file
    )
    assert code == 2 and "not extracted" in out


# ----------------------------------------------------------------- AC-6


def test_fetch_waits_for_the_other_download_and_skips_without_a_request(
    catalog_file, library, scripted, capsys, vdir
):
    # The other Session is downloading this very version: nothing is held
    # yet when we start, and its original lands before its lock goes.
    def other_download():
        time.sleep(0.4)
        library.store(
            "mctp", "DSP0236", "1.3.3", PDF_BYTES, "pdf", url=URL_133, method="direct"
        )

    hold_from_thread(vdir, 0, body=other_download, command="fetch DSP0236 1.3.3")
    scripted.responses[URL_133] = ok(PDF_BYTES)
    code, out = run(
        capsys, "--wait", "10", "fetch", "DSP0236", catalog_file=catalog_file
    )
    assert code == 0, out
    assert any(ln.startswith("skipped DSP0236 1.3.3") for ln in out.splitlines())
    assert scripted.calls == []  # no network request of our own
    assert not (vdir / ".lock").exists()


def test_fetch_all_counts_busy_and_makes_no_request_for_the_locked_one(
    catalog_file, library, scripted, capsys, vdir
):
    other_lock(vdir, command="fetch DSP0236 1.3.3")
    scripted.responses[URL_133] = ok(PDF_BYTES)
    # the other documents have no route here and fail: a failure outranks
    # busy in the exit code (2), the summary still counts the busy one
    code, out = run(capsys, "--wait", "0", "fetch", "--all", catalog_file=catalog_file)
    assert URL_133 not in scripted.calls
    assert busy_line(vdir, command="fetch DSP0236 1.3.3") in out.splitlines()
    assert out.splitlines()[-1].endswith(", busy 1")
    assert code == 2


# ----------------------------------------------------------------- AC-7


def test_table_merge_is_locked_and_keeps_both_pages(
    catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    pytest.importorskip("pdfplumber")
    from tests import pdfgen
    from tests.test_tables import HEADER, ROWS_1, ROWS_2, furniture, ruled_table

    page1 = furniture(1) + [(72, 740, "5 Codes"), (72, 714, "Table 1 - Codes")]
    page1 += ruled_table(72, 700, [100, 80, 200], [16] * 3, [HEADER, *ROWS_1])
    page2 = furniture(2) + [(72, 740, "6 More"), (72, 714, "Table 2 - More")]
    page2 += ruled_table(72, 700, [120, 60, 200], [16] * 3, [HEADER, *ROWS_2])
    pdf = pdfgen.write_pdf(tmp_path / "t.pdf", [page1, page2])
    scripted.responses[URL_133] = ok(pdf.read_bytes())
    assert run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)[0] == 0
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"

    # a live lock past the wait: exit 3, tables.json untouched
    other_lock(vdir, command="table DSP0236 page 2")
    code, out = run(
        capsys,
        "--wait",
        "0",
        "table",
        "DSP0236",
        "--page",
        "1",
        catalog_file=catalog_file,
    )
    assert code == 3 and out.strip() == busy_line(vdir, command="table DSP0236 page 2")
    assert not (vdir / "tables.json").exists()
    (vdir / ".lock").unlink()

    # the other Session's merge lands while we wait; ours merges on top
    def other_merge():
        from bmc_toolkit.spec import tables as tables_mod

        time.sleep(0.3)
        with tables_mod.Reader(vdir / "original.pdf") as reader:
            _, found, done = reader.read_page(2, section_of=lambda p, c: "-")
        tables_mod.store(vdir, done, found)

    hold_from_thread(vdir, 0, body=other_merge, command="table DSP0236 page 2")
    code, out = run(
        capsys,
        "--wait",
        "10",
        "table",
        "DSP0236",
        "--page",
        "1",
        catalog_file=catalog_file,
    )
    assert code == 0, out
    data = json.loads((vdir / "tables.json").read_text(encoding="utf-8"))
    assert data["pages_done"] == [1, 2]
    assert sorted(t["first"] for t in data["tables"]) == [1, 2]
    assert not list(vdir.glob("*.part"))


# ----------------------------------------------------------------- AC-8


def test_single_files_go_through_pid_token_part_names(
    catalog_file, scripted, capsys, monkeypatch, vdir
):
    renames = []
    real_replace = os.replace

    def recording_replace(src, dst, *args, **kwargs):
        renames.append((str(src), str(dst)))
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", recording_replace)
    scripted.responses[URL_133] = ok(PDF_BYTES)
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    targets = {os.path.basename(dst): os.path.basename(src) for src, dst in renames}
    assert {"original.pdf", "meta.json"} <= set(targets)
    for name in ("original.pdf", "meta.json"):
        tmp = targets[name]
        assert tmp.startswith(f"{name}.{os.getpid()}-") and tmp.endswith(".part")
        token = tmp[len(f"{name}.{os.getpid()}-") : -len(".part")]
        assert token and token.isalnum()
    assert not list(vdir.glob("*.part"))


def test_add_force_replaces_the_original_through_a_temp_name(
    stored, catalog_file, tmp_path, capsys, monkeypatch
):
    # Round 2 (F2): the Drop-in original is a single-file write like any
    # other: copied to <name>.<pid>-<token>.part and renamed into place,
    # never truncated and rewritten where a reader may have it open.
    src = tmp_path / "mine.pdf"
    src.write_bytes(PDF_BYTES + b"\n%% dropin")
    renames = []
    real_replace = os.replace

    def recording_replace(a, b, *args, **kwargs):
        renames.append((os.path.basename(str(a)), os.path.basename(str(b))))
        return real_replace(a, b, *args, **kwargs)

    monkeypatch.setattr(os, "replace", recording_replace)
    opened_for_write = []
    real_open = open

    def spying_open(file, mode="r", *args, **kwargs):
        if "w" in str(mode) and os.path.basename(str(file)) == "original.pdf":
            opened_for_write.append(file)
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", spying_open)
    code, out = run(
        capsys,
        "add",
        str(src),
        "--document",
        "DSP0236",
        "--version",
        "1.3.3",
        "--force",
        catalog_file=catalog_file,
    )
    monkeypatch.undo()
    assert code == 0, out
    assert out.startswith("replaced DSP0236 1.3.3 as Drop-in")
    assert opened_for_write == []  # the target itself is never written
    sources = [a for a, b in renames if b == "original.pdf"]
    assert len(sources) == 1
    assert sources[0].startswith(f"original.pdf.{os.getpid()}-")
    assert sources[0].endswith(".part")
    assert (stored / "original.pdf").read_bytes() == PDF_BYTES + b"\n%% dropin"
    assert not list(stored.glob("*.part"))
    meta = json.loads((stored / "meta.json").read_text(encoding="utf-8"))
    assert meta["dropin"] is True and meta["size"] == len(PDF_BYTES + b"\n%% dropin")


def test_two_writers_of_one_png_both_succeed_and_leave_one_valid_file(tmp_path):
    out = tmp_path / "renders" / "page-1.png"
    out.parent.mkdir()
    rows = [b"\x01\x02\x03" * 2] * 2
    errors = []
    start = threading.Barrier(4)

    def write():
        start.wait()
        try:
            for _ in range(40):
                render_mod.write_png(out, 2, 2, rows)
        except Exception as exc:  # noqa: BLE001 - any failure is the finding
            errors.append(exc)

    threads = [threading.Thread(target=write) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    png = out.read_bytes()
    assert png.startswith(b"\x89PNG\r\n\x1a\n") and png.endswith(b"IEND\xaeB`\x82")
    assert not list(out.parent.glob("*.part"))


def test_many_meta_writers_leave_one_valid_meta(tmp_path):
    library = Library(tmp_path / "lib")
    vdir = library.specs / "f" / "d" / "v"
    vdir.mkdir(parents=True)
    errors = []
    start = threading.Barrier(4)

    def write(n):
        start.wait()
        try:
            for i in range(40):
                library.write_meta(vdir, {"writer": n, "round": i, "pad": "x" * 2000})
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    data = json.loads((vdir / "meta.json").read_text(encoding="utf-8"))
    assert data["round"] == 39 and len(data["pad"]) == 2000
    assert not list(vdir.glob("*.part"))
