"""A table with no caption above it takes the caption of the figure it is
drawn in: a Figure line below the boxes, else one further above them."""

import json

import pytest

from bmc_toolkit.spec import tables as T
from tests import pdfgen
from tests.test_tables import WIDTHS, cell_table, ruled_table

pytest.importorskip("pdfplumber")

ASCENT = 8  # a 10 pt line's top lies about this far above its baseline

BYTES = [["+0", "+1", "+2", "+3"], ["RSVD", "Version", "Dest", "Src"]]
BYTE_WIDTHS = [60] * 4
TOP = 600  # PDF points, origin bottom-left
BOTTOM = TOP - 32  # two 16 pt rows


def boxes(top=TOP):
    """A packet layout drawn as tiled boxes, the way DMTF draws one."""
    return cell_table(72, top, BYTE_WIDTHS, [16, 16], BYTES)


def below(gap, text, bottom=BOTTOM):
    """A text line whose top lies ``gap`` points under a table bottom."""
    return (72, bottom - gap - ASCENT, text)


def above(gap, text, top=TOP):
    """A text line whose top lies ``gap`` points over a table top."""
    return (72, top + gap - ASCENT, text)


def captions(tmp_path, pages, number=1):
    pdf = pdfgen.write_pdf(tmp_path / "f.pdf", pages)
    with T.Reader(pdf) as r:
        return [t.caption for t in r.logical_tables(number)]


def captions_of_pages(tmp_path, pages):
    pdf = pdfgen.write_pdf(tmp_path / "f.pdf", pages)
    with T.Reader(pdf) as r:
        return [r.logical_tables(n)[0].caption for n in range(1, len(pages) + 1)]


# ---------------------------------------------------------------- AC-1


def test_a_figure_caption_below_names_the_boxes_up_to_200_points(tmp_path):
    pages = [
        boxes() + [below(30, "Figure 3 - Packet format")],
        boxes() + [below(190, "Figure 3 - Packet format")],
        boxes() + [below(210, "Figure 3 - Packet format")],
    ]
    assert captions_of_pages(tmp_path, pages) == [
        "Figure 3 - Packet format",
        "Figure 3 - Packet format",
        None,
    ]


def test_caption_forms_from_the_library_are_read(tmp_path):
    pages = [
        boxes()
        + [(37, BOTTOM - 30 - ASCENT, "2220"), below(30, "Figure 24 - Vendor ID")],
        boxes() + [below(30, "Figure B-1 Current Address Read")],
        boxes() + [below(30, "Figure 6-2, LAN to IPMB Bridged Request Example")],
        boxes() + [below(30, "Figure 28. OPERATION Command Data Byte")],
    ]
    assert captions_of_pages(tmp_path, pages) == [
        "Figure 24 - Vendor ID",
        "Figure B-1 Current Address Read",
        "Figure 6-2, LAN to IPMB Bridged Request Example",
        "Figure 28. OPERATION Command Data Byte",
    ]


@pytest.mark.parametrize(
    "line, caption",
    [
        ("Figure 3 – Packet format", "Figure 3 – Packet format"),
        ("174 Figure 4 — Two-byte field bit map", "Figure 4 — Two-byte field bit map"),
        ("Figure 60: Input Timing Diagram", "Figure 60: Input Timing Diagram"),
        ("Figure 3-1 Bit Organization", "Figure 3-1 Bit Organization"),
        (
            "Figure 6-, LAN to IPMB Bridged Request Example",
            "Figure 6-, LAN to IPMB Bridged Request Example",
        ),
    ],
)
def test_figure_caption_text(line, caption):
    assert T.figure_caption(line) == caption


# ---------------------------------------------------------------- AC-2


def test_a_figure_caption_further_above_names_the_boxes(tmp_path):
    pages = [
        boxes() + [above(100, "Figure 6-2, LAN to IPMB Bridged Request Example")],
        boxes() + [above(100, "Figure 5 - Above"), below(30, "Figure 4 - Below")],
        boxes() + [above(210, "Figure 5 - Too far")],
    ]
    assert captions_of_pages(tmp_path, pages) == [
        "Figure 6-2, LAN to IPMB Bridged Request Example",
        "Figure 4 - Below",
        None,
    ]


# ---------------------------------------------------------------- AC-3


def test_a_table_caption_above_is_kept(tmp_path):
    page = boxes() + [above(14, "Table 2 - Codes"), below(30, "Figure 3 - Packet")]
    ruled = ruled_table(72, TOP, WIDTHS, [16, 16], [["A", "B", "C"], ["1", "2", "3"]])
    ruled += [above(14, "Table 4 - Rules"), below(30, "Figure 5 - Packet")]
    assert captions_of_pages(tmp_path, [page, ruled]) == [
        "Table 2 - Codes",
        "Table 4 - Rules",
    ]


