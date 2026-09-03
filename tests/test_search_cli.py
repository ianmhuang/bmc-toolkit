"""The reading commands through the CLI: find, section, page, render, their
companions and error paths. Documents are synthetic PDFs from pdfgen."""

import json
import struct
import sys
import zlib

import pytest

from bmc_toolkit.spec import extract as extract_mod
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import MINI_CATALOG, ZIP_BYTES, ok

pytest.importorskip("pypdfium2")

URL = "https://example.test/DSP0236_1.3.3.pdf"
IPMI_URL = "https://example.test/ipmi-v2-rev1-1.pdf"
UPDATE_URL = "https://example.test/ipmi-update.pdf"

# IPMI is searched together with an errata document that the mini catalog
# does not have; the tests that need it use this catalog.
COMPANION_CATALOG = (
    MINI_CATALOG.replace(
        'title = "IPMI Specification v2.0"',
        'title = "IPMI Specification v2.0"\nsearched_with = ["IPMI-UPDATE"]',
    ).replace('fetch = "wayback"', 'fetch = "direct"')
    + """
[[documents]]
id = "IPMI-UPDATE"
family = "ipmi"
title = "IPMI Specification Update"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "Errata 7"
url = "https://example.test/ipmi-update.pdf"
type = "pdf"
published = "2015-04-01"
"""
)


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def mctp_pdf(tmp_path):
    """Two numbered pages with bookmarks, a diagonal drawing on page 2."""
    page1 = pdfgen.numbered_page(
        100,
        [
            "8 MCTP base protocol",
            "8.1 Overview",
            "The base protocol defines the common fields.",
            "8.2 MCTP packet fields",
            "Msg tag 3 bits Message tag",
            "TO 1 bit Tag owner",
        ],
    )
    page2 = pdfgen.numbered_page(
        106,
        ["8.3 Message assembly", "Figure text inside", "", "Msg Tag repeated"],
    )
    # a diagram around the second line of page 2: y of line index 1 is 706
    page2 += [
        ("rect", 60, 690, 300, 40),
        ("line", 60, 690, 360, 730),
        ("line", 360, 690, 400, 730),
    ]
    return pdfgen.write_pdf(
        tmp_path / "mctp.pdf",
        [page1, page2],
        bookmarks=[
            (0, "8 MCTP base protocol", 0),
            (1, "8.1 Overview", 0),
            (1, "8.2 MCTP packet fields", 0),
            (1, "8.3 Message assembly", 1),
        ],
    ).read_bytes()


def plain_pdf(tmp_path, name, lines):
    return pdfgen.write_pdf(tmp_path / name, [pdfgen.plain_page(lines)]).read_bytes()


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    """DSP0236 fetched and extracted."""
    scripted.responses[URL] = ok(mctp_pdf(tmp_path))
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


# ---------------------------------------------------------------- find


