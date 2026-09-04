"""CLI behaviour: catalog listing, fetch, add, scan, status, exit codes."""

import json

import pytest

from bmc_toolkit.spec import fetch as fetch_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import (
    HTML_BYTES,
    PDF_BYTES,
    ZIP_BYTES,
    ok,
    wayback_hit,
    wayback_miss,
)

URL = "https://example.test/DSP0236_1.3.3.pdf"


def run(capsys, *argv, catalog_file=None):
    args = ["--catalog", str(catalog_file)] if catalog_file else []
    code = main([*args, *argv])
    return code, capsys.readouterr().out


def test_catalog_lists_one_record_per_document(catalog_file, capsys):
    code, out = run(capsys, "catalog", catalog_file=catalog_file)
    assert code == 0
    lines = out.strip().splitlines()
    assert lines[0].split("\t") == [
        "mctp",
        "DSP0236",
        "open",
        "direct",
        "1.3.3",
        "MCTP Base Specification",
        "1.3.2;1.3.3;1.4.0",
    ]
    assert [ln.split("\t")[1] for ln in lines] == [
        "DSP0236",
        "IPMI",
        "BUNDLE",
        "SECRET",
    ]


def test_catalog_family_filter_and_unknown_family(catalog_file, capsys):
    code, out = run(capsys, "catalog", "--family", "ipmi", catalog_file=catalog_file)
    assert code == 0
    assert [ln.split("\t")[1] for ln in out.strip().splitlines()] == ["IPMI"]
    code, out = run(capsys, "catalog", "--family", "nope", catalog_file=catalog_file)
    assert code == 2


def test_catalog_single_document_shows_versions_newest_first(catalog_file, capsys):
    code, out = run(capsys, "catalog", "dsp0236", catalog_file=catalog_file)
    assert code == 0
    assert "latest: 1.3.3" in out
    versions = [
        ln.strip().split("\t") for ln in out.splitlines() if ln.startswith("\t")
    ]
    assert [v[0] for v in versions] == ["1.4.0", "1.3.3", "1.3.2"]
    assert versions[0][3] == "wip"
    assert versions[1][3] == "published"


def test_catalog_unknown_document(catalog_file, capsys):
    code, out = run(capsys, "catalog", "DSP9999", catalog_file=catalog_file)
    assert code == 2
    assert "unknown document" in out


def test_malformed_catalog_exits_1_with_key(tmp_path, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_text('schema_version = 1\n[families.x]\ntitle = "x"\n', encoding="utf-8")
    code, out = run(capsys, "catalog", catalog_file=bad)
    assert code == 1
    assert "families.x: missing key 'publisher'" in out


def test_fetch_latest_creates_library_and_announces_once(
    catalog_file, library, scripted, capsys
):
    scripted.responses[URL] = ok(PDF_BYTES)
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[0] == f"Library created at {library.root}"
    assert "fetched DSP0236 1.3.3 via direct" in out
    assert (library.specs / "mctp" / "DSP0236" / "1.3.3" / "original.pdf").exists()
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0
    assert "Library created" not in out
    assert "skipped DSP0236 1.3.3: already in Library" in out
    assert scripted.calls == [URL]


def test_fetch_specific_and_wip_versions(catalog_file, library, scripted, capsys):
    scripted.responses["https://example.test/DSP0236_1.3.2.pdf"] = ok(PDF_BYTES)
    scripted.responses["https://example.test/DSP0236_1.4.0.pdf"] = ok(PDF_BYTES)
    code, out = run(
        capsys, "fetch", "DSP0236", "--version", "1.3.2", catalog_file=catalog_file
    )
    assert code == 0 and "fetched DSP0236 1.3.2" in out
    code, out = run(capsys, "fetch", "DSP0236", "--wip", catalog_file=catalog_file)
    assert code == 0 and "fetched DSP0236 1.4.0" in out


def test_fetch_unknown_version_names_known_and_dropin_path(
    catalog_file, library, scripted, capsys
):
    code, out = run(
        capsys, "fetch", "IPMI", "--version", "1.5", catalog_file=catalog_file
    )
    assert code == 2
    assert "unknown version '1.5'" in out
    assert "Known: 2.0 rev 1.1" in out
    assert "specs/ipmi/IPMI/1.5/" in out
    assert scripted.calls == []


def test_fetch_unknown_document(catalog_file, library, scripted, capsys):
    code, out = run(capsys, "fetch", "DSP9999", catalog_file=catalog_file)
    assert code == 2
    assert "unknown document" in out


def test_fetch_requires_document_or_all(catalog_file, library, scripted, capsys):
    code, out = run(capsys, "fetch", catalog_file=catalog_file)
    assert code == 2
    code, out = run(capsys, "fetch", "DSP0236", "--all", catalog_file=catalog_file)
    assert code == 2


def test_fetch_failure_prints_url_and_path(catalog_file, library, scripted, capsys):
    scripted.responses[URL] = ok(HTML_BYTES, "text/html")
    scripted.responses[fetch_mod.WAYBACK_AVAILABLE + URL] = wayback_miss()
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 2
    assert f"Open in a browser: {URL}" in out
    assert str(library.specs / "mctp" / "DSP0236" / "1.3.3" / "original.pdf") in out
    assert "direct: not a pdf" in out


def test_fetch_force_redownloads(catalog_file, library, scripted, capsys):
    scripted.responses[URL] = ok(PDF_BYTES)
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "fetch", "DSP0236", "--force", catalog_file=catalog_file)
    assert code == 0 and "fetched" in out
    assert scripted.calls == [URL, URL]


