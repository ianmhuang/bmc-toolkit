"""Reviewer acceptance tests for tables drawn as tiled cell boxes (M9
AC-1 to AC-4): detection from box edges, the ``table:`` drawing label and
the store version, ruled tables left alone, shapes that are not tables.
Synthetic PDFs only; the scripted client keeps the network out."""

import json

import pytest

from bmc_toolkit.spec import tables as T
from bmc_toolkit.spec.cli import ROW_CAP, main
from tests import pdfgen
from tests.conftest import ok

pytest.importorskip("pypdfium2")
pytest.importorskip("pdfplumber")

URL = "https://example.test/DSP0236_1.3.3.pdf"
WIDTHS = [100, 80, 200]
HEADER = ["Type", "Code", "Meaning"]
ROWS_A = [["PLDM", "0x01", "platform level"], ["NVMe-MI", "0x04", "management"]]
ROWS_B = [["SPDM", "0x05", "security"], ["Vendor", "0x7E", "PCI vendor"]]


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def boxes(x, top, widths, heights, cells, *, gray=0.9, header_gray=0.8):
    """pdfgen items for a table with no ruling lines: one filled box per
    cell, boxes tiled edge to edge, the header row darker. ``top`` is the
    top edge in PDF points (origin bottom-left). A cell given as None is
    merged into the box on its left."""
    items = []
    xs = [x]
    for w in widths:
        xs.append(xs[-1] + w)
    ys = [top]
    for h in heights:
        ys.append(ys[-1] - h)
    for r, row in enumerate(cells):
        h = heights[r]
        c = 0
        while c < len(row):
            span = 1
            while c + span < len(row) and row[c + span] is None:
                span += 1
            w = xs[c + span] - xs[c]
            items.append(
                ("fill", xs[c], ys[r] - h, w, h, header_gray if r == 0 else gray)
            )
            lines = row[c] if isinstance(row[c], list) else [row[c]]
            for k, text in enumerate(lines):
                if text:
                    items.append((xs[c] + 3, ys[r] - 11 - 12 * k, text))
            c += span
    return items


def rules(x, top, widths, heights, cells):
    """A Word-style ruled table: thin filled rectangles as rules, text in
    each cell, and a shaded box behind every header cell (the way Word
    paints a shaded header), which lies inside the table's rules."""
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
    for c, w in enumerate(widths):  # one shaded box per header cell
        items.append(("fill", xs[c], top - heights[0], w, heights[0], 0.85))
    for r, row in enumerate(cells):
        for c, cell in enumerate(row):
            items.append((xs[c] + 3, ys[r] - 11, cell))
    return items


def furniture(n):
    return [(72, 760, "Spec Title"), (300, 40, f"Page {n}")]


