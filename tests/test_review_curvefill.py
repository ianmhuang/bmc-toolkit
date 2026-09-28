"""Reviewer acceptance tests for rules drawn as path curves (AC-1 to AC-6),
through the Reader: a table ruled with straight Bezier segments is read as
a ``ruled`` table where no other table lies; curves over a table found
from rectangles, lines or cell boxes change nothing; a curve table over a
found table is dropped; boxes, diagonals and arcs are not rules; a curve
part joins across a page break by the existing rules; a version 3 store is
discarded. Synthetic PDFs only."""

import json

import pytest

from bmc_toolkit.spec import tables as T
from tests import pdfgen

pytest.importorskip("pdfplumber")

WIDTHS = [100, 80, 200]
HEADER = ["Name", "Code", "Meaning"]
ROWS_1 = [["Temperature", "01h", "degrees"], ["Voltage", "02h", "volts"]]
ROWS_2 = [["Current", "03h", "amps"], ["Fan", "04h", "rpm"]]


# ---------------------------------------------------------------- drawing


def bez(x0, y0, x1, y1):
    """A straight segment stroked with the Bezier operator, its control
    points on the line: pdfplumber files it under ``curves``."""
    dx, dy = x1 - x0, y1 - y0
    return (
        "curve",
        x0,
        y0,
        x0 + dx / 4,
        y0 + dy / 4,
        x0 + 3 * dx / 4,
        y0 + 3 * dy / 4,
        x1,
        y1,
    )


def _edges(x, top, widths, heights):
    xs = [x]
    for w in widths:
        xs.append(xs[-1] + w)
    ys = [top]
    for h in heights:
        ys.append(ys[-1] - h)
    return xs, ys


def _text(items, xs, ys, cells):
    for r, row in enumerate(cells):
        for c, cell in enumerate(row):
            lines = cell if isinstance(cell, list) else [cell]
            for k, text in enumerate(lines):
                if text:
                    items.append((xs[c] + 3, ys[r] - 11 - 12 * k, text))


def curve_rules(x, top, widths, heights, *, top_rule=True, bottom_rule=True):
    """The ruling lines of a table, every one a straight Bezier curve;
    ``top`` is the table's top edge in PDF points (origin bottom-left)."""
    xs, ys = _edges(x, top, widths, heights)
    items = []
    for i, y in enumerate(ys):
        if (i == 0 and not top_rule) or (i == len(ys) - 1 and not bottom_rule):
            continue
        items.append(bez(xs[0], y, xs[-1], y))
    for cx in xs:
        items.append(bez(cx, ys[0], cx, ys[-1]))
    return items


def curve_table(x, top, widths, heights, cells, **rules):
    """A table whose rules are all curves, with its cell text."""
    items = curve_rules(x, top, widths, heights, **rules)
    xs, ys = _edges(x, top, widths, heights)
    _text(items, xs, ys, cells)
    return items


def ruled(x, top, widths, heights, cells, *, style="fill", bottom_rule=True):
    """A table found today: rules as thin filled rectangles (Word) or as
    stroked lines."""
    xs, ys = _edges(x, top, widths, heights)
    total_w, total_h = sum(widths), sum(heights)
    items = []
    for i, y in enumerate(ys):
        if i == len(ys) - 1 and not bottom_rule:
            continue
        if style == "fill":
            items.append(("fill", x, y - 0.3, total_w, 0.6))
        else:
            items.append(("line", x, y, x + total_w, y))
    for cx in xs:
        if style == "fill":
            items.append(("fill", cx - 0.3, top - total_h, 0.6, total_h))
        else:
            items.append(("line", cx, top, cx, top - total_h))
    _text(items, xs, ys, cells)
    return items


