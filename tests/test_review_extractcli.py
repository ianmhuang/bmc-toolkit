"""Acceptance tests for M2 through the CLI: AC-1, AC-2, AC-9, AC-10, AC-11.

Black-box through ``bmc_toolkit.spec.cli.main``. Documents enter the Library
with ``add`` (no network); the one forced ``fetch`` uses the scripted client
from ``tests.conftest``.
"""

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bmc_toolkit.spec import cli  # noqa: E402
from tests.conftest import ZIP_BYTES, ok  # noqa: E402

URL_133 = "https://example.test/DSP0236_1.3.3.pdf"
ZIP = ZIP_BYTES  # a real archive without a json-schema folder
FAKE_PDF = b"%PDF-1.4\n%not really\n" + b"x" * 64
DERIVED = ("extract.txt", "extract.json", "outline.json", "linemap.json")


def run(capsys, catalog_file, *argv):
    code = cli.main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def add(capsys, catalog_file, path, doc, version, *extra):
    argv = ["add", str(path), "--document", doc, "--version", version, *extra]
    code, out = run(capsys, catalog_file, *argv)
    assert code == 0, out


@pytest.fixture
def pdfgen():
    pytest.importorskip("pypdfium2")
    from tests import pdfgen as mod

    return mod


def vdir_of(library, doc="DSP0236", version="1.3.3", family="mctp"):
    return library.specs / family / doc / version


def read_json(path):
    return json.loads(path.read_text("utf-8"))


def status_row(capsys, catalog_file, doc, version):
    code, out = run(capsys, catalog_file, "status")
    assert code == 0
    rows = [
        ln.split("\t")
        for ln in out.splitlines()
        if "\t" in ln and ln.split("\t")[1] == doc and ln.split("\t")[2] == version
    ]
    assert len(rows) == 1, out
    return rows[0]


def set_old_mtime(path):
    old = 1_500_000_000
    os.utime(path, (old, old))
    return path.stat().st_mtime_ns


# ------------------------------------------------------------------- AC-1


def test_extract_writes_the_four_files_and_the_run_metadata(
    catalog_file, library, tmp_path, capsys, pdfgen
):
    pdf = pdfgen.write_pdf(
        tmp_path / "n.pdf",
        [
            pdfgen.numbered_page(1, ["alpha", "beta", "gamma", "delta", "epsilon"]),
            pdfgen.numbered_page(6, ["zeta", "eta", "theta", "iota", "kappa"]),
        ],
    )
    add(capsys, catalog_file, pdf, "DSP0236", "1.3.3")
    code, out = run(capsys, catalog_file, "extract", "DSP0236")
    assert code == 0, out
    vdir = vdir_of(library)
    for name in DERIVED:
        assert (vdir / name).is_file(), name
    text = (vdir / "extract.txt").read_text("utf-8")
    assert text.startswith("=== page 1 ===\n")
    assert "\n=== page 2 ===\n" in text
    assert "alpha" in text and "kappa" in text
    meta = read_json(vdir / "extract.json")
    assert isinstance(meta["extractor_version"], int)
    assert meta["pages"] == 2
    assert isinstance(meta["seconds"], (int, float)) and meta["seconds"] >= 0
    assert meta["line_numbers"] is True
    assert meta["outline_source"] == "none"
    assert read_json(vdir / "outline.json") == []
    linemap = read_json(vdir / "linemap.json")
    assert set(linemap["pages"]) == {"1", "2"}
    assert (linemap["pages"]["2"]["first"], linemap["pages"]["2"]["last"]) == (6, 10)


def test_extract_without_line_numbers_writes_no_linemap(
    catalog_file, library, tmp_path, capsys, pdfgen
):
    pdf = pdfgen.write_pdf(tmp_path / "p.pdf", [pdfgen.plain_page(["plain text"])])
    add(capsys, catalog_file, pdf, "DSP0236", "1.3.3")
    code, out = run(capsys, catalog_file, "extract", "DSP0236")
    assert code == 0, out
    vdir = vdir_of(library)
    assert (vdir / "extract.txt").is_file()
    assert not (vdir / "linemap.json").exists()
    meta = read_json(vdir / "extract.json")
    assert meta["line_numbers"] is False
    assert meta["outline_source"] == "none"


