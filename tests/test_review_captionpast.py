"""Review tests for the caption taken past the lines between it and the
table (fix/caption-past-header-line).

The AC: the caption is the nearest line within 40 pt above the table
that reads like one, past lines that do not (AC-1); a caption-like line
with another table between is not taken and the table falls back to the
Figure rule, else `-` (AC-2); the window does not grow (AC-3); where the
nearest line is a caption, or no line in the window is one, nothing
changes (AC-4); TABLES_VERSION 9 retires every version 8 store (AC-5).

Geometry: pdfgen places text by its baseline in PDF points, origin
bottom-left; pdfplumber puts a 10 pt Helvetica line's top about 8 pt
above the baseline, so a line whose top lies ``gap`` points over a table
top has its baseline at ``top + gap - 8``."""

import json

import pytest

from bmc_toolkit.spec import tables as T
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok
from tests.test_tables import WIDTHS, furniture, ruled_table

pytest.importorskip("pdfplumber")

ASCENT = 8
TOP = 600
HEADER = ["byte", "data field", "meaning"]
ROWS = [HEADER, ["1", "Device ID", "see below"], ["2", "Revision", "bits"]]
URL = "https://example.test/DSP0236_1.3.3.pdf"


def table(top=TOP, rows=ROWS, x=72):
    return ruled_table(x, top, WIDTHS, [16] * len(rows), rows)


def over(gap, text, top=TOP):
    """A text line whose top lies ``gap`` points above a table top."""
    return (72, top + gap - ASCENT, text)


def under(gap, text, bottom):
    """A text line whose top lies ``gap`` points below a table bottom."""
    return (72, bottom - gap - ASCENT, text)


def read(tmp_path, pages, name="c.pdf"):
    pdf = pdfgen.write_pdf(tmp_path / name, pages)
    with T.Reader(pdf) as r:
        return [r.logical_tables(n) for n in range(1, len(pages) + 1)]


def captions(tmp_path, pages):
    return [[t.caption for t in found] for found in read(tmp_path, pages)]


# ------------------------------------------------------------------ AC-1


def test_ac1_the_caption_over_an_ipmi_column_name_line_is_taken(tmp_path):
    page = table() + [
        over(26, "Table 22-, Get Self Test Results Command"),
        over(12, "byte data field"),
    ]
    assert captions(tmp_path, [page]) == [["Table 22-, Get Self Test Results Command"]]


def test_ac1_a_margin_line_number_is_dropped_from_the_caption_taken_past(tmp_path):
    page = table() + [
        over(26, "415 Table 5 - Capability Descriptor"),
        over(12, "Values"),
    ]
    assert captions(tmp_path, [page]) == [["Table 5 - Capability Descriptor"]]


def test_ac1_two_note_lines_between_are_walked_past_inside_the_window(tmp_path):
    page = table() + [
        over(36, "Table 14. Status Register Bits"),
        over(24, "Note: bits not listed are reserved and"),
        over(12, "shall be written as zero."),
    ]
    assert captions(tmp_path, [page]) == [["Table 14. Status Register Bits"]]


def test_ac1_a_figure_line_is_taken_past_a_column_name_line_too(tmp_path):
    # the existing `Table ...` / `Figure ...` rule applies to the line found
    page = table() + [over(26, "Figure 12 - Request Format"), over(12, "byte data field")]
    assert captions(tmp_path, [page]) == [["Figure 12 - Request Format"]]


def test_ac1_only_the_first_part_of_a_continued_table_gives_the_caption(tmp_path):
    # the walk happens on the first page; page 2 carries on the table under
    # the running header only, and the Logical Table keeps page 1's caption
    page1 = furniture(1) + [
        over(26, "Table 22-, Get Self Test Results Command", top=200),
        over(12, "byte data field", top=200),
        *ruled_table(72, 200, WIDTHS, [16] * 2, ROWS[:2]),
    ]
    page2 = furniture(2) + ruled_table(72, 740, WIDTHS, [16] * 2, [HEADER, ROWS[2]])
    found = read(tmp_path, [page1, page2])
    assert [(t.first, t.last, t.caption) for t in found[1]] == [
        (1, 2, "Table 22-, Get Self Test Results Command")
    ]