def boxed(x, top, widths, heights, cells):
    """A table found today as ``cells``: one filled box per cell, tiled
    edge to edge, no rules."""
    xs, ys = _edges(x, top, widths, heights)
    items = []
    for r, row in enumerate(cells):
        h = heights[r]
        for c in range(len(row)):
            gray = 0.8 if r == 0 else 0.9
            items.append(("fill", xs[c], ys[r] - h, xs[c + 1] - xs[c], h, gray))
    _text(items, xs, ys, cells)
    return items


def drawn_today(kind, x, top, widths, heights, cells, **kw):
    if kind == "cells":
        return boxed(x, top, widths, heights, cells)
    return ruled(x, top, widths, heights, cells, style=kind, **kw)


def diagram(top=640):
    """A block diagram: boxes stroked as closed curve paths and tiled edge
    to edge like a table, a label in each, a diagonal connector, an arc,
    and prose around it. ``top`` is the top edge of the first row of
    boxes, at most 640."""
    items = [(72, top + 80, "Figure 3 - Block diagram")]
    for r in range(2):
        for c in range(3):
            x, y = 72 + 110 * c, top - 50 * (r + 1)
            items.append(("curvebox", x, y, 110, 50))
            items.append((x + 8, y + 20, f"Unit {r}{c}"))
    items.append(bez(80, 300, 400, 480))  # a diagonal connector
    items.append(("curve", 90, 240, 160, 300, 260, 300, 330, 240))  # an arc
    items.append((72, 200, "Prose under the figure."))
    return items


def furniture(n):
    return [(72, 760, "Spec Title"), (300, 40, f"Page {n}")]


def read(tmp_path, pages, name="t.pdf"):
    return T.Reader(pdfgen.write_pdf(tmp_path / name, pages))


def shape(tables):
    """Everything a PageTable carries, rounded so two readings compare."""
    return [
        (
            t.index,
            t.drawn,
            [round(v, 1) for v in t.bbox],
            [round(c) for c in t.columns],
            t.rows,
            t.open_bottom,
        )
        for t in tables
    ]


def logical_shape(tables):
    return [
        (
            t.first,
            t.last,
            t.index,
            t.caption,
            t.drawn,
            [round(c) for c in t.columns],
            t.parts,
            t.rows,
            t.row_pages,
        )
        for t in tables
    ]


# ------------------------------------------------------------------ AC-1


def test_ac1_a_table_whose_rules_are_all_curves_is_a_ruled_table(tmp_path):
    page = furniture(1) + [
        (72, 740, "The codes are listed below."),
        (72, 694, "Table 7 - Codes"),
    ]
    page += curve_table(72, 680, WIDTHS, [16] * 4, [HEADER, *ROWS_1, ROWS_2[0]])
    page += [(72, 580, "Prose after the table.")]
    with read(tmp_path, [page]) as r:
        (t,) = r.page(1).tables
        assert t.drawn == T.RULED
        assert t.rows == [HEADER, *ROWS_1, ROWS_2[0]]
        assert [round(c) for c in t.columns] == [72, 172, 252, 452]
        assert [round(v) for v in t.bbox] == [72, 112, 452, 176]
        assert t.open_bottom is False
        (lt,) = r.logical_tables(1)
        assert lt.drawn == T.RULED
        assert lt.caption == "Table 7 - Codes"
        assert (lt.first, lt.last, lt.index) == (1, 1, 1)
        assert T.describe(lt) == (
            "table: Table 7 - Codes | ruled | page 1 | 3 columns | 4 rows"
        )


def test_ac1_a_curve_table_keeps_a_two_line_cell_and_a_merged_cell(tmp_path):
    # a row twice as tall holds two text lines in one cell; a row with no
    # inner vertical rule is one merged cell
    xs, ys = _edges(72, 700, WIDTHS, [16, 28, 16])
    items = [bez(72, y, 452, y) for y in ys]
    items += [bez(72, ys[0], 72, ys[-1]), bez(452, ys[0], 452, ys[-1])]
    items += [bez(cx, ys[0], cx, ys[2]) for cx in xs[1:-1]]  # not the last row
    _text(items, xs, ys, [HEADER, ["Processor", "07h", ["IERR", "Thermal Trip"]]])
    items.append((75, ys[2] - 11, "Reserved for future use"))
    with read(tmp_path, [items]) as r:
        (t,) = r.page(1).tables
        assert t.drawn == T.RULED
        assert t.rows[0] == HEADER
        assert t.rows[1] == ["Processor", "07h", "IERR\nThermal Trip"]
        assert t.rows[2][0] == "Reserved for future use"
        assert not any(c for c in t.rows[2][1:])


