"""Reviewer acceptance tests for T69.2 (AC-1 to AC-5): a table whose pages
differ by a table nested in a cell or by inner column edges reads as one
Logical Table with its rows on the union of the parts' column edges, and
the stop cases keep the parts apart. Synthetic ruled PDFs only."""

import pytest

from bmc_toolkit.spec import tables as T
from tests import pdfgen
from tests.test_tables import ruled_table

pytest.importorskip("pdfplumber")

TOP = 680  # a table's top edge, PDF points from the page's foot
ROW_H = 16
LEFT = 72
RUNNING = "Example Specification, Revision 2.4"
CAPTION = "Figure 12: Identify Data Structure"
OTHER = "Figure 13: Another Data Structure"
PROSE = "The values are listed here."
HEADER = ["Bytes", "O/M", "Description"]
NESTED = [["Value", "Definition"], ["0b", "No"], ["1b", "Yes"]]
THREE = [100, 80, 260]  # edges 72, 172, 252, 512
FOUR = [100, 80, 60, 200]  # edges 72, 172, 252, 312, 512: THREE's and one more
MOVED = [120, 70, 250]  # edges 72, 192, 262, 512: THREE's frame, other inner edges
FIVE = [60, 60, 120, 100, 100]  # edges 72, 132, 192, 312, 412, 512
LESS = [60, 60, 220, 100]  # FIVE's edges without 312
HEAD5 = ["Bytes", "O/M", "Description", "", ""]
HEAD4 = ["Bytes", "O/M", "Description", ""]
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


def grid(widths, cells, x=LEFT, top=TOP):
    return ruled_table(x, top, widths, [ROW_H] * len(cells), cells)


def body(first, count, width=3):
    return [
        [f"{first + i:02d}", "M", f"Field {first + i}"] + ["note"] * (width - 3)
        for i in range(count)
    ]


def five(first, count):
    return [
        [f"{n:02d}", "M", f"Field {n}", f"b{n}", f"c{n}"]
        for n in range(first, first + count)
    ]


def four(first, count):
    return [
        [f"{n:02d}", "M", f"Field {n}", f"c{n}"] for n in range(first, first + count)
    ]


def read(tmp_path, pages):
    pdf = pdfgen.write_pdf(tmp_path / "doc.pdf", pages)
    with T.Reader(pdf) as r:
        return {n: r.logical_tables(n) for n in range(1, len(pages) + 1)}


def spans(tables):
    return [(t.first, t.last, t.caption) for t in tables]


def first_page(widths=THREE, cells=None):
    """Page 1: the caption and a part with nothing under it."""
    cells = [HEADER, *body(0, 3)] if cells is None else cells
    return furniture(1) + [over(CAPTION)] + grid(widths, cells)


# ---------------------------------------------------------------- AC-1


def nested_page(after):
    """Page 1: an outer table whose tall row (616 down to 536) holds a
    Value/Definition table (596 down to 548) in its Description cell, 20 pt
    inside the cell's left edge and 30 pt inside its right one, with
    ``after`` plain rows under the tall row."""
    cells = [HEADER, *body(0, 3), ["28", "M", "Capabilities"], *body(3, after)]
    heights = [ROW_H] * 4 + [80] + [ROW_H] * after
    outer = ruled_table(LEFT, TOP, THREE, heights, cells)
    inner = ruled_table(272, 596, [60, 150], [ROW_H] * len(NESTED), NESTED)
    return furniture(1) + [over(CAPTION)] + outer + inner


@pytest.mark.parametrize("after", [0, 2], ids=["last-row", "middle-row"])
def test_ac1_a_nested_table_does_not_stop_the_join(tmp_path, after):
    pages = [
        nested_page(after),
        furniture(2)
        + [over(CAPTION)]
        + grid(THREE, [HEADER, *body(40, 4)])
        + [tail(2)],
    ]
    got = read(tmp_path, pages)
    assert spans(got[2]) == [(1, 2, CAPTION)]
    (joined,) = got[2]
    assert [int(p[0]) for p in joined.parts] == [1, 2]
    assert [row[0] for row in joined.rows] == (
        ["Bytes", "00", "01", "02", "28"]
        + ["03", "04"][:after]
        + ["40", "41", "42", "43"]
    )
    assert joined.rows.count(HEADER) == 1
    assert "Capabilities" in joined.rows[4][2]


@pytest.mark.parametrize("after", [0, 2], ids=["last-row", "middle-row"])
def test_ac1_the_nested_table_stays_a_logical_table_of_its_own(tmp_path, after):
    pages = [
        nested_page(after),
        furniture(2)
        + [over(CAPTION)]
        + grid(THREE, [HEADER, *body(40, 4)])
        + [tail(2)],
    ]
    one = read(tmp_path, pages)[1]
    assert sorted((t.first, t.last) for t in one) == [(1, 1), (1, 2)]
    (nested,) = [t for t in one if t.last == 1]
    assert nested.rows == NESTED
    assert len(nested.parts) == 1


