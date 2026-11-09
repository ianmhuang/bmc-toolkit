"""A joined table's columns pair each part's edges with union edges in
order, one to one, so two edges of one part never fall on one column and
every row has one cell per column (PR #119 F7)."""

import pytest

from bmc_toolkit.spec import tables as T
from tests.test_join_nested_parts import (
    FOUR,
    FULL,
    HEADER,
    SHIFTED,
    THREE,
    body,
    logical,
    nested_part,
    part,
    two_pages,
)

pytest.importorskip("pdfplumber")

# edges 72, 168, 176, 252, 512: an 8 pt column whose edges both lie
# within 6 pt of THREE's 172
SPLIT = [96, 8, 76, 260]


def split_rows(first, count):
    return [[f"{first + i:02d}", "M", "", f"Field {first + i}"] for i in range(count)]


# ---------------------------------------------------------------- AC-1


def test_two_edges_of_one_part_near_one_union_edge_stay_two(tmp_path):
    pages = two_pages(
        part(THREE, [HEADER] + body(0, FULL, 3)), part(SPLIT, split_rows(40, 4))
    )
    (lt,) = logical(tmp_path, pages)
    assert (lt.first, lt.last) == (1, 2)
    assert [round(c) for c in lt.columns] == [72, 172, 176, 252, 512]
    assert {len(r) for r in lt.rows} == {4}
    assert lt.rows[1] == ["00", "M", "", "Field 0"]
    assert lt.rows[-1] == ["43", "M", "", "Field 43"]


# ---------------------------------------------------------------- AC-2


@pytest.mark.parametrize(
    ("parts", "union"),
    [
        ([[72, 80, 200], [77, 85, 200]], [72, 80, 200]),
        ([[72, 172, 252, 512], [72, 172, 262, 512]], [72, 172, 252, 262, 512]),
        ([[72, 172, 252, 312, 512], [72, 172, 512]], [72, 172, 252, 312, 512]),
        ([[72, 200], [68, 76, 200]], [72, 76, 200]),
        ([[72, 172, 512], [72, 168, 176, 512]], [72, 172, 176, 512]),
    ],
    ids=["narrow-shift", "inner-shift", "subset", "f7", "split"],
)
def test_union_pairs_edges_in_order_one_to_one(parts, union):
    assert T.union_columns(parts) == union


def test_the_union_has_as_many_edges_as_any_part():
    parts = [[72, 200], [68, 74, 80, 200], [70, 200]]
    assert len(T.union_columns(parts)) >= max(len(p) for p in parts)


# ---------------------------------------------------------------- AC-3


def test_spread_row_never_returns_a_row_wider_than_the_union():
    union = T.union_columns([[72.0, 200.0], [68.0, 76.0, 200.0]])
    assert T.spread_row(["a", "b"], [68.0, 76.0, 200.0], union) == ["a", "b"]
    assert T.spread_row(["a"], [72.0, 200.0], union) == ["a", ""]


@pytest.mark.parametrize(
    "pages",
    [
        two_pages(
            part(THREE, [HEADER] + body(0, FULL, 3)), part(THREE, body(40, 4, 3))
        ),
        two_pages(
            part(FOUR, [HEADER + [""]] + body(0, FULL, 4)), part(THREE, body(40, 4, 3))
        ),
        two_pages(
            part(THREE, [HEADER] + body(0, FULL, 3)), part(SHIFTED, body(40, 4, 3))
        ),
        two_pages(
            part(THREE, [HEADER] + body(0, FULL, 3)), part(SPLIT, split_rows(40, 4))
        ),
        two_pages(nested_part(30), part(THREE, [HEADER] + body(40, 4, 3))),
    ],
    ids=["same", "subset", "frame", "split", "nested"],
)
def test_every_row_has_one_cell_per_column(tmp_path, pages):
    joined = [t for t in logical(tmp_path, pages) if t.last == 2]
    assert joined
    for lt in joined:
        assert {len(r) for r in lt.rows} == {len(lt.columns) - 1}
