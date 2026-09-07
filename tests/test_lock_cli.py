"""Locks through the CLI: busy and take-over paths of the writing commands,
readers waiting for an extraction, status and prune, atomic single-file
writes, and the SessionStart hook (AC-3 to AC-11)."""

import json
import os
import threading
import time
import zlib
from pathlib import Path

import pytest

from bmc_toolkit.spec import lock as lock_mod
from bmc_toolkit.spec import render as render_mod
from bmc_toolkit.spec.cli import main
from bmc_toolkit.spec.lock import Lock
from tests.conftest import PDF_BYTES, ZIP_BYTES, ok
from tests.test_lock import backdate, fake_lock

URL = "https://example.test/DSP0236_1.3.3.pdf"
ZIP_URL = "https://example.test/bundle_2026.1.zip"


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


@pytest.fixture
def stored(catalog_file, library, scripted, capsys):
    """DSP0236 1.3.3 fetched (a fake PDF), not extracted."""
    scripted.responses[URL] = ok(PDF_BYTES)
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    scripted.calls.clear()
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


def hold(vdir, seconds, command="other session"):
    """Hold the directory's lock from a thread for ``seconds``; returns when held."""
    ready = threading.Event()

    def body():
        with Lock(vdir, command, wait=0):
            ready.set()
            time.sleep(seconds)

    threading.Thread(target=body, daemon=True).start()
    assert ready.wait(5)


# ----------------------------------------------------------- AC-3, AC-4


def test_extract_meets_a_live_lock_and_exits_3(stored, catalog_file, capsys):
    fake_lock(stored, command="extract DSP0236 1.3.3")
    code, out = run(
        capsys, "--wait", "0", "extract", "DSP0236", catalog_file=catalog_file
    )
    assert code == 3
    assert out.strip() == (
        f"busy: {stored / '.lock'} is held by pid 4242 on host elsewhere "
        "(extract DSP0236 1.3.3, since 2026-09-05T00:00:00+00:00); retry with --wait"
    )
    assert not (stored / "extract.txt").exists()
    assert (stored / ".lock").exists()  # the other Session's lock is left alone


def test_extract_all_counts_busy_and_exits_3(stored, catalog_file, capsys):
    fake_lock(stored)
    code, out = run(
        capsys, "--wait", "0", "extract", "--all", catalog_file=catalog_file
    )
    assert code == 3
    assert out.splitlines()[-1] == "summary: extracted 0, skipped 0, failed 0, busy 1"


def test_add_meets_a_live_lock_and_exits_3(catalog_file, library, tmp_path, capsys):
    src = tmp_path / "mine.pdf"
    src.write_bytes(PDF_BYTES)
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.2"
    fake_lock(vdir, command="add DSP0236 1.3.2")
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
    assert code == 3 and out.startswith("busy: ")
    assert not (vdir / "meta.json").exists()


def test_fetch_meets_a_live_lock_and_exits_3_without_a_request(
    catalog_file, library, scripted, capsys
):
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    fake_lock(vdir, command="fetch DSP0236 1.3.3")
    scripted.responses[URL] = ok(PDF_BYTES)
    code, out = run(
        capsys, "--wait", "0", "fetch", "DSP0236", catalog_file=catalog_file
    )
    assert code == 3 and "busy: " in out
    assert scripted.calls == []
    # --all: the other documents have no route here and fail, and a failure
    # outranks busy in the exit code; the summary still counts the busy one.
    code, out = run(capsys, "--wait", "0", "fetch", "--all", catalog_file=catalog_file)
    assert code == 2
    assert out.splitlines()[-1].endswith(", busy 1")
    assert URL not in scripted.calls


def test_stale_lock_is_taken_over_with_a_note(stored, catalog_file, scripted, capsys):
    fake_lock(stored, command="extract DSP0236 1.3.3", age=lock_mod.STALE_SECONDS + 1)
    scripted.responses[URL] = ok(PDF_BYTES)
    started = time.monotonic()
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert time.monotonic() - started < 5  # no waiting on a stale lock
    assert code == 0, out
    lines = out.splitlines()
    assert (
        "note: took over a stale lock from pid 4242 on host elsewhere "
        "(extract DSP0236 1.3.3, since 2026-09-05T00:00:00+00:00)"
    ) in lines
    assert any(ln.startswith("skipped DSP0236 1.3.3") for ln in lines)
    assert not (stored / ".lock").exists()