def test_ac1_two_curve_tables_on_a_page_are_both_found_in_order(tmp_path):
    page = curve_table(72, 700, WIDTHS, [16] * 2, [HEADER, ROWS_1[0]])
    page += [(72, 600, "Prose between the tables.")]
    page += curve_table(72, 500, WIDTHS, [16] * 2, [HEADER, ROWS_2[0]])
    with read(tmp_path, [page]) as r:
        tables = r.page(1).tables
        assert [(t.index, t.drawn, t.rows[1][0]) for t in tables] == [
            (0, T.RULED, "Temperature"),
            (1, T.RULED, "Current"),
        ]
        assert [(t.first, t.last, t.index) for t in r.logical_tables(1)] == [
            (1, 1, 1),
            (1, 1, 2),
        ]


# ------------------------------------------------------------------ AC-2


@pytest.mark.parametrize("kind", ["cells", "fill", "line"])
@pytest.mark.parametrize("overlay", ["same", "finer"])
def test_ac2_curves_over_a_table_found_today_change_nothing(tmp_path, kind, overlay):
    """The same grid stroked again as curves, or a finer one splitting
    every row and column: the table found without the curves keeps its
    bbox, rows, columns, drawn value and open_bottom, and no second table
    appears over it."""
    plain = [(72, 714, "Table 1 - Codes")]
    plain += drawn_today(kind, 72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_1])
    if overlay == "same":
        curves = curve_rules(72, 700, WIDTHS, [16] * 3)
    else:
        curves = curve_rules(72, 700, [50, 50, 40, 40, 100, 100], [8] * 6)
    with read(tmp_path, [plain], "plain.pdf") as r:
        before = shape(r.page(1).tables)
        before_logical = logical_shape(r.logical_tables(1))
    with read(tmp_path, [plain + curves], "curves.pdf") as r:
        after = shape(r.page(1).tables)
        after_logical = logical_shape(r.logical_tables(1))
    assert len(before) == 1
    assert before[0][1] == (T.CELLS if kind == "cells" else T.RULED)
    assert after == before
    assert after_logical == before_logical


def test_ac2_a_curve_bottom_rule_under_an_open_part_does_not_close_it(tmp_path):
    """A rectangle-ruled part the page break left open at the bottom stays
    open when a curve is stroked along its cut edge: its continuation row
    is still joined, as on develop."""
    rows1 = [HEADER, ["Processor", "07h", "IERR"]]
    page1 = furniture(1) + ruled(72, 200, WIDTHS, [16, 16], rows1, bottom_rule=False)
    page2 = furniture(2) + ruled(
        72, 740, WIDTHS, [16] * 3, [HEADER, ["", "", "Thermal Trip"], ROWS_2[0]]
    )
    with read(tmp_path, [page1, page2], "plain.pdf") as r:
        before = logical_shape(r.logical_tables(1))
        assert before[0][7] == [
            HEADER,
            ["Processor", "07h", "IERR\nThermal Trip"],
            ROWS_2[0],
        ]
    with read(tmp_path, [page1 + [bez(72, 168, 452, 168)], page2], "c.pdf") as r:
        assert r.page(1).tables[0].open_bottom is True
        assert logical_shape(r.logical_tables(1)) == before


# ------------------------------------------------------------------ AC-3