def document(tmp_path):
    """Page 1: a captioned cell-box table, prose below it. Page 2: a
    captioned cell-box table at the foot of the page that carries on at
    the top of page 3 with its header repeated; prose below it on page 3.
    Page 4: a ruled table with a shaded header, then a cell-box table
    lower down. Page 5: shaded things that are not a table. Page 6: a
    cell-box table with a merged row, a title bar right above it and a
    note box right below it."""
    page1 = furniture(1) + [(72, 740, "7 Message types"), (72, 714, "Table 1 - Types")]
    page1 += boxes(72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_A])
    page1 += [(72, 620, "The values above are assigned by DMTF.")]

    page2 = furniture(2) + [(72, 214, "Table 2 - Split")]
    page2 += boxes(72, 200, WIDTHS, [16] * 3, [HEADER, *ROWS_A])
    page3 = furniture(3) + boxes(72, 740, WIDTHS, [16] * 3, [HEADER, *ROWS_B])
    page3 += [(72, 600, "Text after the split table.")]

    page4 = furniture(4) + [(72, 714, "Table 3 - Ruled")]
    page4 += rules(72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_A])
    page4 += [(72, 560, "Table 4 - Boxed")]
    page4 += boxes(72, 546, WIDTHS, [16] * 2, [HEADER, ROWS_B[0]])

    page5 = furniture(5) + [
        (72, 740, "8 Nothing tabular here"),
        ("fill", 72, 640, 400, 40, 0.9),  # a NOTE box
        (75, 660, "NOTE: one shaded block"),
    ]
    page5 += boxes(72, 560, WIDTHS, [16], [HEADER])  # one row of boxes
    page5 += [  # two rows of boxes touching only at a corner
        ("fill", 72, 400, 100, 16, 0.9),
        ("fill", 172, 384, 100, 16, 0.9),
        ("fill", 72, 368, 100, 16, 0.9),
        ("fill", 172, 352, 100, 16, 0.9),
    ]

    page6 = furniture(6) + [
        ("fill", 72, 684, sum(WIDTHS), 16, 0.7),  # touches the table's top
        (75, 689, "Title bar"),
    ]
    page6 += boxes(
        72, 684, WIDTHS, [16] * 4, [HEADER, ["Group A", None, None], *ROWS_A]
    )
    page6 += [("fill", 72, 684 - 16 * 5, sum(WIDTHS), 16, 0.9)]
    page6 += [(75, 684 - 16 * 5 + 5, "NOTE: below the table")]

    # Page 7: a cell-box table at the foot whose last row has a two-line
    # cell; page 8: the page break put the second line into a box of its
    # own (first cell empty) under the repeated header (round 1, F1).
    page7 = furniture(7) + [(72, 214, "Table 5 - Cut")]
    page7 += boxes(
        72, 200, WIDTHS, [16] * 3, [HEADER, ROWS_A[0], ["Fan", "0x06", "rpm and"]]
    )
    page8 = furniture(8) + boxes(
        72, 740, WIDTHS, [16] * 3, [HEADER, ["", "", "duty cycle"], ROWS_B[0]]
    )
    page8 += [(72, 600, "Text after the cut table.")]
    return pdfgen.write_pdf(
        tmp_path / "doc.pdf",
        [page1, page2, page3, page4, page5, page6, page7, page8],
        bookmarks=[(0, "7 Message types", 0), (0, "8 Nothing tabular here", 4)],
    )


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    scripted.responses[URL] = ok(document(tmp_path).read_bytes())
    for argv in (["fetch", "DSP0236"], ["extract", "DSP0236"]):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


@pytest.fixture
def reader(tmp_path):
    with T.Reader(document(tmp_path)) as r:
        yield r


# ------------------------------------------------------------------ AC-1


def test_ac1_tiled_boxes_are_a_table_with_rows_and_columns_from_the_edges(reader):
    (t,) = reader.page(1).tables
    assert t.drawn == T.CELLS
    assert t.rows == [HEADER, *ROWS_A]
    assert [round(c) for c in t.columns] == [72, 172, 252, 452]
    (lt,) = reader.logical_tables(1)
    assert lt.drawn == T.CELLS
    assert lt.caption == "Table 1 - Types"
    assert (lt.first, lt.last, lt.index) == (1, 1, 1)
    assert lt.rows == [HEADER, *ROWS_A]


def test_ac1_cells_table_continues_across_pages_and_drops_the_header(reader):
    (lt,) = reader.logical_tables(2)
    assert lt.drawn == T.CELLS
    assert (lt.first, lt.last) == (2, 3)
    assert lt.caption == "Table 2 - Split"
    assert lt.rows == [HEADER, *ROWS_A, *ROWS_B]
    assert reader.logical_tables(3) == [lt]


def test_ac1_a_cells_row_the_page_break_cut_is_joined(reader):
    # round 1, F1: a cells table has no rule to show its last row complete,
    # so the continuation row with an empty first cell is the rest of it
    (lt,) = reader.logical_tables(7)
    assert lt.drawn == T.CELLS
    assert (lt.first, lt.last) == (7, 8)
    assert lt.caption == "Table 5 - Cut"
    assert lt.rows == [
        HEADER,
        ROWS_A[0],
        ["Fan", "0x06", "rpm and\nduty cycle"],
        ROWS_B[0],
    ]
    assert lt.row_pages == [7, 7, 7, 8]
    assert reader.logical_tables(8) == [lt]


