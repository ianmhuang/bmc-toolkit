"""Review tests for the caption taken from the foot of the page before
(fix/caption-on-page-before).

The AC: a table first on its page with nothing above it, and no caption by
the window or the figure rule, takes the last body line of the page before
when that line is a `Table` caption below every table there, margin line
number dropped (AC-1); a `Figure` line, a `Table` line that is not last, a
`Table` line over its own table, a body line above the table, a table
second on its page and a table carrying on one from the page before are
not taken (AC-2); a caption found by the window or the figure rule is kept
(AC-3); a repeated caption with another margin number still joins (AC-4);
only a line with a table within 40 pt under it is a caption a repeat may
match (AC-5); TABLES_VERSION is 11 and a version 10 store is not served
(AC-6); DSP2058 records no limit for Table 1 (AC-8).

Geometry: pdfgen places text by its baseline in PDF points, origin
bottom-left; pdfplumber puts a 10 pt Helvetica line's top about 8 pt
above the baseline. Every page carries a running header and a page
number; a table's top edge sits at TABLE_TOP unless said otherwise.
"""

import json

import pytest

from bmc_toolkit.spec import tables as T
from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok
from tests.test_tables import ruled_table

pytest.importorskip("pdfplumber")

ASCENT = 8
TABLE_TOP = 680
ROW_H = 16
COLS = [100, 80, 200]
OTHER_COLS = [150, 80, 150]
FULL = 38  # rows of 16 pt from 680 down to 72: nothing lies under the table
HEADER = "Example Specification, Revision 2.4"
URL = "https://example.test/DSP0236_1.3.3.pdf"
ORDINALS = ["first", "second", "third", "fourth"]

IPMI = "Table 21-4, Get Command Sub-function Support Command"
DMTF = "Table 1 - Threat modeling assessment and mitigations"


def header_and_number(n):
    return [(72, 750, HEADER), (300, 40, str(n))]


def grid(first, count, top=TABLE_TOP, widths=COLS, cells=None):
    if cells is None:
        cells = [
            [f"{first + i:02d}h", "RO", f"Field {first + i}"] for i in range(count)
        ]
    return ruled_table(72, top, widths, [ROW_H] * len(cells), cells)


def over(text, gap=12, top=TABLE_TOP):
    """A text line whose top lies ``gap`` points over a table top."""
    return (72, top + gap - ASCENT, text)


def under(text, gap, top=TABLE_TOP, count=4):
    """A text line whose top lies ``gap`` points under the bottom of a
    ``count``-row table at ``top``."""
    return (72, top - count * ROW_H - gap - ASCENT, text)


def tail(n):
    """Prose under a short table, in other words on each page."""
    return (72, 120, f"The {ORDINALS[n - 1]} part ends here.")


def foot(*texts, y=300):
    """A paragraph whose last lines are ``texts``, the last at baseline
    ``y``: the page's text ends there, with blank paper below."""
    lines = ["The command is described in the table that follows.", *texts]
    return [(72, y + 14 * (len(lines) - 1 - i), text) for i, text in enumerate(lines)]


def read(tmp_path, pages):
    pdf = pdfgen.write_pdf(tmp_path / "doc.pdf", pages)
    with T.Reader(pdf) as r:
        return {
            n: [(t.first, t.last, t.caption) for t in r.logical_tables(n)]
            for n in range(1, len(pages) + 1)
        }


def two_pages(tmp_path, page_1_text, above=(), widths=COLS):
    """Page 1 ends with ``page_1_text``; page 2 holds ``above`` over a
    four-row table and prose under it. The tables found on page 2."""
    pages = [
        header_and_number(1) + foot(*page_1_text),
        header_and_number(2) + list(above) + grid(0, 4, widths=widths) + [tail(2)],
    ]
    return read(tmp_path, pages)[2]


# --------------------------------------------------------------- AC-1


def test_ac1_a_table_caption_ending_the_page_before_names_the_table(tmp_path):
    # IPMI Table 21-4: the caption is the last line of one page, the
    # table the first thing on the next
    assert two_pages(tmp_path, [IPMI]) == [(2, 2, IPMI)]


def test_ac1_a_margin_line_number_in_front_of_the_caption_is_dropped(tmp_path):
    # DSP2058 Table 1: DMTF prints a line number in the margin
    assert two_pages(tmp_path, [f"61 {DMTF}"]) == [(2, 2, DMTF)]


def test_ac1_the_caption_lies_below_a_table_of_its_own_page(tmp_path):
    # page 1 holds a captioned table at its top, prose, then the caption
    # of the table that did not fit; page 2's table is not a part of
    # page 1's (prose lies under that one) and takes the foot caption
    pages = [
        header_and_number(1)
        + [over("Table 2 - First")]
        + grid(0, 4)
        + foot("Table 3 - Second"),
        header_and_number(2) + grid(0, 4) + [tail(2)],
    ]
    assert read(tmp_path, pages) == {
        1: [(1, 1, "Table 2 - First")],
        2: [(2, 2, "Table 3 - Second")],
    }


