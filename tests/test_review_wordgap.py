"""Review tests for the table word gap (fix/table-word-gap).

DMTF draws a hyperlink in a table cell as its own text run with no space
character on either side, about 2.1 pt from its neighbours; at pdfplumber's
default x_tolerance (3 pt) the words were joined (`seeDSP0251`). The AC: an
upright cell splits at a word gap and keeps kerning gaps joined, a cell of
rotated characters reads as before, the rule holds for ruled, tiled-box and
curve-drawn tables, and TABLES_VERSION 7 retires every version 6 store.

The synthetic tables place the runs from Helvetica's AFM advance widths
(what pdfminer uses for the base-14 fonts), so a gap in this file is the
gap pdfplumber measures."""

import json

import pytest

from bmc_toolkit.spec import tables as T
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok
from tests.test_curve_rules import curve_table
from tests.test_tables import HEADER, WIDTHS, cell_table, reader, ruled_table

pytest.importorskip("pdfplumber")
pytest.importorskip("pypdfium2")

# Helvetica advance widths, per 1000 em, for the letters the runs use
AFM = {
    "0": 556,
    "2": 556,
    "4": 556,
    "8": 556,
    "D": 722,
    "P": 667,
    "S": 667,
    "a": 556,
    "b": 556,
    "c": 500,
    "e": 556,
    "f": 278,
    "m": 833,
    "o": 556,
    "r": 333,
    "s": 500,
    "t": 278,
    " ": 278,
}


def width(text, size=10):
    return sum(AFM[ch] for ch in text) * size / 1000


def runs(x, y, words, gap, size=10):
    """``words`` drawn left to right as separate runs ``gap`` pt apart with
    no space character between them."""
    items = []
    for word in words:
        items.append((x, y, word, size))
        x += width(word, size) + gap
    return items


TOP = 700
HEIGHTS = [16, 16, 16]
COL3 = 72 + WIDTHS[0] + WIDTHS[1] + 3  # where the third column's text starts
ROW1 = TOP - 16 - 11  # the baseline of the second row's text
ROW2 = TOP - 32 - 11  # the baseline of the third row's text
ROTATED = (0, 1, -1, 0)

CELLS = [HEADER, ["Name", "Code", ""], ["Other", "01h", ""]]  # column 3 drawn here


def rows_of(tmp_path, page, kind):
    with reader(tmp_path, [page]) as r:
        (t,) = r.page(1).tables
        assert t.drawn == kind
        return t.rows


# ------------------------------------------------------------------ AC-1


def test_a_word_gap_splits_and_a_kerning_gap_does_not(tmp_path):
    page = ruled_table(72, TOP, WIDTHS, HEIGHTS, CELLS)
    page += runs(COL3, ROW1, ["of", "DSP0248", "for"], 2.1)
    page += runs(COL3, ROW2, ["a", "b", "c"], 0.5)
    rows = rows_of(tmp_path, page, T.RULED)
    assert rows[1][2] == "of DSP0248 for"
    assert rows[2][2] == "abc"


def test_the_dmtf_case_at_seven_and_a_half_points(tmp_path):
    # DSP0251 1.0.0 p.28 the way DMTF sets it: 7.5 pt, the link its own run,
    # a real space inside the run after it
    page = ruled_table(72, TOP, WIDTHS, HEIGHTS, CELLS)
    page += runs(COL3, ROW1, ["see", "DSP0248", "for more"], 2.1, size=7.5)
    page += runs(COL3, ROW2, ["See", "DSP0248", "for"], 2.1, size=7.5)
    rows = rows_of(tmp_path, page, T.RULED)
    assert rows[1][2] == "see DSP0248 for more"
    assert rows[2][2] == "See DSP0248 for"