# ------------------------------------------------------------------ AC-2


def test_ac2_a_captioned_table_right_over_an_uncaptioned_one_keeps_its_caption(
    tmp_path,
):
    first_top = 626
    page = (
        table(top=first_top, rows=[["X", "Y", "Z"]])
        + [over(12, "Table 1 - First", top=first_top)]
        + table()
    )
    assert captions(tmp_path, [page]) == [["Table 1 - First", None]]


def test_ac2_a_cell_line_of_the_table_above_that_starts_with_table_is_not_taken(
    tmp_path,
):
    # the nearest line over the second table is the last row of the first;
    # it starts with `Table` and a table (the first) lies between
    first_top = 626
    page = (
        table(top=first_top, rows=[["Table 3 ref", "02h", "see"]])
        + [over(12, "Table 1 - First", top=first_top)]
        + table()
    )
    assert captions(tmp_path, [page]) == [["Table 1 - First", None]]


def test_ac2_with_a_table_between_the_figure_rule_still_decides(tmp_path):
    first_top = 626
    bottom = TOP - 16 * len(ROWS)
    page = (
        table(top=first_top, rows=[["X", "Y", "Z"]])
        + [over(12, "Table 1 - First", top=first_top)]
        + table()
        + [under(30, "Figure 7 - Register layout", bottom)]
    )
    assert captions(tmp_path, [page]) == [["Table 1 - First", "Figure 7 - Register layout"]]


# ------------------------------------------------------------------ AC-3


def test_ac3_a_caption_line_whose_top_lies_beyond_40_points_is_not_taken(tmp_path):
    pages = [
        table() + [over(46, "Table 8 - Too far"), over(12, "byte data field")],
        table() + [over(46, "Table 8 - Too far")],
        table()
        + [
            over(46, "Table 8 - Too far"),
            over(28, "Note: the first byte is the"),
            over(12, "completion code."),
        ],
    ]
    assert captions(tmp_path, pages) == [[None], [None], [None]]


# ------------------------------------------------------------------ AC-4


def test_ac4_the_nearest_caption_line_is_still_the_one_taken(tmp_path):
    pages = [
        table() + [over(12, "Table 7 - Near")],
        # round 1 validation: distinct words per page, or the same line at
        # the same height on the next page reads as a running header
        table() + [over(26, "Table 6 - Earlier"), over(12, "Table 8 - Second one")],
        table() + [over(12, "Figure 3 - Also a caption")],
    ]
    assert captions(tmp_path, pages) == [
        ["Table 7 - Near"],
        ["Table 8 - Second one"],
        ["Figure 3 - Also a caption"],
    ]


def test_ac4_prose_only_in_the_window_leaves_the_figure_rule_to_decide(tmp_path):
    bottom = TOP - 16 * len(ROWS)
    with_figure = table() + [
        over(26, "The fields are described below."),
        over(12, "byte data field"),
        under(30, "Figure 3 - Packet format", bottom),
    ]
    without = table() + [
        over(26, "The fields are described below."),
        over(12, "byte data field"),
    ]
    assert captions(tmp_path, [with_figure, without]) == [
        ["Figure 3 - Packet format"],
        [None],
    ]


# ------------------------------------------------- round 1 F1 (AC-2, AC-4)
# Past the nearest line, a `Figure` line is a caption only when the figure
# rule's own filter accepts it: "Figure 3 shows ..." is prose, not a caption.
# On develop that line never reached the caption rule (it was not the
# nearest) and the figure rule's filter rejected it, so the table printed
# `-`; the walk must not take it either.


