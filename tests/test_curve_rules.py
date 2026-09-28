"""Rules drawn as path curves: pdfplumber files a ruling line stroked as a
Bezier segment under ``curves``. Such thin curves are read as rules only
where no table was found from rectangles, lines or cell boxes."""

import json

import pytest

from bmc_toolkit.spec import tables as T
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok
from tests.test_tables import (
    HEADER,
    ROWS_1,
    ROWS_2,
    WIDTHS,
    cell_table,
    furniture,
    reader,
    ruled_table,
    sample_table,
)

pytest.importorskip("pdfplumber")

URL = "https://example.test/DSP0236_1.3.3.pdf"


def _straight(x0, y0, x1, y1):
    """A straight segment stroked as a Bezier curve."""
    return (
        "curve",
        x0,
        y0,
        x0 + (x1 - x0) / 3,
        y0 + (y1 - y0) / 3,
        x0 + 2 * (x1 - x0) / 3,
        y0 + 2 * (y1 - y0) / 3,
        x1,
        y1,
    )


def curve_grid(x, top, widths, heights):
    """pdfgen items for the ruling lines of a table, each a straight curve."""
    xs = [x]
    for w in widths:
        xs.append(xs[-1] + w)
    ys = [top]
    for h in heights:
        ys.append(ys[-1] - h)
    items = [_straight(xs[0], y, xs[-1], y) for y in ys]
    items += [_straight(cx, ys[0], cx, ys[-1]) for cx in xs]
    return items


def curve_table(x, top, widths, heights, cells):
    """A table whose rules are all curves, with its cell text."""
    items = curve_grid(x, top, widths, heights)
    xs = [x]
    for w in widths:
        xs.append(xs[-1] + w)
    y = top
    for r, row in enumerate(cells):
        for c, text in enumerate(row):
            if text:
                items.append((xs[c] + 3, y - 11, text))
        y -= heights[r]
    return items


def _shape(tables):
    return [
        (t.drawn, [round(v, 1) for v in t.bbox], t.rows, [round(c) for c in t.columns])
        for t in tables
    ]


# ---------------------------------------------------------------- AC-1


def test_a_table_ruled_with_curves_is_read(tmp_path):
    page = [(72, 714, "Table 1 - Codes")]
    page += curve_table(72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_1])
    with reader(tmp_path, [page]) as r:
        (t,) = r.page(1).tables
        assert t.drawn == T.RULED
        assert t.rows == [HEADER, *ROWS_1]
        assert [round(c) for c in t.columns] == [72, 172, 252, 452]
        (lt,) = r.logical_tables(1)
        assert lt.caption == "Table 1 - Codes"


# ---------------------------------------------------------------- AC-2


@pytest.mark.parametrize("draw", ["cells", "fill", "line"])
def test_curves_over_a_table_found_today_change_nothing(tmp_path, draw):
    if draw == "cells":
        plain = cell_table(72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_1])
    else:
        plain = ruled_table(72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_1], style=draw)
    with_curves = plain + curve_grid(72, 700, WIDTHS, [16] * 3)
    with reader(tmp_path, [plain], "plain.pdf") as r:
        before = _shape(r.page(1).tables)
    with reader(tmp_path, [with_curves], "curves.pdf") as r:
        after = _shape(r.page(1).tables)
    assert len(before) == 1
    assert after == before


def test_a_curve_row_inside_a_found_table_adds_no_table(tmp_path):
    # an extra curve rule splitting a row of a ruled table: the table stays
    # as the rectangles draw it and no second table appears over it
    plain = ruled_table(72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_1])
    extra = plain + [_straight(72, 676, 452, 676), _straight(172, 700, 172, 652)]
    with reader(tmp_path, [plain], "plain.pdf") as r:
        before = _shape(r.page(1).tables)
    with reader(tmp_path, [extra], "extra.pdf") as r:
        assert _shape(r.page(1).tables) == before


# ---------------------------------------------------------------- AC-3


def test_a_curve_table_overlapping_a_found_table_is_dropped(tmp_path):
    plain = ruled_table(72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_1])
    # a curve grid half over the ruled table, half beside and below it
    overlap = plain + curve_grid(252, 684, [100, 100, 100], [16] * 3)
    with reader(tmp_path, [plain], "plain.pdf") as r:
        before = _shape(r.page(1).tables)
    with reader(tmp_path, [overlap], "overlap.pdf") as r:
        assert _shape(r.page(1).tables) == before