def test_rotated_characters_a_word_gap_apart_stay_joined(tmp_path):
    # Two glyphs turned 90 degrees, their x0 2.2 pt apart: pdfplumber reads
    # rotated text in columns of chars whose x0 lie within x_tolerance, so
    # at the default they are one column ("tt") and at WORD_GAP_PT two
    # lines. The same glyph twice so the reading order does not matter.
    page = ruled_table(72, TOP, WIDTHS, HEIGHTS, CELLS)
    page += runs(COL3, ROW1, ["of", "DSP0248", "for"], 2.1)
    page += [
        (COL3 + 10, ROW2 - 4, "t", 10, ROTATED),
        (COL3 + 12.2, ROW2 - 4, "t", 10, ROTATED),
    ]
    rows = rows_of(tmp_path, page, T.RULED)
    assert rows[1][2] == "of DSP0248 for"  # the upright cell beside it splits
    assert rows[2][2] == "tt"


def test_a_cell_mixing_rotated_and_upright_keeps_the_default(tmp_path):
    # the rule is "every character upright": one rotated glyph in the cell
    # and the upright runs beside it are read at 3 pt again
    page = ruled_table(72, TOP, WIDTHS, HEIGHTS, CELLS)
    page += runs(COL3, ROW1, ["of", "DSP0248", "for"], 2.1)
    page += runs(COL3, ROW2, ["of", "DSP0248", "for"], 2.1)
    page += [(COL3 + 120, ROW2 - 4, "t", 10, ROTATED)]
    rows = rows_of(tmp_path, page, T.RULED)
    assert rows[1][2] == "of DSP0248 for"
    assert rows[2][2].startswith("ofDSP0248for")


# ------------------------------------------------------------------ AC-2


def test_tiled_cell_boxes(tmp_path):
    page = cell_table(72, TOP, WIDTHS, HEIGHTS, CELLS)
    page += runs(COL3, ROW1, ["of", "DSP0248", "for"], 2.1)
    page += runs(COL3, ROW2, ["a", "b", "c"], 0.5)
    rows = rows_of(tmp_path, page, T.CELLS)
    assert rows[1][2] == "of DSP0248 for"
    assert rows[2][2] == "abc"


def test_curve_drawn_rules(tmp_path):
    page = curve_table(72, TOP, WIDTHS, HEIGHTS, CELLS)
    page += runs(COL3, ROW1, ["of", "DSP0248", "for"], 2.1)
    page += runs(COL3, ROW2, ["a", "b", "c"], 0.5)
    rows = rows_of(tmp_path, page, T.RULED)
    assert rows[1][2] == "of DSP0248 for"
    assert rows[2][2] == "abc"


# ------------------------------------------------------------------ AC-3

URL = "https://example.test/DSP0236_1.3.3.pdf"


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def test_tables_version_is_7_and_a_version_6_store_is_not_served(
    catalog_file, library, scripted, tmp_path, capsys
):
    assert T.TABLES_VERSION == 8
    page = ruled_table(72, TOP, WIDTHS, HEIGHTS, CELLS)
    page += runs(COL3, ROW1, ["of", "DSP0248", "for"], 2.1)
    page += runs(COL3, ROW2, ["See", "DSP0248", "for"], 2.1, size=7.5)
    pdf = pdfgen.write_pdf(tmp_path / "link.pdf", [page]).read_bytes()
    scripted.responses[URL] = ok(pdf)
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    store = vdir / T.TABLES_NAME

    # what version 6 left behind for this page: the joined words
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0, out
    data = json.loads(store.read_text("utf-8"))
    assert data["tables_version"] == 8
    data["tables_version"] = 6
    for table in data["tables"]:
        for row in table["rows"]:
            row[:] = [
                cell.replace(" ", "") if "DSP0248" in cell else cell for cell in row
            ]
    store.write_text(json.dumps(data), "utf-8", newline="")
    assert "ofDSP0248for" in store.read_text("utf-8")
    assert T.stored_for_page(vdir, 1) is None  # not served

    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0, out
    assert "of DSP0248 for" in out
    assert "See DSP0248 for" in out
    assert "ofDSP0248for" not in out
    data = json.loads(store.read_text("utf-8"))
    assert data["tables_version"] == 8
    assert data["pages_done"] == [1]
    (stored,) = T.stored_for_page(vdir, 1)
    assert stored.rows[1][2] == "of DSP0248 for"
    assert stored.rows[2][2] == "See DSP0248 for"