def test_extract_picks_the_latest_held_version_or_the_one_requested(
    catalog_file, library, tmp_path, capsys, pdfgen
):
    pdf = pdfgen.write_pdf(tmp_path / "p.pdf", [pdfgen.plain_page(["text"])])
    add(capsys, catalog_file, pdf, "DSP0236", "1.3.2")
    add(capsys, catalog_file, pdf, "DSP0236", "1.3.3")
    code, out = run(capsys, catalog_file, "extract", "DSP0236")
    assert code == 0, out
    assert "1.3.3" in out
    assert (vdir_of(library, version="1.3.3") / "extract.txt").is_file()
    assert not (vdir_of(library, version="1.3.2") / "extract.txt").exists()
    code, out = run(capsys, catalog_file, "extract", "DSP0236", "--version", "1.3.2")
    assert code == 0, out
    assert (vdir_of(library, version="1.3.2") / "extract.txt").is_file()


def test_extract_error_paths_exit_2_with_a_message(
    catalog_file, library, tmp_path, capsys, pdfgen
):
    code, out = run(capsys, catalog_file, "extract", "IPMI")
    assert code == 2
    assert "IPMI" in out and "Library" in out
    code, out = run(capsys, catalog_file, "extract")
    assert code == 2
    code, out = run(capsys, catalog_file, "extract", "DSP0236", "--all")
    assert code == 2
    pdf = pdfgen.write_pdf(tmp_path / "p.pdf", [pdfgen.plain_page(["text"])])
    add(capsys, catalog_file, pdf, "DSP0236", "1.3.3")
    code, out = run(capsys, catalog_file, "extract", "DSP0236", "--version", "9.9")
    assert code == 2
    assert not (vdir_of(library) / "extract.txt").exists()


def test_extract_of_a_corrupt_pdf_fails_cleanly(catalog_file, library, tmp_path, capsys):
    pytest.importorskip("pypdfium2")
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(FAKE_PDF)
    add(capsys, catalog_file, bad, "DSP0236", "1.3.3")
    code, out = run(capsys, catalog_file, "extract", "DSP0236")
    assert code == 2
    assert "failed" in out.lower()
    assert not (vdir_of(library) / "extract.txt").exists()
    assert not (vdir_of(library) / "extract.json").exists()


def test_extract_all_covers_every_pdf_skips_zip_and_summarises(
    catalog_file, library, tmp_path, capsys, pdfgen
):
    pdf = pdfgen.write_pdf(tmp_path / "p.pdf", [pdfgen.plain_page(["text"])])
    add(capsys, catalog_file, pdf, "DSP0236", "1.3.3")
    add(capsys, catalog_file, pdf, "DSP0236", "1.3.2")
    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(ZIP)
    add(capsys, catalog_file, bundle, "BUNDLE", "2026.1")

    code, out = run(capsys, catalog_file, "extract", "--all")
    assert code == 0, out
    summary = out.strip().splitlines()[-1]
    assert summary.startswith("summary:")
    assert "extracted 2" in summary and "skipped 1" in summary and "failed 0" in summary
    zip_line = next(ln for ln in out.splitlines() if "BUNDLE" in ln)
    assert zip_line.startswith("skipped")
    assert (vdir_of(library, version="1.3.3") / "extract.txt").is_file()
    assert (vdir_of(library, version="1.3.2") / "extract.txt").is_file()
    assert not any(vdir_of(library, "BUNDLE", "2026.1").glob("extract.*"))

    code, out = run(capsys, catalog_file, "extract", "--all")
    assert code == 0, out
    summary = out.strip().splitlines()[-1]
    assert "extracted 0" in summary and "skipped 3" in summary
    code, out = run(capsys, catalog_file, "extract", "--all", "--version", "1.3.3")
    assert code == 2


# ------------------------------------------------------------------- AC-2


def test_second_extract_is_a_no_op_unless_forced_or_the_extractor_is_older(
    catalog_file, library, tmp_path, capsys, pdfgen
):
    pdf = pdfgen.write_pdf(tmp_path / "p.pdf", [pdfgen.plain_page(["text"])])
    add(capsys, catalog_file, pdf, "DSP0236", "1.3.3")
    assert run(capsys, catalog_file, "extract", "DSP0236")[0] == 0
    vdir = vdir_of(library)
    extract_txt = vdir / "extract.txt"
    meta_path = vdir / "extract.json"
    content = extract_txt.read_bytes()
    current = read_json(meta_path)["extractor_version"]

    old = set_old_mtime(extract_txt)
    code, out = run(capsys, catalog_file, "extract", "DSP0236")
    assert code == 0, out
    assert "skip" in out.lower() or "already" in out.lower()
    assert extract_txt.stat().st_mtime_ns == old
    assert extract_txt.read_bytes() == content

    old = set_old_mtime(extract_txt)
    code, out = run(capsys, catalog_file, "extract", "DSP0236", "--force")
    assert code == 0, out
    assert "extracted" in out.lower()
    assert extract_txt.stat().st_mtime_ns != old

    meta = read_json(meta_path)
    meta["extractor_version"] = current - 1
    meta_path.write_text(json.dumps(meta), "utf-8")
    old = set_old_mtime(extract_txt)
    code, out = run(capsys, catalog_file, "extract", "DSP0236")
    assert code == 0, out
    assert "extracted" in out.lower()
    assert extract_txt.stat().st_mtime_ns != old
    assert read_json(meta_path)["extractor_version"] == current