def test_negative_wait_is_refused(catalog_file, capsys):
    code, out = run(capsys, "--wait", "-1", "status", catalog_file=catalog_file)
    assert code == 2 and out.strip() == "--wait takes a number of seconds, 0 or more"


# ----------------------------------------------------------------- AC-6


def test_add_decides_existing_inside_the_lock(stored, catalog_file, tmp_path, capsys):
    # Validation of review round 4: another Session's add has taken meta.json
    # away for the moment; a Session that waits must see the finished holding
    # (refuse without --force, say "replaced" with it), not "added".
    from bmc_toolkit.spec.library import Library

    library = Library(stored.parents[3])
    src = tmp_path / "mine.pdf"
    src.write_bytes(PDF_BYTES + b"\nmine")
    meta = stored / "meta.json"
    ready = threading.Event()

    def other_add():
        with Lock(stored, "add DSP0236 1.3.3", wait=0):
            saved = meta.read_bytes()
            meta.unlink()  # _clear_previous did this in the other Session
            ready.set()
            time.sleep(0.5)
            library.write_meta(stored, json.loads(saved))

    for force in (False, True):
        ready.clear()
        threading.Thread(target=other_add, daemon=True).start()
        assert ready.wait(5)
        argv = ["add", str(src), "--document", "DSP0236", "--version", "1.3.3"]
        if force:
            argv.append("--force")
        code, out = run(capsys, "--wait", "10", *argv, catalog_file=catalog_file)
        if force:
            assert code == 0 and out.strip().startswith("replaced DSP0236 1.3.3"), out
        else:
            assert code == 2 and "already in the Library" in out, out
    assert not (stored / ".lock").exists()


def test_fetch_waits_for_the_other_download_then_skips(
    stored, catalog_file, scripted, capsys
):
    hold(stored, 0.5, "fetch DSP0236 1.3.3")
    scripted.responses[URL] = ok(PDF_BYTES)
    code, out = run(
        capsys, "--wait", "10", "fetch", "DSP0236", catalog_file=catalog_file
    )
    assert code == 0, out
    assert any(ln.startswith("skipped DSP0236 1.3.3") for ln in out.splitlines())
    assert scripted.calls == []


# ----------------------------------------------------------------- AC-5