@pytest.mark.parametrize("kind", ["cells", "fill"])
def test_ac3_a_curve_table_over_a_found_table_is_dropped(tmp_path, kind):
    plain = drawn_today(kind, 72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_1])
    # a curve grid with text in it whose top row lies over the found
    # table's last row and whose right column reaches past its right edge
    over = curve_rules(300, 668, [100, 100], [16] * 3)
    over += [(305, 641, "stray"), (405, 641, "note"), (305, 625, "below")]
    with read(tmp_path, [plain], "plain.pdf") as r:
        before = shape(r.page(1).tables)
    with read(tmp_path, [plain + over], "over.pdf") as r:
        after = shape(r.page(1).tables)
    assert len(before) == 1
    assert after == before


def test_ac3_curve_tables_clear_of_a_found_table_are_kept_in_page_order(tmp_path):
    page = curve_table(72, 740, WIDTHS, [16] * 2, [HEADER, ROWS_1[0]])
    page += boxed(72, 620, WIDTHS, [16] * 2, [HEADER, ROWS_1[1]])
    page += curve_table(72, 500, WIDTHS, [16] * 2, [HEADER, ROWS_2[0]])
    with read(tmp_path, [page]) as r:
        tables = r.page(1).tables
        assert [(t.index, t.drawn, t.rows[1][0]) for t in tables] == [
            (0, T.RULED, "Temperature"),
            (1, T.CELLS, "Voltage"),
            (2, T.RULED, "Current"),
        ]
        assert [(t.index, t.rows[1][0]) for t in r.logical_tables(1)] == [
            (1, "Temperature"),
            (2, "Voltage"),
            (3, "Current"),
        ]


# ------------------------------------------------------------------ AC-4


def test_ac4_curve_boxes_diagonals_and_arcs_are_no_table(tmp_path):
    with read(tmp_path, [diagram()]) as r:
        assert r.page(1).tables == []
        assert r.logical_tables(1) == []


def test_ac4_a_diagram_under_a_found_table_adds_nothing(tmp_path):
    page = ruled(72, 760, WIDTHS, [16] * 2, [HEADER, ROWS_1[0]])
    page += [(72, 710, "Prose between the table and the figure.")]
    page += diagram(top=600)
    with read(tmp_path, [page]) as r:
        (t,) = r.page(1).tables
        assert t.drawn == T.RULED
        assert t.rows == [HEADER, ROWS_1[0]]


# ------------------------------------------------------------------ AC-5


def test_ac5_a_curve_row_after_the_break_joins_the_cells_table_before(tmp_path):
    page1 = furniture(1) + [(72, 214, "Table 1 - Codes")]
    page1 += boxed(72, 200, WIDTHS, [16] * 3, [HEADER, *ROWS_1])
    page2 = furniture(2) + curve_table(72, 740, WIDTHS, [16], [ROWS_2[0]])
    page2 += [(72, 600, "Prose after the table.")]
    with read(tmp_path, [page1, page2]) as r:
        (lt,) = r.logical_tables(1)
        assert lt.drawn == T.CELLS
        assert (lt.first, lt.last, lt.index) == (1, 2, 1)
        assert lt.caption == "Table 1 - Codes"
        assert lt.rows == [HEADER, *ROWS_1, ROWS_2[0]]
        assert lt.row_pages == [1, 1, 1, 2]
        assert [p[:2] for p in lt.parts] == [[1, 0], [2, 0]]
        assert logical_shape(r.logical_tables(2)) == logical_shape([lt])


