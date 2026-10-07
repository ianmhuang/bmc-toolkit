"""Review tests: a table with no caption just above it is named by the
caption of the figure it is drawn in (AC-1 to AC-8 of the change).

Geometry is built here from scratch: a packet layout drawn as tiled boxes
(the way DMTF draws one) and text lines placed a known number of points
under or over it. PDF points, origin bottom-left; Helvetica 10 pt puts a
line's top about 8 pt above its baseline.
"""

import json

import pytest

from bmc_toolkit.spec import tables as T
from tests import pdfgen
from tests.test_tables import WIDTHS, cell_table, ruled_table

pytest.importorskip("pdfplumber")

ASCENT = 8
GRID_TOP = 600
ROW_H = 16
GRID_H = 2 * ROW_H
PACKET = [["+0", "+1", "+2", "+3"], ["RSVD", "Version", "Dest", "Src"]]
OTHER = [["Bit 7", "Bit 6", "Bit 5", "Bit 4"], ["EN", "RST", "IRQ", "ACK"]]
CODES = [["Name", "Code", "Meaning"], ["Temp", "01h", "degrees"]]


def grid(top=GRID_TOP, cells=PACKET):
    return cell_table(72, top, [60] * 4, [ROW_H, ROW_H], cells)


def under(gap, text, top=GRID_TOP):
    """A line whose top lies ``gap`` pt below the bottom of a grid at ``top``."""
    return (72, top - GRID_H - gap - ASCENT, text)


def over(gap, text, top=GRID_TOP):
    """A line whose top lies ``gap`` pt above the top of a grid at ``top``."""
    return (72, top + gap - ASCENT, text)


def read(tmp_path, pages, number=1):
    pdf = pdfgen.write_pdf(tmp_path / "review.pdf", pages)
    with T.Reader(pdf) as r:
        return r.logical_tables(number)


def caption_per_page(tmp_path, pages):
    pdf = pdfgen.write_pdf(tmp_path / "review.pdf", pages)
    with T.Reader(pdf) as r:
        out = []
        for n in range(1, len(pages) + 1):
            (t,) = r.logical_tables(n)
            out.append(t.caption)
        return out


# ---------------------------------------------------------------- AC-1


def test_the_figure_caption_below_is_taken_within_200_points(tmp_path):
    pages = [
        grid() + [under(30, "Figure 3 - Packet format")],
        grid() + [under(190, "Figure 3 - Packet format")],
        grid() + [under(210, "Figure 3 - Packet format")],
    ]
    assert caption_per_page(tmp_path, pages) == [
        "Figure 3 - Packet format",
        "Figure 3 - Packet format",
        None,
    ]


def test_the_en_dash_form_of_the_criterion_is_a_caption():
    line = "Figure 3 – Packet format"
    assert T.figure_caption(line) == line


def test_caption_shapes_with_letter_prefix_dot_and_comma(tmp_path):
    margin_number = (37, GRID_TOP - GRID_H - 30 - ASCENT, "1234")
    pages = [
        grid() + [under(30, "Figure B-1 Current Address Read")],
        grid() + [under(30, "Figure 28. OPERATION Command Data Byte")],
        grid() + [under(30, "Figure 2.4: Timing grid")],
        grid() + [margin_number, under(30, "Figure 9 - Id")],
    ]
    assert caption_per_page(tmp_path, pages) == [
        "Figure B-1 Current Address Read",
        "Figure 28. OPERATION Command Data Byte",
        "Figure 2.4: Timing grid",
        "Figure 9 - Id",
    ]


# ---------------------------------------------------------------- AC-2


def test_a_figure_caption_100_points_above_is_taken(tmp_path):
    page = grid() + [over(100, "Figure 6-2, LAN to IPMB Bridged Request Example")]
    (t,) = read(tmp_path, [page])
    assert t.caption == "Figure 6-2, LAN to IPMB Bridged Request Example"


