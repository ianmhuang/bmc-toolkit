"""Acceptance tests for the reading commands on pages whose printed line
numbers the Extract missed (AC-6, AC-7, AC-8), black-box through the CLI on
synthetic PDFs. No network: the scripted client serves the bytes.

The document held as DSP0236 1.3.3 has a table page (106-107) and a short
page (108-109) between two pages the page-by-page rules number (100-105 and
110-115). On the base branch pages 2 and 3 print ``lines -``.
"""

import json

import pytest

from bmc_toolkit.spec import extract as ex
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok

pytest.importorskip("pypdfium2")

URL = "https://example.test/DSP0236_1.3.3.pdf"
URL_OLDER = "https://example.test/DSP0236_1.3.2.pdf"
FIRST = [
    "1 Introduction",
    "This document describes the widget bus.",
    "Scope text follows.",
    "More scope text.",
    "Reserved fields are zero.",
    "End of the first page.",
]
LAST = [
    "2 Commands",
    "Frobnicate sets the FROB bit.",
    "Reset clears it.",
    "Both take one byte.",
    "Neither answers.",
    "End of the last page.",
]


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def table_page(numbers, rows=5, footer=None):
    """A text line behind each margin number, then table rows that start
    with a byte offset, then a footer that starts with the page number."""
    items = []
    y = 720.0
    for n in numbers:
        items += [(37, y, str(n)), (72, y, f"Row text {n}")]
        y -= 14
    for off in range(rows):
        items += [(75, y, str(off)), (120, y, "uint8"), (200, y, f"field at {off}")]
        y -= 14
    if footer is not None:
        items += [(72, 40, str(footer)), (284, 40, "Published")]
    return items


def short_page(first):
    return [
        (37, 700, str(first)),
        (72, 700, "Key: D = device"),
        (37, 686, str(first + 1)),
        (72, 686, "Second key line"),
    ]


def numbered_lines(first, texts):
    """What ``page`` prints for lines numbered from ``first``."""
    return [f"{first + i:>4}  {text}" for i, text in enumerate(texts)]


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    pages = [
        pdfgen.numbered_page(100, FIRST),
        table_page([106, 107], footer=2),
        short_page(108),
        pdfgen.numbered_page(110, LAST),
    ]
    pdf = pdfgen.write_pdf(
        tmp_path / "doc.pdf",
        pages,
        bookmarks=[(0, "1 Introduction", 0), (0, "2 Commands", 3)],
    )
    scripted.responses[URL] = ok(pdf.read_bytes())
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


def cite_and_body(out):
    """The fields of the first ``cite:`` line and the lines after it."""
    lines = out.splitlines()
    at = next(i for i, ln in enumerate(lines) if ln.startswith("cite:"))
    return lines[at].split(" | "), lines[at + 1 :]


# ------------------------------------------------------------------- AC-6


def test_ac6_page_prints_a_recovered_page_behind_its_printed_numbers(
    held, catalog_file, capsys
):
    code, out = run(capsys, "page", "DSP0236", "2", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].split(" | ")[3:5] == ["PDF page 2", "lines 106-107"]
    # the numbers are the prefix and are gone from the text
    assert lines[1:3] == [" 106  Row text 106", " 107  Row text 107"]
    # the table rows and the footer keep their integers and have no number
    assert len(lines) == 9
    assert all(ln[:6] == " " * 6 for ln in lines[3:])
    assert [ln.split()[:2] for ln in lines[3:8]] == [
        [str(off), "uint8"] for off in range(5)
    ]
    assert lines[8].split() == ["2", "Published"]

    code, out = run(capsys, "page", "DSP0236", "3", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].split(" | ")[3:5] == ["PDF page 3", "lines 108-109"]
    assert lines[1:] == [" 108  Key: D = device", " 109  Second key line"]


def test_ac6_find_names_the_printed_line_on_a_recovered_page(
    held, catalog_file, capsys
):
    code, out = run(capsys, "find", "DSP0236", "Row text 107", catalog_file=catalog_file)
    assert code == 0, out
    hits = out.strip().splitlines()
    assert len(hits) == 1
    assert hits[0].startswith("DSP0236 p.2 line 107 | ")
    assert hits[0].endswith(" | Row text 107")
    code, out = run(capsys, "find", "DSP0236", "second key", catalog_file=catalog_file)
    assert code == 0, out
    hits = out.strip().splitlines()
    assert len(hits) == 1
    assert hits[0].startswith("DSP0236 p.3 line 109 | ")
    assert hits[0].endswith(" | Second key line")
    # a line of the page without a printed number names the page only
    code, out = run(capsys, "find", "DSP0236", "field at 3", catalog_file=catalog_file)
    assert code == 0, out
    hits = out.strip().splitlines()
    assert len(hits) == 1
    assert hits[0].startswith("DSP0236 p.2 | ")


# ------------------------------------------------------------------- AC-7


