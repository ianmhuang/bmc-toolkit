"""Word gaps in table cells: DMTF draws a hyperlink as its own text run
with no space character on either side, about 2.1 pt from its neighbours;
pdfplumber's default x_tolerance (3 pt) joined them (`seeDSP0251`). Upright
cell text now splits at WORD_GAP_PT; rotated text is read as before."""

import json

import pytest

from bmc_toolkit.spec import tables as T
from tests import pdfgen
from tests.test_review_curvefill import curve_table
from tests.test_tables import HEADER, WIDTHS, cell_table, reader, ruled_table

pdfplumber = pytest.importorskip("pdfplumber")
utils = pytest.importorskip("pdfplumber.utils")

TOP = 700
X = 255  # the third column starts at 72 + 100 + 80 = 252; text sits 3 in
Y = TOP - 16 - 11  # the second row's text line
ROTATED = (0, 1, -1, 0)

# Helvetica advance widths at 10 pt: "of" 8.34, "DSP0248" 42.80, "a" 5.56
OF, DSP, A = 8.34, 42.80, 5.56


def link_runs(gap=2.1):
    """`of`, `DSP0248`, `for` as three runs ``gap`` apart, no spaces."""
    return [
        (X, Y, "of"),
        (X + OF + gap, Y, "DSP0248"),
        (X + OF + gap + DSP + gap, Y, "for"),
    ]


ROW = ["Name", "Code", ""]  # the third cell is drawn by link_runs


def first_row(page_items, tmp_path):
    with reader(tmp_path, [page_items]) as r:
        (t,) = r.page(1).tables
        return t, t.rows[1]


# ------------------------------------------------------------------ AC-1


def test_upright_runs_a_word_gap_apart_are_separate_words(tmp_path):
    page = ruled_table(72, TOP, WIDTHS, [16] * 2, [HEADER, ROW]) + link_runs()
    t, row = first_row(page, tmp_path)
    assert t.drawn == T.RULED
    assert row == ["Name", "Code", "of DSP0248 for"]


def test_kerning_gaps_stay_inside_a_word(tmp_path):
    page = ruled_table(72, TOP, WIDTHS, [16] * 2, [HEADER, ROW])
    page += [(X, Y, "a"), (X + A + 0.5, Y, "b"), (X + A + 0.5 + A + 1.5, Y, "c")]
    _, row = first_row(page, tmp_path)
    assert row[2] == "abc"


def test_rotated_characters_keep_the_default_reading(tmp_path):
    # pdfplumber reads characters that are not upright in columns, a column
    # being those whose x0 lie within x_tolerance: two glyphs turned 90
    # degrees with x0 2.2 pt apart are one column at 3 pt and two at
    # WORD_GAP_PT (NVMe-MI's box diagram labels: "B y te 3")
    page = ruled_table(72, TOP, WIDTHS, [16] * 2, [HEADER, ROW])
    page += [(X + 10, Y - 4, "t", 10, ROTATED), (X + 12.2, Y - 4, "e", 10, ROTATED)]
    path = pdfgen.write_pdf(tmp_path / "rot.pdf", [page])
    with pdfplumber.open(path) as pdf:
        chars = [c for c in pdf.pages[0].chars if not c["upright"]]
        assert [c["text"] for c in chars] == ["t", "e"]
        assert round(chars[1]["x0"] - chars[0]["x0"], 1) == 2.2
        default = utils.extract_text(chars)
        # the rule bites: WORD_GAP_PT for this cell would read it otherwise
        assert utils.extract_text(chars, x_tolerance=T.WORD_GAP_PT) != default
    with T.Reader(path) as r:
        (t,) = r.page(1).tables
        assert t.rows[1][2] == default


# ------------------------------------------------------------------ AC-2


def test_tiled_cell_boxes_split_the_same_way(tmp_path):
    page = cell_table(72, TOP, WIDTHS, [16] * 2, [HEADER, ROW]) + link_runs()
    t, row = first_row(page, tmp_path)
    assert t.drawn == T.CELLS
    assert row[2] == "of DSP0248 for"


def test_curve_drawn_rules_split_the_same_way(tmp_path):
    page = curve_table(72, TOP, WIDTHS, [16] * 2, [HEADER, ROW]) + link_runs()
    t, row = first_row(page, tmp_path)
    assert t.drawn == T.RULED
    assert row[2] == "of DSP0248 for"


# ------------------------------------------------------------------ AC-3


def test_tables_version_is_7_and_a_version_6_store_is_read_again(tmp_path):
    assert T.TABLES_VERSION == 7
    page = ruled_table(72, TOP, WIDTHS, [16] * 2, [HEADER, ROW]) + link_runs()
    path = pdfgen.write_pdf(tmp_path / "t.pdf", [page])
    vdir = tmp_path / "v"
    vdir.mkdir()
    # what version 6 stored for this page: the joined words
    stale = {
        "tables_version": 6,
        "pages_done": [1],
        "tables": [
            {
                "first": 1,
                "last": 1,
                "index": 1,
                "caption": "",
                "section": "",
                "drawn": "ruled",
                "columns": [72.0, 172.0, 252.0, 452.0],
                "parts": [[1, 0, 72.0, 92.0, 452.0, 124.0]],
                "rows": [HEADER, ["Name", "Code", "ofDSP0248for"]],
                "row_pages": [1, 1],
            }
        ],
    }
    (vdir / T.TABLES_NAME).write_text(json.dumps(stale), "utf-8", newline="")
    assert T.stored_for_page(vdir, 1) is None
    with T.Reader(path) as r:
        tables = r.logical_tables(1)
    T.store(vdir, [1], tables)
    (stored,) = T.stored_for_page(vdir, 1)
    assert stored.rows[1] == ["Name", "Code", "of DSP0248 for"]
    data = json.loads((vdir / T.TABLES_NAME).read_text("utf-8"))
    assert data["tables_version"] == 7