def test_a_curve_table_beside_a_found_table_is_added_in_page_order(tmp_path):
    page = curve_table(72, 700, WIDTHS, [16] * 2, [HEADER, ROWS_1[0]])
    page += ruled_table(72, 500, WIDTHS, [16] * 2, [HEADER, ROWS_2[0]])
    with reader(tmp_path, [page]) as r:
        tables = r.page(1).tables
        assert [(t.index, t.rows[1][0]) for t in tables] == [
            (0, "Temperature"),
            (1, "Current"),
        ]
        assert [t.drawn for t in tables] == [T.RULED, T.RULED]


# ---------------------------------------------------------------- AC-4


def diagram_page():
    """A block diagram: boxes stroked as closed curve paths, tiled edge to
    edge like a table, labels inside, a diagonal and an arc."""
    page = []
    for r in range(2):
        for c in range(3):
            x, y = 72 + 120 * c, 600 - 40 * r
            page.append(("curvebox", x, y, 120, 40))
            page.append((x + 10, y + 15, f"Block {r}{c}"))
    page.append(_straight(100, 300, 400, 500))  # a diagonal connector
    page.append(("curve", 100, 200, 150, 260, 250, 260, 300, 200))  # an arc
    return page


def test_boxes_diagonals_and_arcs_drawn_as_curves_are_no_table(tmp_path):
    with reader(tmp_path, [diagram_page()]) as r:
        assert r.page(1).tables == []


# ---------------------------------------------------------------- AC-5


def test_a_curve_row_at_the_top_of_a_page_joins_the_cells_table_before(tmp_path):
    page1 = furniture(1) + [(72, 214, "Table 1 - Codes")]
    page1 += cell_table(72, 200, WIDTHS, [16] * 3, [HEADER, *ROWS_1])
    page2 = furniture(2) + curve_table(72, 740, WIDTHS, [16], [ROWS_2[0]])
    page2 += [(72, 600, "Some prose after the table.")]
    with reader(tmp_path, [page1, page2]) as r:
        (lt,) = r.logical_tables(2)
        assert (lt.first, lt.last) == (1, 2)
        assert lt.rows == [HEADER, *ROWS_1, ROWS_2[0]]
        assert lt.row_pages == [1, 1, 1, 2]


def test_two_one_row_curve_parts_across_a_page_break_are_one_table(tmp_path):
    # a Version / Release table the page break cut after its first row
    version = ["Version", "v1.2", "v1.1"]
    release = ["Release", "2026.1", "2025.4"]
    page1 = furniture(1) + [(72, 60 + 16 + 20, "Some prose before the table.")]
    page1 += curve_table(72, 60 + 16, WIDTHS, [16], [version])
    page2 = furniture(2) + curve_table(72, 740, WIDTHS, [16], [release])
    page2 += [(72, 600, "Some prose after the table.")]
    with reader(tmp_path, [page1, page2]) as r:
        (lt,) = r.logical_tables(1)
        assert (lt.first, lt.last) == (1, 2)
        assert lt.rows == [version, release]


# ---------------------------------------------------------------- AC-6


def test_a_version_3_store_is_read_again(tmp_path):
    assert T.TABLES_VERSION == 4
    T.store(tmp_path, 2, [sample_table()])
    path = tmp_path / T.TABLES_NAME
    data = json.loads(path.read_text("utf-8"))
    assert data["tables_version"] == 4
    assert T.stored_for_page(tmp_path, 2) is not None
    data["tables_version"] = 3  # may lack the rows curves draw
    path.write_text(json.dumps(data), "utf-8")
    assert T.stored_for_page(tmp_path, 2) is None


# ------------------------------------------------------- through the CLI


def run(capsys, catalog_file, *argv):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    pytest.importorskip("pypdfium2")
    page1 = furniture(1) + [(72, 740, "5 Codes"), (72, 714, "Table 1 - Codes")]
    page1 += curve_table(72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_1])
    page2 = furniture(2) + [(72, 740, "6 Blocks")] + diagram_page()
    pdf = pdfgen.write_pdf(
        tmp_path / "codes.pdf",
        [page1, page2],
        bookmarks=[(0, "5 Codes", 0), (0, "6 Blocks", 1)],
    )
    scripted.responses[URL] = ok(pdf.read_bytes())
    code, out = run(capsys, catalog_file, "fetch", "DSP0236")
    assert code == 0, out


def test_table_prints_a_curve_ruled_table(held, catalog_file, capsys):
    code, out = run(capsys, catalog_file, "table", "DSP0236", "--page", "1")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[1] == "table: Table 1 - Codes | ruled | page 1 | 3 columns | 3 rows"
    assert lines[4:] == ["Temperature | 01h  | degrees", "Voltage     | 02h  | volts"]


def test_table_on_a_curve_diagram_exits_2(held, catalog_file, capsys):
    code, out = run(capsys, catalog_file, "table", "DSP0236", "--page", "2")
    assert code == 2
    assert out.startswith("no table on page 2 of DSP0236 1.3.3; ")