def test_below_wins_over_above(tmp_path):
    page = grid() + [over(100, "Figure 5 - Above"), under(30, "Figure 4 - Below")]
    (t,) = read(tmp_path, [page])
    assert t.caption == "Figure 4 - Below"


def test_a_figure_caption_too_far_above_is_not_taken(tmp_path):
    low = 400  # room for a line 210 pt over the grid inside the page
    pages = [
        grid(low) + [over(190, "Figure 5 - Near enough", low)],
        grid(low) + [over(210, "Figure 5 - Too far", low)],
    ]
    assert caption_per_page(tmp_path, pages) == ["Figure 5 - Near enough", None]


# ---------------------------------------------------------------- AC-3


def test_a_table_caption_just_above_beats_a_figure_caption_below(tmp_path):
    boxes = grid() + [over(14, "Table 2 - Codes"), under(30, "Figure 3 - Packet")]
    ruled = ruled_table(72, GRID_TOP, WIDTHS, [ROW_H, ROW_H], CODES)
    ruled += [over(14, "Table 4 - Rules"), under(30, "Figure 5 - Packet")]
    # control: a figure line at the same gap is taken once the Table caption
    # is gone (its own title, or it repeats the lines above at the same
    # height and body_lines drops it as page furniture)
    control = grid() + [under(30, "Figure 6 - Control")]
    assert caption_per_page(tmp_path, [boxes, ruled, control]) == [
        "Table 2 - Codes",
        "Table 4 - Rules",
        "Figure 6 - Control",
    ]


# ---------------------------------------------------------------- AC-4


@pytest.mark.parametrize(
    "prose",
    [
        "Figure 3 shows the format",
        "Figure 101.",
        "Figure 223Figure 223).",
        "Figure 65), if applicable",
    ],
)
def test_prose_that_starts_with_figure_is_not_a_caption(tmp_path, prose):
    assert T.figure_caption(prose) is None
    pages = [
        grid() + [under(30, prose)],
        grid() + [under(30, "Figure 7 - Control")],  # same layout, a real caption
    ]
    assert caption_per_page(tmp_path, pages) == [None, "Figure 7 - Control"]


def test_prose_between_the_grid_and_its_caption_is_walked_past(tmp_path):
    page = grid() + [under(15, "Bytes are sent most significant first.")]
    page += [under(40, "Figure 3 - Packet")]
    (t,) = read(tmp_path, [page])
    assert t.caption == "Figure 3 - Packet"


# ---------------------------------------------------------------- AC-5


def test_a_table_mention_between_stops_the_walk_below(tmp_path):
    fig = under(40, "Figure 3 - Packet")
    pages = [
        grid() + [under(15, "The fields are in Table 7."), fig],
        grid()
        + [under(15, "The fields are listed later."), under(40, "Figure 4 - Layout")],
    ]
    assert caption_per_page(tmp_path, pages) == [None, "Figure 4 - Layout"]


def test_a_table_mention_between_stops_the_walk_above(tmp_path):
    fig = over(100, "Figure 3 - Packet")
    pages = [
        grid() + [fig, over(60, "See Table 7 for values.")],
        grid() + [over(100, "Figure 4 - Layout"), over(60, "See below for values.")],
    ]
    assert caption_per_page(tmp_path, pages) == [None, "Figure 4 - Layout"]


# ---------------------------------------------------------------- AC-6


def test_a_caption_with_a_table_right_under_it_belongs_to_that_table(tmp_path):
    # NVMe captions its real tables "Figure N" above them
    line_baseline = GRID_TOP - GRID_H - 30 - ASCENT
    second_top = line_baseline - 2 - 20  # 20 pt under the line's bottom
    page = grid() + [under(30, "Figure 3 - Codes")] + grid(second_top, OTHER)
    first, second = read(tmp_path, [page])
    assert (first.caption, second.caption) == (None, "Figure 3 - Codes")
    assert (first.rows, second.rows) == (PACKET, OTHER)


