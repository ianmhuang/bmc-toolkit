"""Reviewer acceptance tests for the table command through the CLI
(AC-1, AC-5, AC-6, AC-7, AC-8, AC-9): output shape, the store, its removal,
the Citation form, the error paths, and life without pdfplumber. Synthetic
ruled PDFs only; the scripted client keeps the network out."""

import json
import sys

import pytest

from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok

pytest.importorskip("pypdfium2")
pytest.importorskip("pdfplumber")

URL = "https://example.test/DSP0236_1.3.3.pdf"
WIDTHS = [100, 80, 200]
HEADER = ["Name", "Code", "Meaning"]


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def grid(x, top, widths, heights, cells):
    """A Word-style ruled table: thin filled rectangles as rules, text in
    each cell; ``top`` is the table's top edge in PDF points (origin
    bottom-left). A cell is a string or a list of lines."""
    items = []
    total_w = sum(widths)
    total_h = sum(heights)
    xs = [x]
    for w in widths:
        xs.append(xs[-1] + w)
    ys = [top]
    for h in heights:
        ys.append(ys[-1] - h)
    for y in ys:
        items.append(("fill", x, y - 0.3, total_w, 0.6))
    for cx in xs:
        items.append(("fill", cx - 0.3, top - total_h, 0.6, total_h))
    for r, row in enumerate(cells):
        for c, cell in enumerate(row):
            lines = cell if isinstance(cell, list) else [cell]
            for k, text in enumerate(lines):
                if text:
                    items.append((xs[c] + 3, ys[r] - 11 - 12 * k, text))
    return items


def furniture(n):
    return [(72, 760, "Spec Title"), (300, 40, f"Page {n}")]


def document(tmp_path):
    """Page 1: a heading, a captioned table that runs onto page 2 (header
    repeated), then a second heading below the table. Page 2: the rest of
    the table. Page 3: a single-page table with a two-line cell and no
    caption. Page 4: prose only."""
    page1 = furniture(1) + [
        (72, 740, "5 Codes"),
        (72, 714, "Table 1 - Codes"),
    ]
    page1 += grid(
        72,
        700,
        WIDTHS,
        [16] * 3,
        [HEADER, ["Temperature", "01h", "degrees"], ["Voltage", "02h", "volts"]],
    )
    page1 += [(72, 640, "5.1 After the table")]
    # page 1 has body text below the table, so the table must not merge
    # with page 2 by geometry alone: put the continuation on page 2 of a
    # second pair instead (pages 2-3 below)
    page2 = furniture(2) + [(72, 214, "Table 2 - Split")]
    page2 += grid(
        72,
        200,
        WIDTHS,
        [16] * 3,
        [HEADER, ["Current", "03h", "amps"], ["Fan", "04h", "rpm"]],
    )
    page3 = furniture(3) + grid(
        72,
        740,
        WIDTHS,
        [16] * 3,
        [HEADER, ["Power", "05h", "watts"], ["Speed", "06h", "rpm"]],
    )
    # prose (not a caption) right above the table: stops a merge with page
    # 3's table, and AC-5 says a non-caption nearest line gives no caption
    page4 = furniture(4) + [(72, 714, "The processor events are listed below.")]
    page4 += grid(
        72,
        700,
        WIDTHS,
        [16, 28],
        [HEADER, ["Processor", "07h", ["IERR", "Thermal Trip"]]],
    )
    page5 = furniture(5) + [(72, 700, "6 Nothing ruled here")]
    return pdfgen.write_pdf(
        tmp_path / "doc.pdf",
        [page1, page2, page3, page4, page5],
        bookmarks=[
            (0, "5 Codes", 0),
            (1, "5.1 After the table", 0),
            (0, "6 Nothing ruled here", 4),
        ],
    ).read_bytes()


@pytest.fixture
def fetched(catalog_file, library, scripted, tmp_path, capsys):
    scripted.responses[URL] = ok(document(tmp_path))
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


@pytest.fixture
def held(fetched, catalog_file, capsys):
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return fetched


# ---------------------------------------------------------- AC-1 / AC-7


