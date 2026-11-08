"""Acceptance tests for the caption-repeated-on-each-page fix.

A caption-like line with a table starting within 40 pt under it is not
page furniture (AC-1); a table still joins across a page break when the
only body lines above the next page's table repeat a caption-like line
from the page before or the two before that (AC-2); a different caption
there stops the join (AC-3); other furniture and a caption-like line with
no table under it are as before (AC-4); TABLES_VERSION is 10 (AC-5); the
catalog limits say what AC-7 asks of them.

Each page is built from scratch here: a running header and a page number
on every page, a table whose top edge is at a fixed height, and a caption
either 12 pt or 60 pt over it.
"""

import json

import pytest

from bmc_toolkit.spec import tables as T
from bmc_toolkit.spec.catalog import load_catalog
from tests import pdfgen
from tests.test_tables import ruled_table

pytest.importorskip("pdfplumber")

TABLE_TOP = 680  # PDF points from the page's foot
ROW_H = 16
COLS = [100, 80, 200]
OTHER_COLS = [150, 80, 150]
# 38 rows of 16 pt run from 680 down to 72: nothing lies under the table
FULL = 38
HEADER = "Example Specification, Revision 2.4"


def header_and_number(n):
    return [(72, 750, HEADER), (300, 40, str(n))]


def grid(first, count, top=TABLE_TOP, widths=COLS):
    cells = [[f"{first + i:02d}h", "RO", f"Field {first + i}"] for i in range(count)]
    return ruled_table(72, top, widths, [ROW_H] * count, cells)


def over(text, gap=12, top=TABLE_TOP):
    """A text line whose top lies ``gap`` points over the table's top edge
    (a 10 pt Helvetica line's top is about 8 pt over its baseline)."""
    return (72, top + gap - 8, text)


ORDINALS = ["first", "second", "third", "fourth", "fifth"]


def tail(n):
    """Prose under a short table, in other words on every page (digits
    alone would not tell it from furniture): the table is not the last
    thing on its page."""
    return (72, 120, f"The {ORDINALS[n - 1]} part ends here.")


def read(tmp_path, pages):
    pdf = pdfgen.write_pdf(tmp_path / "doc.pdf", pages)
    with T.Reader(pdf) as r:
        return {
            n: [(t.first, t.last, t.caption) for t in r.logical_tables(n)]
            for n in range(1, len(pages) + 1)
        }


# --------------------------------------------------------------- AC-1


def test_ac1_captions_at_one_height_differing_in_numbers_name_each_table(tmp_path):
    # the same words, digits aside, at the same height on facing pages:
    # the running-header rule's pattern, but each has a table under it
    first, second = "Figure 157: Alpha Log Page", "Figure 159: Alpha Log Page"
    pages = [
        header_and_number(1) + [over(first)] + grid(0, 4) + [tail(1)],
        header_and_number(2) + [over(second)] + grid(0, 4) + [tail(2)],
    ]
    assert read(tmp_path, pages) == {
        1: [(1, 1, "Figure 157: Alpha Log Page")],
        2: [(2, 2, "Figure 159: Alpha Log Page")],
    }


def test_ac1_a_caption_repeated_over_parts_with_other_columns_names_both(tmp_path):
    text = "Figure 41: Offset 14h: Controller Configuration"
    pages = [
        header_and_number(1) + [over(text)] + grid(0, FULL),
        header_and_number(2)
        + [over(text)]
        + grid(FULL, 4, widths=OTHER_COLS)
        + [tail(2)],
    ]
    assert read(tmp_path, pages) == {1: [(1, 1, text)], 2: [(2, 2, text)]}


def test_ac1_the_caption_is_body_while_header_and_page_number_stay_furniture(tmp_path):
    text = "Table 12: Status Codes"
    pages = [
        header_and_number(1) + [over(text)] + grid(0, 4) + [tail(1)],
        header_and_number(2) + [over(text)] + grid(0, 4) + [tail(2)],
    ]
    pdf = pdfgen.write_pdf(tmp_path / "doc.pdf", pages)
    with T.Reader(pdf) as r:
        for n in (1, 2):
            body = [ln.text for ln in r.body_lines(n)]
            assert text in body, n
            assert HEADER not in body, n
            assert str(n) not in body, n


# --------------------------------------------------------------- AC-2