def test_a_caption_with_another_table_between_is_not_taken_below(tmp_path):
    second_top = GRID_TOP - GRID_H - 60
    page = grid() + grid(second_top, OTHER)
    page += [under(30, "Figure 3 - Packet", second_top)]
    first, second = read(tmp_path, [page])
    assert (first.caption, second.caption) == (None, "Figure 3 - Packet")


def test_a_caption_with_another_table_between_is_not_taken_above(tmp_path):
    upper_top = GRID_TOP + GRID_H + 60
    page = [over(60, "Figure 3 - Packet", upper_top)]
    page += grid(upper_top, OTHER) + grid()
    upper, lower = read(tmp_path, [page])
    assert (upper.caption, lower.caption) == ("Figure 3 - Packet", None)


# ---------------------------------------------------------------- AC-7


def furniture(n):
    return [(72, 760, "Spec Title"), (300, 40, f"Page {n}")]


def continued(first_page_extra):
    page1 = furniture(1) + grid(200) + first_page_extra
    page2 = furniture(2) + grid(740, OTHER)
    page2 += [under(30, "Figure 9 - Elsewhere", 740)]
    return [page1, page2]


@pytest.mark.parametrize(
    "extra, caption",
    [
        ([over(14, "Table 1 - Codes", 200)], "Table 1 - Codes"),
        ([over(100, "Figure 2 - Layout", 200)], "Figure 2 - Layout"),
        ([], None),
    ],
)
def test_a_continued_table_keeps_its_first_page_caption(tmp_path, extra, caption):
    pdf = pdfgen.write_pdf(tmp_path / "review.pdf", continued(extra))
    with T.Reader(pdf) as r:
        (t,) = r.logical_tables(2)
    assert (t.first, t.last) == (1, 2)
    assert t.caption == caption
    assert t.rows == PACKET + OTHER


# ---------------------------------------------------------------- AC-8


def test_numbering_rows_and_the_table_line_are_as_before(tmp_path):
    page = grid() + [under(30, "Figure 3 - Packet")]
    page += ruled_table(72, 300, WIDTHS, [ROW_H, ROW_H], CODES)
    page += [over(14, "Table 4 - Rules", 300)]
    boxes, ruled = read(tmp_path, [page])
    assert (boxes.index, boxes.caption, boxes.rows) == (1, "Figure 3 - Packet", PACKET)
    assert (ruled.index, ruled.caption, ruled.rows) == (2, "Table 4 - Rules", CODES)
    assert T.describe(boxes) == (
        "table: Figure 3 - Packet | cells (no ruling lines) | page 1 "
        "| 4 columns | 2 rows"
    )
    assert T.describe(ruled) == (
        "table: Table 4 - Rules | ruled | page 1 | 3 columns | 2 rows"
    )


def test_a_version_5_store_is_discarded_and_version_6_written(tmp_path):
    assert T.TABLES_VERSION == 6
    page = grid() + [under(30, "Figure 3 - Packet")]
    found = read(tmp_path, [page])
    path = tmp_path / T.TABLES_NAME
    stale = {
        "tables_version": 5,
        "pages_done": [1],
        "tables": [
            {
                "first": 1,
                "last": 1,
                "index": 1,
                "caption": None,
                "section": None,
                "drawn": "cells",
                "columns": [72.0, 132.0, 192.0, 252.0, 312.0],
                "parts": [[1, 0, 72.0, 192.0, 312.0, 224.0]],
                "rows": PACKET,
                "row_pages": [1, 1],
            }
        ],
    }
    path.write_text(json.dumps(stale), encoding="utf-8")
    assert T.stored_for_page(tmp_path, 1) is None  # read again, not trusted
    T.store(tmp_path, [1], found)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tables_version"] == 6
    assert data["pages_done"] == [1]
    assert [t["caption"] for t in data["tables"]] == ["Figure 3 - Packet"]
    (stored,) = T.stored_for_page(tmp_path, 1)
    assert (stored.index, stored.rows) == (1, PACKET)