def test_ac1_cli_prints_the_joined_row_as_one_row(held, catalog_file, capsys):
    code, out = run(capsys, "table", "DSP0236", "--page", "8", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].split(" | ")[3] == "PDF pages 7-8"
    assert lines[1] == (
        "table: Table 5 - Cut | cells (no ruling lines) | pages 7-8 | 3 columns "
        "| 4 rows"
    )
    body = [ln.split(" | ") for ln in lines[4:] if "+" not in ln]
    cells = [[c.strip() for c in row] for row in body]
    assert ["Fan", "0x06", "rpm and"] in cells
    assert ["", "", "duty cycle"] in cells  # the second physical line of the cell
    assert cells.index(["", "", "duty cycle"]) == cells.index(["Fan", "0x06", "rpm and"]) + 1
    assert cells[-1] == ROWS_B[0]


def test_ac1_a_merged_box_stays_one_cell_and_bars_around_it_are_not_rows(reader):
    (t,) = reader.page(6).tables
    assert t.drawn == T.CELLS
    assert t.rows[0] == HEADER
    assert t.rows[1][0] == "Group A"
    assert "Group A" not in t.rows[1][1:]
    assert t.rows[2:] == ROWS_A
    assert "Title bar" not in str(t.rows) and "NOTE" not in str(t.rows)


