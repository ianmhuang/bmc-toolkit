"""Logical Tables from synthetic ruled PDFs: cells from rules only,
continuation across pages, captions, page furniture, the store, the grid."""

import json

import pytest

from bmc_toolkit.spec import tables as T
from tests import pdfgen

pytest.importorskip("pdfplumber")

WIDTHS = [100, 80, 200]
HEADER = ["Name", "Code", "Meaning"]
ROWS_1 = [["Temperature", "01h", "degrees"], ["Voltage", "02h", "volts"]]
ROWS_2 = [["Current", "03h", "amps"], ["Fan", "04h", "rpm"]]


def ruled_table(
    x,
    top,
    widths,
    heights,
    cells,
    *,
    style="fill",
    shade_header=False,
    top_rule=True,
    bottom_rule=True,
):
    """pdfgen items for a ruled table whose top edge is at ``top`` (PDF
    points, origin bottom-left); ``cells[r][c]`` is a string or a list of
    lines. ``fill`` draws the rules as thin filled rectangles the way Word
    does, ``line`` strokes them."""
    items = []
    total_w = sum(widths)
    total_h = sum(heights)
    xs = [x]
    for w in widths:
        xs.append(xs[-1] + w)
    ys = [top]
    for h in heights:
        ys.append(ys[-1] - h)
    if shade_header:  # Word paints a shaded cell as one block per text line
        h = heights[0]
        items.append(("fill", x, top - h / 2, total_w, h / 2, 0.9))
        items.append(("fill", x, top - h, total_w, h / 2, 0.9))
    for i, y in enumerate(ys):
        if (i == 0 and not top_rule) or (i == len(ys) - 1 and not bottom_rule):
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
    for r, row in enumerate(cells):
        for c, cell in enumerate(row):
            lines = cell if isinstance(cell, list) else [cell]
            for k, text in enumerate(lines):
                if text:
                    items.append((xs[c] + 3, ys[r] - 11 - 12 * k, text))
    return items


def furniture(n):
    """A running header and a page number, at the same height on every page."""
    return [(72, 760, "Spec Title"), (300, 40, f"Page {n}")]


def two_pages(
    *, header2=None, between=None, caption2=False, widths2=None, style="fill"
):
    """A table starting at the bottom of page 1 and carrying on at the top
    of page 2, with the knobs the continuation tests turn."""
    page1 = furniture(1) + [(72, 214, "Table 1 - Codes")]
    page1 += ruled_table(72, 200, WIDTHS, [16] * 3, [HEADER, *ROWS_1], style=style)
    if between:
        page1.append((72, 120, between))
    page2 = furniture(2)
    if caption2:
        page2.append((72, 754, "Table 2 - More"))
    rows2 = [header2 or HEADER, *ROWS_2]
    page2 += ruled_table(72, 740, widths2 or WIDTHS, [16] * 3, rows2, style=style)
    return [page1, page2]


def reader(tmp_path, pages, name="t.pdf"):
    return T.Reader(pdfgen.write_pdf(tmp_path / name, pages))


# ------------------------------------------------------------ one page


def test_rules_define_the_cells_and_shading_does_not(tmp_path):
    page = [(72, 714, "Table 1 - Codes")]
    page += ruled_table(72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_1], shade_header=True)
    with reader(tmp_path, [page]) as r:
        tables = r.logical_tables(1)
    assert len(tables) == 1
    t = tables[0]
    assert (t.first, t.last, t.index) == (1, 1, 1)
    assert t.caption == "Table 1 - Codes"
    assert t.rows == [HEADER, *ROWS_1]
    assert [round(c) for c in t.columns] == [72, 172, 252, 452]
    assert t.parts[0][:2] == [1, 0]


def test_stroked_lines_are_rules_too(tmp_path):
    page = ruled_table(72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_1], style="line")
    with reader(tmp_path, [page]) as r:
        tables = r.logical_tables(1)
    assert len(tables) == 1
    assert tables[0].rows == [HEADER, *ROWS_1]
    assert tables[0].caption is None