def test_fetch_all_summarises_and_continues_past_failures(
    catalog_file, library, scripted, capsys
):
    ipmi = "https://example.test/ipmi-v2-rev1-1.pdf"
    scripted.responses[URL] = ok(PDF_BYTES)
    scripted.responses[fetch_mod.WAYBACK_AVAILABLE + ipmi] = wayback_hit(ipmi)
    scripted.responses["http://web.archive.org/web/20250101000000id_/" + ipmi] = ok(
        PDF_BYTES
    )
    bundle = "https://example.test/bundle_2026.1.zip"
    scripted.responses[bundle] = ok(HTML_BYTES, "text/html")
    scripted.responses[fetch_mod.WAYBACK_AVAILABLE + bundle] = wayback_miss()
    code, out = run(capsys, "fetch", "--all", catalog_file=catalog_file)
    assert code == 2
    assert "fetched DSP0236 1.3.3 via direct" in out
    assert "fetched IPMI 2.0 rev 1.1 via wayback" in out
    assert "failed BUNDLE 2026.1" in out
    assert "SECRET" not in out
    assert out.strip().splitlines()[-1] == "summary: fetched 2, skipped 0, failed 1"
    code, out = run(capsys, "fetch", "--all", catalog_file=catalog_file)
    assert "summary: fetched 0, skipped 2, failed 1" in out


def test_add_dropin_and_status(catalog_file, library, tmp_path, capsys):
    src = tmp_path / "secret.pdf"
    src.write_bytes(PDF_BYTES)
    code, out = run(
        capsys,
        "add",
        str(src),
        "--document",
        "secret",
        "--version",
        "0.9",
        catalog_file=catalog_file,
    )
    assert code == 0
    assert "added SECRET 0.9 as Drop-in" in out
    meta = json.loads(
        (library.specs / "vendor" / "SECRET" / "0.9" / "meta.json").read_text("utf-8")
    )
    assert meta["dropin"] is True and meta["url"] is None
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[0] == f"library: {library.root}"
    assert "vendor\tSECRET\t0.9\tdropin\t" in out


def test_add_rejects_missing_file_bad_type_unknown_document(
    catalog_file, library, tmp_path, capsys
):
    code, out = run(
        capsys,
        "add",
        str(tmp_path / "nope.pdf"),
        "--document",
        "SECRET",
        "--version",
        "1",
        catalog_file=catalog_file,
    )
    assert code == 2 and "file not found" in out
    txt = tmp_path / "x.txt"
    txt.write_text("x")
    code, out = run(
        capsys,
        "add",
        str(txt),
        "--document",
        "SECRET",
        "--version",
        "1",
        catalog_file=catalog_file,
    )
    assert code == 2 and "unsupported file type" in out
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(PDF_BYTES)
    code, out = run(
        capsys,
        "add",
        str(pdf),
        "--document",
        "NOPE",
        "--version",
        "1",
        catalog_file=catalog_file,
    )
    assert code == 2 and "unknown document" in out