def test_ac1_a_table_over_two_pages_takes_the_caption_once(tmp_path):
    # the caption ends page 1, the table fills page 2 and ends on page 3:
    # one Logical Table named by the caption, page 3's part asks for none
    pages = [
        header_and_number(1) + foot("Table 5 - Register map"),
        header_and_number(2) + grid(0, FULL),
        header_and_number(3) + grid(FULL, 4) + [tail(3)],
    ]
    got = read(tmp_path, pages)
    assert got[2] == got[3] == [(2, 3, "Table 5 - Register map")]
    assert got[1] == []


def test_ac1_the_table_command_prints_the_caption_and_stores_it(
    catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    pages = [
        header_and_number(1) + foot(IPMI),
        header_and_number(2) + grid(0, 4) + [tail(2)],
    ]
    pdf = pdfgen.write_pdf(tmp_path / "doc.pdf", pages)
    scripted.responses[URL] = ok(pdf.read_bytes())
    code = main(["--catalog", str(catalog_file), "fetch", "DSP0236"])
    out = capsys.readouterr().out
    assert code == 0, out
    code = main(["--catalog", str(catalog_file), "table", "DSP0236", "--page", "2"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert [ln for ln in out.splitlines() if ln.startswith("table: ")] == [
        f"table: {IPMI} | ruled | page 2 | 3 columns | 4 rows"
    ]
    store = library.specs / "mctp" / "DSP0236" / "1.3.3" / T.TABLES_NAME
    data = json.loads(store.read_text("utf-8"))
    assert data["tables_version"] == 11
    assert [t["caption"] for t in data["tables"]] == [IPMI]


# --------------------------------------------------------------- AC-2


def test_ac2_a_figure_caption_ending_the_page_before_is_not_taken(tmp_path):
    # SMBus 3.3.1 page 17 ends with its figure's caption under the drawing
    assert two_pages(tmp_path, ["Figure 5: Timeout intervals"]) == [(2, 2, None)]


def test_ac2_a_table_line_followed_by_another_line_is_not_taken(tmp_path):
    got = two_pages(
        tmp_path, ["Table 7 - Earlier", "Its fields follow on the next page."]
    )
    assert got == [(2, 2, None)]


def test_ac2_a_prose_line_ending_the_page_before_is_not_taken(tmp_path):
    got = two_pages(tmp_path, ["The fields of the command are listed below."])
    assert got == [(2, 2, None)]


def test_ac2_a_table_line_over_its_own_table_on_the_page_before_is_not_taken(
    tmp_path,
):
    # page 1's caption names the table under it, which ends that page;
    # page 2's table has other column edges, so it is not a part of it
    pages = [
        header_and_number(1)
        + [over("Table 8 - Own table", top=400)]
        + grid(0, 4, top=400),
        header_and_number(2) + grid(0, 4, widths=OTHER_COLS) + [tail(2)],
    ]
    assert read(tmp_path, pages) == {
        1: [(1, 1, "Table 8 - Own table")],
        2: [(2, 2, None)],
    }


def test_ac2_a_row_starting_with_table_inside_the_last_table_is_not_taken(tmp_path):
    # the last body line of page 1 is a row of its table, not a caption
    rows = [["Name", "Code", "Meaning"], ["Table 3 ref", "02h", "see"]]
    pages = [
        header_and_number(1) + grid(0, 2, cells=rows),
        header_and_number(2) + grid(0, 4, widths=OTHER_COLS) + [tail(2)],
    ]
    assert read(tmp_path, pages)[2] == [(2, 2, None)]


def test_ac2_a_body_line_above_the_table_on_its_own_page_stops_the_look_back(
    tmp_path,
):
    got = two_pages(
        tmp_path, ["Table 9 - Before"], [over("The values are listed below.", gap=20)]
    )
    assert got == [(2, 2, None)]


def test_ac2_only_the_first_table_on_the_page_looks_back(tmp_path):
    pages = [
        header_and_number(1) + foot("Table 10 - Before"),
        header_and_number(2)
        + grid(0, 2)
        + grid(0, 2, top=TABLE_TOP - 200, widths=OTHER_COLS)
        + [tail(2)],
    ]
    got = read(tmp_path, pages)[2]
    assert [(a, b) for a, b, _ in got] == [(2, 2), (2, 2)]
    assert [c for _, _, c in got] == ["Table 10 - Before", None]


def test_ac2_a_table_carrying_on_from_the_page_before_keeps_no_caption(tmp_path):
    # page 1 holds a caption-less table to its foot; page 2 carries it on
    # under the running header, so the join stands and no caption appears
    pages = [
        header_and_number(1) + grid(0, FULL),
        header_and_number(2) + grid(FULL, 4) + [tail(2)],
    ]
    got = read(tmp_path, pages)
    assert got[1] == got[2] == [(1, 2, None)]


def test_ac2_a_first_page_table_has_no_page_before(tmp_path):
    page = header_and_number(1) + grid(0, 4) + [tail(1)]
    assert read(tmp_path, [page]) == {1: [(1, 1, None)]}


# --------------------------------------------------------------- AC-3


def test_ac3_a_caption_in_the_window_is_kept_over_the_foot_line(tmp_path):
    got = two_pages(tmp_path, ["Table 3 - Other"], [over("Table 4 - Own")])
    assert got == [(2, 2, "Table 4 - Own")]


def test_ac3_a_caption_walked_to_past_a_column_line_is_kept(tmp_path):
    got = two_pages(
        tmp_path,
        ["Table 3 - Other"],
        [over("Table 22-, Get Self Test Results Command", gap=26), over("byte data")],
    )
    assert got == [(2, 2, "Table 22-, Get Self Test Results Command")]


def test_ac3_a_figure_caption_under_the_table_is_kept_over_the_foot_line(tmp_path):
    pages = [
        header_and_number(1) + foot("Table 3 - Other"),
        header_and_number(2)
        + grid(0, 4)
        + [under("Figure 2 - Layout", 30), tail(2)],
    ]
    assert read(tmp_path, pages)[2] == [(2, 2, "Figure 2 - Layout")]


# --------------------------------------------------------------- AC-4


def test_ac4_a_repeat_with_another_margin_number_still_joins(tmp_path):
    pages = [
        header_and_number(1) + [over("12 Figure 7: Status")] + grid(0, FULL),
        header_and_number(2)
        + [over("40 Figure 7: Status")]
        + grid(FULL, 4)
        + [tail(2)],
    ]
    got = read(tmp_path, pages)
    assert got[1] == got[2] == [(1, 2, "Figure 7: Status")]


def test_ac4_a_repeat_with_a_margin_number_on_one_page_only_still_joins(tmp_path):
    pages = [
        header_and_number(1) + [over("Figure 7: Status")] + grid(0, FULL),
        header_and_number(2)
        + [over("40 Figure 7: Status")]
        + grid(FULL, 4)
        + [tail(2)],
    ]
    got = read(tmp_path, pages)
    assert got[1] == got[2] == [(1, 2, "Figure 7: Status")]


def test_ac4_another_caption_behind_a_margin_number_still_stops_the_join(tmp_path):
    pages = [
        header_and_number(1) + [over("12 Figure 7: Status")] + grid(0, FULL),
        header_and_number(2)
        + [over("40 Figure 8: Control")]
        + grid(0, 4)
        + [tail(2)],
    ]
    assert read(tmp_path, pages) == {
        1: [(1, 1, "Figure 7: Status")],
        2: [(2, 2, "Figure 8: Control")],
    }


# --------------------------------------------------------------- AC-5


def test_ac5_a_caption_like_line_with_no_table_under_it_is_no_repeat(tmp_path):
    # page 1: a drawing's caption 250 pt over the table (past the caption
    # window and the figure rule), then a table to the page's foot; page
    # 2: the same words over a table with the same column edges. The
    # line on page 1 captions no table, so page 2's table is its own
    low = 430
    depth = (low - 72) // ROW_H
    pages = [
        header_and_number(1)
        + [over("Figure 7: Status", gap=250, top=low)]
        + grid(0, depth, top=low),
        header_and_number(2)
        + [over("Figure 7: Status")]
        + grid(depth, 4)
        + [tail(2)],
    ]
    got = read(tmp_path, pages)
    assert [(a, b) for a, b, _ in got[1]] == [(1, 1)]
    assert got[2] == [(2, 2, "Figure 7: Status")]


def test_ac5_a_caption_with_its_table_under_it_is_still_a_repeat(tmp_path):
    text = "Figure 123: Identify Namespace Data Structure"
    pages = [
        header_and_number(1) + [over(text)] + grid(0, FULL),
        header_and_number(2) + [over(text)] + grid(FULL, 4) + [tail(2)],
    ]
    got = read(tmp_path, pages)
    assert got[1] == got[2] == [(1, 2, text)]


# --------------------------------------------------------------- AC-6


def test_ac6_tables_version_is_11_and_a_version_10_store_is_read_again(tmp_path):
    assert T.TABLES_VERSION == 11
    pages = [
        header_and_number(1) + foot(IPMI),
        header_and_number(2) + grid(0, 4) + [tail(2)],
    ]
    pdf = pdfgen.write_pdf(tmp_path / "doc.pdf", pages)
    with T.Reader(pdf) as r:
        found = r.logical_tables(2)
    vdir = tmp_path / "v"
    vdir.mkdir()
    path = T.store(vdir, [2], found)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tables_version"] == 11
    assert [t["caption"] for t in data["tables"]] == [IPMI]
    assert T.stored_for_page(vdir, 2) is not None
    # what version 10 stored for this page: no caption
    data["tables_version"] = 10
    for t in data["tables"]:
        t["caption"] = None
    path.write_text(json.dumps(data), encoding="utf-8", newline="")
    assert T.stored_for_page(vdir, 2) is None


# --------------------------------------------------------------- AC-8


def test_ac8_dsp2058_records_no_limit_for_table_1():
    limits = load_catalog().get("DSP2058").limits
    assert "Table 1" not in limits
    assert "page 14" not in limits
