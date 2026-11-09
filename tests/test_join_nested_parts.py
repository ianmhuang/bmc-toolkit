"""NVMe figures run over pages whose tables differ by a table nested in a
cell or by inner column edges (NVME-NVM Figure 123). A nested table does
not stop the join, column edges may be a subset, and under a repeated
caption only the outer frame must match; the joined rows sit on the
union of the parts' column edges."""

import pytest

from bmc_toolkit.spec import tables as T
from tests import pdfgen
from tests.test_caption_not_furniture import FULL, furniture, prose
from tests.test_tables import ROWS_2, WIDTHS, cell_table, ruled_table

pytest.importorskip("pdfplumber")

ASCENT = 8
TOP = 680
CAPTION = "Figure 7: Identify Data"
HEADER = ["Bytes", "O/M", "Description"]
THREE = [100, 80, 260]  # edges 72, 172, 252, 512
FOUR = [100, 80, 60, 200]  # edges 72, 172, 252, 312, 512 (a subset of THREE's)
SHIFTED = [100, 90, 250]  # edges 72, 172, 262, 512 (inner edge 10 pt off)


def body(first, count, width):
    return [
        [f"{first + i:02d}", "M", f"Field {first + i}"] + [""] * (width - 3)
        for i in range(count)
    ]


def part(widths, rows, top=TOP):
    return ruled_table(72, top, widths, [16] * len(rows), rows)


def cap(text=CAPTION, top=TOP):
    return (72, top + 12 - ASCENT, text)


def nested_part(count):
    """An outer table whose last row holds a nested Value/Definition table."""
    rows = [HEADER] + body(0, count, 3) + [["28", "M", "Capabilities"]]
    heights = [16] * (count + 1) + [70]
    outer = ruled_table(72, TOP, THREE, heights, rows)
    inner_top = TOP - 16 * (count + 1) - 18
    inner = ruled_table(
        272,
        inner_top,
        [60, 150],
        [16] * 3,
        [["Value", "Definition"], ["0b", "No"], ["1b", "Yes"]],
    )
    return outer + inner


def tables(tmp_path, pages):
    pdf = pdfgen.write_pdf(tmp_path / "n.pdf", pages)
    with T.Reader(pdf) as r:
        return {
            n: sorted(
                ((t.first, t.last, t.caption) for t in r.logical_tables(n)),
                key=lambda t: (t[0], t[1], t[2] or ""),
            )
            for n in range(1, len(pages) + 1)
        }


def logical(tmp_path, pages, page=1):
    pdf = pdfgen.write_pdf(tmp_path / "l.pdf", pages)
    with T.Reader(pdf) as r:
        return [t for t in r.logical_tables(page) if t.first == page]


def two_pages(first, second, second_above=None):
    if second_above is None:
        second_above = (cap(),)
    return [
        furniture(1) + [cap()] + first,
        furniture(2) + list(second_above) + second + [prose(2)],
    ]


# ---------------------------------------------------------------- AC-1


def test_a_nested_table_does_not_stop_the_join(tmp_path):
    pages = two_pages(nested_part(30), part(THREE, [HEADER] + body(40, 4, 3)))
    got = tables(tmp_path, pages)
    assert (1, 2, CAPTION) in got[1]
    assert got[2] == [(1, 2, CAPTION)]


def test_the_nested_table_stays_a_table_of_its_own(tmp_path):
    pages = two_pages(nested_part(30), part(THREE, [HEADER] + body(40, 4, 3)))
    got = logical(tmp_path, pages)
    nested = [t for t in got if t.header == ["Value", "Definition"]]
    assert [(t.first, t.last) for t in nested] == [(1, 1)]


# ---------------------------------------------------------------- AC-2