def test_ac5_two_one_row_curve_parts_are_one_two_row_table(tmp_path):
    version = ["Version", "v1.2", "v1.1"]
    release = ["Release", "2026.1", "2025.4"]
    page1 = furniture(1) + [(72, 120, "The versions and their releases:")]
    page1 += curve_table(72, 92, WIDTHS, [16], [version])
    page2 = furniture(2) + curve_table(72, 740, WIDTHS, [16], [release])
    page2 += [(72, 600, "Prose after the table.")]
    with read(tmp_path, [page1, page2]) as r:
        (lt,) = r.logical_tables(2)
        assert lt.drawn == T.RULED
        assert (lt.first, lt.last) == (1, 2)
        assert lt.rows == [version, release]
        assert lt.row_pages == [1, 2]
        assert T.describe(lt) == "table: - | ruled | pages 1-2 | 3 columns | 2 rows"
        assert logical_shape(r.logical_tables(1)) == logical_shape([lt])


def test_ac5_an_open_curve_part_joins_the_cut_row_by_the_ruled_rule(tmp_path):
    # the break cut a two-line cell: no bottom rule on page 1, an empty
    # first cell on page 2, so the ruled rule joins them
    page1 = furniture(1) + [(72, 130, "Prose before the table.")]
    page1 += curve_table(
        72,
        100,
        WIDTHS,
        [16, 16],
        [HEADER, ["Processor", "07h", "IERR"]],
        bottom_rule=False,
    )
    page2 = furniture(2) + curve_table(
        72,
        740,
        WIDTHS,
        [16, 16],
        [["", "", "Thermal Trip"], ["Power", "08h", "watts"]],
    )
    page2 += [(72, 600, "Prose after the table.")]
    with read(tmp_path, [page1, page2]) as r:
        assert r.page(1).tables[0].open_bottom is True
        (lt,) = r.logical_tables(1)
        assert (lt.first, lt.last) == (1, 2)
        assert lt.rows == [
            HEADER,
            ["Processor", "07h", "IERR\nThermal Trip"],
            ["Power", "08h", "watts"],
        ]
        assert lt.row_pages == [1, 1, 2]


def test_ac5_prose_between_two_curve_parts_keeps_them_apart(tmp_path):
    page1 = furniture(1) + curve_table(72, 200, WIDTHS, [16] * 2, [HEADER, ROWS_1[0]])
    page1 += [(72, 120, "Prose after the first table.")]
    page2 = furniture(2) + curve_table(72, 740, WIDTHS, [16] * 2, [HEADER, ROWS_2[0]])
    with read(tmp_path, [page1, page2]) as r:
        assert [(t.first, t.last) for t in r.logical_tables(1)] == [(1, 1)]
        assert [(t.first, t.last) for t in r.logical_tables(2)] == [(2, 2)]


# ------------------------------------------------------------------ AC-6


def test_ac6_the_store_is_version_4_and_a_version_3_store_is_discarded(tmp_path):
    assert T.TABLES_VERSION == 4
    table = T.LogicalTable(
        first=1,
        last=2,
        index=1,
        caption="Table 1 - Codes",
        section=None,
        columns=[72.0, 172.0, 252.0, 452.0],
        parts=[[1, 0, 72.0, 152.0, 452.0, 200.0], [2, 0, 72.0, 52.0, 452.0, 68.0]],
        rows=[HEADER, *ROWS_1, ROWS_2[0]],
        drawn=T.CELLS,
        row_pages=[1, 1, 1, 2],
    )
    T.store(tmp_path, [1, 2], [table])
    path = tmp_path / T.TABLES_NAME
    data = json.loads(path.read_text("utf-8"))
    assert data["tables_version"] == 4
    assert T.stored_for_page(tmp_path, 1) == [table]
    assert T.stored_for_page(tmp_path, 2) == [table]
    data["tables_version"] = 3  # written before curves were read: rows missing
    path.write_text(json.dumps(data), "utf-8")
    assert T.stored_for_page(tmp_path, 1) is None
    assert T.stored_for_page(tmp_path, 2) is None
    # storing again replaces the old file with a version 4 one
    T.store(tmp_path, [1, 2], [table])
    data = json.loads(path.read_text("utf-8"))
    assert data["tables_version"] == 4
    assert data["pages_done"] == [1, 2]
    assert T.stored_for_page(tmp_path, 2) == [table]
