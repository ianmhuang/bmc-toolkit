"""Review tests for how a joined table's column edges pair
(fix/figure-caption-past-table, AC-3 to AC-5).

The AC: ``union_columns`` pairs a later part's edges with the union's in
order, one to one, with the most pairs within COLUMN_TOL_PT and then the
least total distance, the earlier edge on a tie, and adds the edges left
unpaired (AC-3). ``spread_row`` places a part's cells in order, one to a
union column, with the most cells within COLUMN_TOL_PT of their column's
edge and then the least total distance (AC-4). The two expectations of
PR #120's review that pinned "the first edge within 6 pt pairs" are
restated for the nearest edge (AC-5).

The rule is checked against every pairing counted by hand (``pairings``,
``placements``) on a 1 pt grid: where several pairings score the same,
any of them is accepted, and the tie rule is checked on the cases the AC
names. Two synthetic PDFs then read a joined table through the Reader."""

import itertools

import pytest

from bmc_toolkit.spec import tables as T

TOL = T.COLUMN_TOL_PT


def filled(row):
    return [cell for cell in row if cell]


def pairings(xs, us):
    """Every in-order, one-to-one pairing of ``xs`` with ``us`` whose pairs
    all lie within the tolerance: (the paired indices of xs, of us)."""
    for k in range(min(len(xs), len(us)) + 1):
        for xi in itertools.combinations(range(len(xs)), k):
            for uj in itertools.combinations(range(len(us)), k):
                if all(abs(xs[i] - us[j]) <= TOL for i, j in zip(xi, uj, strict=True)):
                    yield xi, uj


def allowed_unions(first, second):
    """The unions AC-3 allows for two parts: the first part's edges plus
    the second part's edges left unpaired by a pairing with the most pairs
    and, among those, the least total distance."""
    scored = []
    for xi, uj in pairings(second, first):
        distance = sum(abs(second[i] - first[j]) for i, j in zip(xi, uj, strict=True))
        scored.append(((len(xi), -distance), xi))
    top = max(score for score, _ in scored)
    return {
        tuple(sorted(first + [x for i, x in enumerate(second) if i not in xi]))
        for score, xi in scored
        if score == top
    }


def placements(row, edges, union):
    """The rows AC-4 allows: the cells in order, one to a union column,
    with the most cells within the tolerance of their column's edge and,
    among those, the least total distance."""
    xs, us = edges[:-1], union[:-1]
    scored = []
    for columns in itertools.combinations(range(len(us)), len(xs)):
        gaps = [abs(x - us[k]) for x, k in zip(xs, columns, strict=True)]
        scored.append(((sum(gap <= TOL for gap in gaps), -sum(gaps)), columns))
    top = max(score for score, _ in scored)
    rows = set()
    for score, columns in scored:
        if score == top:
            out = [""] * len(us)
            for cell, k in zip(row, columns, strict=True):
                out[k] = cell
            rows.add(tuple(out))
    return rows


def parts_on_a_grid(low, high):
    """Parts with one or two inner edges on a 1 pt grid between ``low``
    and ``high``, in the frame 72 to 512."""
    for a in range(low, high):
        yield [72, a, 512]
        for b in range(a + 1, high):
            yield [72, a, b, 512]


# ------------------------------------------------------------------ AC-3

AC3_CASES = [
    # a narrow column shifted 5 pt: both edges pair, nothing is added
    ("unchanged", [[72, 80, 200], [77, 85, 200]], [72, 80, 200]),
    # 175 lies 3 pt from 172 and 168 lies 4 pt: 175 pairs, 168 is added
    ("nearer-later", [[72, 172, 512], [72, 168, 175, 512]], [72, 168, 172, 512]),
    # 4 pt either side: the earlier edge pairs, 176 is added
    ("tie", [[72, 172, 512], [72, 168, 176, 512]], [72, 172, 176, 512]),
]


def test_ac3_the_three_cases_the_criterion_names():
    got = {name: T.union_columns(parts) for name, parts, _ in AC3_CASES}
    assert got == {name: union for name, _, union in AC3_CASES}