def test_single_page_table_output_shape(held, catalog_file, capsys):
    """AC-1: cite line, table: line, header, rule, body rows. AC-7: a
    single-page table cites ``PDF page N`` and ``table K``."""
    code, out = run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].split(" | ") == [
        "cite: mctp",
        "DSP0236 1.3.3",
        "5 Codes",
        "PDF page 1",
        "lines table 1",
        URL,
        str(held),
    ]
    assert lines[1] == "table: Table 1 - Codes | ruled | page 1 | 3 columns | 3 rows"
    assert lines[2] == "Name        | Code | Meaning"
    assert lines[3] == "------------+------+--------"
    assert lines[4:] == [
        "Temperature | 01h  | degrees",
        "Voltage     | 02h  | volts",
    ]


def test_multi_line_cell_gets_one_physical_line_per_cell_line_and_a_rule(
    held, catalog_file, capsys
):
    """AC-1: a row with a two-line cell prints two lines and is followed
    by a rule line; AC-5: no caption prints ``-``."""
    code, out = run(capsys, "table", "DSP0236", "--page", "4", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[1] == "table: - | ruled | page 4 | 3 columns | 2 rows"
    assert lines[2:] == [
        "Name      | Code | Meaning",
        "----------+------+-------------",
        "Processor | 07h  | IERR",
        "          |      | Thermal Trip",
        "----------+------+-------------",
    ]


def test_spanning_table_cites_the_page_range_and_page_output_is_unchanged(
    held, catalog_file, capsys
):
    """AC-3 / AC-7: the table split over pages 2-3 prints once, with
    ``PDF pages 2-3``, the header once and every row; ``page`` still cites
    a single page with ``lines -``."""
    for n in ("2", "3"):
        code, out = run(capsys, "table", "DSP0236", "--page", n, catalog_file=catalog_file)
        assert code == 0, out
        lines = out.splitlines()
        fields = lines[0].split(" | ")
        assert fields[3] == "PDF pages 2-3"
        assert fields[4] == "lines table 1"
        assert lines[1] == "table: Table 2 - Split | ruled | pages 2-3 | 3 columns | 5 rows"
        assert lines[2] == "Name    | Code | Meaning"
        assert lines[4:] == [
            "Current | 03h  | amps",
            "Fan     | 04h  | rpm",
            "Power   | 05h  | watts",
            "Speed   | 06h  | rpm",
        ]
        assert out.count("cite:") == 1
    code, out = run(capsys, "page", "DSP0236", "2", catalog_file=catalog_file)
    assert code == 0, out
    fields = out.splitlines()[0].split(" | ")
    assert fields[3] == "PDF page 2" and fields[4] == "lines -"


def test_index_selects_one_table_and_rejects_bad_values(held, catalog_file, capsys):
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", "--index", "1", catalog_file=catalog_file
    )
    assert code == 0 and out.count("cite:") == 1
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", "--index", "2", catalog_file=catalog_file
    )
    assert code == 2 and "cite:" not in out
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", "--index", "0", catalog_file=catalog_file
    )
    assert code == 2 and "cite:" not in out


# ----------------------------------------------------------------- AC-5


def test_section_is_the_entry_in_force_at_the_caption_line(held, catalog_file, capsys):
    """AC-5: page 1 holds two headings; the table sits under ``5 Codes``
    and above ``5.1 After the table``, so the Citation names ``5 Codes``
    even though a later entry starts on the same page."""
    code, out = run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[0].split(" | ")[2] == "5 Codes"


# ----------------------------------------------------------------- AC-6


def test_store_file_has_the_documented_shape(held, catalog_file, capsys):
    code, out = run(capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file)
    assert code == 0, out
    data = json.loads((held / "tables.json").read_text("utf-8"))
    assert data["tables_version"] == 2
    assert 2 in data["pages_done"]
    (entry,) = [t for t in data["tables"] if t["first"] == 2]
    assert entry["last"] == 3
    assert entry["caption"] == "Table 2 - Split"
    assert entry["section"] == "5.1 After the table"  # the entry in force
    assert len(entry["columns"]) == 4
    assert entry["rows"][0] == HEADER
    assert len(entry["rows"]) == 5