# ---------------------------------------------------------------- AC-2


@pytest.mark.parametrize("captioned", [True, False], ids=["caption", "no-caption"])
@pytest.mark.parametrize(
    ("first", "second"),
    [(THREE, FOUR), (FOUR, THREE)],
    ids=["fewer-first", "more-first"],
)
def test_ac2_column_edges_that_are_a_subset_join(tmp_path, first, second, captioned):
    head = HEADER + [""] * (len(first) - 3)
    above = [over(CAPTION)] if captioned else []
    pages = [
        first_page(first, [head, *body(0, 3, len(first))]),
        furniture(2) + above + grid(second, body(40, 3, len(second))) + [tail(2)],
    ]
    got = read(tmp_path, pages)
    assert spans(got[1]) == spans(got[2]) == [(1, 2, CAPTION)]
    (table,) = got[2]
    firsts = ["Bytes", "00", "01", "02", "40", "41", "42"]
    assert [row[0] for row in table.rows] == firsts


def test_ac2_subset_edges_4_pt_off_still_join(tmp_path):
    # every edge of the part with fewer lies within 6 pt of one of the other's
    pages = [
        first_page(),
        furniture(2) + grid(FOUR, body(40, 3, 4), x=LEFT + 4) + [tail(2)],
    ]
    assert spans(read(tmp_path, pages)[2]) == [(1, 2, CAPTION)]


def test_ac2_a_chain_with_the_extra_edge_on_the_middle_page_is_one_table(tmp_path):
    pages = [
        first_page(),
        furniture(2) + grid(FOUR, body(40, 3, 4)),
        furniture(3) + grid(THREE, body(80, 3)) + [tail(3)],
    ]
    got = read(tmp_path, pages)
    whole = [(1, 3, CAPTION)]
    assert {n: spans(found) for n, found in got.items()} == {
        1: whole,
        2: whole,
        3: whole,
    }
    (table,) = got[2]
    assert {len(row) for row in table.rows} == {4}
    assert len(table.rows) == 10


# ---------------------------------------------------------------- AC-3


def test_ac3_under_the_repeated_caption_only_the_frame_must_match(tmp_path):
    pages = [
        first_page(),
        furniture(2) + [over(CAPTION)] + grid(MOVED, body(40, 3)) + [tail(2)],
    ]
    got = read(tmp_path, pages)
    assert spans(got[1]) == spans(got[2]) == [(1, 2, CAPTION)]


def test_ac3_the_caption_may_repeat_one_from_two_pages_before(tmp_path):
    # page 2 carries no caption; page 3 repeats page 1's over other inner edges
    pages = [
        first_page(),
        furniture(2) + grid(THREE, body(40, 3)),
        furniture(3) + [over(CAPTION)] + grid(MOVED, body(80, 3)) + [tail(3)],
    ]
    got = read(tmp_path, pages)
    whole = [(1, 3, CAPTION)]
    assert {n: spans(found) for n, found in got.items()} == {
        1: whole,
        2: whole,
        3: whole,
    }


# ---------------------------------------------------------------- AC-4


def test_ac4_other_inner_edges_without_a_caption_do_not_join(tmp_path):
    pages = [first_page(), furniture(2) + grid(MOVED, body(40, 3)) + [tail(2)]]
    got = read(tmp_path, pages)
    assert spans(got[1]) == [(1, 1, CAPTION)]
    assert spans(got[2]) == [(2, 2, None)]


@pytest.mark.parametrize(
    ("x", "widths"),
    [(LEFT, [120, 70, 240]), (LEFT + 10, [110, 70, 250])],
    ids=["right-edge", "left-edge"],
)
def test_ac4_a_frame_10_pt_off_does_not_join_under_the_caption(tmp_path, x, widths):
    pages = [
        first_page(),
        furniture(2) + [over(CAPTION)] + grid(widths, body(40, 3), x=x) + [tail(2)],
    ]
    got = read(tmp_path, pages)
    assert spans(got[1]) == [(1, 1, CAPTION)]
    assert spans(got[2]) == [(2, 2, CAPTION)]


def test_ac4_subset_edges_in_another_frame_do_not_join(tmp_path):
    # THREE's inner edges and one more, the right edge 10 pt in
    pages = [
        first_page(),
        furniture(2) + grid([100, 80, 60, 190], body(40, 3, 4)) + [tail(2)],
    ]
    assert spans(read(tmp_path, pages)[2]) == [(2, 2, None)]