def test_ac2_a_figure_captioned_on_each_of_three_pages_is_one_table(tmp_path):
    text = "Figure 123: Identify Namespace Data Structure"
    pages = [
        header_and_number(1) + [over(text)] + grid(0, FULL),
        header_and_number(2) + [over(text)] + grid(FULL, FULL),
        header_and_number(3) + [over(text)] + grid(2 * FULL, 4) + [tail(3)],
    ]
    whole = [(1, 3, text)]
    assert read(tmp_path, pages) == {1: whole, 2: whole, 3: whole}


def test_ac2_a_repeat_of_the_caption_two_pages_before_the_break_joins(tmp_path):
    # NVMe Figure 338: the middle page fills from its top with no caption,
    # the page after repeats the caption from two pages back
    text = "Figure 338: Identify Controller Data Structure"
    pages = [
        header_and_number(1) + [over(text)] + grid(0, FULL),
        header_and_number(2) + grid(FULL, FULL, top=TABLE_TOP + 20),
        header_and_number(3) + [over(text)] + grid(2 * FULL, 4) + [tail(3)],
    ]
    whole = [(1, 3, text)]
    assert read(tmp_path, pages) == {1: whole, 2: whole, 3: whole}


def test_ac2_the_window_reaches_the_two_pages_before_the_page_before(tmp_path):
    # caption on page 1, none on 2 and 3, repeated on 4: page 4 joins
    text = "Figure 338: Identify Controller Data Structure"
    pages = [
        header_and_number(1) + [over(text)] + grid(0, FULL),
        header_and_number(2) + grid(FULL, FULL, top=TABLE_TOP + 20),
        header_and_number(3) + grid(2 * FULL, FULL, top=TABLE_TOP + 20),
        header_and_number(4) + [over(text)] + grid(3 * FULL, 4) + [tail(4)],
    ]
    whole = [(1, 4, text)]
    assert read(tmp_path, pages) == {n: whole for n in range(1, 5)}


def test_ac2_a_repeat_further_back_than_the_window_does_not_join(tmp_path):
    # caption on page 1, none on 2, 3 and 4, repeated on 5: the window is
    # the page before plus two, so page 5 starts a table of its own
    text = "Figure 338: Identify Controller Data Structure"
    pages = [
        header_and_number(1) + [over(text)] + grid(0, FULL),
        header_and_number(2) + grid(FULL, FULL, top=TABLE_TOP + 20),
        header_and_number(3) + grid(2 * FULL, FULL, top=TABLE_TOP + 20),
        header_and_number(4) + grid(3 * FULL, FULL, top=TABLE_TOP + 20),
        header_and_number(5) + [over(text)] + grid(4 * FULL, 4) + [tail(5)],
    ]
    got = read(tmp_path, pages)
    assert got[1] == got[4] == [(1, 4, text)]
    assert got[5] == [(5, 5, text)]


def test_ac2_a_repeat_that_differs_in_whitespace_only_joins(tmp_path):
    pages = [
        header_and_number(1) + [over("Figure 7:  Status Register")] + grid(0, FULL),
        header_and_number(2)
        + [over("Figure 7: Status  Register")]
        + grid(FULL, 4)
        + [tail(2)],
    ]
    got = read(tmp_path, pages)
    assert [(a, b) for a, b, _ in got[1]] == [(1, 2)]
    assert got[2] == got[1]
    assert got[1][0][2] == "Figure 7: Status Register"


# --------------------------------------------------------------- AC-3


def test_ac3_a_caption_that_repeats_nothing_before_it_stops_the_join(tmp_path):
    # two figures with the same column edges back to back, the second's
    # caption at the height the first's stood on the page before
    pages = [
        header_and_number(1) + [over("Table 1: Alpha")] + grid(0, FULL),
        header_and_number(2) + [over("Table 2: Beta")] + grid(0, 4) + [tail(2)],
    ]
    assert read(tmp_path, pages) == {
        1: [(1, 1, "Table 1: Alpha")],
        2: [(2, 2, "Table 2: Beta")],
    }