def test_ac1_cli_prints_the_cells_table_with_a_cite_line(held, catalog_file, capsys):
    code, out = run(capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    fields = lines[0].split(" | ")
    assert fields[0] == "cite: mctp"
    assert fields[1] == "DSP0236 1.3.3"
    assert fields[3] == "PDF pages 2-3"
    assert fields[4] == "lines table 1"
    assert lines[1] == (
        "table: Table 2 - Split | cells (no ruling lines) | pages 2-3 | 3 columns "
        "| 5 rows"
    )
    assert lines[2].split(" | ") == ["Type   ", "Code", "Meaning"]
    body = [ln.split(" | ") for ln in lines[4:]]
    assert [[c.strip() for c in row] for row in body] == [*ROWS_A, *ROWS_B]


# ------------------------------------------------------------------ AC-2


def test_ac2_table_line_names_the_drawing_and_the_store_records_it(
    held, catalog_file, capsys
):
    code, out = run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[1] == (
        "table: Table 1 - Types | cells (no ruling lines) | page 1 | 3 columns | 3 rows"
    )
    code, out = run(capsys, "table", "DSP0236", "--page", "4", catalog_file=catalog_file)
    assert code == 0, out
    table_lines = [ln for ln in out.splitlines() if ln.startswith("table: ")]
    assert table_lines == [
        "table: Table 3 - Ruled | ruled | page 4 | 3 columns | 3 rows",
        "table: Table 4 - Boxed | cells (no ruling lines) | page 4 | 3 columns | 2 rows",
    ]
    data = json.loads((held / "tables.json").read_text("utf-8"))
    assert data["tables_version"] == 2
    assert T.TABLES_VERSION == 2
    drawn = {(t["first"], t["index"]): t["drawn"] for t in data["tables"]}
    assert drawn == {(1, 1): "cells", (4, 1): "ruled", (4, 2): "cells"}


def test_ac2_a_version_1_store_is_read_again(held, catalog_file, capsys):
    # a store written by version 1 claims page 1 is done and holds no table
    (held / "tables.json").write_text(
        json.dumps({"tables_version": 1, "pages_done": [1], "tables": []}), "utf-8"
    )
    code, out = run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert code == 0, out
    assert "cells (no ruling lines)" in out.splitlines()[1]
    data = json.loads((held / "tables.json").read_text("utf-8"))
    assert data["tables_version"] == 2
    assert 1 in data["pages_done"]
    assert len(data["tables"]) == 1
    # and a version 2 store is served without reading the PDF again
    data["tables"][0]["caption"] = "Table 1 - From the store"
    (held / "tables.json").write_text(json.dumps(data), "utf-8")
    code, out = run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[1].startswith("table: Table 1 - From the store | cells")


# ------------------------------------------------------------------ AC-3


def test_ac3_a_ruled_table_with_shaded_header_boxes_stays_one_ruled_table(reader):
    tables = reader.page(4).tables
    assert [t.drawn for t in tables] == [T.RULED, T.CELLS]
    ruled, cells = tables
    assert ruled.rows == [HEADER, *ROWS_A]
    assert [round(c) for c in ruled.columns] == [72, 172, 252, 452]
    assert cells.rows == [HEADER, ROWS_B[0]]
    assert ruled.top < cells.top
    logical = reader.logical_tables(4)
    assert [(lt.caption, lt.drawn, lt.index) for lt in logical] == [
        ("Table 3 - Ruled", T.RULED, 1),
        ("Table 4 - Boxed", T.CELLS, 2),
    ]


def test_ac3_a_page_with_both_kinds_is_listed_in_page_order(held, catalog_file, capsys):
    code, out = run(capsys, "table", "DSP0236", "--page", "4", catalog_file=catalog_file)
    assert code == 0, out
    cites = [ln for ln in out.splitlines() if ln.startswith("cite: ")]
    assert [c.split(" | ")[4] for c in cites] == ["lines table 1", "lines table 2"]
    code, out = run(
        capsys, "table", "DSP0236", "--page", "4", "--index", "2", catalog_file=catalog_file
    )
    assert code == 0, out
    assert out.splitlines()[1].startswith("table: Table 4 - Boxed | cells")
    assert "Table 3 - Ruled" not in out


# ------------------------------------------------------------------ AC-4


def test_ac4_lone_boxes_single_rows_and_corner_contacts_are_not_tables(reader):
    assert reader.page(5).tables == []
    assert reader.logical_tables(5) == []


def test_row_cap_on_a_cells_table_counts_body_rows_only(
    catalog_file, library, scripted, tmp_path, capsys
):
    """The row cap (declared in What, not an AC) on a cells table: only the
    rows starting on the page asked for, and on the first page the note
    does not count the header as row 0 (round 1, F2)."""
    per_page = 40
    pages = ROW_CAP // per_page + 2
    doc = []
    n = 0
    for p in range(1, pages + 1):
        rows = []
        for _ in range(per_page):
            n += 1
            rows.append([f"item{n}", f"{n:03d}"])
        items = furniture(p)
        if p == 1:
            items.append((72, 714, "Table 9 - Long"))
        items += boxes(72, 700, [120, 80], [12] * (per_page + 1), [["Name", "Code"], *rows])
        doc.append(items)
    pdf = pdfgen.write_pdf(tmp_path / "long.pdf", doc)
    scripted.responses[URL] = ok(pdf.read_bytes())
    for argv in (["fetch", "DSP0236"], ["extract", "DSP0236"]):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert code == 0, out
    total = per_page * pages
    code, out = run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[1] == (
        f"table: Table 9 - Long | cells (no ruling lines) | pages 1-{pages} | "
        f"2 columns | {total + 1} rows"
    )
    assert lines[2] == (
        f"note: rows 1-{per_page} of {total}, those starting on page 1; "
        f"the table runs over pages 1-{pages}; --all-rows prints them all"
    )
    body = [ln for ln in lines[3:] if ln.startswith("item")]
    assert len(body) == per_page and body[0].startswith("item1 ")
    code, out = run(capsys, "table", "DSP0236", "--page", "3", catalog_file=catalog_file)
    assert code == 0, out
    first = 2 * per_page + 1
    assert out.splitlines()[2].startswith(f"note: rows {first}-{first + per_page - 1} of ")
    code, out = run(
        capsys, "table", "DSP0236", "--page", "3", "--all-rows", catalog_file=catalog_file
    )
    assert code == 0, out
    assert "note:" not in out
    assert len([ln for ln in out.splitlines() if ln.startswith("item")]) == total


def test_ac4_no_table_message_names_the_page_and_exits_2(held, catalog_file, capsys):
    code, out = run(capsys, "table", "DSP0236", "--page", "5", catalog_file=catalog_file)
    assert code == 2
    assert out.strip() == (
        "no table on page 5 of DSP0236 1.3.3; read the page with: "
        "bmcspec page DSP0236 5, or look at it with: bmcspec render DSP0236 --page 5"
    )
    assert "ruled" not in out