def test_ac7_an_extract_of_version_4_is_made_again_on_the_next_use(
    held, catalog_file, capsys
):
    assert ex.EXTRACTOR_VERSION >= 5
    meta_path = held / "extract.json"
    linemap_path = held / "linemap.json"
    meta = json.loads(meta_path.read_text("utf-8"))
    assert meta["extractor_version"] == ex.EXTRACTOR_VERSION
    # what the extractor of version 4 left: no entry for pages 2 and 3
    linemap = json.loads(linemap_path.read_text("utf-8"))
    for n in ("2", "3"):
        linemap["pages"].pop(n, None)
    linemap_path.write_text(json.dumps(linemap), encoding="utf-8", newline="")
    meta_path.write_text(
        json.dumps({**meta, "extractor_version": 4}), encoding="utf-8", newline=""
    )
    # a reading command, no --force
    code, out = run(capsys, "page", "DSP0236", "2", catalog_file=catalog_file)
    assert code == 0, out
    fields, body = cite_and_body(out)
    assert fields[3:5] == ["PDF page 2", "lines 106-107"]
    assert body[0] == " 106  Row text 106"
    meta = json.loads(meta_path.read_text("utf-8"))
    assert meta["extractor_version"] == ex.EXTRACTOR_VERSION
    assert meta["line_numbers"] is True
    assert meta["line_numbered_pages"] == 4
    # linemap.json keeps its format: pages, each with first, last and lines
    # (the index of the line within the page's block to its printed number)
    stored = json.loads(linemap_path.read_text("utf-8"))
    assert set(stored) == {"pages"}
    assert sorted(stored["pages"]) == ["1", "2", "3", "4"]
    for page in stored["pages"].values():
        assert set(page) == {"first", "last", "lines"}
        assert all(k.isdigit() and isinstance(v, int) for k, v in page["lines"].items())
        numbers = [page["lines"][k] for k in sorted(page["lines"], key=int)]
        assert (page["first"], page["last"]) == (numbers[0], numbers[-1])
    assert stored["pages"]["2"] == {
        "first": 106,
        "last": 107,
        "lines": {"0": 106, "1": 107},
    }
    assert stored["pages"]["3"] == {
        "first": 108,
        "last": 109,
        "lines": {"0": 108, "1": 109},
    }


# ------------------------------------------------------------------- AC-8


def test_ac8_pages_numbered_before_and_a_document_without_a_line_map_read_as_before(
    held, catalog_file, library, scripted, tmp_path, capsys
):
    # the premise, which the base branch does not meet: the document holds
    # newly numbered pages
    code, out = run(capsys, "page", "DSP0236", "2", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[0].split(" | ")[4] == "lines 106-107"

    # the pages numbered before print what the base branch prints
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    fields = lines[0].split(" | ")
    assert fields[:2] == ["cite: mctp", "DSP0236 1.3.3"]
    assert fields[3:] == ["PDF page 1", "lines 100-105", URL, str(held)]
    assert lines[1:] == numbered_lines(100, FIRST)
    code, out = run(capsys, "page", "DSP0236", "4", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].split(" | ")[3:5] == ["PDF page 4", "lines 110-115"]
    assert lines[1:] == numbered_lines(110, LAST)
    code, out = run(capsys, "find", "DSP0236", "widget bus", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip().splitlines() == [
        "DSP0236 p.1 line 101 | 1 Introduction | "
        "This document describes the widget bus."
    ]
    code, out = run(capsys, "find", "DSP0236", "FROB bit", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip().splitlines() == [
        "DSP0236 p.4 line 111 | 2 Commands | Frobnicate sets the FROB bit."
    ]
    code, out = run(capsys, "section", "DSP0236", "Commands", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip() == "0 | 2 Commands | pages 4-4"

    # a document without a Line Map: the same table page and short page with
    # no numbered page beside them, held as the older version
    plain = pdfgen.write_pdf(
        tmp_path / "plain.pdf", [table_page([106, 107], footer=1), short_page(108)]
    )
    scripted.responses[URL_OLDER] = ok(plain.read_bytes())
    older = ("--version", "1.3.2")
    run(capsys, "fetch", "DSP0236", *older, catalog_file=catalog_file)
    code, out = run(capsys, "extract", "DSP0236", *older, catalog_file=catalog_file)
    assert code == 0, out
    older_dir = library.specs / "mctp" / "DSP0236" / "1.3.2"
    assert not (older_dir / "linemap.json").exists()
    code, out = run(capsys, "page", "DSP0236", "1", *older, catalog_file=catalog_file)
    assert code == 0, out
    fields, body = cite_and_body(out)
    assert fields[1] == "DSP0236 1.3.2"
    assert fields[3:5] == ["PDF page 1", "lines -"]
    # no prefix, and the integers of the margin stay in the text
    assert body[0].startswith("106")
    assert body[0].split() == ["106", "Row", "text", "106"]
    assert body[1].split() == ["107", "Row", "text", "107"]
    code, out = run(capsys, "page", "DSP0236", "2", *older, catalog_file=catalog_file)
    assert code == 0, out
    fields, body = cite_and_body(out)
    assert fields[3:5] == ["PDF page 2", "lines -"]
    assert body[0].split() == ["108", "Key:", "D", "=", "device"]
    code, out = run(
        capsys, "find", "DSP0236", "Row text 107", *older, catalog_file=catalog_file
    )
    assert code == 0, out
    hits = [ln for ln in out.splitlines() if ln.startswith("DSP0236 p.")]
    assert len(hits) == 1
    assert hits[0].startswith("DSP0236 p.1 | ")