def test_find_prints_page_line_section_and_text(held, catalog_file, capsys):
    code, out = run(capsys, "find", "DSP0236", "msg tag", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.strip().splitlines()
    assert lines[0] == (
        "DSP0236 p.1 line 104 | 8.2 MCTP packet fields | Msg tag 3 bits Message tag"
    )
    assert lines[1] == "DSP0236 p.2 line 109 | 8.3 Message assembly | Msg Tag repeated"
    assert len(lines) == 2


def test_find_case_regex_context_and_max(held, catalog_file, capsys):
    code, out = run(
        capsys, "find", "DSP0236", "msg tag", "--case", catalog_file=catalog_file
    )
    assert code == 0 and out.strip() == "no hits"
    code, out = run(
        capsys,
        "find",
        "DSP0236",
        r"Msg [Tt]ag",
        "--regex",
        "--case",
        catalog_file=catalog_file,
    )
    assert code == 0 and len(out.strip().splitlines()) == 2
    code, out = run(
        capsys,
        "find",
        "DSP0236",
        "Overview",
        "--context",
        "1",
        catalog_file=catalog_file,
    )
    lines = out.strip().splitlines()
    assert lines[0].startswith("DSP0236 p.1 line 101 | 8.1 Overview | 8.1 Overview")
    assert lines[1] == "    line 100: 8 MCTP base protocol"
    assert lines[2] == "    line 102: The base protocol defines the common fields."
    assert lines[3] == "--"
    code, out = run(
        capsys, "find", "DSP0236", "msg tag", "--max", "1", catalog_file=catalog_file
    )
    lines = out.strip().splitlines()
    assert len(lines) == 2
    assert lines[1] == "1 more hits not shown; narrow the pattern or raise --max"
    code, out = run(
        capsys, "find", "DSP0236", "msg tag", "--max", "0", catalog_file=catalog_file
    )
    assert len(out.strip().splitlines()) == 2  # 0 lifts the cap


def test_find_marks_lines_inside_a_figure(held, catalog_file, capsys):
    figures = json.loads((held / "figures.json").read_text("utf-8"))
    assert list(figures["pages"]) == ["2"]
    assert 1 in figures["pages"]["2"]["lines"]
    code, out = run(capsys, "find", "DSP0236", "inside", catalog_file=catalog_file)
    assert out.strip() == (
        "DSP0236 p.2 line 107 | 8.3 Message assembly | [figure] Figure text inside"
    )


def test_find_bad_regex_exits_2(held, catalog_file, capsys):
    code, out = run(
        capsys, "find", "DSP0236", "(", "--regex", catalog_file=catalog_file
    )
    assert code == 2 and "bad regular expression" in out


def test_find_searches_companions_first_and_notes_missing_ones(
    library, scripted, tmp_path, capsys
):
    cat = tmp_path / "companion.toml"
    cat.write_text(COMPANION_CATALOG, encoding="utf-8", newline="")
    scripted.responses[IPMI_URL] = ok(
        plain_pdf(tmp_path, "ipmi.pdf", ["Get Device ID NetFn App", "other"])
    )
    scripted.responses[UPDATE_URL] = ok(
        plain_pdf(tmp_path, "upd.pdf", ["Get Device ID errata", "x"])
    )
    run(capsys, "fetch", "IPMI", catalog_file=cat)
    run(capsys, "extract", "IPMI", catalog_file=cat)
    code, out = run(capsys, "find", "IPMI", "get device id", catalog_file=cat)
    assert code == 0
    lines = out.strip().splitlines()
    assert lines[0] == (
        "note: IPMI-UPDATE is not in the Library; run: bmcspec fetch IPMI-UPDATE"
    )
    assert lines[1].startswith("IPMI p.1 | - | Get Device ID NetFn App")
    run(capsys, "fetch", "IPMI-UPDATE", catalog_file=cat)
    code, out = run(capsys, "find", "IPMI", "get device id", catalog_file=cat)
    lines = out.strip().splitlines()
    assert lines[0].startswith("note: IPMI-UPDATE Errata 7 is not extracted")
    run(capsys, "extract", "IPMI-UPDATE", catalog_file=cat)
    code, out = run(capsys, "find", "IPMI", "get device id", catalog_file=cat)
    lines = out.strip().splitlines()
    assert lines[0].startswith("IPMI-UPDATE p.1 | - | Get Device ID errata")
    assert lines[1].startswith("IPMI p.1 | - | Get Device ID NetFn App")
    code, out = run(capsys, "find", "IPMI", "get device id", "--only", catalog_file=cat)
    lines = out.strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith("IPMI p.1")


# ------------------------------------------------------------- section


def test_section_by_number_and_by_words(held, catalog_file, capsys):
    code, out = run(capsys, "section", "DSP0236", "8.2", catalog_file=catalog_file)
    assert code == 0
    assert out.strip() == "1 | 8.2 MCTP packet fields | pages 1-2"
    code, out = run(capsys, "section", "DSP0236", "8", catalog_file=catalog_file)
    assert out.strip().splitlines() == [
        "0 | 8 MCTP base protocol | pages 1-2",
        "1 | 8.1 Overview | pages 1-1",
        "1 | 8.2 MCTP packet fields | pages 1-2",
        "1 | 8.3 Message assembly | pages 2-2",
    ]
    code, out = run(
        capsys, "section", "DSP0236", "message ASSEMBLY", catalog_file=catalog_file
    )
    assert out.strip() == "1 | 8.3 Message assembly | pages 2-2"
    code, out = run(capsys, "section", "DSP0236", "nope", catalog_file=catalog_file)
    assert code == 0 and out.strip() == "no matching section"


def test_section_marks_approximate_pages(
    library, catalog_file, scripted, tmp_path, capsys
):
    # a contents page and body pages without any page numbers
    contents = [(72, 740, "Contents")]
    y = 720.0
    for num, title, page in [
        ("1", "Intro", 1),
        ("1.1", "Scope", 1),
        ("2", "Overview", 2),
        ("2.1", "Arch", 2),
        ("3", "Commands", 3),
        ("3.1", "Get", 3),
        ("3.2", "Set", 3),
        ("4", "Errors", 4),
    ]:
        contents.append((72, y, f"{num} {title} ............ {page}"))
        y -= 14
    pages = [contents] + [[(72, 700, "body text without any number")] for _ in range(5)]
    scripted.responses[URL] = ok(
        pdfgen.write_pdf(tmp_path / "u.pdf", pages).read_bytes()
    )
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "section", "DSP0236", "2", catalog_file=catalog_file)
    assert out.strip().splitlines() == [
        "0 | 2 Overview | pages ~2-3",
        "1 | 2.1 Arch | pages ~2-3",
    ]
    code, out = run(capsys, "page", "DSP0236", "2", catalog_file=catalog_file)
    # both entries claim page 2 and neither heading is on it: the last owns
    assert out.splitlines()[0].split(" | ")[2] == "~2.1 Arch"


