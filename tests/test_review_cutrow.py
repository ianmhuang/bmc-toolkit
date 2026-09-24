"""Reviewer acceptance tests for the cells-table cut-row rule (AC-1 to
AC-4): a continuation row with an empty first cell joins the row before
only when another cell is empty too; ruled tables keep the open-bottom
rule; a version 2 ``tables.json`` is discarded and read again. Synthetic
PDFs only; the scripted client keeps the network out."""

import json

import pytest

from bmc_toolkit.spec import tables as T
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok

pytest.importorskip("pypdfium2")
pytest.importorskip("pdfplumber")

URL = "https://example.test/DSP0236_1.3.3.pdf"
WIDTHS = [100, 80, 200]
HEADER = ["Property", "Type", "Description"]
POWER = ["Power", "object", "The power state"]
LIMIT = ["", "number", "The power limit in watts"]
STATE = ["", "string", "The state of the outlet"]
OUTLET = ["Outlet", "object", "One outlet of the PDU"]


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def boxes(x, top, widths, heights, cells, *, gray=0.9, header_gray=0.8):
    """pdfgen items for a table with no ruling lines: one filled box per
    cell, boxes tiled edge to edge, the header row darker. ``top`` is the
    top edge in PDF points (origin bottom-left)."""
    items = []
    xs = [x]
    for w in widths:
        xs.append(xs[-1] + w)
    ys = [top]
    for h in heights:
        ys.append(ys[-1] - h)
    for r, row in enumerate(cells):
        h = heights[r]
        for c, cell in enumerate(row):
            w = xs[c + 1] - xs[c]
            items.append(
                ("fill", xs[c], ys[r] - h, w, h, header_gray if r == 0 else gray)
            )
            if cell:
                items.append((xs[c] + 3, ys[r] - 11, cell))
    return items


def rules(x, top, widths, heights, cells, *, bottom_rule=True):
    """A Word-style ruled table: thin filled rectangles as rules, text in
    each cell; ``bottom_rule=False`` leaves the last row open at the
    bottom, as a page break cuts it."""
    items = []
    total_w = sum(widths)
    total_h = sum(heights)
    xs = [x]
    for w in widths:
        xs.append(xs[-1] + w)
    ys = [top]
    for h in heights:
        ys.append(ys[-1] - h)
    for i, y in enumerate(ys):
        if i == len(ys) - 1 and not bottom_rule:
            continue
        items.append(("fill", x, y - 0.3, total_w, 0.6))
    for cx in xs:
        items.append(("fill", cx - 0.3, top - total_h, 0.6, total_h))
    for r, row in enumerate(cells):
        for c, cell in enumerate(row):
            if cell:
                items.append((xs[c] + 3, ys[r] - 11, cell))
    return items


def furniture(n):
    return [(72, 760, "Spec Title"), (300, 40, f"Page {n}")]


def cells_pages(first_rows, *later_rows):
    """A cells table at the foot of page 1 whose body carries on at the
    top of each later page under a repeated header."""
    page1 = furniture(1) + [(72, 214, "Table 1 - Properties")]
    page1 += boxes(72, 200, WIDTHS, [16] * len(first_rows), first_rows)
    pages = [page1]
    for n, rows in enumerate(later_rows, start=2):
        pages.append(furniture(n) + boxes(72, 740, WIDTHS, [16] * len(rows), rows))
    return pages


def read(tmp_path, pages):
    return T.Reader(pdfgen.write_pdf(tmp_path / "t.pdf", pages))


# ------------------------------------------------------------------ AC-1


def test_ac1_a_grouped_cells_row_after_the_break_is_its_own_row(tmp_path):
    # DSP2053's shape: the property name is given once, the rows under it
    # leave the first cell empty. The break falls inside the group, and the
    # first row of page 2 has text in every other cell: a new row.
    pages = cells_pages([HEADER, POWER, LIMIT], [HEADER, STATE, OUTLET])
    with read(tmp_path, pages) as r:
        (lt,) = r.logical_tables(1)
        assert lt.drawn == T.CELLS
        assert (lt.first, lt.last) == (1, 2)
        assert lt.rows == [HEADER, POWER, LIMIT, STATE, OUTLET]
        assert lt.row_pages == [1, 1, 1, 2, 2]
        assert r.logical_tables(2) == [lt]


def test_ac1_the_rule_is_applied_at_every_page_break_of_one_table(tmp_path):
    # Three pages: the break into page 2 falls inside a group (complete row,
    # stays), the break into page 3 cuts a two-line cell (partial row, joined).
    pages = cells_pages(
        [HEADER, POWER, LIMIT],
        [HEADER, STATE, ["Fan", "number", "rpm and"]],
        [HEADER, ["", "", "duty cycle"], OUTLET],
    )
    with read(tmp_path, pages) as r:
        (lt,) = r.logical_tables(2)
        assert (lt.first, lt.last) == (1, 3)
        assert lt.rows == [
            HEADER,
            POWER,
            LIMIT,
            STATE,
            ["Fan", "number", "rpm and\nduty cycle"],
            OUTLET,
        ]
        assert lt.row_pages == [1, 1, 1, 2, 2, 3]


