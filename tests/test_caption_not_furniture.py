"""NVMe repeats a figure's caption at the top of each page the figure
runs over. A caption-like line with a table right under it is not a
running header, a repeated caption does not stop a join, and a new
caption does."""

import pytest

from bmc_toolkit.spec import tables as T
from bmc_toolkit.spec.catalog import load_catalog
from tests import pdfgen
from tests.test_tables import WIDTHS, ruled_table

pytest.importorskip("pdfplumber")

ASCENT = 8  # a 10 pt line's top lies about this far above its baseline
TOP = 680  # PDF points, origin bottom-left
CAPTION_GAP = 12  # the caption's top lies this far over the table top


def table(rows, top=TOP, widths=WIDTHS, height=16):
    return ruled_table(72, top, widths, [height] * len(rows), rows)


def caption(text, top=TOP, gap=CAPTION_GAP):
    return (72, top + gap - ASCENT, text)


def furniture(n):
    """A running header and a page number, the same on every page."""
    return [(72, 750, "Example Specification, Revision 2.4"), (300, 40, str(n))]


def rows(first, count):
    return [[f"{first + i:02d}h", "RO", f"Field {first + i}"] for i in range(count)]


# a table this tall runs to the page's foot: nothing lies under it
FULL = 38
# prose under a table: the table is not the last thing on its page (other
# words on each page, or the line repeats and is taken for furniture)
WORDS = ["first", "second", "third"]


def prose(n):
    return (72, 120, f"The {WORDS[n - 1]} part ends here.")


def read(tmp_path, pages):
    pdf = pdfgen.write_pdf(tmp_path / "f.pdf", pages)
    with T.Reader(pdf) as r:
        return {
            n: [(t.first, t.last, t.caption) for t in r.logical_tables(n)]
            for n in range(1, len(pages) + 1)
        }


# ---------------------------------------------------------------- AC-1


def test_captions_differing_only_in_numbers_are_each_tables_own(tmp_path):
    # NVME-NVM Figure 157 and 159 on facing pages at one height
    pages = [
        furniture(1)
        + [caption("Figure 157: Alpha Log Page")]
        + table(rows(0, 4))
        + [prose(1)],
        furniture(2)
        + [caption("Figure 159: Alpha Log Page")]
        + table(rows(0, 4))
        + [prose(2)],
    ]
    assert read(tmp_path, pages) == {
        1: [(1, 1, "Figure 157: Alpha Log Page")],
        2: [(2, 2, "Figure 159: Alpha Log Page")],
    }


def test_a_repeated_caption_over_tables_that_do_not_join_names_both(tmp_path):
    # the parts have other column edges (NVMe nests tables in cells)
    pages = [
        furniture(1)
        + [caption("Figure 41: Offset 14h: Controller Configuration")]
        + table(rows(0, FULL)),
        furniture(2)
        + [caption("Figure 41: Offset 14h: Controller Configuration")]
        + table(rows(FULL, 4), widths=[150, 80, 150])
        + [prose(2)],
    ]
    assert read(tmp_path, pages) == {
        1: [(1, 1, "Figure 41: Offset 14h: Controller Configuration")],
        2: [(2, 2, "Figure 41: Offset 14h: Controller Configuration")],
    }


# ---------------------------------------------------------------- AC-2


def test_a_figure_repeating_its_caption_on_each_page_joins(tmp_path):
    text = "Figure 123: Identify Namespace Data Structure"
    pages = [
        furniture(1) + [caption(text)] + table(rows(0, FULL)),
        furniture(2) + [caption(text)] + table(rows(FULL, FULL)),
        furniture(3) + [caption(text)] + table(rows(2 * FULL, 4)) + [prose(3)],
    ]
    one = [(1, 3, text)]
    assert read(tmp_path, pages) == {1: one, 2: one, 3: one}