def test_ac3_the_new_figure_then_joins_its_own_repeated_caption(tmp_path):
    # NVMe Figures 204 and 205: the second starts at the top of the next
    # page and repeats its caption on the page after
    first = "Figure 204: Offset 14h: Controller Configuration"
    second = "Figure 205: Offset 1Ch: Controller Status"
    pages = [
        header_and_number(1) + [over(first)] + grid(0, FULL),
        header_and_number(2) + [over(second)] + grid(0, FULL),
        header_and_number(3) + [over(second)] + grid(FULL, 4) + [tail(3)],
    ]
    assert read(tmp_path, pages) == {
        1: [(1, 1, first)],
        2: [(2, 3, second)],
        3: [(2, 3, second)],
    }


def test_ac3_a_repeated_caption_beside_a_prose_line_still_stops_the_join(tmp_path):
    # any other body line above the next page's table stops it, as before
    text = "Figure 9: Command Dword 10"
    pages = [
        header_and_number(1) + [over(text)] + grid(0, FULL),
        header_and_number(2)
        + [over("This paragraph was moved here by a page break.", gap=28), over(text)]
        + grid(FULL, 4)
        + [tail(2)],
    ]
    got = read(tmp_path, pages)
    assert got[1] == [(1, 1, text)]
    assert got[2] == [(2, 2, text)]


# --------------------------------------------------------------- AC-4


def test_ac4_a_repeated_caption_like_line_with_no_table_within_40pt_stays_furniture(
    tmp_path,
):
    text = "Figure 2 - Platform overview"
    pages = [
        header_and_number(1) + [over(text, gap=60)] + grid(0, 4) + [tail(1)],
        header_and_number(2) + [over(text, gap=60)] + grid(0, 4) + [tail(2)],
    ]
    assert read(tmp_path, pages) == {1: [(1, 1, None)], 2: [(2, 2, None)]}
    pdf = tmp_path / "doc.pdf"
    with T.Reader(pdf) as r:
        assert text not in [ln.text for ln in r.body_lines(1)]


def test_ac4_a_running_header_right_over_a_table_is_still_furniture(tmp_path):
    # the header stands 12 pt over the table at the top of each page but
    # does not read like a caption, so the join and the caption are as before
    pages = [
        [(72, TABLE_TOP + 4, HEADER), (300, 40, "1")] + grid(0, FULL),
        [(72, TABLE_TOP + 4, HEADER), (300, 40, "2")] + grid(FULL, 4) + [tail(2)],
    ]
    got = read(tmp_path, pages)
    assert got[1] == got[2] == [(1, 2, None)]


def test_ac4_headers_footers_and_page_numbers_still_let_a_table_join(tmp_path):
    pages = [
        header_and_number(1) + grid(0, FULL),
        header_and_number(2) + grid(FULL, 4) + [tail(2)],
    ]
    got = read(tmp_path, pages)
    assert got[1] == got[2] == [(1, 2, None)]


def test_ac4_a_body_line_above_the_next_pages_table_still_stops_the_join(tmp_path):
    pages = [
        header_and_number(1) + grid(0, FULL),
        header_and_number(2)
        + [over("The following values are reserved.")]
        + grid(FULL, 4)
        + [tail(2)],
    ]
    got = read(tmp_path, pages)
    assert got[1] == [(1, 1, None)]
    assert got[2] == [(2, 2, None)]


# --------------------------------------------------------------- AC-5


def test_ac5_tables_version_is_10_and_a_version_9_store_is_read_again(tmp_path):
    assert T.TABLES_VERSION == 10
    text = "Table 3: Codes"
    page = header_and_number(1) + [over(text)] + grid(0, 3) + [tail(1)]
    pdf = pdfgen.write_pdf(tmp_path / "doc.pdf", [page])
    with T.Reader(pdf) as r:
        found = r.logical_tables(1)
    vdir = tmp_path / "v"
    vdir.mkdir()
    path = T.store(vdir, [1], found)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tables_version"] == 10
    assert T.stored_for_page(vdir, 1) is not None
    data["tables_version"] = 9
    path.write_text(json.dumps(data), encoding="utf-8")
    assert T.stored_for_page(vdir, 1) is None


# --------------------------------------------------------------- AC-7 (catalog limits)


def test_ac7_the_catalog_limits_record_what_is_left():
    cat = load_catalog()
    nvm = cat.get("NVME-NVM").limits
    about_123 = [s for s in nvm.split(". ") if "Figure 123" in s]
    assert about_123, nvm
    assert all("`-`" not in s for s in about_123), nvm
    ipmi = cat.get("IPMI-UPDATE").limits
    for words in ("Table 30-2", "436", "437"):
        assert words in ipmi, words
