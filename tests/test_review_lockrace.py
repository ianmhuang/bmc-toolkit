"""Review acceptance tests for M13 across processes: a helper process holds
a version directory's lock while the CLI runs in another process (AC-12),
and two extracts plus table reads race on one version (AC-13).

The busy and take-over paths need no PDF library. The waiting extract and
the race skip without pypdfium2 (and pdfplumber for the tables).
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from bmc_toolkit.spec import extract as extract_mod
from bmc_toolkit.spec import lock as lock_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import PDF_BYTES, ok

ROOT = Path(__file__).resolve().parents[1]
URL = "https://example.test/DSP0236_1.3.3.pdf"

HOLDER = """
import json, os, sys, time
from pathlib import Path
d = Path(sys.argv[1]); d.mkdir(parents=True, exist_ok=True)
fd = os.open(d / ".lock", os.O_CREAT | os.O_EXCL | os.O_WRONLY)
with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
    json.dump({"pid": os.getpid(), "host": "helper-host",
               "command": "extract DSP0236 1.3.3",
               "started": "2026-09-05T01:02:03+00:00"}, fh)
print("held", os.getpid(), flush=True)
deadline = time.monotonic() + float(sys.argv[2])
while time.monotonic() < deadline:
    os.utime(d / ".lock", None)
    time.sleep(0.1)