# ---------------------------------------------------------------- AC-4


@pytest.mark.parametrize(
    "line",
    [
        "Figure 3 shows the format",
        "Figure 101.",
        "Figure 223Figure 223).",
        "Figure 65), if applicable",
    ],
)
def test_prose_starting_with_figure_is_not_a_caption(tmp_path, line):
    assert T.figure_caption(line) is None
    assert captions(tmp_path, [boxes() + [below(30, line)]]) == [None]


# ---------------------------------------------------------------- AC-5


def test_a_line_mentioning_a_table_stops_the_search(tmp_path):
    pages = [
        boxes()
        + [below(15, "The fields are in Table 7."), below(40, "Figure 3 - Packet")],
        boxes()
        + [above(100, "Figure 3 - Packet"), above(60, "See Table 7 for values.")],
    ]
    assert captions_of_pages(tmp_path, pages) == [None, None]


# ---------------------------------------------------------------- AC-6


def test_a_caption_with_a_table_right_under_it_names_that_table(tmp_path):
    # NVMe captions its tables "Figure N" and puts the caption above them
    second_top = BOTTOM - 30 - 10 - 20  # 20 pt under the caption line's bottom
    page = boxes() + [below(30, "Figure 3 - Codes")] + boxes(second_top)
    assert captions(tmp_path, [page]) == [None, "Figure 3 - Codes"]


def test_a_caption_with_another_table_between_is_not_taken_below(tmp_path):
    second_top = BOTTOM - 60
    second_bottom = second_top - 32
    page = boxes() + boxes(second_top) + [below(30, "Figure 3 - Packet", second_bottom)]
    assert captions(tmp_path, [page]) == [None, "Figure 3 - Packet"]


def test_a_caption_with_another_table_between_is_not_taken_above(tmp_path):
    first_top = TOP + 92  # this table sits 60 pt over the one at TOP
    page = [above(60, "Figure 3 - Packet", first_top)] + boxes(first_top) + boxes()
    assert captions(tmp_path, [page]) == ["Figure 3 - Packet", None]


# ---------------------------------------------------------------- AC-7


def furniture(n):
    return [(72, 760, "Spec Title"), (300, 40, f"Page {n}")]


def continued(caption):
    page1 = furniture(1) + boxes(200)
    if caption:
        page1.append(above(14, caption, 200))
    page2 = furniture(2) + boxes(740) + [below(30, "Figure 9 - Elsewhere", 740 - 32)]
    return [page1, page2]


def test_a_continued_table_keeps_its_first_page_caption(tmp_path):
    pdf = pdfgen.write_pdf(tmp_path / "f.pdf", continued("Table 1 - Codes"))
    with T.Reader(pdf) as r:
        (t,) = r.logical_tables(2)
    assert (t.first, t.last, t.caption) == (1, 2, "Table 1 - Codes")


def test_a_figure_line_under_a_continuation_is_not_used(tmp_path):
    pdf = pdfgen.write_pdf(tmp_path / "f.pdf", continued(None))
    with T.Reader(pdf) as r:
        (t,) = r.logical_tables(2)
    assert (t.first, t.last, t.caption) == (1, 2, None)


# ---------------------------------------------------------------- AC-8


def test_numbering_rows_and_the_table_line(tmp_path):
    page = boxes() + [below(30, "Figure 3 - Packet")]
    page += ruled_table(72, 300, WIDTHS, [16, 16], [["A", "B", "C"], ["1", "2", "3"]])
    page.append(above(14, "Table 4 - Rules", 300))
    pdf = pdfgen.write_pdf(tmp_path / "f.pdf", [page])
    with T.Reader(pdf) as r:
        grid, ruled = r.logical_tables(1)
    assert (grid.index, grid.caption, grid.rows) == (1, "Figure 3 - Packet", BYTES)
    assert (ruled.index, ruled.caption) == (2, "Table 4 - Rules")
    assert T.describe(grid) == (
        "table: Figure 3 - Packet | cells (no ruling lines) | page 1 "
        "| 4 columns | 2 rows"
    )


def test_a_version_5_store_is_read_again(tmp_path):
    assert T.TABLES_VERSION == 6
    pdf = pdfgen.write_pdf(tmp_path / "f.pdf", [boxes() + [below(30, "Figure 3 - P")]])
    with T.Reader(pdf) as r:
        found = r.logical_tables(1)
    T.store(tmp_path, [1], found)
    path = tmp_path / T.TABLES_NAME
    data = json.loads(path.read_text("utf-8"))
    assert data["tables_version"] == 6
    assert data["tables"][0]["caption"] == "Figure 3 - P"
    assert T.stored_for_page(tmp_path, 1) is not None
    data["tables_version"] = 5
    path.write_text(json.dumps(data), "utf-8")
    assert T.stored_for_page(tmp_path, 1) is None