@pytest.mark.parametrize("above", [(cap(),), ()], ids=["caption", "none"])
def test_column_edges_that_are_a_subset_join(tmp_path, above):
    pages = two_pages(
        part(FOUR, [HEADER + [""]] + body(0, FULL, 4)),
        part(THREE, body(40, 4, 3)),
        second_above=above,
    )
    assert tables(tmp_path, pages)[2] == [(1, 2, CAPTION)]


# ---------------------------------------------------------------- AC-3


def test_under_a_repeated_caption_only_the_frame_must_match(tmp_path):
    pages = two_pages(
        part(THREE, [HEADER] + body(0, FULL, 3)), part(SHIFTED, body(40, 4, 3))
    )
    assert tables(tmp_path, pages)[2] == [(1, 2, CAPTION)]


# ---------------------------------------------------------------- AC-4


def test_shifted_inner_edges_without_a_caption_do_not_join(tmp_path):
    pages = two_pages(
        part(THREE, [HEADER] + body(0, FULL, 3)),
        part(SHIFTED, body(40, 4, 3)),
        second_above=(),
    )
    assert tables(tmp_path, pages)[2] == [(2, 2, None)]


@pytest.mark.parametrize(
    ("x", "widths"), [(72, [100, 80, 250]), (82, [90, 80, 260])], ids=["right", "left"]
)
def test_a_frame_that_differs_does_not_join_under_a_caption(tmp_path, x, widths):
    # the right edge 10 pt in, or the left edge 10 pt in
    second = ruled_table(x, TOP, widths, [16] * 4, body(40, 4, 3))
    pages = two_pages(part(THREE, [HEADER] + body(0, FULL, 3)), second)
    assert tables(tmp_path, pages)[2] == [(2, 2, CAPTION)]


def test_another_caption_above_does_not_join(tmp_path):
    pages = two_pages(
        part(THREE, [HEADER] + body(0, FULL, 3)),
        part(THREE, [HEADER] + body(40, 4, 3)),
        second_above=(cap("Figure 8: Other Data"),),
    )
    assert tables(tmp_path, pages)[2] == [(2, 2, "Figure 8: Other Data")]


def test_a_table_after_the_first_part_that_is_not_nested_stops_it(tmp_path):
    first = part(THREE, [HEADER] + body(0, 20, 3)) + part(
        [60, 150], [["Value", "Definition"], ["0b", "No"]], top=TOP - 16 * 21 - 30
    )
    pages = two_pages(first, part(THREE, body(40, 4, 3)))
    assert tables(tmp_path, pages)[2] == [(2, 2, CAPTION)]


# ---------------------------------------------------------------- AC-5


def test_rows_sit_on_the_union_of_the_column_edges(tmp_path):
    pages = two_pages(
        part(THREE, [HEADER] + body(0, FULL, 3)),
        part(FOUR, [HEADER + [""]] + body(40, 4, 4)),
    )
    (lt,) = logical(tmp_path, pages)
    assert (lt.first, lt.last) == (1, 2)
    assert [round(c) for c in lt.columns] == [72, 172, 252, 312, 512]
    assert {len(r) for r in lt.rows} == {4}
    assert lt.rows.count(HEADER + [""]) == 1
    assert lt.rows[1] == ["00", "M", "Field 0", ""]
    assert lt.rows[-1] == ["43", "M", "Field 43", ""]
    assert len(lt.rows) == 1 + FULL + 4


def test_a_cell_lands_under_the_edge_it_starts_at(tmp_path):
    # the wider part first: the narrower part's Description spans two
    pages = two_pages(
        part(FOUR, [HEADER + ["Common"]] + body(0, FULL, 4)),
        part(THREE, [["44", "M", "Field 44"]]),
    )
    (lt,) = logical(tmp_path, pages)
    assert lt.rows[-1] == ["44", "M", "Field 44", ""]