def test_ac1_cli_counts_the_grouped_row_as_a_row(held, catalog_file, capsys):
    code, out = run(capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[1] == (
        "table: Table 1 - Properties | cells (no ruling lines) | pages 1-2 "
        "| 3 columns | 5 rows"
    )


# ------------------------------------------------------------------ AC-2


def test_ac2_a_cut_cells_row_with_two_empty_cells_is_still_joined(tmp_path):
    pages = cells_pages(
        [HEADER, POWER, ["Fan", "number", "rpm and"]],
        [HEADER, ["", "", "duty cycle"], OUTLET],
    )
    with read(tmp_path, pages) as r:
        (lt,) = r.logical_tables(1)
        assert lt.rows == [
            HEADER,
            POWER,
            ["Fan", "number", "rpm and\nduty cycle"],
            OUTLET,
        ]
        assert lt.row_pages == [1, 1, 1, 2]


def test_ac2_one_empty_cell_besides_the_first_is_enough_to_join(tmp_path):
    # The middle cell carries the overflow, the last cell is empty: still
    # the rest of a cut row.
    pages = cells_pages(
        [HEADER, POWER, ["Fan", "number or", "rpm"]],
        [HEADER, ["", "string", ""], OUTLET],
    )
    with read(tmp_path, pages) as r:
        (lt,) = r.logical_tables(1)
        assert lt.rows == [
            HEADER,
            POWER,
            ["Fan", "number or\nstring", "rpm"],
            OUTLET,
        ]


def test_ac2_a_continuation_row_with_a_filled_first_cell_is_never_joined(tmp_path):
    pages = cells_pages([HEADER, POWER, LIMIT], [HEADER, OUTLET, STATE])
    with read(tmp_path, pages) as r:
        (lt,) = r.logical_tables(1)
        assert lt.rows == [HEADER, POWER, LIMIT, OUTLET, STATE]


# ------------------------------------------------------------------ AC-3


def ruled_pages(bottom_rule):
    page1 = furniture(1) + [(72, 214, "Table 2 - Ruled")]
    page1 += rules(72, 200, WIDTHS, [16, 16], [HEADER, POWER], bottom_rule=bottom_rule)
    page2 = furniture(2) + rules(72, 740, WIDTHS, [16] * 3, [HEADER, LIMIT, OUTLET])
    return [page1, page2]


def test_ac3_an_open_bottomed_ruled_part_joins_a_complete_row(tmp_path):
    with read(tmp_path, ruled_pages(bottom_rule=False)) as r:
        (lt,) = r.logical_tables(1)
        assert lt.drawn == T.RULED
        assert lt.rows == [
            HEADER,
            ["Power", "object\nnumber", "The power state\nThe power limit in watts"],
            OUTLET,
        ]
        assert lt.row_pages == [1, 1, 2]


def test_ac3_a_closed_ruled_part_does_not_join_the_next_row(tmp_path):
    with read(tmp_path, ruled_pages(bottom_rule=True)) as r:
        (lt,) = r.logical_tables(1)
        assert lt.drawn == T.RULED
        assert lt.rows == [HEADER, POWER, LIMIT, OUTLET]
        assert lt.row_pages == [1, 1, 2, 2]


# ------------------------------------------------------------------ AC-4


def test_ac4_the_store_is_version_3_and_a_version_2_store_is_discarded(tmp_path):
    assert T.TABLES_VERSION == 3
    table = T.LogicalTable(
        first=1,
        last=2,
        index=1,
        caption="Table 1 - Properties",
        section=None,
        columns=[72.0, 172.0, 252.0, 452.0],
        parts=[[1, 0, 72.0, 152.0, 452.0, 200.0], [2, 0, 72.0, 692.0, 452.0, 740.0]],
        rows=[HEADER, POWER, LIMIT, STATE, OUTLET],
        drawn=T.CELLS,
        row_pages=[1, 1, 1, 2, 2],
    )
    T.store(tmp_path, [1, 2], [table])
    path = tmp_path / T.TABLES_NAME
    data = json.loads(path.read_text("utf-8"))
    assert data["tables_version"] == 3
    assert T.stored_for_page(tmp_path, 1) == [table]
    data["tables_version"] = 2
    path.write_text(json.dumps(data), "utf-8")
    assert T.stored_for_page(tmp_path, 1) is None
    assert T.stored_for_page(tmp_path, 2) is None


def test_ac4_cli_reads_the_pdf_again_over_a_version_2_store(
    held, catalog_file, capsys
):
    code, out = run(capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file)
    assert code == 0, out
    path = held / "tables.json"
    data = json.loads(path.read_text("utf-8"))
    assert data["tables_version"] == 3
    # a store the previous version wrote, holding the wrong join
    data["tables_version"] = 2
    (entry,) = data["tables"]
    entry["rows"] = [HEADER, POWER, ["", "number\nstring", "STALE JOIN"], OUTLET]
    entry["row_pages"] = [1, 1, 1, 2]
    path.write_text(json.dumps(data), "utf-8")
    code, out = run(capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file)
    assert code == 0, out
    assert "STALE JOIN" not in out
    assert "| 5 rows" in out.splitlines()[1]
    data = json.loads(path.read_text("utf-8"))
    assert data["tables_version"] == 3
    (entry,) = data["tables"]
    assert entry["rows"] == [HEADER, POWER, LIMIT, STATE, OUTLET]


# --------------------------------------------------------------- fixtures


def document(tmp_path):
    return pdfgen.write_pdf(
        tmp_path / "doc.pdf", cells_pages([HEADER, POWER, LIMIT], [HEADER, STATE, OUTLET])
    )


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    scripted.responses[URL] = ok(document(tmp_path).read_bytes())
    for argv in (["fetch", "DSP0236"], ["extract", "DSP0236"]):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"
