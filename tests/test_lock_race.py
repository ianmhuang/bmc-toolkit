"""Concurrency across processes (AC-12, AC-13): a helper process holds a
lock while the CLI runs in another process, and a real race of two
extracts plus two table reads on one version.

The busy paths need no PDF library; the extract and table races skip when
pypdfium2 or pdfplumber is missing.
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
from tests.test_lock import backdate

ROOT = Path(__file__).resolve().parents[1]
URL = "https://example.test/DSP0236_1.3.3.pdf"

HOLDER = """
import os, sys, time
from bmc_toolkit.spec.lock import Lock
lock = Lock(sys.argv[1], "extract DSP0236 1.3.3", wait=0).acquire()
print("held", os.getpid(), flush=True)
time.sleep(float(sys.argv[2]))
lock.release()
"""


def env_for(library_root):
    env = dict(os.environ)
    env["BMC_SPEC_LIBRARY"] = str(library_root)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(ROOT)
    return env


def cli(library_root, catalog_file, *argv):
    """Start the CLI in a child process; returns the Popen."""
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
        env=env_for(library_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def finish(proc, timeout=120):
    out, _ = proc.communicate(timeout=timeout)
    return proc.returncode, out


def holder(vdir, seconds):
    """A process that holds ``vdir``'s lock for ``seconds``; returns once held.
    ``proc.lock_pid`` is the pid the lock file records (a venv launcher on
    Windows runs the interpreter as a child, so it can differ from
    ``proc.pid``)."""
    proc = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(vdir), str(seconds)],
        cwd=ROOT,
        env=env_for(vdir),
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    word, pid = proc.stdout.readline().split()
    assert word == "held"
    proc.lock_pid = int(pid)
    return proc


@pytest.fixture
def stored(catalog_file, library, scripted, capsys):
    scripted.responses[URL] = ok(PDF_BYTES)
    code = main(["--catalog", str(catalog_file), "fetch", "DSP0236"])
    assert code == 0, capsys.readouterr().out
    capsys.readouterr()
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


# ---------------------------------------------------------------- AC-12


def test_extract_in_another_process_sees_busy_then_takes_over(
    stored, library, catalog_file
):
    proc = holder(stored, 30)
    try:
        code, out = finish(
            cli(library.root, catalog_file, "--wait", "0", "extract", "DSP0236")
        )
        assert code == 3, out
        assert (
            f"busy: {stored / '.lock'} is held by pid {proc.lock_pid} on host " in out
        )
        assert "(extract DSP0236 1.3.3, since " in out
        assert not (stored / "extract.txt").exists()
    finally:
        proc.kill()
        proc.wait()
    # The killed holder left its lock; it is live until it ages out.
    assert (stored / ".lock").exists()
    backdate(stored / ".lock", lock_mod.STALE_SECONDS + 1)
    code, out = finish(
        cli(library.root, catalog_file, "--wait", "0", "extract", "DSP0236")
    )
    assert "note: took over a stale lock from pid" in out
    # A fake PDF cannot be extracted; what matters is that the lock was
    # taken over and released rather than waited on.
    assert not (stored / ".lock").exists()


def test_add_in_another_process_waits_for_the_holder(
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


def test_extract_in_another_process_waits_then_extracts(
    catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    from tests import pdfgen

    pdf = pdfgen.write_pdf(
        tmp_path / "d.pdf", [pdfgen.plain_page(["1 Intro", "hello"])]
    )
    scripted.responses[URL] = ok(pdf.read_bytes())
    assert main(["--catalog", str(catalog_file), "fetch", "DSP0236"]) == 0
    capsys.readouterr()
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    proc = holder(vdir, 1.5)
    try:
        code, out = finish(
            cli(library.root, catalog_file, "--wait", "30", "extract", "DSP0236")
        )
        assert code == 0, out
        assert "extracted DSP0236 1.3.3" in out
        assert extract_mod.is_current(vdir)
    finally:
        proc.wait(timeout=30)
    assert not (vdir / ".lock").exists()


# ---------------------------------------------------------------- AC-13


def test_two_extracts_and_two_table_reads_race_to_a_consistent_end(
    catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    pytest.importorskip("pdfplumber")
    from tests import pdfgen
    from tests.test_tables import HEADER, ROWS_1, ROWS_2, furniture, ruled_table

    pages = []
    for n in range(1, 5):
        page = furniture(n) + [
            (72, 740, f"{n} Section {n}"),
            (72, 714, f"Table {n} - T{n}"),
        ]
        rows = ROWS_1 if n % 2 else ROWS_2
        page += ruled_table(72, 700, [100 + 10 * n, 80, 200], [16] * 3, [HEADER, *rows])
        page += [(72, 400, f"Body text of page {n} " * 3)]
        pages.append(page)
    pdf = pdfgen.write_pdf(tmp_path / "race.pdf", pages)
    scripted.responses[URL] = ok(pdf.read_bytes())
    assert main(["--catalog", str(catalog_file), "fetch", "DSP0236"]) == 0
    capsys.readouterr()
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"

    extracts = [
        cli(library.root, catalog_file, "--wait", "120", "extract", "DSP0236")
        for _ in range(2)
    ]
    results = [finish(p) for p in extracts]
    assert all(code == 0 for code, _ in results), results
    verbs = sorted(out.split()[0] for _, out in results)
    assert verbs == ["extracted", "skipped"], results
    assert extract_mod.is_current(vdir)

    tables = [
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
        for n in (1, 2, 3, 4)
    ]
    results = [finish(p) for p in tables]
    assert all(code == 0 for code, _ in results), results
    data = json.loads((vdir / "tables.json").read_text("utf-8"))
    assert data["pages_done"] == [1, 2, 3, 4]
    assert sorted(t["first"] for t in data["tables"]) == [1, 2, 3, 4]

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