def test_multi_line_cells_keep_their_lines(tmp_path):
    rows = [HEADER, ["Processor", "07h", ["IERR", "Thermal Trip"]]]
    page = ruled_table(72, 700, WIDTHS, [16, 28], rows)
    with reader(tmp_path, [page]) as r:
        t = r.logical_tables(1)[0]
    assert t.rows[1] == ["Processor", "07h", "IERR\nThermal Trip"]


def test_caption_skips_a_margin_line_number_and_needs_the_word_table(tmp_path):
    numbered = [(37, 714, "2343"), (72, 714, "Table 69 - Format")]
    numbered += ruled_table(72, 700, WIDTHS, [16] * 2, [HEADER, ROWS_1[0]])
    prose = [(72, 714, "The table below lists the codes.")]
    prose += ruled_table(72, 700, WIDTHS, [16] * 2, [HEADER, ROWS_1[0]])
    far = [(72, 760, "Table 3 - Far away")]
    far += ruled_table(72, 700, WIDTHS, [16] * 2, [HEADER, ROWS_1[0]])
    with reader(tmp_path, [numbered, prose, far]) as r:
        assert r.logical_tables(1)[0].caption == "Table 69 - Format"
        assert r.logical_tables(2)[0].caption is None
        assert r.logical_tables(3)[0].caption is None


def test_two_tables_on_a_page_stay_apart_and_keep_their_order(tmp_path):
    page = ruled_table(72, 700, WIDTHS, [16] * 2, [HEADER, ROWS_1[0]])
    page += ruled_table(72, 500, WIDTHS, [16] * 2, [HEADER, ROWS_2[0]])
    with reader(tmp_path, [page]) as r:
        tables = r.logical_tables(1)
    assert [(t.index, t.rows[1][0]) for t in tables] == [
        (1, "Temperature"),
        (2, "Current"),
    ]


def test_a_frame_around_text_is_not_a_table(tmp_path):
    stroked = [("rect", 40, 40, 532, 712), (72, 700, "Just a framed page")]
    filled = ruled_table(40, 752, [532], [712], [["Just a framed page"]])
    with reader(tmp_path, [stroked, filled]) as r:
        assert r.logical_tables(1) == []
        assert r.logical_tables(2) == []


def test_an_underline_and_a_bar_are_not_a_table(tmp_path):
    # pdfplumber refuses fewer than two explicit rules each way: guard it
    underline = [(72, 700, "Heading"), ("fill", 72, 696, 200, 0.6)]
    one_each = [("fill", 72, 696, 200, 0.6), ("fill", 300, 500, 0.6, 100)]
    with reader(tmp_path, [underline, one_each]) as r:
        assert r.logical_tables(1) == []
        assert r.logical_tables(2) == []


# --------------------------------------------------------- continuation


def test_continuation_merges_and_drops_the_repeated_header(tmp_path):
    with reader(tmp_path, two_pages()) as r:
        from_two = r.logical_tables(2)
        from_one = r.logical_tables(1)
    assert len(from_two) == 1
    t = from_two[0]
    assert (t.first, t.last, t.index) == (1, 2, 1)
    assert t.caption == "Table 1 - Codes"
    assert t.rows == [HEADER, *ROWS_1, *ROWS_2]
    assert [p[:2] for p in t.parts] == [[1, 0], [2, 0]]
    assert from_one[0].rows == t.rows


def test_continued_header_is_dropped_too(tmp_path):
    pages = two_pages(header2=["Name (continued)", "Code", "Meaning"])
    with reader(tmp_path, pages) as r:
        t = r.logical_tables(2)[0]
    assert t.rows == [HEADER, *ROWS_1, *ROWS_2]


def test_stroked_tables_continue_as_well(tmp_path):
    with reader(tmp_path, two_pages(style="line")) as r:
        t = r.logical_tables(2)[0]
    assert (t.first, t.last) == (1, 2)


def test_body_text_between_the_parts_stops_the_merge(tmp_path):
    with reader(tmp_path, two_pages(between="Some prose after the table.")) as r:
        first = r.logical_tables(1)
        second = r.logical_tables(2)
    assert [(t.first, t.last) for t in first] == [(1, 1)]
    assert [(t.first, t.last) for t in second] == [(2, 2)]
    assert second[0].rows == [HEADER, *ROWS_2]  # its header is its own