def test_ac3_every_union_on_a_grid_has_the_most_pairs_then_the_least_distance():
    firsts = [[72, 172, 512], [72, 164, 172, 512], [72, 172, 181, 512]]
    for first in firsts:
        for second in parts_on_a_grid(158, 190):
            union = T.union_columns([first, second])
            assert tuple(union) in allowed_unions(first, second), (first, second)


def test_ac3_the_union_is_never_shorter_than_a_part():
    first = [72, 172, 512]
    for second in parts_on_a_grid(160, 186):
        for third in ([72, 170, 512], [72, 166, 174, 512]):
            parts = [first, second, third]
            union = T.union_columns(parts)
            assert union == sorted(union), parts
            assert len(union) >= max(len(part) for part in parts), parts
    # the pairing the count rests on is the nearest one
    assert T.union_columns([first, [72, 168, 175, 512]]) == [72, 168, 172, 512]


def test_ac3_a_third_part_pairs_with_the_union_the_second_part_left():
    # the second part adds 168 (175 pairs with 172); the third part's 166
    # then pairs with 168, 2 pt off, and adds nothing
    parts = [[72, 172, 512], [72, 168, 175, 512], [72, 166, 512]]
    assert T.union_columns(parts) == [72, 168, 172, 512]


# ------------------------------------------------------------------ AC-4


def test_ac4_the_case_the_criterion_names():
    union = [72, 166, 172, 512]
    assert T.spread_row(["a", "b"], [72, 170, 512], union) == ["a", "", "b"]


def test_ac4_every_row_on_a_grid_has_the_most_cells_near_then_the_least_distance():
    unions = [[72, 164, 172, 512], [72, 100, 110, 115, 512], [72, 172, 252, 512]]
    for union in unions:
        for edges in parts_on_a_grid(union[1] - 12, union[-2] + 13):
            if len(edges) > len(union):
                continue
            row = ["a", "b", "c"][: len(edges) - 1]
            got = T.spread_row(row, edges, union)
            assert tuple(got) in placements(row, edges, union), (edges, union)
            assert len(got) == len(union) - 1, (edges, union)
            assert filled(got) == row, (edges, union)


def test_ac4_a_part_of_a_union_built_from_it_keeps_its_cells_under_its_own_edges():
    # each part's cell sits in the union column that starts at its edge
    first, second = [72, 172, 512], [72, 168, 175, 512]
    union = T.union_columns([first, second])
    assert union == [72, 168, 172, 512]
    assert T.spread_row(["a", "b"], first, union) == ["a", "", "b"]
    assert T.spread_row(["c", "d", "e"], second, union) == ["c", "d", "e"]


def test_ac4_a_row_with_more_cells_than_the_union_has_columns_is_refused():
    # round 1 F2: three cells cannot sit one to a column on two columns;
    # an all-empty row would drop them without a sign (develop raised
    # ValueError here too)
    with pytest.raises(ValueError):
        T.spread_row(["a", "b", "c"], [72, 100, 150, 512], [72, 300, 512])
    # as many cells as columns is placed, none lost
    union = [72, 300, 400, 512]
    got = T.spread_row(["a", "b", "c"], [72, 100, 150, 512], union)
    assert got == ["a", "b", "c"]


# ------------------------------------------------------------------ AC-5


def test_ac5_the_nearer_of_two_edges_around_one_pairs_and_the_other_is_added():
    # the later part draws 172 - below and 172 + above, each within 6 pt of
    # 172 and more than 6 pt apart: the nearer pairs, the earlier on a tie
    for below in range(1, 6):
        for above in range(7 - below, 6):
            part = [72, 172 - below, 172 + above, 512]
            added = 172 + above if below <= above else 172 - below
            union = T.union_columns([[72, 172, 512], part])
            assert union == sorted([72, 172, added, 512]), part
            assert len(union) == len(part)


