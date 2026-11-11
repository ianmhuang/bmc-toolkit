"""A table that starts a page takes its caption from the foot of the page
before when that page ends with a `Table` caption (IPMI Table 21-4,
DSP2058 Table 1), and the repeated-caption join of PR #116 compares
captions without their margin line numbers and only with lines that
caption a table."""

import pytest

from bmc_toolkit.spec import tables as T
from tests import pdfgen
from tests.test_caption_not_furniture import (
    FULL,
    TOP,
    caption,
    furniture,
    prose,
    rows,
    table,
)

pytest.importorskip("pdfplumber")


def at(y, text):
    """A text line with its baseline at ``y`` (PDF points, bottom-left)."""
    return (72, y, text)


def ending(*texts, last_y=300):
    """Prose lines ending with ``texts``, the last at ``last_y``."""
    lines = []
    y = last_y + 14 * len(texts)
    for text in ("The command is described in the table that follows.", *texts):
        lines.append(at(y, text))
        y -= 14
    return lines


def read(tmp_path, pages):
    pdf = pdfgen.write_pdf(tmp_path / "b.pdf", pages)
    with T.Reader(pdf) as r:
        return {
            n: [(t.first, t.last, t.caption) for t in r.logical_tables(n)]
            for n in range(1, len(pages) + 1)
        }


def starts_page_2(tmp_path, page_1, page_2_extra=()):
    pages = [
        furniture(1) + page_1,
        furniture(2) + table(rows(0, 4)) + list(page_2_extra) + [prose(2)],
    ]
    return read(tmp_path, pages)[2]


# ---------------------------------------------------------------- AC-1


def test_a_table_caption_ending_the_page_before_is_taken(tmp_path):
    got = starts_page_2(
        tmp_path, ending("Table 21-4, Get Command Sub-function Support Command")
    )
    assert got == [(2, 2, "Table 21-4, Get Command Sub-function Support Command")]


def test_the_margin_line_number_is_dropped(tmp_path):
    got = starts_page_2(tmp_path, ending("61 Table 1 - Threat modeling assessment"))
    assert got == [(2, 2, "Table 1 - Threat modeling assessment")]


def test_a_table_running_on_takes_the_caption_once(tmp_path):
    pages = [
        furniture(1) + ending("Table 5 - Register map"),
        furniture(2) + table(rows(0, FULL)),
        furniture(3) + table(rows(FULL, 4)) + [prose(3)],
    ]
    got = read(tmp_path, pages)
    assert got[2] == got[3] == [(2, 3, "Table 5 - Register map")]


# ---------------------------------------------------------------- AC-2


def test_a_figure_caption_ending_the_page_before_is_not_taken(tmp_path):
    # SMBus 3.3.1 page 17: a figure's caption sits under its drawing
    got = starts_page_2(tmp_path, ending("Figure 5: Timeout intervals"))
    assert got == [(2, 2, None)]


def test_a_table_line_that_is_not_the_last_line_is_not_taken(tmp_path):
    got = starts_page_2(
        tmp_path, ending("Table 7 - Earlier", "Its fields follow on the next page.")
    )
    assert got == [(2, 2, None)]


def test_a_table_line_with_its_own_table_under_it_is_not_taken(tmp_path):
    # page 1: the caption names the table under it; page 2's table has
    # other column edges, so it does not carry that one on
    page_1 = [caption("Table 8 - Own table", top=400)] + table(rows(0, 4), top=400)
    pages = [
        furniture(1) + page_1,
        furniture(2) + table(rows(0, 4), widths=[150, 80, 150]) + [prose(2)],
    ]
    got = read(tmp_path, pages)
    assert got[1] == [(1, 1, "Table 8 - Own table")]
    assert got[2] == [(2, 2, None)]


def test_a_table_with_a_body_line_above_it_does_not_look_back(tmp_path):
    got = starts_page_2(
        tmp_path,
        ending("Table 9 - Before"),
        [caption("The values are listed below.", gap=20)],
    )
    assert got == [(2, 2, None)]


def test_a_table_second_on_its_page_does_not_look_back(tmp_path):
    pages = [
        furniture(1) + ending("Table 10 - Before"),
        furniture(2)
        + table(rows(0, 2))
        + table(rows(0, 2), top=TOP - 200, widths=[150, 80, 150])
        + [prose(2)],
    ]
    got = read(tmp_path, pages)[2]
    assert [c for _, _, c in got] == ["Table 10 - Before", None]


# ---------------------------------------------------------------- AC-3


def test_a_caption_in_the_window_is_kept(tmp_path):
    got = starts_page_2(tmp_path, ending("Table 3 - Other"), [caption("Table 4 - Own")])
    assert got == [(2, 2, "Table 4 - Own")]


def test_a_figure_caption_under_the_table_is_kept(tmp_path):
    got = starts_page_2(
        tmp_path, ending("Table 3 - Other"), [at(TOP - 64 - 30, "Figure 2 - Layout")]
    )
    assert got == [(2, 2, "Figure 2 - Layout")]


# ---------------------------------------------------------------- AC-4


def test_a_repeat_with_another_margin_number_still_joins(tmp_path):
    pages = [
        furniture(1) + [caption("12 Figure 7: Status")] + table(rows(0, FULL)),
        furniture(2)
        + [caption("40 Figure 7: Status")]
        + table(rows(FULL, 4))
        + [prose(2)],
    ]
    got = read(tmp_path, pages)
    assert got[1] == got[2] == [(1, 2, "Figure 7: Status")]


# ---------------------------------------------------------------- AC-5


def test_a_caption_like_line_over_no_table_is_not_a_caption_to_repeat(tmp_path):
    # page 1's line names a drawing 250 pt over the table, past both the
    # caption window and the figure rule; page 2's same line names its
    # table, which does not carry page 1's on
    low = 430
    depth = (low - 72) // 16
    pages = [
        furniture(1)
        + [caption("Figure 7: Status", top=low, gap=250)]
        + table(rows(0, depth), top=low),
        furniture(2)
        + [caption("Figure 7: Status")]
        + table(rows(depth, 4))
        + [prose(2)],
    ]
    got = read(tmp_path, pages)
    assert [(a, b) for a, b, _ in got[1]] == [(1, 1)]
    assert got[2] == [(2, 2, "Figure 7: Status")]
