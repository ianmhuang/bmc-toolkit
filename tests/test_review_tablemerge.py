"""Reviewer acceptance tests for the Logical Table rules (AC-2, AC-3, AC-4,
AC-5) against the Reader on synthetic ruled PDFs: cells from rules only,
the continuation conditions and their stop cases, page furniture, captions."""

import pytest

from tests import pdfgen

pytest.importorskip("pdfplumber")

from bmc_toolkit.spec.tables import Reader  # noqa: E402

WIDTHS = [100, 80, 200]
HEADER = ["Name", "Code", "Meaning"]
ROWS_A = [["Temperature", "01h", "degrees"], ["Voltage", "02h", "volts"]]
ROWS_B = [["Current", "03h", "amps"], ["Fan", "04h", "rpm"]]


def grid(
    x,
    top,
    widths,
    heights,
    cells,
    *,
    style="fill",
    per_cell=False,
    shade=False,
    bottom_rule=True,
):
    """A ruled table with its top edge at ``top`` (PDF points, origin
    bottom-left). ``fill`` draws thin filled rectangles, ``line`` strokes.
    ``per_cell`` draws every cell's own four borders, neighbours 1 pt
    apart, the way Word emits adjacent border rectangles. ``shade`` paints
    the header row's background in two light blocks. ``bottom_rule=False``
    leaves the last row open at the bottom, as a page break cuts it."""
    items = []
    total_w = sum(widths)
    total_h = sum(heights)
    xs = [x]
    for w in widths:
        xs.append(xs[-1] + w)
    ys = [top]
    for h in heights:
        ys.append(ys[-1] - h)
    if shade:
        h = heights[0]
        items.append(("fill", x, top - h / 2, total_w, h / 2, 0.9))
        items.append(("fill", x, top - h, total_w, h / 2, 0.9))
    if per_cell:
        for r in range(len(heights)):
            for c in range(len(widths)):
                x0, x1 = xs[c] + 0.5, xs[c + 1] - 0.5
                y1, y0 = ys[r] - 0.5, ys[r + 1] + 0.5
                items.append(("fill", x0, y1 - 0.3, x1 - x0, 0.6))
                items.append(("fill", x0, y0 - 0.3, x1 - x0, 0.6))
                items.append(("fill", x0 - 0.3, y0, 0.6, y1 - y0))
                items.append(("fill", x1 - 0.3, y0, 0.6, y1 - y0))
    else:
        for y in ys[:-1] if not bottom_rule else ys:
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
    return [(72, 760, "Spec Title"), (300, 40, f"Page {n}")]


def split(
    *, header2=None, between=None, caption2=None, x2=72, widths2=None, style="fill"
):
    """A captioned table at the foot of page 1 and a table at the head of
    page 2, with the knobs AC-3 and AC-4 talk about."""
    page1 = furniture(1) + [(72, 214, "Table 1 - Codes")]
    page1 += grid(72, 200, WIDTHS, [16] * 3, [HEADER, *ROWS_A], style=style)
    if between:
        page1.append((72, 120, between))
    page2 = furniture(2)
    if caption2:
        page2.append((72, 754, caption2))
    rows2 = [header2 or HEADER, *ROWS_B]
    page2 += grid(x2, 740, widths2 or WIDTHS, [16] * 3, rows2, style=style)
    return [page1, page2]


def reader(tmp_path, pages):
    return Reader(pdfgen.write_pdf(tmp_path / "t.pdf", pages))


def spans(tables):
    return [(t.first, t.last) for t in tables]


# ----------------------------------------------------------------- AC-2


def test_shaded_header_stays_one_row_and_filled_rules_define_cells(tmp_path):
    page = grid(72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_A], shade=True)
    with reader(tmp_path, [page]) as r:
        (t,) = r.logical_tables(1)
    assert t.rows == [HEADER, *ROWS_A]
    assert len(t.columns) == 4


def test_adjacent_border_rectangles_make_no_phantom_columns(tmp_path):
    page = grid(72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_A], per_cell=True)
    with reader(tmp_path, [page]) as r:
        (t,) = r.logical_tables(1)
    assert t.rows == [HEADER, *ROWS_A]
    assert len(t.columns) == 4
    for got, want in zip(t.columns, [72, 172, 252, 452], strict=True):
        assert abs(got - want) <= 1.5, t.columns