def test_a_caption_on_the_next_page_stops_the_merge(tmp_path):
    with reader(tmp_path, two_pages(caption2=True)) as r:
        second = r.logical_tables(2)
    assert [(t.first, t.last, t.caption) for t in second] == [(2, 2, "Table 2 - More")]


def test_different_columns_stop_the_merge(tmp_path):
    with reader(tmp_path, two_pages(widths2=[120, 60, 200])) as r:
        assert [(t.first, t.last) for t in r.logical_tables(2)] == [(2, 2)]


def test_furniture_must_repeat_at_the_same_height(tmp_path):
    # The running header's text again, but lower on the page: body text.
    with reader(tmp_path, two_pages(between="Spec Title")) as r:
        assert [(t.first, t.last) for t in r.logical_tables(2)] == [(2, 2)]


def test_a_row_cut_by_the_page_break_is_closed_and_joined(tmp_path):
    rows1 = [HEADER, ["Processor", "07h", ["IERR", "Thermal Trip"]]]
    page1 = furniture(1) + ruled_table(
        72, 200, WIDTHS, [16, 28], rows1, bottom_rule=False
    )
    rows2 = [HEADER, ["", "", ["FRB1", "FRB2"]], ["Power", "08h", "watts"]]
    page2 = furniture(2) + ruled_table(72, 740, WIDTHS, [16, 28, 16], rows2)
    with reader(tmp_path, [page1, page2]) as r:
        t = r.logical_tables(1)[0]
    assert (t.first, t.last) == (1, 2)
    assert t.rows == [
        HEADER,
        ["Processor", "07h", "IERR\nThermal Trip\nFRB1\nFRB2"],
        ["Power", "08h", "watts"],
    ]


def test_a_grouped_row_after_a_closed_bottom_stays_a_row(tmp_path):
    # An empty first cell is how tables group rows; only a missing bottom
    # rule says the page break cut a row.
    rows1 = [HEADER, ["Processor", "07h", "IERR"]]
    page1 = furniture(1) + ruled_table(72, 200, WIDTHS, [16, 16], rows1)
    rows2 = [HEADER, ["", "08h", "Thermal Trip"], ["Power", "09h", "watts"]]
    page2 = furniture(2) + ruled_table(72, 740, WIDTHS, [16] * 3, rows2)
    with reader(tmp_path, [page1, page2]) as r:
        t = r.logical_tables(1)[0]
    assert (t.first, t.last) == (1, 2)
    assert t.rows == [HEADER, *rows1[1:], *rows2[1:]]


def test_a_body_row_equal_to_an_earlier_one_is_kept(tmp_path):
    placeholder = ["reserved", "-", "-"]
    page1 = furniture(1) + ruled_table(
        72, 200, WIDTHS, [16] * 3, [HEADER, placeholder, ROWS_1[0]]
    )
    page2 = furniture(2) + ruled_table(
        72, 740, WIDTHS, [16] * 3, [HEADER, placeholder, ROWS_2[0]]
    )
    with reader(tmp_path, [page1, page2]) as r:
        t = r.logical_tables(2)[0]
    assert t.rows == [HEADER, placeholder, ROWS_1[0], placeholder, ROWS_2[0]]


def test_a_repeated_header_and_a_continued_sub_header_are_both_dropped(tmp_path):
    widths = [100, 160, 120]
    sub = ["Type", "Response data", ""]
    page1 = furniture(1) + ruled_table(
        72, 200, widths, [16] * 3, [HEADER, sub, ROWS_1[0]]
    )
    rows2 = [HEADER, ["Type", "Response data (continued)", ""], ROWS_2[0]]
    page2 = furniture(2) + ruled_table(72, 740, widths, [16] * 3, rows2)
    with reader(tmp_path, [page1, page2]) as r:
        t = r.logical_tables(1)[0]
    assert t.rows == [HEADER, sub, ROWS_1[0], ROWS_2[0]]


