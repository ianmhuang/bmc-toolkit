"""A joined table's column edges pair in order, one to one, with the most
pairs within COLUMN_TOL_PT and then the least total distance, so a cell
sits under the union column nearest its own edge (T71: NVMe Figure 213
and Figure 338 put a nested row's cell under the first edge within 6 pt,
not the nearest)."""

import pytest

from bmc_toolkit.spec import tables as T

# ---------------------------------------------------------------- AC-3


@pytest.mark.parametrize(
    ("parts", "union"),
    [
        # a narrow column shifted 5 pt: 77 is nearer 80, but pairing 77
        # with 72 and 85 with 80 pairs more edges
        ([[72, 80, 200], [77, 85, 200]], [72, 80, 200]),
        # 175 is 3 pt from 172, 168 is 4 pt: 175 pairs, 168 is added
        ([[72, 172, 512], [72, 168, 175, 512]], [72, 168, 172, 512]),
        # a tie, 4 pt each side: the earlier edge pairs
        ([[72, 172, 512], [72, 168, 176, 512]], [72, 172, 176, 512]),
        # one part edge between two union edges takes neither: nothing added
        ([[72, 166, 172, 512], [72, 170, 512]], [72, 166, 172, 512]),
        # 74 is 1 pt from 75: it pairs, 70 and 80 are added
        ([[75, 200], [70, 74, 80, 200]], [70, 75, 80, 200]),
    ],
    ids=["narrow-shift", "nearer-later", "tie", "between", "nearest-own"],
)
def test_union_pairs_the_most_edges_then_the_nearest(parts, union):
    assert T.union_columns(parts) == union


def test_three_parts_pair_against_the_growing_union():
    # the second part adds 168 (develop added 175); the third part's 170
    # lies 2 pt from both 168 and 172 and pairs, adding nothing
    parts = [[72, 172, 512], [72, 168, 175, 512], [72, 170, 512]]
    assert T.union_columns(parts) == [72, 168, 172, 512]


# ---------------------------------------------------------------- AC-4


def test_a_cell_sits_under_the_nearest_union_edge():
    # T71's Figure 213 case: an inner rule at 170 between union edges 166
    # and 172 goes under 172, not the first within 6 pt
    union = [72, 166, 172, 512]
    assert T.spread_row(["a", "b"], [72, 170, 512], union) == ["a", "", "b"]


def test_cells_keep_their_order_and_one_column_each():
    union = [72, 100, 110, 115, 512]
    # 112 lies within 6 pt of 110 and 115, 114 nearest 115: 112 takes 110
    row = T.spread_row(["a", "b", "c"], [72, 112, 114, 512], union)
    assert row == ["a", "", "b", "c"]


def test_a_tie_places_the_cell_under_the_earlier_edge():
    # 103 -> 100 and 105 -> 104 cost 4 pt, as do 103 -> 104 and 105 -> 108
    union = [72, 100, 104, 108, 512]
    row = T.spread_row(["a", "b", "c"], [72, 103, 105, 512], union)
    assert row == ["a", "b", "c", ""]


def test_a_cell_far_from_every_free_edge_takes_the_nearest_one():
    # no free edge lies within 6 pt of 300: it goes under 252, the nearest
    union = [72, 172, 252, 512]
    assert T.spread_row(["a", "b"], [72, 300, 512], union) == ["a", "", "b"]


def test_a_row_whose_edges_match_the_union_is_kept():
    union = [72, 172, 252, 512]
    row = ["a", "b", "c"]
    assert T.spread_row(row, [73, 171, 253, 512], union) == row