# ---------------------------------------------------------------- page


def test_page_prints_cite_header_and_numbered_lines(held, catalog_file, capsys):
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == " | ".join(
        [
            "cite: mctp",
            "DSP0236 1.3.3",
            "8 MCTP base protocol",
            "PDF page 1",
            "lines 100-105",
            URL,
            str(held),
        ]
    )
    assert lines[1] == " 100  8 MCTP base protocol"
    assert lines[5] == " 104  Msg tag 3 bits Message tag"
    assert len(lines) == 7


def test_page_range_section_and_limits(held, catalog_file, capsys):
    code, out = run(
        capsys, "page", "DSP0236", "1", "--to", "2", catalog_file=catalog_file
    )
    assert code == 0
    cites = [ln for ln in out.splitlines() if ln.startswith("cite:")]
    assert len(cites) == 2 and "PDF page 2" in cites[1]
    assert "[figure]" in out
    code, out = run(
        capsys, "page", "DSP0236", "--section", "8.3", catalog_file=catalog_file
    )
    assert code == 0
    assert out.splitlines()[0].split(" | ")[3] == "PDF page 2"
    assert out.count("cite:") == 1
    code, out = run(
        capsys,
        "page",
        "DSP0236",
        "1",
        "--to",
        "2",
        "--max-pages",
        "1",
        catalog_file=catalog_file,
    )
    assert code == 2 and "limit is 1" in out
    code, out = run(capsys, "page", "DSP0236", "3", catalog_file=catalog_file)
    assert code == 2 and "outside DSP0236 1.3.3 (pages 1-2)" in out
    code, out = run(
        capsys, "page", "DSP0236", "--section", "nope", catalog_file=catalog_file
    )
    assert code == 2 and "no matching section" in out
    code, out = run(capsys, "page", "DSP0236", catalog_file=catalog_file)
    assert code == 2
    code, out = run(
        capsys, "page", "DSP0236", "1", "--section", "8", catalog_file=catalog_file
    )
    assert code == 2


# -------------------------------------------------------------- render