def test_stroked_lines_are_rules(tmp_path):
    page = grid(72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_A], style="line")
    with reader(tmp_path, [page]) as r:
        (t,) = r.logical_tables(1)
    assert t.rows == [HEADER, *ROWS_A]


# ----------------------------------------------------------------- AC-3


def test_continuation_merges_from_either_page_and_drops_the_repeated_header(
    tmp_path,
):
    with reader(tmp_path, split()) as r:
        one = r.logical_tables(1)
        two = r.logical_tables(2)
    assert spans(one) == [(1, 2)] and spans(two) == [(1, 2)]
    assert one[0].rows == [HEADER, *ROWS_A, *ROWS_B]
    assert two[0].rows == one[0].rows
    assert one[0].caption == "Table 1 - Codes"
    assert one[0].index == 1


def test_header_marked_continued_is_dropped(tmp_path):
    pages = split(header2=["Name (continued)", "Code", "Meaning"])
    with reader(tmp_path, pages) as r:
        (t,) = r.logical_tables(2)
    assert t.rows == [HEADER, *ROWS_A, *ROWS_B]


def test_column_edges_within_six_points_still_match(tmp_path):
    with reader(tmp_path, split(x2=76)) as r:
        assert spans(r.logical_tables(2)) == [(1, 2)]


def test_running_header_and_page_number_are_not_body_content(tmp_path):
    """The furniture sits between the two parts on both pages (a footer
    under the first part, a header over the second); the merge happens.
    The same words at a different height are body text and stop it."""
    with reader(tmp_path, split()) as r:
        assert spans(r.logical_tables(1)) == [(1, 2)]
    with reader(tmp_path, split(between="Spec Title")) as r:
        assert spans(r.logical_tables(1)) == [(1, 1)]


def test_a_row_cut_by_the_page_break_is_joined_after_an_open_bottom(tmp_path):
    """AC-3: the part before the break has no rule under its last row, and
    the continuation's first row has an empty first cell: it is the rest of
    the cut row and its cells are joined to it."""
    rows1 = [HEADER, ["Processor", "07h", ["IERR", "Thermal Trip"]]]
    page1 = furniture(1) + grid(72, 200, WIDTHS, [16, 28], rows1, bottom_rule=False)
    rows2 = [HEADER, ["", "", ["FRB1", "FRB2"]], ["Power", "08h", "watts"]]
    page2 = furniture(2) + grid(72, 740, WIDTHS, [16, 28, 16], rows2)
    with reader(tmp_path, [page1, page2]) as r:
        (t,) = r.logical_tables(2)
    assert (t.first, t.last) == (1, 2)
    assert t.rows == [
        HEADER,
        ["Processor", "07h", "IERR\nThermal Trip\nFRB1\nFRB2"],
        ["Power", "08h", "watts"],
    ]


def test_a_grouped_row_after_a_closed_bottom_stays_a_row(tmp_path):
    """AC-3: an empty first cell after a closed bottom rule is a grouped
    row (a sensor type followed by its offsets), not a cut row."""
    rows1 = [HEADER, ["Processor", "07h", "IERR"]]
    page1 = furniture(1) + grid(72, 200, WIDTHS, [16] * 2, rows1)
    rows2 = [HEADER, ["", "08h", "Thermal Trip"], ["Power", "09h", "watts"]]
    page2 = furniture(2) + grid(72, 740, WIDTHS, [16] * 3, rows2)
    with reader(tmp_path, [page1, page2]) as r:
        (t,) = r.logical_tables(1)
    assert (t.first, t.last) == (1, 2)
    assert t.rows == [HEADER, rows1[1], rows2[1], rows2[2]]


def test_a_body_row_equal_to_an_earlier_row_is_kept(tmp_path):
    """AC-3: only the header (or a "(continued)" sub-header) is deduped; a
    placeholder row that repeats stays."""
    reserved = ["reserved", "-", "-"]
    page1 = furniture(1) + grid(72, 200, WIDTHS, [16] * 3, [HEADER, reserved, ROWS_A[0]])
    page2 = furniture(2) + grid(72, 740, WIDTHS, [16] * 3, [HEADER, reserved, ROWS_B[0]])
    with reader(tmp_path, [page1, page2]) as r:
        (t,) = r.logical_tables(2)
    assert t.rows == [HEADER, reserved, ROWS_A[0], reserved, ROWS_B[0]]