def test_scan_registers_hand_placed_files(catalog_file, library, capsys):
    known = library.specs / "ipmi" / "IPMI" / "2.0_rev_1.1"
    known.mkdir(parents=True)
    (known / "original.pdf").write_bytes(PDF_BYTES)
    new_version = library.specs / "mctp" / "dsp0236" / "9.9.9"
    new_version.mkdir(parents=True)
    (new_version / "original.pdf").write_bytes(PDF_BYTES)
    unknown_doc = library.specs / "vendor" / "OEM-CMDS" / "1.0"
    unknown_doc.mkdir(parents=True)
    (unknown_doc / "original.pdf").write_bytes(PDF_BYTES)
    wrong_family = library.specs / "ipmi" / "DSP0236" / "1.3.3"
    wrong_family.mkdir(parents=True)
    (wrong_family / "original.pdf").write_bytes(PDF_BYTES)
    bad_type = library.specs / "mctp" / "DSP0236" / "1.3.2"
    bad_type.mkdir(parents=True)
    (bad_type / "original.docx").write_bytes(b"x")

    code, out = run(capsys, "scan", catalog_file=catalog_file)
    assert code == 0
    assert "registered IPMI 2.0 rev 1.1 as Drop-in" in out
    assert "registered DSP0236 9.9.9 as Drop-in" in out
    assert "registered OEM-CMDS 1.0 as Drop-in (not in catalog)" in out
    assert "belongs to family 'mctp', not 'ipmi'" in out
    assert "unsupported file type 'original.docx'" in out
    assert out.strip().splitlines()[-1] == "scan: registered 3, skipped 2"
    meta = json.loads((known / "meta.json").read_text("utf-8"))
    assert meta["version"] == "2.0 rev 1.1"
    assert meta["document"] == "IPMI"
    assert meta["dropin"] is True
    meta = json.loads((new_version / "meta.json").read_text("utf-8"))
    assert meta["document"] == "DSP0236" and meta["catalog_known"] is True
    code, out = run(capsys, "scan", catalog_file=catalog_file)
    assert "scan: registered 0, skipped 2" in out


def test_scan_on_missing_library(catalog_file, library, capsys):
    code, out = run(capsys, "scan", catalog_file=catalog_file)
    assert code == 0
    assert "no specs/ directory" in out


def test_status_empty(catalog_file, library, capsys):
    code, out = run(capsys, "status")
    assert code == 0
    assert "(empty)" in out


def test_output_survives_a_narrow_console_encoding(catalog_file, monkeypatch):
    # Windows consoles default to a legacy code page; DMTF titles carry "®".
    import io
    import sys

    text = catalog_file.read_text("utf-8").replace(
        'title = "MCTP Base Specification"', 'title = "PCIe® VDM Binding"'
    )
    catalog_file.write_text(text, encoding="utf-8", newline="")
    narrow = io.TextIOWrapper(io.BytesIO(), encoding="ascii", errors="strict")
    monkeypatch.setattr(sys, "stdout", narrow)
    code = main(["--catalog", str(catalog_file), "catalog", "DSP0236"])
    narrow.flush()
    assert code == 0
    assert "PCIe® VDM Binding" in narrow.buffer.getvalue().decode("utf-8")


def test_fetch_rejects_all_with_version(catalog_file, library, scripted, capsys):
    code, out = run(
        capsys, "fetch", "--all", "--version", "1.3.2", catalog_file=catalog_file
    )
    assert code == 2
    assert "--version" in out
    assert scripted.calls == []


def test_fetch_unknown_document_creates_no_library(
    catalog_file, library, scripted, capsys
):
    code, out = run(capsys, "fetch", "DSP9999", catalog_file=catalog_file)
    assert code == 2
    assert not library.root.exists()
    code, out = run(
        capsys, "fetch", "IPMI", "--version", "1.5", catalog_file=catalog_file
    )
    assert code == 2
    assert not library.root.exists()
    assert "Library created" not in out


