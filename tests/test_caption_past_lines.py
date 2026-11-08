"""A table's caption is the nearest caption-like line within 40 points
above it, even when other lines stand between (IPMI's column names
`byte data field`, a note), unless another table stands between too."""

import pytest

from bmc_toolkit.spec import tables as T
from tests import pdfgen
from tests.test_tables import WIDTHS, ruled_table

pytest.importorskip("pdfplumber")

ASCENT = 8  # a 10 pt line's top lies about this far above its baseline
TOP = 600  # PDF points, origin bottom-left
ROWS = [["A", "B", "C"], ["1", "2", "3"]]


def table(top=TOP, rows=ROWS, height=16):
    return ruled_table(72, top, WIDTHS, [height] * len(rows), rows)


def above(gap, text, top=TOP):
    """A text line whose top lies ``gap`` points over a table top."""
    return (72, top + gap - ASCENT, text)


def captions(tmp_path, pages):
    pdf = pdfgen.write_pdf(tmp_path / "c.pdf", pages)
    with T.Reader(pdf) as r:
        return [
            [t.caption for t in r.logical_tables(n)] for n in range(1, len(pages) + 1)
        ]


# ---------------------------------------------------------------- AC-1


def test_the_caption_above_a_column_name_line_is_taken(tmp_path):
    pages = [
        table()
        + [above(26, "Table 20-, Get Device ID Command"), above(12, "byte data field")],
        table() + [above(26, "343 Table 2 - Buffer Descriptor"), above(12, "0001b")],
        table()
        + [
            above(38, "Table 31. Command Summary"),
            above(25, "Note: The byte count is not included."),
            above(12, "byte count byte of block transactions."),
        ],
    ]
    assert captions(tmp_path, pages) == [
        ["Table 20-, Get Device ID Command"],
        ["Table 2 - Buffer Descriptor"],
        ["Table 31. Command Summary"],
    ]


# ---------------------------------------------------------------- AC-2


def test_a_caption_with_another_table_between_is_not_taken(tmp_path):
    # Table 1 sits right over the second table; its caption lies within
    # 40 points of the second one, but Table 1 stands between
    first_top = 626
    page = (
        table(top=first_top, rows=[["X", "Y", "Z"]])
        + [above(12, "Table 1 - First", top=first_top)]
        + table()
    )
    assert captions(tmp_path, [page]) == [["Table 1 - First", None]]


# ---------------------------------------------------------------- AC-3


def test_a_caption_beyond_40_points_is_not_taken(tmp_path):
    page = table() + [above(52, "Table 9 - Too far"), above(12, "byte data field")]
    assert captions(tmp_path, [page]) == [[None]]


# ---------------------------------------------------------------- AC-4


def test_the_nearest_caption_wins_over_one_further_up(tmp_path):
    page = table() + [above(30, "Table 8 - Earlier"), above(12, "Table 9 - Nearest")]
    assert captions(tmp_path, [page]) == [["Table 9 - Nearest"]]


def test_prose_only_in_the_window_still_falls_back_to_the_figure_caption(tmp_path):
    bottom = TOP - 32
    page = table() + [
        above(26, "The fields are described below."),
        above(12, "byte data field"),
        (72, bottom - 30 - ASCENT, "Figure 3 - Packet format"),
    ]
    assert captions(tmp_path, [page]) == [["Figure 3 - Packet format"]]