def test_second_call_for_the_same_page_does_not_open_the_pdf(
    held, catalog_file, capsys
):
    """AC-6: once stored, the page is answered from tables.json; with the
    original gone the answer is unchanged, and ``--force`` goes back to
    the PDF (and therefore fails). Any page of the stored table counts:
    the table read from page 2 spans 2-3, so page 3 is answered from the
    store as well; page 4 was never visited and is not."""
    code, first = run(capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file)
    assert code == 0, first
    data = json.loads((held / "tables.json").read_text("utf-8"))
    assert 2 in data["pages_done"] and 3 in data["pages_done"]
    assert 4 not in data["pages_done"]
    (held / "original.pdf").unlink()
    code, again = run(capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file)
    assert code == 0 and again == first
    code, other = run(capsys, "table", "DSP0236", "--page", "3", catalog_file=catalog_file)
    assert code == 0 and other == first
    code, out = run(capsys, "table", "DSP0236", "--page", "4", catalog_file=catalog_file)
    assert code != 0 and "cite:" not in out
    code, out = run(
        capsys, "table", "DSP0236", "--page", "2", "--force", catalog_file=catalog_file
    )
    assert code != 0 and "cite:" not in out


def test_the_stored_section_is_what_the_cite_line_prints(held, catalog_file, capsys):
    """AC-6: the section is stored with the table and the cite: line is
    read back from the store; a store edited by hand shows in the output,
    so the field is not dead data."""
    code, out = run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert code == 0, out
    path = held / "tables.json"
    data = json.loads(path.read_text("utf-8"))
    for entry in data["tables"]:
        if entry["first"] == 1:
            entry["section"] = "edited by hand"
    path.write_text(json.dumps(data), encoding="utf-8")
    code, out = run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[0].split(" | ")[2] == "edited by hand"


def test_no_table_result_is_stored_too(held, catalog_file, capsys):
    code, out = run(capsys, "table", "DSP0236", "--page", "5", catalog_file=catalog_file)
    assert code == 2
    (held / "original.pdf").unlink()
    code, again = run(capsys, "table", "DSP0236", "--page", "5", catalog_file=catalog_file)
    assert code == 2 and again == out


def test_store_is_removed_by_extract_force_fetch_force_and_add_force(
    held, catalog_file, capsys, tmp_path
):
    store = held / "tables.json"
    run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert store.is_file()
    code, out = run(capsys, "extract", "DSP0236", "--force", catalog_file=catalog_file)
    assert code == 0, out
    assert not store.exists()
    run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert store.is_file()
    code, out = run(capsys, "fetch", "DSP0236", "--force", catalog_file=catalog_file)
    assert code == 0, out
    assert not store.exists()
    run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert store.is_file()
    mine = tmp_path / "mine.pdf"
    mine.write_bytes(document(tmp_path))
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
    assert code == 0, out
    assert not store.exists()


# ----------------------------------------------------------------- AC-8


def test_error_paths(fetched, catalog_file, capsys):
    code, out = run(capsys, "table", "IPMI", "--page", "1", catalog_file=catalog_file)
    assert code == 2 and "fetch IPMI" in out
    code, out = run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert code == 2 and "extract DSP0236" in out
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    code, out = run(capsys, "table", "DSP0236", "--page", "6", catalog_file=catalog_file)
    assert code == 2 and "6" in out and "cite:" not in out
    code, out = run(capsys, "table", "DSP0236", "--page", "0", catalog_file=catalog_file)
    assert code == 2 and "cite:" not in out
    code, out = run(capsys, "table", "DSP0236", "--page", "5", catalog_file=catalog_file)
    assert code == 2
    assert "no table on page" in out
    assert "page DSP0236 5" in out and "render DSP0236 --page 5" in out


def test_missing_pdfplumber_is_exit_2_with_an_install_hint(
    held, catalog_file, capsys, monkeypatch
):
    """AC-8: the real import path, not a stub: a None entry in sys.modules
    makes ``import pdfplumber`` raise ImportError."""
    monkeypatch.setitem(sys.modules, "pdfplumber", None)
    code, out = run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert code == 2
    assert "pdfplumber" in out and "pip install" in out


# ----------------------------------------------------------------- AC-9


def test_other_commands_run_without_pdfplumber(held, catalog_file, capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "pdfplumber", None)
    for argv in (
        ["status"],
        ["catalog"],
        ["page", "DSP0236", "1"],
        ["find", "DSP0236", "Temperature"],
        ["section", "DSP0236", "Codes"],
        ["library"],
    ):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert code == 0, (argv, out)