def test_f1_figure_prose_past_the_nearest_line_gives_no_caption(tmp_path):
    pages = [
        table()
        + [over(26, "Figure 3 shows the fields below."), over(12, "byte data field")],
        table()
        + [
            over(36, "Figure 101."),
            over(24, "Note: bits not listed are reserved and"),
            over(12, "shall be written as zero."),
        ],
        table() + [over(26, "Figure 7 lists the bytes:"), over(12, "Values")],
    ]
    assert captions(tmp_path, pages) == [[None], [None], [None]]


def test_f1_the_walk_skips_figure_prose_and_takes_a_caption_further_up(tmp_path):
    page = table() + [
        over(38, "Figure 4 - Packet format"),
        over(25, "Figure 4 shows the fields below."),
        over(12, "byte data field"),
    ]
    assert captions(tmp_path, [page]) == [["Figure 4 - Packet format"]]


def test_f1_figure_prose_past_the_nearest_line_leaves_the_figure_rule_to_decide(
    tmp_path,
):
    # the prose line is skipped, the figure rule then finds the caption below
    bottom = TOP - 16 * len(ROWS)
    page = table() + [
        over(26, "Figure 3 shows the fields below."),
        over(12, "byte data field"),
        under(30, "Figure 3 - Packet format", bottom),
    ]
    assert captions(tmp_path, [page]) == [["Figure 3 - Packet format"]]


def test_f1_a_figure_caption_with_a_margin_line_number_past_the_nearest_line(
    tmp_path,
):
    # the filter sees the whole line, margin number included, and still
    # accepts a real caption; the margin number is dropped as for `Table`
    page = table() + [over(26, "512 Figure 9 - Request Format"), over(12, "Values")]
    assert captions(tmp_path, [page]) == [["Figure 9 - Request Format"]]


# ------------------------------------------------------------------ AC-5


def test_ac5_tables_version_is_9_and_a_version_8_store_is_not_served(tmp_path):
    assert T.TABLES_VERSION == 12
    page = table() + [
        over(26, "Table 22-, Get Self Test Results Command"),
        over(12, "byte data field"),
    ]
    (found,) = read(tmp_path, [page])
    vdir = tmp_path / "v"
    vdir.mkdir()
    T.store(vdir, [1], found)
    path = vdir / T.TABLES_NAME
    data = json.loads(path.read_text("utf-8"))
    assert data["tables_version"] == 12
    assert [t["caption"] for t in data["tables"]] == [
        "Table 22-, Get Self Test Results Command"
    ]
    assert T.stored_for_page(vdir, 1) is not None

    # what version 8 stored for this page: no caption
    data["tables_version"] = 8
    for t in data["tables"]:
        t["caption"] = None
    path.write_text(json.dumps(data), "utf-8", newline="")
    assert T.stored_for_page(vdir, 1) is None  # read again, not trusted

    T.store(vdir, [1], found)
    data = json.loads(path.read_text("utf-8"))
    assert data["tables_version"] == 12
    assert data["pages_done"] == [1]
    (stored,) = T.stored_for_page(vdir, 1)
    assert stored.caption == "Table 22-, Get Self Test Results Command"


# ------------------------------------------------------- the table command


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def table_lines(out: str) -> list[str]:
    return [ln for ln in out.splitlines() if ln.startswith("table: ")]


def test_ac1_the_table_command_prints_the_caption_taken_past_the_line(
    catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    page = furniture(1) + [
        over(26, "Table 22-, Get Self Test Results Command"),
        over(12, "byte data field"),
        *table(),
    ]
    pdf = pdfgen.write_pdf(tmp_path / "ipmi.pdf", [page])
    scripted.responses[URL] = ok(pdf.read_bytes())
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    code, out = run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert code == 0, out
    assert table_lines(out) == [
        "table: Table 22-, Get Self Test Results Command | ruled | page 1"
        " | 3 columns | 3 rows"
    ]
    # the store carries the caption too, under the new version
    store = library.specs / "mctp" / "DSP0236" / "1.3.3" / T.TABLES_NAME
    data = json.loads(store.read_text("utf-8"))
    assert data["tables_version"] == 12
    assert [t["caption"] for t in data["tables"]] == [
        "Table 22-, Get Self Test Results Command"
    ]