def test_add_refuses_to_overwrite_without_force(
    catalog_file, library, scripted, tmp_path, capsys
):
    scripted.responses[URL] = ok(PDF_BYTES)
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    fetched_meta = json.loads((vdir / "meta.json").read_text("utf-8"))
    mine = tmp_path / "mine.pdf"
    mine.write_bytes(b"%PDF-1.4 my own copy")
    code, out = run(
        capsys,
        "add",
        str(mine),
        "--document",
        "DSP0236",
        "--version",
        "1.3.3",
        catalog_file=catalog_file,
    )
    assert code == 2
    assert "already in the Library" in out and "--force" in out
    assert (vdir / "original.pdf").read_bytes() == PDF_BYTES
    assert json.loads((vdir / "meta.json").read_text("utf-8")) == fetched_meta
    code, out = run(
        capsys,
        "add",
        str(mine),
        "--document",
        "DSP0236",
        "--version",
        "1.3.3",
        "--force",
        catalog_file=catalog_file,
    )
    assert code == 0
    assert "replaced DSP0236 1.3.3" in out
    assert (vdir / "original.pdf").read_bytes() == b"%PDF-1.4 my own copy"
    meta = json.loads((vdir / "meta.json").read_text("utf-8"))
    assert meta["dropin"] is True and meta["url"] is None


def test_add_rejects_file_with_wrong_magic(catalog_file, library, tmp_path, capsys):
    fake = tmp_path / "blocked.pdf"
    fake.write_bytes(HTML_BYTES)
    code, out = run(
        capsys,
        "add",
        str(fake),
        "--document",
        "SECRET",
        "--version",
        "0.9",
        catalog_file=catalog_file,
    )
    assert code == 2
    assert "not a pdf" in out
    assert not library.root.exists()


def test_scan_skips_file_with_wrong_magic(catalog_file, library, capsys):
    bad = library.specs / "mctp" / "DSP0236" / "1.3.2"
    bad.mkdir(parents=True)
    (bad / "original.pdf").write_bytes(HTML_BYTES)
    code, out = run(capsys, "scan", catalog_file=catalog_file)
    assert code == 0
    assert "is not a pdf" in out
    assert not (bad / "meta.json").exists()
    assert "scan: registered 0, skipped 1" in out


def test_add_reports_directory_collision(catalog_file, library, tmp_path, capsys):
    src = tmp_path / "a.pdf"
    src.write_bytes(PDF_BYTES)
    args = ["add", str(src), "--document", "SECRET"]
    code, _ = run(capsys, *args, "--version", "1.0 a", catalog_file=catalog_file)
    assert code == 0
    code, out = run(capsys, *args, "--version", "1.0_a", catalog_file=catalog_file)
    assert code == 2
    assert "already holds version '1.0 a'" in out


def _pdf_bytes(tmp_path, name="gen.pdf", numbered=False):
    from tests import pdfgen

    page = (
        pdfgen.numbered_page(1, ["alpha", "beta", "gamma", "delta", "epsilon"])
        if numbered
        else pdfgen.plain_page(["alpha", "beta"])
    )
    return pdfgen.write_pdf(tmp_path / name, [page]).read_bytes()


