"""A table with no caption from the 40 pt window, the Figure rule or the
page before takes a `Table` caption whose bottom lies within 40 points
above it (PMBus Table 31: its top lies 47 points up, past two note lines),
and the page-before rule takes `Table` in any case (PR #117 F1)."""

import pytest

from bmc_toolkit.spec import tables as T
from tests import pdfgen
from tests.test_caption_page_before import ending, starts_page_2
from tests.test_tables import WIDTHS, ruled_table

pytest.importorskip("pdfplumber")

ASCENT = 8  # a 10 pt line's top lies about this far above its baseline
TOP = 600  # PDF points, origin bottom-left
ROWS = [["A", "B", "C"], ["1", "2", "3"]]
NOTES = [
    (25, "Note: The byte count is not included."),
    (12, "byte count byte of block transactions."),
]


def table(top=TOP, rows=ROWS):
    return ruled_table(72, top, WIDTHS, [16] * len(rows), rows)


def above(gap, text, top=TOP):
    """A text line whose top lies ``gap`` points over a table top."""
    return (72, top + gap - ASCENT, text)


def notes():
    return [above(gap, text) for gap, text in NOTES]


def read(tmp_path, pages):
    pdf = pdfgen.write_pdf(tmp_path / "c.pdf", pages)
    with T.Reader(pdf) as r:
        return [
            [t.caption for t in r.logical_tables(n)] for n in range(1, len(pages) + 1)
        ]


def line_gaps(tmp_path, gap, text):
    """(top, bottom) of the line drawn by ``above(gap, text)``, measured
    from the table top, as the Reader sees them."""
    pdf = pdfgen.write_pdf(tmp_path / "g.pdf", [table() + [above(gap, text)]])
    with T.Reader(pdf) as r:
        info = r.page(1)
        t = info.tables[0]
        (ln,) = [ln for ln in info.lines if ln.text == text]
        return t.top - ln.top, t.top - ln.bottom


# ---------------------------------------------------------------- AC-1


def test_the_geometry_matches_pmbus_table_31(tmp_path):
    # the caption's top lies outside the 40 pt window, its bottom inside
    top, bottom = line_gaps(tmp_path, 47, "Table 31. Command Summary")
    assert top > T.CAPTION_GAP_PT
    assert bottom < T.CAPTION_GAP_PT


def test_a_table_caption_ending_within_40_points_is_taken(tmp_path):
    pages = [
        table() + [above(47, "Table 31. Command Summary")] + notes(),
        table() + [above(47, "112 Table 4 - Margin numbered")] + notes(),
        table() + [above(47, "TABLE 5 - Upper case")] + notes(),
        table() + [above(47, "Table 20-, Get Device ID Command")] + notes(),
    ]
    assert read(tmp_path, pages) == [
        ["Table 31. Command Summary"],
        ["Table 4 - Margin numbered"],
        ["TABLE 5 - Upper case"],
        ["Table 20-, Get Device ID Command"],
    ]


def test_a_caption_with_nothing_between_is_taken_too(tmp_path):
    page = table() + [above(47, "Table 6 - Alone")]
    assert read(tmp_path, [page]) == [["Table 6 - Alone"]]


# ---------------------------------------------------------------- AC-2


def test_a_figure_line_is_not_taken(tmp_path):
    # the Figure rule has its own prose filter; the fallback takes no Figure
    page = table() + [above(47, "Figure 24 shows a large request.")] + notes()
    assert read(tmp_path, [page]) == [[None]]


@pytest.mark.parametrize(
    "text",
    ["Table 3 lists the fields below.", "Table 31 and Table 32 list them.", "Tables"],
)
def test_prose_starting_with_table_is_not_taken(tmp_path, text):
    page = table() + [above(47, text)] + notes()
    assert read(tmp_path, [page]) == [[None]]


def test_a_caption_ending_beyond_40_points_is_not_taken(tmp_path):
    top, bottom = line_gaps(tmp_path, 56, "Table 9 - Too far")
    assert bottom > T.CAPTION_GAP_PT
    page = table() + [above(56, "Table 9 - Too far")] + notes()
    assert read(tmp_path, [page]) == [[None]]


def test_a_caption_with_another_table_between_is_not_taken(tmp_path):
    # a one-row table sits between the caption and the table; the caption
    # names that one (its top lies 13 pt over it, 43 pt over the table)
    small_top = TOP + 30
    page = (
        table(top=small_top, rows=[["X", "Y", "Z"]])
        + [above(13, "Table 1 - Small", top=small_top)]
        + table()
    )
    assert read(tmp_path, [page]) == [["Table 1 - Small", None]]


# ---------------------------------------------------------------- AC-3


def test_a_caption_in_the_window_wins(tmp_path):
    page = table() + [
        above(47, "Table 8 - Further up"),
        above(25, "Table 9 - In the window"),
        above(12, "byte data field"),
    ]
    assert read(tmp_path, [page]) == [["Table 9 - In the window"]]


def test_a_figure_caption_wins(tmp_path):
    page = (
        table()
        + [above(47, "Table 8 - Further up")]
        + notes()
        + [(72, TOP - 32 - 30 - ASCENT, "Figure 3 - Packet format")]
    )
    assert read(tmp_path, [page]) == [["Figure 3 - Packet format"]]


# ---------------------------------------------------------------- AC-4


@pytest.mark.parametrize("text", ["TABLE 5 - Register map", "table 5 - register map"])
def test_the_page_before_rule_takes_table_in_any_case(tmp_path, text):
    assert starts_page_2(tmp_path, ending(text)) == [(2, 2, text)]