def test_read_page_assembles_every_table_on_the_pages_it_visits(tmp_path):
    page1 = furniture(1) + ruled_table(72, 200, WIDTHS, [16] * 2, [HEADER, ROWS_1[0]])
    page2 = furniture(2) + ruled_table(72, 740, WIDTHS, [16] * 2, [HEADER, ROWS_1[1]])
    page2 += ruled_table(72, 500, WIDTHS, [16] * 2, [HEADER, ROWS_2[0]])
    page3 = furniture(3) + ruled_table(72, 740, WIDTHS, [16] * 2, [HEADER, ROWS_2[1]])
    with reader(tmp_path, [page1, page2, page3]) as r:
        on_page, found, done = r.read_page(1)
    assert [(t.first, t.last) for t in on_page] == [(1, 2)]
    assert sorted((t.first, t.last, t.index) for t in found) == [(1, 2, 1), (2, 3, 2)]
    assert done == [1, 2, 3]


def test_three_pages_walk_both_ways_from_the_middle(tmp_path):
    page1 = furniture(1) + ruled_table(72, 200, WIDTHS, [16] * 2, [HEADER, ROWS_1[0]])
    page2 = furniture(2) + ruled_table(72, 740, WIDTHS, [16] * 2, [HEADER, ROWS_1[1]])
    page3 = furniture(3) + ruled_table(72, 740, WIDTHS, [16] * 2, [HEADER, ROWS_2[0]])
    with reader(tmp_path, [page1, page2, page3]) as r:
        t = r.logical_tables(2)[0]
    assert (t.first, t.last) == (1, 3)
    assert t.rows == [HEADER, ROWS_1[0], ROWS_1[1], ROWS_2[0]]


# ------------------------------------------------------------ pure parts


def test_drop_repeated_header_and_join_cells():
    so_far = [HEADER, ["Type", "Response data"]]
    assert T.drop_repeated_header(
        so_far, [["Type", "Response data (continued)"], ["a"]]
    ) == [["a"]]
    assert T.drop_repeated_header(so_far, [["NAME", " code ", "meaning"], ["a"]]) == [
        ["a"]
    ]
    assert T.drop_repeated_header(so_far, [["Other"], ["a"]]) == [["Other"], ["a"]]
    body = [["Type", "Response data"], ["a"]]  # equal to a body row, unmarked
    assert T.drop_repeated_header(so_far, body) == body
    assert T.drop_repeated_header(so_far, []) == []
    assert T.join_cells(["a", "b"], ["", "c", "d"]) == ["a", "b\nc", "d"]


def test_columns_match_within_tolerance():
    assert T.columns_match([72.0, 172.0], [77.9, 166.1])
    assert not T.columns_match([72.0, 172.0], [72.0, 180.0])
    assert not T.columns_match([72.0, 172.0], [72.0, 172.0, 300.0])


def sample_table():
    return T.LogicalTable(
        first=1,
        last=2,
        index=1,
        caption="Table 1 - Codes",
        section="5 Codes",
        columns=[72.0, 172.0, 452.0],
        parts=[[1, 0, 72.0, 92.0, 452.0, 140.0], [2, 0, 72.0, 52.0, 452.0, 100.0]],
        rows=[["Name", "Meaning"], ["A", "one"], ["B", "two\nlines"], ["C", "x" * 70]],
    )


def test_format_table_grid_and_describe():
    lines = T.format_table(sample_table())
    rule = "-" * 4 + "-+-" + "-" * 60
    assert lines == [
        "Name | Meaning",
        rule,
        "A    | one",
        "B    | two",
        "     | lines",
        rule,
        "C    | " + "x" * 60,
        "     | " + "x" * 10,
        rule,
    ]
    assert T.describe(sample_table()) == (
        "table: Table 1 - Codes | ruled | pages 1-2 | 2 columns | 4 rows"
    )
    single = sample_table()
    single.last = 1
    single.caption = None
    assert T.describe(single).startswith("table: - | ruled | page 1 | ")