os.unlink(d / ".lock")
"""


def env_for(root):
    env = dict(os.environ)
    env["BMC_SPEC_LIBRARY"] = str(root)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(ROOT)
    return env


def cli(root, catalog_file, *argv):
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "bmc_toolkit.spec.cli",
            "--catalog",
            str(catalog_file),
            *argv,
        ],
        cwd=ROOT,
        env=env_for(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def finish(proc, timeout=180):
    out, _ = proc.communicate(timeout=timeout)
    return proc.returncode, out


def holder(vdir, seconds):
    """Another process that writes the lock file the way a Session does and
    keeps touching it for ``seconds``; returns once the lock is held."""
    proc = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(vdir), str(seconds)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    word, pid = proc.stdout.readline().split()
    assert word == "held"
    proc.lock_pid = int(pid)
    return proc


def backdate(path, seconds):
    old = time.time() - seconds
    os.utime(path, (old, old))


@pytest.fixture
def stored(catalog_file, library, scripted, capsys):
    scripted.responses[URL] = ok(PDF_BYTES)
    assert main(["--catalog", str(catalog_file), "fetch", "DSP0236"]) == 0
    capsys.readouterr()
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


def real_pdf_stored(catalog_file, library, scripted, tmp_path, capsys, pages):
    from tests import pdfgen

    pdf = pdfgen.write_pdf(tmp_path / "real.pdf", pages)
    scripted.responses[URL] = ok(pdf.read_bytes())
    assert main(["--catalog", str(catalog_file), "fetch", "DSP0236"]) == 0
    capsys.readouterr()
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


# ---------------------------------------------------------------- AC-12


def test_extract_wait_0_exits_3_naming_the_helper(stored, library, catalog_file):
    proc = holder(stored, 20)
    try:
        started = time.monotonic()
        code, out = finish(
            cli(library.root, catalog_file, "--wait", "0", "extract", "DSP0236")
        )
        assert time.monotonic() - started < 15
        assert code == 3, out
        assert out.strip() == (
            f"busy: {stored / '.lock'} is held by pid {proc.lock_pid} on host "
            "helper-host (extract DSP0236 1.3.3, since 2026-09-05T01:02:03+00:00); "
            "retry with --wait"
        )
        assert not (stored / "extract.txt").exists()
        assert (stored / ".lock").is_file()
    finally:
        proc.kill()
        proc.wait()


def test_add_waits_longer_than_the_hold_and_succeeds(
    stored, library, catalog_file, tmp_path
):
    src = tmp_path / "mine.pdf"
    src.write_bytes(PDF_BYTES)
    proc = holder(stored, 1.5)
    try:
        started = time.monotonic()
        code, out = finish(
            cli(
                library.root,
                catalog_file,
                "--wait",
                "30",
                "add",
                str(src),
                "--document",
                "DSP0236",
                "--version",
                "1.3.3",
                "--force",
            )
        )
        assert code == 0, out
        assert time.monotonic() - started >= 1.0
        assert "replaced DSP0236 1.3.3 as Drop-in" in out
    finally:
        proc.wait(timeout=30)
    assert not (stored / ".lock").exists()
    assert not list(stored.glob("*.part"))
    meta = json.loads((stored / "meta.json").read_text(encoding="utf-8"))
    assert meta["dropin"] is True


def test_extract_waits_longer_than_the_hold_and_extracts(
    catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    from tests import pdfgen

    vdir = real_pdf_stored(
        catalog_file,
        library,
        scripted,
        tmp_path,
        capsys,
        [pdfgen.plain_page(["1 Intro", "hello there"])],
    )
    proc = holder(vdir, 1.5)
    try:
        started = time.monotonic()
        code, out = finish(
            cli(library.root, catalog_file, "--wait", "30", "extract", "DSP0236")
        )
        assert code == 0, out
        assert time.monotonic() - started >= 1.0
        assert "extracted DSP0236 1.3.3" in out
    finally:
        proc.wait(timeout=30)
    assert extract_mod.is_current(vdir)
    assert not (vdir / ".lock").exists()


def test_stale_lock_from_a_dead_process_is_taken_over_without_waiting(
    stored, library, catalog_file
):
    proc = holder(stored, 20)
    proc.kill()
    proc.wait()
    lock = stored / ".lock"
    assert lock.is_file()  # the dead holder left it behind
    backdate(lock, 600)  # ten minutes: stale
    started = time.monotonic()
    code, out = finish(
        cli(library.root, catalog_file, "--wait", "30", "extract", "DSP0236")
    )
    assert time.monotonic() - started < 20
    assert (
        f"note: took over a stale lock from pid {proc.lock_pid} on host helper-host "
        "(extract DSP0236 1.3.3, since 2026-09-05T01:02:03+00:00)"
    ) in out.splitlines()
    assert not lock.exists()
    assert code != 3


# ---------------------------------------------------------------- AC-13


def test_two_extracts_then_table_reads_race_to_one_consistent_version(
    catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    pytest.importorskip("pdfplumber")
    from tests import pdfgen
    from tests.test_tables import HEADER, ROWS_1, ROWS_2, furniture, ruled_table

    pages = []
    for n in (1, 2):
        page = furniture(n) + [
            (72, 740, f"{n} Section {n}"),
            (72, 714, f"Table {n} - T{n}"),
        ]
        rows = ROWS_1 if n == 1 else ROWS_2
        page += ruled_table(72, 700, [100 + 10 * n, 80, 200], [16] * 3, [HEADER, *rows])
        page += [(72, 400, f"Body text of page {n} " * 3)]
        pages.append(page)
    vdir = real_pdf_stored(catalog_file, library, scripted, tmp_path, capsys, pages)

    extracts = [
        cli(library.root, catalog_file, "--wait", "120", "extract", "DSP0236")
        for _ in range(2)
    ]
    results = [finish(p) for p in extracts]
    assert all(code == 0 for code, _ in results), results
    first_words = sorted(out.split()[0] for _, out in results)
    assert first_words == ["extracted", "skipped"], results  # exactly once
    assert extract_mod.is_current(vdir)

    readers = [
        cli(
            library.root,
            catalog_file,
            "--wait",
            "120",
            "table",
            "DSP0236",
            "--page",
            str(n),
        )
        for n in (1, 2)
    ]
    results = [finish(p) for p in readers]
    assert all(code == 0 for code, _ in results), results
    data = json.loads((vdir / "tables.json").read_text(encoding="utf-8"))
    assert data["pages_done"] == [1, 2]
    assert sorted(t["first"] for t in data["tables"]) == [1, 2]

    assert not (vdir / ".lock").exists()
    assert not list(vdir.rglob("*.part"))
    assert sorted(p.name for p in vdir.iterdir()) == [
        "extract.json",
        "extract.txt",
        "meta.json",
        "original.pdf",
        "outline.json",
        "tables.json",
    ]