def test_extract_writes_files_then_skips_then_forces(
    catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    scripted.responses[URL] = ok(_pdf_bytes(tmp_path, numbered=True))
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    assert "extracted DSP0236 1.3.3: 1 pages" in out
    assert "line numbers on 1 pages" in out
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    assert (vdir / "extract.txt").read_text("utf-8").startswith("=== page 1 ===\nalpha")
    assert (vdir / "linemap.json").exists()
    meta = json.loads((vdir / "extract.json").read_text("utf-8"))
    assert meta["outline_source"] == "none"
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0 and "skipped DSP0236 1.3.3: already extracted" in out
    code, out = run(capsys, "extract", "DSP0236", "--force", catalog_file=catalog_file)
    assert code == 0 and "extracted DSP0236 1.3.3" in out
    code, out = run(capsys, "status", catalog_file=catalog_file)
    row = next(ln for ln in out.splitlines() if "DSP0236" in ln).split("\t")
    assert row[5:] == ["extracted", "none"]


def test_extract_reextracts_when_extractor_version_is_older(
    catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    scripted.responses[URL] = ok(_pdf_bytes(tmp_path))
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    meta = json.loads((vdir / "extract.json").read_text("utf-8"))
    meta["extractor_version"] = 0
    (vdir / "extract.json").write_text(json.dumps(meta), "utf-8")
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0 and "extracted DSP0236" in out


def test_extract_specific_version_and_missing(
    catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    scripted.responses["https://example.test/DSP0236_1.3.2.pdf"] = ok(
        _pdf_bytes(tmp_path)
    )
    run(capsys, "fetch", "DSP0236", "--version", "1.3.2", catalog_file=catalog_file)
    code, out = run(
        capsys, "extract", "DSP0236", "--version", "1.3.2", catalog_file=catalog_file
    )
    assert code == 0 and "extracted DSP0236 1.3.2" in out
    # latest (1.3.3) is not held: fall back to the held version
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0 and "skipped DSP0236 1.3.2: already extracted" in out
    code, out = run(capsys, "extract", "IPMI", catalog_file=catalog_file)
    assert code == 2 and "not in the Library" in out
    code, out = run(
        capsys, "extract", "DSP0236", "--version", "9.9", catalog_file=catalog_file
    )
    assert code == 2


def test_extract_all_skips_zip_and_summarises(
    catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    scripted.responses[URL] = ok(_pdf_bytes(tmp_path))
    scripted.responses["https://example.test/bundle_2026.1.zip"] = ok(
        ZIP_BYTES, "application/zip"
    )
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    run(capsys, "fetch", "BUNDLE", catalog_file=catalog_file)
    code, out = run(capsys, "extract", "--all", catalog_file=catalog_file)
    assert code == 0, out
    assert "skipped BUNDLE 2026.1: no json-schema/ folder in the archive" in out
    assert out.strip().splitlines()[-1] == "summary: extracted 1, skipped 1, failed 0"
    code, out = run(
        capsys, "extract", "--all", "--version", "1", catalog_file=catalog_file
    )
    assert code == 2
    code, out = run(capsys, "extract", catalog_file=catalog_file)
    assert code == 2


def test_extract_broken_pdf_fails_without_traceback(
    catalog_file, library, scripted, capsys
):
    pytest.importorskip("pypdfium2")
    scripted.responses[URL] = ok(b"%PDF-1.4 garbage")
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 2
    assert "failed DSP0236 1.3.3" in out


def test_extract_picks_the_newest_held_version_by_catalog_date(
    catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    # catalog: 1.3.2 (2024-01-02) < 1.3.3 (2024-03-25) < 1.4.0 wip; hold the
    # two published ones only after renaming so directory order misleads.
    scripted.responses["https://example.test/DSP0236_1.3.2.pdf"] = ok(
        _pdf_bytes(tmp_path)
    )
    scripted.responses["https://example.test/DSP0236_1.4.0.pdf"] = ok(
        _pdf_bytes(tmp_path)
    )
    run(capsys, "fetch", "DSP0236", "--version", "1.3.2", catalog_file=catalog_file)
    run(capsys, "fetch", "DSP0236", "--wip", catalog_file=catalog_file)
    # latest published (1.3.3) is not held: newest held by date is 1.4.0
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0 and "extracted DSP0236 1.4.0" in out


def test_extract_unknown_document_uses_fetch_time(
    catalog_file, library, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    from tests import pdfgen

    older = library.specs / "vendor" / "OEM" / "1.10.0"
    newer = library.specs / "vendor" / "OEM" / "1.9.0"
    for vdir, stamp in (
        (older, "2025-01-01T00:00:00+00:00"),
        (newer, "2025-06-01T00:00:00+00:00"),
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
    code, out = run(capsys, "extract", "OEM", catalog_file=catalog_file)
    assert code == 0 and "extracted OEM 1.9.0" in out


# ------------------------------------------------- M8 follow-ups: round 1


def test_catalog_document_lists_same_day_versions_newest_first_by_number(
    tmp_path, capsys
):
    # Round-1 F3: DSP0276 1.3.0 and 2.0.0 share a date; the listing under
    # "versions:" must agree with the latest: line.
    from tests.test_catalog import _two_versions

    path = tmp_path / "catalog.toml"
    path.write_text(_two_versions("1.3.0", "2.0.0"), encoding="utf-8", newline="")
    code, out = run(capsys, "catalog", "DSP0276", catalog_file=path)
    assert code == 0
    lines = out.splitlines()
    assert "latest: 2.0.0" in lines
    listed = [ln.split("\t")[1] for ln in lines if ln.startswith("\t")]
    assert listed == ["2.0.0", "1.3.0"]