@pytest.mark.parametrize(
    ("line", "caption"), [(OTHER, OTHER), (PROSE, None)], ids=["caption", "prose"]
)
def test_ac4_another_line_above_stops_a_subset_join(tmp_path, line, caption):
    pages = [
        first_page(),
        furniture(2) + [over(line)] + grid(FOUR, body(40, 3, 4)) + [tail(2)],
    ]
    got = read(tmp_path, pages)
    assert spans(got[1]) == [(1, 1, CAPTION)]
    assert spans(got[2]) == [(2, 2, caption)]


def test_ac4_a_line_beside_the_repeated_caption_stops_the_frame_join(tmp_path):
    # not every line above the second part is a repeated caption
    pages = [
        first_page(),
        furniture(2)
        + [(LEFT, TOP + 18, PROSE), over(CAPTION)]
        + grid(MOVED, body(40, 3))
        + [tail(2)],
    ]
    assert spans(read(tmp_path, pages)[2]) == [(2, 2, CAPTION)]


def test_ac4_a_table_under_the_first_part_that_is_not_nested_stops_the_join(
    tmp_path,
):
    # the first part runs from 680 down to 616; the other table starts at 586
    under = grid([60, 150], NESTED, top=586)
    pages = [
        first_page() + under,
        furniture(2)
        + [over(CAPTION)]
        + grid(THREE, [HEADER, *body(40, 4)])
        + [tail(2)],
    ]
    got = read(tmp_path, pages)
    assert [(t.first, t.last) for t in got[1]] == [(1, 1), (1, 1)]
    assert spans(got[2]) == [(2, 2, CAPTION)]


# ---------------------------------------------------------------- AC-5


@pytest.mark.parametrize("captioned", [True, False], ids=["caption", "no-caption"])
@pytest.mark.parametrize("x2", [LEFT, LEFT + 4], ids=["aligned", "4-pt-off"])
def test_ac5_a_five_and_a_four_column_part_give_rows_of_five_cells(
    tmp_path, x2, captioned
):
    above = [over(CAPTION)] if captioned else []
    pages = [
        first_page(FIVE, [HEAD5, *five(0, 3)]),
        furniture(2) + above + grid(LESS, [HEAD4, *four(40, 3)], x=x2) + [tail(2)],
    ]
    (table,) = read(tmp_path, pages)[1]
    assert (table.first, table.last) == (1, 2)
    # the union keeps the first part's positions
    assert [round(c) for c in table.columns] == [72, 132, 192, 312, 412, 512]
    # one header; the four-column part's third cell spans the missing edge
    assert table.rows == [
        HEAD5,
        *five(0, 3),
        *[[a, b, c, "", d] for a, b, c, d in four(40, 3)],
    ]


def test_ac5_the_part_with_fewer_columns_first_gives_the_same_columns(tmp_path):
    pages = [
        first_page(LESS, [HEAD4, *four(0, 3)]),
        furniture(2) + [over(CAPTION)] + grid(FIVE, [HEAD5, *five(40, 3)]) + [tail(2)],
    ]
    (table,) = read(tmp_path, pages)[2]
    assert (table.first, table.last) == (1, 2)
    assert [round(c) for c in table.columns] == [72, 132, 192, 312, 412, 512]
    assert table.rows == [
        HEAD5,
        *[[a, b, c, "", d] for a, b, c, d in four(0, 3)],
        *five(40, 3),
    ]


def test_ac5_under_the_frame_rule_a_cell_lands_under_the_edge_it_starts_at(tmp_path):
    pages = [
        first_page(),
        furniture(2) + [over(CAPTION)] + grid(MOVED, body(40, 3)) + [tail(2)],
    ]
    (table,) = read(tmp_path, pages)[2]
    assert [round(c) for c in table.columns] == [72, 172, 192, 252, 262, 512]
    assert {len(row) for row in table.rows} == {5}
    assert table.rows[1] == ["00", "M", "", "Field 0", ""]
    assert table.rows[-1] == ["42", "", "M", "", "Field 42"]


def test_ac5_parts_with_the_same_edges_read_as_before(tmp_path):
    # the middle part lies 4 pt to the right: inside the tolerance
    pages = [
        first_page(),
        furniture(2)
        + [over(CAPTION)]
        + grid(THREE, [HEADER, *body(40, 3)], x=LEFT + 4),
        furniture(3)
        + [over(CAPTION)]
        + grid(THREE, [HEADER, *body(80, 3)])
        + [tail(3)],
    ]
    (table,) = read(tmp_path, pages)[2]
    assert (table.first, table.last) == (1, 3)
    assert [round(c) for c in table.columns] == [72, 172, 252, 512]
    assert table.rows == [HEADER, *body(0, 3), *body(40, 3), *body(80, 3)]
