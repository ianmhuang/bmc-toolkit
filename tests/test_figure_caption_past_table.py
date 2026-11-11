"""A Figure caption under a drawing read as a table names it even when
another table starts right under the caption, as long as that table takes
a numbered caption of its own between them (PR #72 F2: PMBus Figure 8 over
Table 3, SMBus Figure 63 over Table 13)."""

import pytest

from bmc_toolkit.spec import tables as T
from bmc_toolkit.spec.catalog import load_catalog
from tests import pdfgen
from tests.test_figure_captions import ASCENT, BOTTOM, below, boxes
from tests.test_tables import WIDTHS, ruled_table

pytest.importorskip("pdfplumber")

RULED = [["A", "B", "C"], ["1", "2", "3"]]


def page_with(lines, second_top):
    """The boxes, ``lines`` under them, and a ruled table at
    ``second_top`` (PDF points)."""
    return boxes() + lines + ruled_table(72, second_top, WIDTHS, [16, 16], RULED)


def captions(tmp_path, page):
    pdf = pdfgen.write_pdf(tmp_path / "f.pdf", [page])
    with T.Reader(pdf) as r:
        return [t.caption for t in r.logical_tables(1)]


def baseline(gap):
    """The baseline of a line whose top lies ``gap`` points under BOTTOM."""
    return BOTTOM - gap - ASCENT


# ---------------------------------------------------------------- AC-1


def test_a_table_with_its_own_numbered_caption_leaves_the_figure_line(tmp_path):
    # Figure line 10 pt under the boxes, Table line 24 pt under them, the
    # ruled table 14 pt under the Table line: it starts within 40 pt of
    # the Figure line, which develop took as "the caption of the table
    # right under it"
    second_top = baseline(24) - 14
    page = page_with(
        [below(10, "Figure 8. VID Format Data Bytes"), below(24, "Table 3. VID Types")],
        second_top,
    )
    assert captions(tmp_path, page) == [
        "Figure 8. VID Format Data Bytes",
        "Table 3. VID Types",
    ]


def test_a_colon_caption_form_as_in_smbus(tmp_path):
    second_top = baseline(24) - 14
    page = page_with(
        [
            below(10, "Figure 63: SMBus during suspend"),
            below(24, "Table 13: SMBus Suspend parameters"),
        ],
        second_top,
    )
    assert captions(tmp_path, page) == [
        "Figure 63: SMBus during suspend",
        "Table 13: SMBus Suspend parameters",
    ]


def test_a_table_with_its_own_figure_caption_leaves_the_figure_line(tmp_path):
    # PR #122 F1: a numbered Figure caption taken by the table under counts
    # as its own, as a Table one does (both lines read as captions)
    second_top = baseline(24) - 14
    page = page_with(
        [below(10, "Figure 7: Packet layout"), below(24, "Figure 8: Field codes")],
        second_top,
    )
    assert captions(tmp_path, page) == [
        "Figure 7: Packet layout",
        "Figure 8: Field codes",
    ]


# ---------------------------------------------------------------- AC-2


def test_a_table_that_takes_the_figure_line_keeps_it(tmp_path):
    # NVMe captions a table "Figure N" above it
    second_top = baseline(10) - 20
    page = page_with([below(10, "Figure 3 - Codes")], second_top)
    assert captions(tmp_path, page) == [None, "Figure 3 - Codes"]


def test_a_table_that_takes_a_line_without_an_id_still_blocks(tmp_path):
    # NVME-MI p69: Figure 49's caption wraps, its last word "Table" on a
    # line of its own right over the table, which takes that word
    second_top = baseline(24) - 14
    page = page_with(
        [below(10, "Figure 49: Request Message SQE Mapping"), below(24, "Table")],
        second_top,
    )
    first, second = captions(tmp_path, page)
    assert first is None
    assert second == "Table"


def test_a_table_with_no_caption_line_of_its_own_still_blocks(tmp_path):
    # the table starts about 34 pt under the Figure line's bottom but 44
    # pt under its top, outside its own caption window: it takes no line
    # above it, and the Figure line stays off the boxes as on develop
    second_top = baseline(10) - 36
    page = page_with([below(10, "Figure 3 - Packet")], second_top)
    assert captions(tmp_path, page) == [None, "Figure 3 - Packet"]


def test_a_table_further_down_does_not_block(tmp_path):
    # a table more than 40 pt under the Figure line never blocked it
    second_top = baseline(10) - 60
    page = page_with([below(10, "Figure 3 - Packet")], second_top)
    assert captions(tmp_path, page)[0] == "Figure 3 - Packet"


# ---------------------------------------------------------------- AC-9


def test_sff_8636_limits_name_the_page_26_figures():
    # two drawings captioned under them: the lower takes the upper's
    # caption by the caption-above rule, a known limit
    limits = load_catalog().get("SFF-8636").limits
    assert "Figures 5-5 and 5-6" in limits
    assert "page 26" in limits