# ------------------------------------------------------------------- AC-9


def test_status_shows_extract_presence_and_outline_source(
    catalog_file, library, tmp_path, capsys, pdfgen
):
    pdf = pdfgen.write_pdf(
        tmp_path / "b.pdf",
        [pdfgen.plain_page(["1 Scope"])],
        bookmarks=[(0, "1 Scope", 0)],
    )
    add(capsys, catalog_file, pdf, "DSP0236", "1.3.3")
    row = status_row(capsys, catalog_file, "DSP0236", "1.3.3")
    assert "extracted" not in row
    assert "bookmarks" not in row

    assert run(capsys, catalog_file, "extract", "DSP0236")[0] == 0
    row = status_row(capsys, catalog_file, "DSP0236", "1.3.3")
    assert "extracted" in row
    assert "bookmarks" in row
    assert row.index("bookmarks") > row.index("extracted")


# ------------------------------------------------ AC-1 latest held version


def test_extract_prefers_the_catalog_latest_when_held(
    catalog_file, library, tmp_path, capsys, pdfgen
):
    pdf = pdfgen.write_pdf(tmp_path / "p.pdf", [pdfgen.plain_page(["text"])])
    add(capsys, catalog_file, pdf, "DSP0236", "1.4.0")  # WIP, dated newest
    add(capsys, catalog_file, pdf, "DSP0236", "1.3.3")  # latest published
    code, out = run(capsys, catalog_file, "extract", "DSP0236")
    assert code == 0, out
    assert "1.3.3" in out
    assert (vdir_of(library, version="1.3.3") / "extract.txt").is_file()
    assert not (vdir_of(library, version="1.4.0") / "extract.txt").exists()


def test_extract_picks_the_newest_held_version_by_catalog_date_not_by_name(
    catalog_file, library, tmp_path, capsys, pdfgen
):
    # 1.3.3 (the catalog's latest published) is not held. Of the held
    # versions the catalog dates 1.4.0 (2025) after 1.3.2 (2024); directory
    # order would agree here, so the reverse case below is the real check.
    pdf = pdfgen.write_pdf(tmp_path / "p.pdf", [pdfgen.plain_page(["text"])])
    add(capsys, catalog_file, pdf, "DSP0236", "1.3.2")
    add(capsys, catalog_file, pdf, "DSP0236", "1.4.0")
    code, out = run(capsys, catalog_file, "extract", "DSP0236")
    assert code == 0, out
    assert "1.4.0" in out
    assert (vdir_of(library, version="1.4.0") / "extract.txt").is_file()
    assert not (vdir_of(library, version="1.3.2") / "extract.txt").exists()


def test_extract_for_a_document_unknown_to_the_catalog_uses_fetch_time(
    catalog_file, library, tmp_path, capsys, pdfgen
):
    # Two hand-placed versions of a document the catalog does not know:
    # "1.10.0" sorts before "1.9.0" as a string but was fetched earlier, so
    # the latest held version is 1.9.0.
    earlier = library.specs / "vendor" / "OEM" / "1.10.0"
    later = library.specs / "vendor" / "OEM" / "1.9.0"
    for vdir, stamp in (
        (earlier, "2025-01-01T00:00:00+00:00"),
        (later, "2025-06-01T00:00:00+00:00"),
    ):
        vdir.mkdir(parents=True)
        pdfgen.write_pdf(vdir / "original.pdf", [pdfgen.plain_page(["x"])])
        library.write_meta(
            vdir,
            {
                "family": "vendor",
                "document": "OEM",
                "version": vdir.name,
                "file": "original.pdf",
                "url": None,
                "fetch_method": "dropin",
                "sha256": "0" * 64,
                "size": 1,
                "fetched_at": stamp,
                "dropin": True,
            },
        )
    code, out = run(capsys, catalog_file, "extract", "OEM")
    assert code == 0, out
    assert "1.9.0" in out
    assert (later / "extract.txt").is_file()
    assert not (earlier / "extract.txt").exists()


