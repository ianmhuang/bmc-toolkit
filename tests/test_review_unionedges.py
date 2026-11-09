"""Reviewer acceptance tests for T70 (AC-1 to AC-3) on the two functions
that put a joined table's rows on one column set. ``union_columns`` pairs
a later part's edges with the union's in order, one to one, within 6 pt,
and adds an edge left over; ``spread_row`` then gives every part's row one
cell per union column. No PDF is read here."""

import itertools

from bmc_toolkit.spec import tables as T

# AC-1 as written: 68 and 76 both lie within 6 pt of the first part's 72
ONE = [72.0, 200.0]
TWO = [68.0, 76.0, 200.0]


def filled(row):
    return [cell for cell in row if cell]


# ---------------------------------------------------------------- AC-1


def test_ac1_two_edges_near_one_union_edge_are_both_kept():
    # 68 takes 72; 76 finds no free edge within 6 pt and is added
    assert T.union_columns([ONE, TWO]) == [72.0, 76.0, 200.0]


def test_ac1_rows_of_both_parts_have_one_cell_per_column():
    union = T.union_columns([ONE, TWO])
    width = len(union) - 1
    first = T.spread_row(["a"], ONE, union)
    second = T.spread_row(["b", "c"], TWO, union)
    assert (len(first), len(second)) == (width, width)
    assert second == ["b", "c"]  # the second part's two cells, two columns
    assert filled(first) == ["a"]


# ---------------------------------------------------------------- AC-2

PAIRING = [
    # the three cases the AC lists: edges that pair one to one add nothing
    # (a narrow column shifted 5 pt), an edge 10 pt off is added, a subset
    # leaves the first part's edges as they are
    ("narrow-shift", [[72, 80, 200], [77, 85, 200]], [72, 80, 200]),
    (
        "inner-shift",
        [[72, 172, 252, 512], [72, 172, 262, 512]],
        [72, 172, 252, 262, 512],
    ),
    ("subset", [[72, 172, 252, 312, 512], [72, 172, 512]], [72, 172, 252, 312, 512]),
    # two edges on either side of one union edge: the first takes it, the
    # second is added
    ("either-side", [[72, 172, 512], [72, 167, 177, 512]], [72, 172, 177, 512]),
    # a third part pairs with what the second added: 80 takes the free 76
    # after the 72 its own first edge took
    ("third-part", [[72, 200], [68, 76, 200], [72, 80, 200]], [72, 76, 200]),
    # the part with more edges first: nothing to add
    ("more-first", [[68, 76, 200], [72, 200]], [68, 76, 200]),
]


def test_ac2_the_union_pairs_edges_in_order_one_to_one():
    got = {name: T.union_columns(parts) for name, parts, _ in PAIRING}
    assert got == {name: union for name, _, union in PAIRING}


def test_ac2_every_split_around_an_inner_edge_adds_the_second_edge():
    # the later part draws 172 - below and 172 + above, each within 6 pt of
    # 172 and more than 6 pt from each other
    for below in range(1, 6):
        for above in range(7 - below, 6):
            part = [72, 172 - below, 172 + above, 512]
            union = T.union_columns([[72, 172, 512], part])
            assert union == [72, 172, 172 + above, 512], part


# ---------------------------------------------------------------- AC-3


def test_ac3_no_row_is_wider_than_the_union():
    # on develop the union of these had fewer edges than the second part
    # and its rows came back wider than the columns
    for below in range(1, 6):
        for above in range(7 - below, 6):
            first = [72.0, 172.0, 512.0]
            second = [72.0, 172.0 - below, 172.0 + above, 512.0]
            union = T.union_columns([first, second])
            width = len(union) - 1
            assert len(union) >= max(len(first), len(second)), second
            wide = T.spread_row(["a", "b"], first, union)
            split = T.spread_row(["c", "d", "e"], second, union)
            assert (len(wide), len(split)) == (width, width), second
            assert filled(wide) == ["a", "b"]
            assert split == ["c", "d", "e"]


def test_ac3_a_part_whose_own_edges_lie_within_6_pt_keeps_them_all():
    # round 1 F1: 70 takes 75, 74 is added before it, and 80 must not take
    # 75 a second time; it finds no free edge and is added too
    parts = [[75.0, 200.0], [70.0, 74.0, 80.0, 200.0]]
    union = T.union_columns(parts)
    assert union == [74.0, 75.0, 80.0, 200.0]
    assert T.spread_row(["b", "c", "d"], parts[1], union) == ["b", "c", "d"]
    assert filled(T.spread_row(["a"], parts[0], union)) == ["a"]


def test_ac3_no_spacing_of_a_parts_edges_makes_the_union_shorter():
    # every later part with three edges on a 1 pt grid around the first
    # part's left edge, most of them closer together than 6 pt
    for left in (72.0, 75.0, 80.0):
        first = [left, 200.0]
        for inner in itertools.combinations(range(66, 88), 3):
            second = [float(x) for x in inner] + [200.0]
            union = T.union_columns([first, second])
            assert union == sorted(union), second
            assert len(union) >= len(second), second
            width = len(union) - 1
            one = T.spread_row(["a"], first, union)
            three = T.spread_row(["b", "c", "d"], second, union)
            assert (len(one), len(three)) == (width, width), second
            assert filled(one) == ["a"]
            assert filled(three) == ["b", "c", "d"]


def test_ac3_three_parts_all_sit_on_the_union():
    parts = [[72.0, 200.0], [68.0, 76.0, 200.0], [72.0, 80.0, 140.0, 200.0]]
    union = T.union_columns(parts)
    assert union == [72.0, 76.0, 140.0, 200.0]
    rows = [["a"], ["b", "c"], ["d", "e", "f"]]
    spread = [
        T.spread_row(row, edges, union) for row, edges in zip(rows, parts, strict=True)
    ]
    assert {len(row) for row in spread} == {len(union) - 1}
    assert [filled(row) for row in spread] == rows
    assert spread[1] == ["b", "c", ""]
    assert spread[2] == ["d", "e", "f"]