def test_store_roundtrip_and_page_bookkeeping(tmp_path):
    t = sample_table()
    assert T.stored_for_page(tmp_path, 2) is None
    T.store(tmp_path, 2, [t])
    assert T.stored_for_page(tmp_path, 1) is None  # page 1 was never read
    got = T.stored_for_page(tmp_path, 2)
    assert got == [t]
    T.store(tmp_path, 1, [t])  # the same table again: replaced, not doubled
    data = json.loads((tmp_path / T.TABLES_NAME).read_text("utf-8"))
    assert data["pages_done"] == [1, 2]
    assert len(data["tables"]) == 1
    assert T.stored_for_page(tmp_path, 3) is None
    T.store(tmp_path, 3, [])
    assert T.stored_for_page(tmp_path, 3) == []
    T.remove_store(tmp_path)
    assert not (tmp_path / T.TABLES_NAME).exists()


def test_store_from_another_version_is_ignored(tmp_path):
    t = sample_table()
    T.store(tmp_path, 2, [t])
    path = tmp_path / T.TABLES_NAME
    data = json.loads(path.read_text("utf-8"))
    data["tables_version"] = T.TABLES_VERSION + 1
    path.write_text(json.dumps(data), encoding="utf-8")
    assert T.stored_for_page(tmp_path, 2) is None
    path.write_text("not json", encoding="utf-8")
    assert T.stored_for_page(tmp_path, 2) is None
    T.store(tmp_path, 2, [t])  # a fresh store replaces the unreadable file
    assert T.stored_for_page(tmp_path, 2) == [t]


def test_sort_on_page_orders_by_position_on_that_page():
    ending = sample_table()  # pages 1-2, sits at the top of page 2
    starting = sample_table()
    starting.first, starting.last, starting.index = 2, 3, 2
    starting.parts = [
        [2, 1, 72.0, 400.0, 452.0, 700.0],
        [3, 0, 72.0, 52.0, 452.0, 100.0],
    ]
    assert T.sort_on_page([starting, ending], 2) == [ending, starting]


# ------------------------------------------------------------ cell boxes


def cell_table(x, top, widths, heights, cells, *, gray=0.9, header_gray=0.8):
    """pdfgen items for a table drawn the way DMTF's Markdown PDFs draw
    it: no rules, one filled box per cell, boxes tiled edge to edge. A cell
    given as None is merged into the box to its left (the row then has
    fewer, wider boxes)."""
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


def test_tiled_boxes_make_a_cells_table(tmp_path):
    page = furniture(1) + [(72, 714, "Table 3 - Boxes")]
    page += cell_table(72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_1])
    with reader(tmp_path, [page]) as r:
        (t,) = r.page(1).tables
        assert t.drawn == T.CELLS
        assert t.rows == [HEADER, *ROWS_1]
        assert len(t.columns) == 4
        (lt,) = r.logical_tables(1)
        assert lt.drawn == T.CELLS
        assert lt.caption == "Table 3 - Boxes"
        assert T.describe(lt) == (
            "table: Table 3 - Boxes | cells (no ruling lines) | page 1 | 3 columns "
            "| 3 rows"
        )


def test_a_merged_box_stays_one_cell(tmp_path):
    rows = [HEADER, ["Group A", None, None], *ROWS_1]
    page = cell_table(72, 700, WIDTHS, [16] * 4, rows)
    with reader(tmp_path, [page]) as r:
        (t,) = r.page(1).tables
        assert t.drawn == T.CELLS
        assert t.rows[1][0] == "Group A"
        assert t.rows[0] == HEADER and t.rows[2] == ROWS_1[0]


def test_a_shaded_header_inside_a_ruled_table_is_not_a_second_table(tmp_path):
    page = ruled_table(72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_1])
    # one shaded box per header cell, the way Word paints a shaded header
    x = 72
    for w in WIDTHS:
        page.append(("fill", x, 700 - 16, w, 16, 0.85))
        x += w
    page += cell_table(72, 500, WIDTHS, [16] * 2, [HEADER, ROWS_2[0]])
    with reader(tmp_path, [page]) as r:
        tables = r.page(1).tables
        assert [t.drawn for t in tables] == [T.RULED, T.CELLS]
        assert tables[0].rows == [HEADER, *ROWS_1]
        assert tables[1].rows == [HEADER, ROWS_2[0]]