# ------------------------------------------------- pypdfium2 requirement


def test_extract_refuses_pypdfium2_older_than_5_before_writing_anything(
    catalog_file, library, tmp_path, capsys, pdfgen, monkeypatch
):
    import types

    pdf = pdfgen.write_pdf(tmp_path / "p.pdf", [pdfgen.plain_page(["text"])])
    add(capsys, catalog_file, pdf, "DSP0236", "1.3.3")
    fake = types.ModuleType("pypdfium2")
    fake.PYPDFIUM_INFO = types.SimpleNamespace(major=4, minor=30, patch=0)
    fake.V_PYPDFIUM2 = "4.30.0"
    monkeypatch.setitem(sys.modules, "pypdfium2", fake)
    code, out = run(capsys, catalog_file, "extract", "DSP0236")
    assert code == 2, out
    assert "failed" in out.lower()
    assert "pypdfium2" in out and "5" in out
    vdir = vdir_of(library)
    for name in DERIVED:
        assert not (vdir / name).exists(), name
    # --all reports the same holding as failed and exits 2
    code, out = run(capsys, catalog_file, "extract", "--all")
    assert code == 2, out
    assert out.strip().splitlines()[-1].endswith("failed 1")


def test_requirements_pin_pypdfium2_to_5_or_newer():
    import re

    for name in ("requirements.txt", "pyproject.toml"):
        text = (ROOT / name).read_text("utf-8")
        m = re.search(r"pypdfium2\s*>=\s*(\d+)", text)
        assert m, f"{name} does not require pypdfium2"
        assert int(m.group(1)) >= 5, name


# ------------------------------------------------------------------ AC-10


def test_add_force_removes_other_originals_and_stale_derived_files(
    catalog_file, library, tmp_path, capsys
):
    pdf = tmp_path / "v.pdf"
    pdf.write_bytes(FAKE_PDF)
    add(capsys, catalog_file, pdf, "DSP0236", "1.3.3")
    vdir = vdir_of(library)
    for name in DERIVED:
        (vdir / name).write_text("stale\n", "utf-8")
    bundle = tmp_path / "v.zip"
    bundle.write_bytes(ZIP)
    add(capsys, catalog_file, bundle, "DSP0236", "1.3.3", "--force")
    assert sorted(p.name for p in vdir.iterdir()) == ["meta.json", "original.zip"]
    assert read_json(vdir / "meta.json")["file"] == "original.zip"
    assert (vdir / "original.zip").read_bytes() == ZIP


def test_forced_fetch_removes_other_originals_and_stale_derived_files(
    catalog_file, library, scripted, tmp_path, capsys
):
    bundle = tmp_path / "v.zip"
    bundle.write_bytes(ZIP)
    add(capsys, catalog_file, bundle, "DSP0236", "1.3.3")
    vdir = vdir_of(library)
    for name in DERIVED:
        (vdir / name).write_text("stale\n", "utf-8")
    scripted.responses[URL_133] = ok(FAKE_PDF)
    code, out = run(capsys, catalog_file, "fetch", "DSP0236", "--force")
    assert code == 0, out
    assert sorted(p.name for p in vdir.iterdir()) == ["meta.json", "original.pdf"]
    assert read_json(vdir / "meta.json")["file"] == "original.pdf"
    assert (vdir / "original.pdf").read_bytes() == FAKE_PDF


# ------------------------------------------------------------------ AC-11


def test_docs_carry_the_m1_wording_fixes():
    skill = (ROOT / "skills" / "bmc-spec" / "SKILL.md").read_text("utf-8")
    fetch_rows = [ln for ln in skill.splitlines() if ln.startswith("| `fetch")]
    assert fetch_rows, "SKILL.md lost its fetch rows"
    for row in fetch_rows:
        assert "silent" not in row.lower(), row

    readme = (ROOT / "README.md").read_text("utf-8")
    start = readme.index("`curl_cffi`")
    rest = readme[start:]
    end = rest.find("\n- `")
    bullet = rest[: end if end >= 0 else None]
    assert "Internet Archive" in bullet
    assert "Intel" in bullet
    assert "OCP" in bullet
    assert "direct" in bullet, bullet  # OCP still downloads directly