def test_a_repeat_of_a_caption_two_pages_back_still_joins(tmp_path):
    # NVME-BASE 2.4 Figure 338: page 403's part fills the page from its
    # top with no room for the caption; page 404 repeats it again
    text = "Figure 338: Identify Controller Data Structure"
    wide = [100, 80, 120, 80]
    pages = [
        furniture(1) + [caption(text)] + table(rows(0, FULL)),
        furniture(2)
        + table([r + ["x"] for r in rows(FULL, FULL)], top=TOP + 24, widths=wide),
        furniture(3)
        + [caption(text)]
        + table([r + ["x"] for r in rows(2 * FULL, 4)], widths=wide)
        + [prose(3)],
    ]
    got = read(tmp_path, pages)
    assert got[1] == [(1, 1, text)]
    assert [(a, b) for a, b, _ in got[2]] == [(2, 3)]
    assert got[3] == got[2]


def test_a_repeat_differing_in_spacing_still_joins(tmp_path):
    pages = [
        furniture(1) + [caption("Figure 7: Status  Register")] + table(rows(0, FULL)),
        furniture(2)
        + [caption("Figure 7:  Status Register")]
        + table(rows(FULL, 4))
        + [prose(2)],
    ]
    got = read(tmp_path, pages)
    assert [(a, b) for a, b, _ in got[1]] == [(1, 2)]
    assert got[2] == got[1]


# ---------------------------------------------------------------- AC-3


def test_a_new_caption_on_the_next_page_stops_the_join(tmp_path):
    # NVME-BASE 2.4 pages 239-240: Figure 204 ends at the foot of one
    # page, Figure 205 starts at the top of the next with the same column
    # edges and repeats its caption on the page after
    pages = [
        furniture(1)
        + [caption("Figure 41: Offset 14h: Controller Configuration")]
        + table(rows(0, FULL)),
        furniture(2)
        + [caption("Figure 42: Offset 1Ch: Controller Status")]
        + table(rows(0, FULL)),
        furniture(3)
        + [caption("Figure 42: Offset 1Ch: Controller Status")]
        + table(rows(FULL, 4))
        + [prose(3)],
    ]
    first = (1, 1, "Figure 41: Offset 14h: Controller Configuration")
    second = (2, 3, "Figure 42: Offset 1Ch: Controller Status")
    assert read(tmp_path, pages) == {1: [first], 2: [second], 3: [second]}


# ---------------------------------------------------------------- AC-4


def test_a_repeated_caption_like_line_without_a_table_under_it_stays_furniture(
    tmp_path,
):
    # 60 pt over the table: past the caption window, inside the figure
    # rule's 200 pt, so taking it for body would name the table
    header = "Figure 2 - Platform overview"
    pages = [
        furniture(1) + [caption(header, gap=60)] + table(rows(0, 4)) + [prose(1)],
        furniture(2) + [caption(header, gap=60)] + table(rows(0, 4)) + [prose(2)],
    ]
    assert read(tmp_path, pages) == {1: [(1, 1, None)], 2: [(2, 2, None)]}
    pdf = tmp_path / "f.pdf"
    with T.Reader(pdf) as r:
        body = [ln.text for ln in r.body_lines(1)]
    assert header not in body
    assert "Example Specification, Revision 2.4" not in body
    assert "1" not in body


def test_running_headers_and_page_numbers_still_let_a_table_join(tmp_path):
    pages = [
        furniture(1) + table(rows(0, FULL)),
        furniture(2) + table(rows(FULL, 4)) + [prose(2)],
    ]
    got = read(tmp_path, pages)
    assert got[1] == got[2] == [(1, 2, None)]


# ---------------------------------------------------------------- AC-6


def test_the_one_wrong_join_of_the_survey_is_a_recorded_limit():
    # IPMI-UPDATE page 436 holds a stray fragment of Table 30-2 and page
    # 437 repeats the caption over the whole table: the rule joins them
    limits = load_catalog().get("IPMI-UPDATE").limits
    for words in ("Table 30-2", "Page 436", "page 437", "twice"):
        assert words in limits, words