def test_parts_with_the_same_edges_read_as_before(tmp_path):
    # a 4 pt shift is within the tolerance: the first part's edges, rows as drawn
    pages = two_pages(
        part(THREE, [HEADER] + body(0, FULL, 3)),
        ruled_table(76, TOP, [96, 80, 260], [16] * 5, [HEADER] + body(40, 4, 3)),
    )
    (lt,) = logical(tmp_path, pages)
    assert [round(c) for c in lt.columns] == [72, 172, 252, 512]
    assert lt.rows == [HEADER] + body(0, FULL, 3) + body(40, 4, 3)


FIVE = [100, 80, 60, 60, 140]  # edges 72, 172, 252, 312, 372, 512


def test_a_five_column_and_a_four_column_part_give_rows_of_five(tmp_path):
    # AC-5 as written: one inner edge missing on the second part
    pages = two_pages(
        part(FIVE, [HEADER + ["", ""]] + body(0, FULL, 5)),
        part(FOUR, [HEADER + [""]] + body(40, 4, 4)),
    )
    (lt,) = logical(tmp_path, pages)
    assert [round(c) for c in lt.columns] == [72, 172, 252, 312, 372, 512]
    assert {len(r) for r in lt.rows} == {5}
    assert lt.rows.count(HEADER + ["", ""]) == 1
    assert lt.rows[-1] == ["43", "M", "Field 43", "", ""]


# ------------------------------------------- PR #119 round 1 F1 to F3


def test_edges_within_the_tolerance_keep_the_row_even_on_a_narrow_column():
    # F1: an 8 pt column shifted 5 pt; nearest-edge placement put both
    # cells under 80
    assert T.spread_row(["a", "b"], [77.0, 85.0, 200.0], [72.0, 80.0, 200.0]) == [
        "a",
        "b",
    ]


def test_cells_go_to_union_edges_in_order_one_to_an_edge():
    # F1: another part added an edge at 150; 77 and 85 still go under 72 and 80
    union = [72.0, 80.0, 150.0, 200.0]
    assert T.spread_row(["a", "b"], [77.0, 85.0, 200.0], union) == ["a", "b", ""]
    # an edge more than the tolerance off goes to the nearest free edge
    assert T.spread_row(["a", "b"], [72.0, 160.0, 200.0], union) == ["a", "", "b"]


def test_a_complete_cells_row_on_a_part_with_fewer_columns_stays_a_row(tmp_path):
    # F2: the empty cell spread_row adds for the spanned edge is not a
    # cut cell; the row's own cells are all filled after the first
    header = ["Name", "Code", "Meaning", "Unit"]
    rows1 = [["Temperature", "01h", "degrees", "C"], ["", "05h", "watts", "W"]]
    page1 = furniture(1) + [(72, 214, "Table 1 - Codes")]
    page1 += cell_table(72, 200, [100, 80, 100, 100], [16] * 3, [header, *rows1])
    page2 = furniture(2) + cell_table(
        72, 740, WIDTHS, [16] * 2, [["", "06h", "joules"], ROWS_2[0]]
    )
    pdf = pdfgen.write_pdf(tmp_path / "c.pdf", [page1, page2])
    with T.Reader(pdf) as r:
        (lt,) = r.logical_tables(1)
    assert lt.drawn == T.CELLS
    assert (lt.first, lt.last) == (1, 2)
    assert lt.rows == [header, *rows1, ["", "06h", "joules", ""], ROWS_2[0] + [""]]


def test_a_header_repeated_on_a_frame_rule_part_is_dropped(tmp_path):
    # F3: inner edge 10 pt off under the repeated caption; the header as
    # drawn repeats the first part's
    pages = two_pages(
        part(THREE, [HEADER] + body(0, FULL, 3)),
        part(SHIFTED, [HEADER] + body(40, 4, 3)),
    )
    (lt,) = logical(tmp_path, pages)
    assert (lt.first, lt.last) == (1, 2)
    assert [r[0] for r in lt.rows].count("Bytes") == 1
    assert len(lt.rows) == 1 + FULL + 4