def test_render_writes_png_without_pillow(held, catalog_file, capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "PIL", None)  # any import of PIL would fail
    code, out = run(
        capsys, "render", "DSP0236", "--page", "2", catalog_file=catalog_file
    )
    assert code == 0, out
    png = held / "renders" / "page-2.png"
    assert out.splitlines()[0] == f"rendered {png}"
    cite = out.splitlines()[1].split(" | ")
    assert cite[0] == "cite: mctp" and cite[3] == "PDF page 2"
    assert cite[4] == "lines rendered page"
    data = png.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height, depth, colour = struct.unpack(">IIBB", data[16:26])
    assert (width, height, depth, colour) == (1224, 1584, 8, 2)
    idat = data.index(b"IDAT")
    length = struct.unpack(">I", data[idat - 4 : idat])[0]
    raw = zlib.decompress(data[idat + 4 : idat + 4 + length])
    assert len(raw) == height * (1 + width * 3)
    assert raw[1:4] == b"\xff\xff\xff"  # top-left pixel of a white page
    mtime = png.stat().st_mtime
    code, out = run(
        capsys, "render", "DSP0236", "--page", "2", catalog_file=catalog_file
    )
    assert code == 0 and "existing" in out and png.stat().st_mtime == mtime
    code, out = run(
        capsys,
        "render",
        "DSP0236",
        "--page",
        "2",
        "--force",
        "--scale",
        "1",
        catalog_file=catalog_file,
    )
    assert code == 0 and "existing" not in out
    assert struct.unpack(">II", png.read_bytes()[16:24]) == (612, 792)
    code, out = run(
        capsys, "render", "DSP0236", "--page", "9", catalog_file=catalog_file
    )
    assert code == 2 and "outside" in out


def test_replacing_the_original_removes_renders(
    held, catalog_file, library, tmp_path, capsys
):
    run(capsys, "render", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert (held / "renders" / "page-1.png").exists()
    mine = tmp_path / "mine.pdf"
    mine.write_bytes(mctp_pdf(tmp_path))
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
    assert not (held / "renders").exists()
    assert not (held / "figures.json").exists()


# --------------------------------------------------------- error paths


@pytest.mark.parametrize("command", ["find", "section", "page", "render"])
def test_reading_commands_share_the_error_paths(
    command, catalog_file, library, scripted, tmp_path, capsys
):
    def call(*extra):
        argv = {
            "find": ["find", "DSP0236", "x"],
            "section": ["section", "DSP0236", "x"],
            "page": ["page", "DSP0236", "1"],
            "render": ["render", "DSP0236", "--page", "1"],
        }[command]
        return run(capsys, *argv, *extra, catalog_file=catalog_file)

    code, out = call()
    assert code == 2
    assert out.strip() == "DSP0236 is not in the Library; run: bmcspec fetch DSP0236"
    scripted.responses[URL] = ok(plain_pdf(tmp_path, "a.pdf", ["alpha"]))
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = call()
    assert code == 2
    assert out.startswith("DSP0236 1.3.3 is not extracted")
    assert 'run: bmcspec extract DSP0236 --version "1.3.3"' in out
    code, out = call("--version", "1.3.2")
    assert code == 2
    assert out.strip() == "DSP0236 1.3.2 is not in the Library; held: 1.3.3"
    run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    code, out = call()
    assert code == 0, out
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    meta = json.loads((vdir / "extract.json").read_text("utf-8"))
    meta["extractor_version"] = extract_mod.EXTRACTOR_VERSION - 1
    (vdir / "extract.json").write_text(json.dumps(meta), "utf-8")
    code, out = call()
    assert code == 2 and "older version of the extractor" in out
    code, out = run(capsys, "status", catalog_file=catalog_file)
    row = next(ln for ln in out.splitlines() if "DSP0236" in ln).split("\t")
    assert row[5] == "stale"


def test_bundles_are_refused(catalog_file, library, scripted, capsys):
    scripted.responses["https://example.test/bundle_2026.1.zip"] = ok(
        ZIP_BYTES, "application/zip"
    )
    run(capsys, "fetch", "BUNDLE", catalog_file=catalog_file)
    code, out = run(capsys, "find", "BUNDLE", "x", catalog_file=catalog_file)
    assert code == 2
    assert (
        out.strip() == "BUNDLE 2026.1 is a zip bundle; bundles are not searchable yet"
    )


def test_corrupt_extract_is_an_error_not_a_traceback(held, catalog_file, capsys):
    (held / "extract.txt").write_text("no markers\n", "utf-8")
    code, out = run(capsys, "find", "DSP0236", "x", catalog_file=catalog_file)
    assert code == 1 and "cannot read DSP0236 1.3.3" in out