def test_lone_boxes_and_single_rows_are_not_tables(tmp_path):
    page = [
        ("fill", 72, 600, 400, 40, 0.9),  # a NOTE box
        (75, 620, "NOTE: one shaded block"),
    ]
    page += cell_table(72, 500, WIDTHS, [16], [HEADER])  # one row of boxes
    # two rows of boxes that touch only at a corner
    page.append(("fill", 72, 300, 100, 16, 0.9))
    page.append(("fill", 172, 284, 100, 16, 0.9))
    page.append(("fill", 72, 268, 100, 16, 0.9))
    page.append(("fill", 172, 252, 100, 16, 0.9))
    with reader(tmp_path, [page]) as r:
        assert r.page(1).tables == []


def test_a_grid_drops_leading_and_trailing_single_boxes(tmp_path):
    # a full-width shaded title box right above, and a note box right below,
    # touching the table: neither is a row of it
    page = [("fill", 72, 700, sum(WIDTHS), 16, 0.7), (75, 705, "Title bar")]
    page += cell_table(72, 700 - 16, WIDTHS, [16] * 3, [HEADER, *ROWS_1])
    page.append(("fill", 72, 700 - 16 * 5, sum(WIDTHS), 16, 0.9))
    page.append((75, 700 - 16 * 5 + 5, "NOTE: below"))
    with reader(tmp_path, [page]) as r:
        (t,) = r.page(1).tables
        assert t.rows == [HEADER, *ROWS_1]


def test_cells_tables_continue_across_pages_and_drop_the_header(tmp_path):
    page1 = furniture(1) + [(72, 214, "Table 1 - Codes")]
    page1 += cell_table(72, 200, WIDTHS, [16] * 3, [HEADER, *ROWS_1])
    page2 = furniture(2) + cell_table(72, 740, WIDTHS, [16] * 3, [HEADER, *ROWS_2])
    with reader(tmp_path, [page1, page2]) as r:
        (lt,) = r.logical_tables(1)
        assert lt.drawn == T.CELLS
        assert (lt.first, lt.last) == (1, 2)
        assert lt.rows == [HEADER, *ROWS_1, *ROWS_2]


def test_a_cells_row_cut_by_the_page_break_is_joined(tmp_path):
    # the last row of page 1 has a two-line cell; the page break puts the
    # second line into a box of its own at the top of page 2, first cell empty
    page1 = furniture(1) + [(72, 214, "Table 1 - Codes")]
    page1 += cell_table(
        72, 200, WIDTHS, [16] * 3, [HEADER, ROWS_1[0], ["Fan", "04h", "rpm and"]]
    )
    page2 = furniture(2) + cell_table(
        72, 740, WIDTHS, [16] * 3, [HEADER, ["", "", "duty cycle"], ROWS_2[0]]
    )
    with reader(tmp_path, [page1, page2]) as r:
        (lt,) = r.logical_tables(1)
        assert lt.drawn == T.CELLS
        assert lt.rows == [
            HEADER,
            ROWS_1[0],
            ["Fan", "04h", "rpm and\nduty cycle"],
            ROWS_2[0],
        ]
        assert lt.row_pages == [1, 1, 1, 2]


def test_store_keeps_drawn_and_reads_an_old_store_again(tmp_path):
    t = sample_table()
    t.drawn = T.CELLS
    T.store(tmp_path, 2, [t])
    (got,) = T.stored_for_page(tmp_path, 2)
    assert got.drawn == T.CELLS
    data = json.loads((tmp_path / T.TABLES_NAME).read_text("utf-8"))
    assert data["tables_version"] == 2
    assert data["tables"][0]["drawn"] == "cells"
    del data["tables"][0]["drawn"]  # a version 1 entry has no drawn key
    data["tables_version"] = 1
    (tmp_path / T.TABLES_NAME).write_text(json.dumps(data), "utf-8")
    assert T.stored_for_page(tmp_path, 2) is None
    assert T.LogicalTable.from_dict(data["tables"][0]).drawn == T.RULED