def test_readers_do_not_consult_the_lock_when_current(
    catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    from tests import pdfgen

    pdf = pdfgen.write_pdf(
        tmp_path / "d.pdf", [pdfgen.plain_page(["1 Intro", "hello"])]
    )
    scripted.responses[URL] = ok(pdf.read_bytes())
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    fake_lock(vdir)  # live, but the version is current: nothing to wait for
    started = time.monotonic()
    code, out = run(
        capsys, "--wait", "30", "page", "DSP0236", "1", catalog_file=catalog_file
    )
    assert code == 0 and "hello" in out
    assert time.monotonic() - started < 5


def test_reader_meets_a_live_lock_on_an_unextracted_version(
    stored, catalog_file, capsys
):
    fake_lock(stored, command="extract DSP0236 1.3.3")
    for argv in (
        ["find", "DSP0236", "x"],
        ["section", "DSP0236", "x"],
        ["page", "DSP0236", "1"],
        ["render", "DSP0236", "--page", "1"],
        ["table", "DSP0236", "--page", "1"],
    ):
        code, out = run(capsys, "--wait", "0", *argv, catalog_file=catalog_file)
        assert code == 3, (argv, out)
        assert out.startswith(f"busy: {stored / '.lock'} is held by pid 4242 "), argv


def test_reader_with_a_stale_lock_takes_it_over_and_extracts(
    stored, catalog_file, capsys
):
    # Since the reading commands extract themselves (fewer round trips
    # change, AC-3), a reader is a writer here: the stale lock is taken
    # over with the usual note, and the fake PDF fails to extract (exit 1).
    fake_lock(stored, age=lock_mod.STALE_SECONDS + 1)
    code, out = run(
        capsys, "--wait", "0", "find", "DSP0236", "x", catalog_file=catalog_file
    )
    assert code == 1, out
    assert out.startswith("note: took over a stale lock from ")
    assert "failed DSP0236 1.3.3: " in out
    assert not (stored / ".lock").exists()


def test_reader_waits_and_reads_once_the_extraction_lands(
    catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    from tests import pdfgen

    pdf = pdfgen.write_pdf(
        tmp_path / "d.pdf", [pdfgen.plain_page(["1 Intro", "hello"])]
    )
    scripted.responses[URL] = ok(pdf.read_bytes())
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    meta = vdir / "extract.json"
    aside = vdir / "extract.json.aside"
    meta.rename(aside)  # the extraction is "in progress": no meta yet
    ready = threading.Event()

    def other_session():
        with Lock(vdir, "extract DSP0236 1.3.3", wait=0):
            ready.set()
            time.sleep(0.5)
            aside.rename(meta)  # the extraction lands, then the lock goes

    threading.Thread(target=other_session, daemon=True).start()
    assert ready.wait(5)
    code, out = run(
        capsys, "--wait", "10", "page", "DSP0236", "1", catalog_file=catalog_file
    )
    assert code == 0, out
    assert "hello" in out


def test_schema_and_registry_meet_a_live_lock(catalog_file, library, scripted, capsys):
    scripted.responses[ZIP_URL] = ok(ZIP_BYTES, "application/zip")
    code, out = run(capsys, "fetch", "BUNDLE", catalog_file=catalog_file)
    assert code == 0, out
    vdir = library.specs / "mctp" / "BUNDLE" / "2026.1"
    fake_lock(vdir, command="extract BUNDLE 2026.1")
    for cmd in ("schema", "registry"):
        code, out = run(capsys, "--wait", "0", cmd, "BUNDLE", catalog_file=catalog_file)
        assert code == 3 and out.startswith("busy: "), (cmd, out)
    backdate(vdir / ".lock", lock_mod.STALE_SECONDS + 1)
    # a stale lock is taken over and the bundle unpacked by schema itself;
    # this archive holds nothing to unpack, so that is a failure (exit 1)
    code, out = run(
        capsys, "--wait", "0", "schema", "BUNDLE", catalog_file=catalog_file
    )
    assert code == 1, out
    assert "note: took over a stale lock" in out
    assert "no json-schema/ folder" in out


# ----------------------------------------------------------------- AC-7


def test_table_store_is_locked_and_merges(
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
    scripted.responses[URL] = ok(pdf.read_bytes())
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    fake_lock(vdir, command="table DSP0236 page 2")
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
    assert code == 3 and out.startswith("busy: ")
    assert not (vdir / "tables.json").exists()
    (vdir / ".lock").unlink()
    for page in ("1", "2"):
        code, out = run(
            capsys, "table", "DSP0236", "--page", page, catalog_file=catalog_file
        )
        assert code == 0, out
    data = json.loads((vdir / "tables.json").read_text("utf-8"))
    assert data["pages_done"] == [1, 2]
    assert [t["first"] for t in data["tables"]] == [1, 2]
    assert not list(vdir.glob("*.part"))


# ----------------------------------------------------------------- AC-8


def test_meta_and_original_are_written_through_temp_names(stored):
    assert not list(stored.glob("*.part"))
    assert (stored / "meta.json").is_file() and (stored / "original.pdf").is_file()


def test_add_force_copies_through_a_temp_name(stored, catalog_file, tmp_path, capsys):
    # F2 of review round 1: the Drop-in original is renamed into place too.
    src = tmp_path / "mine.pdf"
    src.write_bytes(PDF_BYTES + b"\nnew")
    seen = []
    real_replace = lock_mod.os.replace

    def spying_replace(a, b):
        seen.append((Path(a).name, Path(b).name))
        return real_replace(a, b)

    from bmc_toolkit.spec import library as library_mod

    monkey = pytest.MonkeyPatch()
    monkey.setattr(library_mod.os, "replace", spying_replace)
    try:
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
    finally:
        monkey.undo()
    assert code == 0, out
    assert (stored / "original.pdf").read_bytes() == PDF_BYTES + b"\nnew"
    assert not list(stored.glob("*.part"))
    tmp_names = [a for a, b in seen if b == "original.pdf"]
    assert tmp_names and all(
        a.startswith(f"original.pdf.{os.getpid()}-") and a.endswith(".part")
        for a in tmp_names
    )


def test_a_replace_killed_midway_leaves_no_meta_over_the_new_original(
    stored, catalog_file, scripted, capsys
):
    # F4 of review round 1: "from scratch" after a crash means the old
    # meta.json must not describe the new original; the next fetch redoes it.
    from bmc_toolkit.spec.library import Library

    library = Library(stored.parents[3])
    monkey = pytest.MonkeyPatch()

    def crash(*_args, **_kwargs):
        raise RuntimeError("killed")

    monkey.setattr(Library, "write_meta", crash)
    with pytest.raises(RuntimeError):
        library.store(
            "mctp",
            "DSP0236",
            "1.3.3",
            PDF_BYTES + b"2",
            "pdf",
            url=URL,
            method="direct",
        )
    monkey.undo()
    assert (stored / "original.pdf").read_bytes() == PDF_BYTES + b"2"
    assert not (stored / "meta.json").exists()
    assert library.find("DSP0236", "1.3.3") is None
    scripted.responses[URL] = ok(PDF_BYTES + b"3")
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0 and "fetched DSP0236 1.3.3" in out
    assert (stored / "original.pdf").read_bytes() == PDF_BYTES + b"3"


def test_two_writers_of_one_png_both_succeed(tmp_path):
    out = tmp_path / "renders" / "page-1.png"
    out.parent.mkdir()
    rows = [b"\x10\x20\x30" * 4] * 3
    errors = []

    def write():
        try:
            for _ in range(50):
                render_mod.write_png(out, 4, 3, rows)
        except Exception as exc:  # noqa: BLE001 - the test reports any failure
            errors.append(exc)

    threads = [threading.Thread(target=write) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    png = out.read_bytes()
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    idat = png.index(b"IDAT") + 4
    length = int.from_bytes(png[idat - 8 : idat - 4], "big")
    assert zlib.decompress(png[idat : idat + length]) == b"".join(
        b"\x00" + r for r in rows
    )
    assert not list(out.parent.glob("*.part"))


def test_temp_names_carry_pid_and_token(tmp_path):
    from bmc_toolkit.spec.library import temp_path

    a = temp_path(tmp_path / "meta.json")
    b = temp_path(tmp_path / "meta.json")
    assert a != b
    assert a.name.startswith(f"meta.json.{os.getpid()}-") and a.name.endswith(".part")


# ----------------------------------------------------------------- AC-9


def test_status_lists_live_and_stale_locks(stored, catalog_file, library, capsys):
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0 and "lock:" not in out
    fake_lock(stored, command="extract DSP0236 1.3.3")
    clone = fake_lock(
        library.root / "code" / "bmcweb", pid=7, command="clone bmcweb main"
    )
    backdate(clone, lock_mod.STALE_SECONDS + 1)
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0
    lines = out.splitlines()
    holding = next(i for i, ln in enumerate(lines) if ln.startswith("mctp\tDSP0236"))
    assert lines[holding + 1] == (
        f"lock: {stored / '.lock'} held by pid 4242 on host elsewhere "
        "(extract DSP0236 1.3.3, since 2026-09-05T00:00:00+00:00), live"
    )
    assert lines[holding + 2] == (
        f"lock: {clone} held by pid 7 on host elsewhere "
        "(clone bmcweb main, since 2026-09-05T00:00:00+00:00), stale"
    )


def test_status_of_an_empty_library_still_lists_locks(catalog_file, library, capsys):
    path = fake_lock(library.root / "code" / "bmcweb", command="clone bmcweb main")
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[1] == "(empty)"
    assert out.splitlines()[2].startswith(f"lock: {path} held by pid 4242")


# ---------------------------------------------------------------- AC-10


def test_prune_removes_stale_locks_and_old_leftovers_only(
    stored, catalog_file, library, capsys
):
    old_part = stored / "original.pdf.999-deadbeef.part"
    old_part.write_bytes(b"x")
    backdate(old_part, lock_mod.STALE_SECONDS + 1)
    fresh_part = stored / "extract.json.999-cafe.part"
    fresh_part.write_bytes(b"x")
    render_part = stored / "renders" / "page-1.png.1-2.part"
    render_part.parent.mkdir()
    render_part.write_bytes(b"x")
    backdate(render_part, lock_mod.STALE_SECONDS + 1)
    root_part = library.root / "freshness.json.5-6.part"
    root_part.write_bytes(b"x")
    backdate(root_part, lock_mod.STALE_SECONDS + 1)
    stale = fake_lock(
        library.root / "code" / "bmcweb", pid=7, command="clone bmcweb main"
    )
    backdate(stale, lock_mod.STALE_SECONDS + 1)
    live_dir = library.root / "code" / "pldm"
    fake_lock(live_dir, command="clone pldm main")  # live: its temp dir is in use
    busy_tmp = live_dir / ".tmp-1-abcd"
    busy_tmp.mkdir()
    loose_tmp = library.root / "code" / "bmcweb" / ".tmp-2-ef01"
    loose_tmp.mkdir()

    code, out = run(capsys, "prune", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert f"would remove {loose_tmp} (leftover)" in lines
    assert f"would remove {root_part} (leftover)" in lines
    assert f"would remove {old_part} (leftover)" in lines
    assert f"would remove {render_part} (leftover)" in lines
    assert (
        f"would remove {stale} (stale lock, pid 7 on host elsewhere "
        "(clone bmcweb main, since 2026-09-05T00:00:00+00:00))"
    ) in lines
    assert not any(str(fresh_part) in ln or str(busy_tmp) in ln for ln in lines)
    assert not any(str(live_dir / ".lock") in ln for ln in lines)
    assert lines[-1] == (
        "prune: 0 superseded tree(s), 4 leftover(s), 1 stale lock(s) "
        "(dry run; --yes removes them)"
    )
    assert old_part.exists() and stale.exists()

    code, out = run(capsys, "prune", "--yes", catalog_file=catalog_file)
    assert code == 0, out
    assert (
        out.splitlines()[-1]
        == "prune: 0 superseded tree(s), 4 leftover(s), 1 stale lock(s)"
    )
    for gone in (old_part, render_part, root_part, stale, loose_tmp):
        assert not gone.exists(), gone
    for kept in (fresh_part, busy_tmp, live_dir / ".lock", stored / "original.pdf"):
        assert kept.exists(), kept


def test_prune_finds_old_parts_and_stale_renames_under_code(
    catalog_file, library, capsys
):
    # F3 of review round 1: .part files under Code Trees are leftovers too.
    tree = library.root / "code" / "bmcweb" / "0123456789abcdef"
    tree.mkdir(parents=True)
    old_part = tree / ".bmc-tree.json.7-abcd.part"
    old_part.write_bytes(b"x")
    backdate(old_part, lock_mod.STALE_SECONDS + 1)
    stale_rename = library.root / "code" / "bmcweb" / ".lock.takeover"
    stale_rename.write_bytes(b"x")
    backdate(stale_rename, lock_mod.STALE_SECONDS + 1)
    busy_tree = library.root / "code" / "pldm" / "fedcba9876543210"
    busy_tree.mkdir(parents=True)
    fake_lock(library.root / "code" / "pldm", command="clone pldm main")
    busy_part = busy_tree / ".bmc-tree.json.8-ef01.part"
    busy_part.write_bytes(b"x")
    backdate(busy_part, lock_mod.STALE_SECONDS + 1)
    code, out = run(capsys, "prune", "--yes", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert f"removed {old_part} (leftover)" in lines
    assert f"removed {stale_rename} (leftover)" in lines
    assert not any(str(busy_part) in ln for ln in lines)
    assert lines[-1] == "prune: 0 superseded tree(s), 2 leftover(s), 0 stale lock(s)"
    assert not old_part.exists() and not stale_rename.exists()
    assert busy_part.exists()


def test_prune_keeps_a_stale_lock_taken_over_while_it_worked(
    stored, catalog_file, monkeypatch, capsys
):
    # F1 of review round 2: the lock listed as stale is re-read right before
    # removal; one refreshed meanwhile (a take-over) is kept.
    from bmc_toolkit.spec import cli

    path = fake_lock(stored, command="extract DSP0236 1.3.3")
    backdate(path, lock_mod.STALE_SECONDS + 1)
    real = cli.lock_mod.locks_under
    calls = []

    def listing_then_takeover(root):
        holders = real(root)
        if not calls:  # only the first prune run is raced
            os.utime(path, None)  # another Session takes it over right after
        calls.append(root)
        return holders

    monkeypatch.setattr(cli.lock_mod, "locks_under", listing_then_takeover)
    code, out = run(capsys, "prune", "--yes", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert f"kept {path} (taken over meanwhile)" in lines
    assert not any(ln.startswith("removed") for ln in lines)
    assert (
        lines[-1]
        == "prune: 0 superseded tree(s), 0 leftover(s), 0 stale lock(s), 1 kept"
    )
    assert path.exists()
    # A take-over in progress (fresh gate) keeps the lock too (F3, round 3).
    backdate(path, lock_mod.STALE_SECONDS + 1)
    gate = stored / ".lock.takeover"
    gate.write_bytes(b"")
    code, out = run(capsys, "prune", "--yes", catalog_file=catalog_file)
    assert code == 0, out
    assert f"kept {path} (take-over in progress)" in out.splitlines()
    assert path.exists() and gate.exists()
    gate.unlink()
    code, out = run(capsys, "prune", "--yes", catalog_file=catalog_file)
    assert code == 0, out
    assert any(
        ln.startswith(f"removed {path} (stale lock, ") for ln in out.splitlines()
    )
    assert (
        out.splitlines()[-1]
        == "prune: 0 superseded tree(s), 0 leftover(s), 1 stale lock(s)"
    )
    assert not path.exists() and not gate.exists()


def test_prune_skips_leftovers_in_a_live_locked_version(stored, catalog_file, capsys):
    part = stored / "original.pdf.1-2.part"
    part.write_bytes(b"x")
    backdate(part, lock_mod.STALE_SECONDS + 1)
    fake_lock(stored)
    code, out = run(capsys, "prune", catalog_file=catalog_file)
    assert code == 0
    assert (
        out.strip()
        == "nothing to prune: no superseded Code Tree, no leftover, no stale lock"
    )


# ---------------------------------------------------------------- AC-11


@pytest.fixture
def hook(monkeypatch, tmp_path):
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "install_deps", root / "hooks" / "install_deps.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = tmp_path / "data"
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(data))
    return module, data


def fake_pip(monkeypatch, module, side_effect=None):
    """A subprocess.run that 'installs' one file into --target."""
    calls = []

    def run(cmd, **_kwargs):
        target = Path(cmd[cmd.index("--target") + 1])
        (target / "pkg.py").write_text("x = 1\n", encoding="utf-8")
        calls.append(target)
        if side_effect is not None:
            side_effect(target)

        class Result:
            returncode = 0
            stderr = ""

        return Result()

    monkeypatch.setattr(module.subprocess, "run", run)
    return calls


def test_hook_installs_through_a_temp_directory(hook, monkeypatch, capsys):
    module, data = hook
    calls = fake_pip(monkeypatch, module)
    assert module.main() == 0
    target = data / "site-packages"
    assert calls and calls[0].name.startswith("site-packages.tmp-")
    assert (target / "pkg.py").is_file()
    assert (target / module.MARKER_NAME).is_file()
    assert [p.name for p in data.iterdir()] == ["site-packages"]  # no temp left
    assert (
        capsys.readouterr().out.strip()
        == f"bmc-toolkit: dependencies installed into {target}"
    )
    assert module.main() == 0 and capsys.readouterr().out == ""  # marker matches: no-op


def test_hook_keeps_the_install_another_session_landed_first(hook, monkeypatch, capsys):
    module, data = hook
    target = data / "site-packages"
    digest = module.hashlib.sha256(module.REQUIREMENTS.read_bytes()).hexdigest()

    def other_session_lands(_tmp):
        target.mkdir(parents=True)
        (target / "theirs.py").write_text("y = 2\n", encoding="utf-8")
        (target / module.MARKER_NAME).write_text(digest + "\n", encoding="utf-8")

    fake_pip(monkeypatch, module, other_session_lands)
    assert module.main() == 0
    assert (target / "theirs.py").is_file() and not (target / "pkg.py").exists()
    assert [p.name for p in data.iterdir()] == ["site-packages"]
    assert capsys.readouterr().out.strip() == (
        f"bmc-toolkit: dependencies already installed into {target}"
    )


def test_hook_replaces_an_install_made_from_older_requirements(
    hook, monkeypatch, capsys
):
    module, data = hook
    target = data / "site-packages"
    target.mkdir(parents=True)
    (target / "old.py").write_text("z = 3\n", encoding="utf-8")
    (target / module.MARKER_NAME).write_text("stale digest\n", encoding="utf-8")
    fake_pip(monkeypatch, module)
    assert module.main() == 0
    assert (target / "pkg.py").is_file() and not (target / "old.py").exists()
    assert [p.name for p in data.iterdir()] == ["site-packages"]


def test_hook_without_plugin_data_does_nothing(hook, monkeypatch, capsys):
    module, _ = hook
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA")
    assert module.main() == 0
    assert "CLAUDE_PLUGIN_DATA not set" in capsys.readouterr().out