def test_a_continued_sub_header_that_repeats_an_earlier_row_is_dropped(tmp_path):
    """AC-3: the DMTF layout: a sub-header row marked "(continued)" on the
    next page repeats a row already seen and is dropped; without the mark
    the same row would stay."""
    sub = ["Type", "Response data", ""]
    widths = [100, 160, 120]  # "(continued)" must fit inside its cell
    page1 = furniture(1) + grid(72, 200, widths, [16] * 3, [HEADER, sub, ROWS_A[0]])
    page2 = furniture(2) + grid(
        72,
        740,
        widths,
        [16] * 2,
        [["Type", "Response data (continued)", ""], ROWS_B[0]],
    )
    with reader(tmp_path, [page1, page2]) as r:
        (t,) = r.logical_tables(1)
    assert (t.first, t.last) == (1, 2)
    assert t.rows == [HEADER, sub, ROWS_A[0], ROWS_B[0]]


def test_walk_both_ways_from_the_middle_page(tmp_path):
    page1 = furniture(1) + grid(72, 200, WIDTHS, [16] * 2, [HEADER, ROWS_A[0]])
    page2 = furniture(2) + grid(72, 740, WIDTHS, [16] * 2, [HEADER, ROWS_A[1]])
    page3 = furniture(3) + grid(72, 740, WIDTHS, [16] * 2, [HEADER, ROWS_B[0]])
    page4 = furniture(4) + [(72, 700, "prose only")]
    with reader(tmp_path, [page1, page2, page3, page4]) as r:
        (t,) = r.logical_tables(2)
        assert (t.first, t.last) == (1, 3)
        assert t.rows == [HEADER, ROWS_A[0], ROWS_A[1], ROWS_B[0]]
        assert spans(r.logical_tables(3)) == [(1, 3)]
        assert r.logical_tables(4) == []


# ----------------------------------------------------------------- AC-4


def test_body_text_between_the_parts_stops_the_merge(tmp_path):
    with reader(tmp_path, split(between="Some prose after the table.")) as r:
        assert spans(r.logical_tables(1)) == [(1, 1)]
        two = r.logical_tables(2)
    assert spans(two) == [(2, 2)]
    assert two[0].rows == [HEADER, *ROWS_B]


def test_different_column_edges_stop_the_merge(tmp_path):
    with reader(tmp_path, split(widths2=[120, 60, 200])) as r:
        assert spans(r.logical_tables(2)) == [(2, 2)]
    with reader(tmp_path, split(x2=80)) as r:  # 8 pt off: beyond the tolerance
        assert spans(r.logical_tables(2)) == [(2, 2)]


def test_different_column_count_stops_the_merge(tmp_path):
    page1 = furniture(1) + grid(72, 200, WIDTHS, [16] * 2, [HEADER, ROWS_A[0]])
    page2 = furniture(2) + grid(
        72, 740, [100, 80, 100, 100], [16] * 2, [["A", "B", "C", "D"], ["1", "2", "3", "4"]]
    )
    with reader(tmp_path, [page1, page2]) as r:
        assert spans(r.logical_tables(1)) == [(1, 1)]
        assert spans(r.logical_tables(2)) == [(2, 2)]


def test_a_caption_on_the_next_page_stops_the_merge(tmp_path):
    with reader(tmp_path, split(caption2="Table 2 - More")) as r:
        two = r.logical_tables(2)
    assert [(t.first, t.last, t.caption) for t in two] == [(2, 2, "Table 2 - More")]


# ----------------------------------------------------------------- AC-5


def test_caption_is_the_nearest_line_within_40_points_starting_with_table_or_figure(
    tmp_path,
):
    table = grid(72, 700, WIDTHS, [16] * 2, [HEADER, ROWS_A[0]])
    near = [(72, 714, "Table 7 - Near")] + table
    figure = [(72, 714, "Figure 3 - Also a caption")] + table
    far = [(72, 745, "Table 8 - Too far")] + table  # 45 pt above the top edge
    prose = [(72, 730, "Table 9 - Hidden"), (72, 714, "see the table below")] + table
    with reader(tmp_path, [near, figure, far, prose]) as r:
        assert r.logical_tables(1)[0].caption == "Table 7 - Near"
        assert r.logical_tables(2)[0].caption == "Figure 3 - Also a caption"
        assert r.logical_tables(3)[0].caption is None
        assert r.logical_tables(4)[0].caption is None


def test_caption_comes_from_the_first_part_only(tmp_path):
    with reader(tmp_path, split()) as r:
        (t,) = r.logical_tables(2)
    assert t.caption == "Table 1 - Codes" and t.first == 1
