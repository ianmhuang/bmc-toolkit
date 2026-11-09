"""Reviewer acceptance tests for T70 (AC-1, AC-3, AC-4) through the
reader: a later part that draws two column edges within 6 pt of one edge
of the first part keeps both in the joined table's columns, and every row
of every part has one cell per column. Synthetic ruled PDFs only."""

import json

import pytest

from bmc_toolkit.spec import tables as T
from tests import pdfgen
from tests.test_tables import ruled_table

pytest.importorskip("pdfplumber")

TOP = 680  # a table's top edge, PDF points from the page's foot
ROW_H = 16
LEFT = 72
RUNNING = "Example Specification, Revision 2.4"
CAPTION = "Figure 21: Feature Data Structure"
HEADER = ["Bytes", "O/M", "Description"]
THREE = [100, 80, 260]  # edges 72, 172, 252, 512
# an 8 pt column whose edges 248 and 256 lie 4 pt either side of THREE's 252
AT_252 = [100, 76, 8, 256]
# a 10 pt column whose edges 167 and 177 lie 5 pt either side of THREE's 172
AT_172 = [95, 10, 75, 260]
ORDINALS = ["first", "second", "third"]


def furniture(n):
    """A running header and a page number, the same on every page."""
    return [(LEFT, 750, RUNNING), (300, 40, str(n))]


def over(text, top=TOP):
    """A text line whose top lies about 12 pt over a table's top edge."""
    return (LEFT, top + 4, text)


def tail(n):
    """Prose under the last part: the table ends on this page."""
    return (LEFT, 120, f"The {ORDINALS[n - 1]} part ends here.")


def grid(widths, cells):
    return ruled_table(LEFT, TOP, widths, [ROW_H] * len(cells), cells)


def body(first, count):
    return [[f"{n:02d}", "M", f"Field {n}"] for n in range(first, first + count)]


def at_252(first, count):
    """Rows for AT_252: the narrow column is the third."""
    return [[f"{n:02d}", "M", "x", f"Field {n}"] for n in range(first, first + count)]


def at_172(first, count):
    """Rows for AT_172: the narrow column is the second."""
    return [[f"{n:02d}", "x", "M", f"Field {n}"] for n in range(first, first + count)]


def first_page():
    """Page 1: the caption and a three-column part with nothing under it."""
    return furniture(1) + [over(CAPTION)] + grid(THREE, [HEADER, *body(0, 3)])


def read(tmp_path, pages, page):
    pdf = pdfgen.write_pdf(tmp_path / "doc.pdf", pages)
    with T.Reader(pdf) as r:
        return r.logical_tables(page)


def filled(row):
    return [cell for cell in row if cell]


SPLITS = [
    (AT_252, at_252(40, 3), [72, 172, 252, 256, 512]),
    (AT_172, at_172(40, 3), [72, 172, 177, 252, 512]),
]
SPLIT_IDS = ["around-252", "around-172"]


# ---------------------------------------------------------------- AC-1


@pytest.mark.parametrize(("widths", "cells", "columns"), SPLITS, ids=SPLIT_IDS)
def test_ac1_two_edges_of_a_later_part_near_one_edge_are_two_columns(
    tmp_path, widths, cells, columns
):
    pages = [
        first_page(),
        furniture(2) + [over(CAPTION)] + grid(widths, cells) + [tail(2)],
    ]
    (table,) = read(tmp_path, pages, 2)
    assert (table.first, table.last, table.caption) == (1, 2, CAPTION)
    # the first of the two edges takes the first part's, the second is added
    assert [round(c) for c in table.columns] == columns
    assert {len(row) for row in table.rows} == {len(table.columns) - 1}
    # the first part's rows keep their cells and order; the second part's
    # four cells sit in four columns as drawn
    assert [filled(row) for row in table.rows[:4]] == [HEADER, *body(0, 3)]
    assert table.rows[4:] == cells
    assert table.row_pages == [1, 1, 1, 1, 2, 2, 2]


# ---------------------------------------------------------------- AC-3


def test_ac3_a_chain_with_the_split_on_the_middle_page_reads_on_one_width(tmp_path):
    pages = [
        first_page(),
        furniture(2) + [over(CAPTION)] + grid(AT_252, at_252(40, 3)),
        furniture(3) + [over(CAPTION)] + grid(THREE, body(80, 3)) + [tail(3)],
    ]
    (table,) = read(tmp_path, pages, 2)
    assert (table.first, table.last) == (1, 3)
    assert [round(c) for c in table.columns] == [72, 172, 252, 256, 512]
    assert {len(row) for row in table.rows} == {4}
    assert [filled(row) for row in table.rows] == [
        HEADER,
        *body(0, 3),
        *at_252(40, 3),
        *body(80, 3),
    ]


def test_ac3_the_split_part_first_gives_rows_of_one_width_too(tmp_path):
    # the part with more edges first: the union is its edges, and the
    # three-column part's rows get an empty cell for the edge they span
    cells = [["Bytes", "O/M", "x", "Description"], *at_252(0, 3)]
    pages = [
        furniture(1) + [over(CAPTION)] + grid(AT_252, cells),
        furniture(2) + [over(CAPTION)] + grid(THREE, body(40, 3)) + [tail(2)],
    ]
    (table,) = read(tmp_path, pages, 1)
    assert (table.first, table.last) == (1, 2)
    assert [round(c) for c in table.columns] == [72, 172, 248, 256, 512]
    assert {len(row) for row in table.rows} == {4}
    assert table.rows[:4] == cells
    assert [filled(row) for row in table.rows[4:]] == body(40, 3)
    # develop joins these two parts the same way (their edges pair one to
    # one); the version pin is what ties this check to the change
    assert T.TABLES_VERSION == 14


# ---------------------------------------------------------------- AC-4


def test_ac4_tables_version_is_14_and_a_version_13_store_is_not_served(tmp_path):
    assert T.TABLES_VERSION == 14
    pages = [
        first_page(),
        furniture(2) + [over(CAPTION)] + grid(AT_252, at_252(40, 3)) + [tail(2)],
    ]
    found = read(tmp_path, pages, 2)
    vdir = tmp_path / "v"
    vdir.mkdir()
    path = T.store(vdir, [1, 2], found)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tables_version"] == 14
    (stored,) = T.stored_for_page(vdir, 2)
    assert len(stored.columns) == 5
    assert {len(row) for row in stored.rows} == {4}
    # what version 13 stored: four edges, the second part's rows too wide
    data["tables_version"] = 13
    path.write_text(json.dumps(data), encoding="utf-8")
    assert T.stored_for_page(vdir, 2) is None