def test_ac5_the_nearest_of_three_edges_within_the_tolerance_pairs():
    # 70, 74 and 80 all lie within 6 pt of 75: 74, 1 pt off, pairs
    parts = [[75, 200], [70, 74, 80, 200]]
    union = T.union_columns(parts)
    assert union == [70, 75, 80, 200]
    assert len(union) == len(parts[1])
    assert T.spread_row(["b", "c", "d"], parts[1], union) == ["b", "c", "d"]
    assert filled(T.spread_row(["a"], parts[0], union)) == ["a"]


# ------------------------------------------- AC-3, AC-4 through the Reader

TOP = 680  # a table's top edge, PDF points from the page's foot
ROW_H = 16
LEFT = 72
RUNNING = "Example Specification, Revision 2.4"
CAPTION = "Figure 21: Feature Data Structure"
HEADER = ["Bytes", "O/M", "Description"]
THREE = [100, 80, 260]  # edges 72, 172, 252, 512
# an 8 pt column whose edges 167 and 175 lie 5 pt and 3 pt from THREE's 172
AROUND_172 = [95, 8, 77, 260]
# an 8 pt column with edges 164 and 172
NARROW = [92, 8, 80, 260]
# one inner edge at 169, 5 pt from NARROW's 164 and 3 pt from its 172
AT_169 = [97, 83, 260]


def body(first, count):
    return [[f"{n:02d}", "M", f"Field {n}"] for n in range(first, first + count)]


def split(first, count):
    """Rows with a cell in the narrow second column."""
    return [[f"{n:02d}", "x", "M", f"Field {n}"] for n in range(first, first + count)]


def joined(tmp_path, first, later):
    """The Logical Table of a two-page PDF, read from page 2: ``first``
    and ``later`` are (column widths, rows) of the part on each page,
    under a caption both pages repeat."""
    pytest.importorskip("pdfplumber")
    from tests import pdfgen
    from tests.test_tables import ruled_table

    pages = []
    for n, (widths, rows) in enumerate((first, later), start=1):
        page = [(LEFT, 750, RUNNING), (300, 40, str(n)), (LEFT, TOP + 4, CAPTION)]
        page += ruled_table(LEFT, TOP, widths, [ROW_H] * len(rows), rows)
        pages.append(page)
    pages[1].append((LEFT, 120, "The second part ends here."))
    pdf = pdfgen.write_pdf(tmp_path / "doc.pdf", pages)
    with T.Reader(pdf) as r:
        (table,) = r.logical_tables(2)
    assert (table.first, table.last, table.caption) == (1, 2, CAPTION)
    return table


def test_ac3_a_joined_table_adds_the_farther_of_two_edges_around_one(tmp_path):
    rows = split(40, 3)
    table = joined(tmp_path, (THREE, [HEADER, *body(0, 3)]), (AROUND_172, rows))
    # 175 pairs with 172 and 167 is added (develop: 167 pairs, 175 is added)
    assert [round(c) for c in table.columns] == [72, 167, 172, 252, 512]
    assert {len(row) for row in table.rows} == {4}
    assert table.rows[:4] == [
        ["Bytes", "", "O/M", "Description"],
        *[[n, "", m, field] for n, m, field in body(0, 3)],
    ]
    assert table.rows[4:] == rows
    # the column the first part heads O/M holds the later part's M cells
    assert [row[2] for row in table.rows] == ["O/M"] + ["M"] * 6


def test_ac4_a_joined_row_sits_under_the_nearer_of_two_union_edges(tmp_path):
    cells = [["Bytes", "x", "O/M", "Description"], *split(0, 3)]
    table = joined(tmp_path, (NARROW, cells), (AT_169, body(40, 3)))
    assert [round(c) for c in table.columns] == [72, 164, 172, 252, 512]
    assert {len(row) for row in table.rows} == {4}
    assert table.rows[:4] == cells
    # the cell that starts at 169 goes under 172, 3 pt off, and not under
    # 164, the first edge within 6 pt
    assert table.rows[4:] == [[n, "", m, field] for n, m, field in body(40, 3)]
    assert [row[2] for row in table.rows] == ["O/M"] + ["M"] * 6
