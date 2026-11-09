"""Review tests for the `Table` caption that ends within 40 points above
its table (fix/caption-to-line-bottom).

The AC: a table with no caption from the 40 pt window or the Figure rule
takes the nearest body line whose bottom lies within 40 pt above it when
that line is a `Table N` caption, in any letter case, margin line number
dropped, with no other table between (AC-1); a `Figure` line, a prose
line, a line ending more than 40 pt up and a line with another table
between are not taken (AC-2); a caption the window or the Figure rule
finds is kept (AC-3); the page-before rule takes `Table` in any letter
case (AC-4); TABLES_VERSION is 12 and a version 11 store is read again
(AC-6); PMBUS-II records no limit for Table 31 (AC-8). Round 2 adds the
prose forms and the wrapped `table.` line of the round 1 findings; round
3 the id forms and the titles of the round 2 findings.

Geometry: pdfgen places text by its baseline in PDF points, origin
bottom-left; pdfplumber puts a 10 pt Helvetica line's top about 8 pt
above the baseline and its bottom about 2 pt below it. A line whose top
lies ``gap`` points over a table top ends ``gap - 10`` points over it,
so 47 gives a top outside the 40 pt window and a bottom inside. Every
case writes its own PDF."""

import json
from pathlib import Path

import pytest

from bmc_toolkit.spec import tables as T
from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok
from tests.test_tables import WIDTHS, ruled_table

pytest.importorskip("pdfplumber")

ROOT = Path(__file__).resolve().parents[1]
ASCENT = 8
ROW_H = 16
TOP = 600
PAGE_TOP = 680  # a table that starts its page, under the running header
ROWS = [
    ["Code", "Name", "Type"],
    ["01h", "PAGE", "R/W Byte"],
    ["02h", "OPERATION", "R/W Byte"],
]
PMBUS = "Table 31. Command Summary"
NOTES = [
    (25, "Note: the byte count is not part of"),
    (12, "the data bytes listed in this column."),
]
URL = "https://example.test/DSP0236_1.3.3.pdf"


def table(top=TOP, rows=ROWS):
    return ruled_table(72, top, WIDTHS, [ROW_H] * len(rows), rows)


def over(gap, text, top=TOP):
    """A text line whose top lies ``gap`` points over a table top."""
    return (72, top + gap - ASCENT, text)


def under(gap, text, top=TOP, rows=ROWS):
    """A text line whose top lies ``gap`` points under the table bottom."""
    return (72, top - ROW_H * len(rows) - gap - ASCENT, text)


def notes(top=TOP):
    """Two lines of notes between a caption and its table (PMBus)."""
    return [over(gap, text, top) for gap, text in NOTES]


def captions(tmp_path, pages):
    pdf = pdfgen.write_pdf(tmp_path / "doc.pdf", pages)
    with T.Reader(pdf) as r:
        return [
            [t.caption for t in r.logical_tables(n)] for n in range(1, len(pages) + 1)
        ]


def gaps(tmp_path, gap, text):
    """How far the top and the bottom of the line ``over(gap, text)`` lie
    over the table top, as the Reader measures them."""
    pdf = pdfgen.write_pdf(tmp_path / "geometry.pdf", [table() + [over(gap, text)]])
    with T.Reader(pdf) as r:
        info = r.page(1)
        (found,) = info.tables
        (line,) = [ln for ln in info.lines if ln.text == text]
        return found.top - line.top, found.top - line.bottom


def header_and_number(n):
    return [(72, 750, "Example Specification, Revision 2.4"), (300, 40, str(n))]


def foot(text, y=300):
    """A paragraph whose last line is ``text``: page 1 ends there."""
    lines = ["The command is described in the table that follows.", text]
    return [(72, y + 14 * (len(lines) - 1 - i), ln) for i, ln in enumerate(lines)]


def on_page_2(tmp_path, last_line, above=()):
    """Page 1 ends with ``last_line``; page 2 holds ``above`` over a table
    that starts the page, and prose under it. Page 2's captions."""
    pages = [
        header_and_number(1) + foot(last_line),
        header_and_number(2)
        + list(above)
        + table(top=PAGE_TOP)
        + [(72, 120, "The second part ends here.")],
    ]
    return captions(tmp_path, pages)[1]


# ------------------------------------------------------------------ AC-1


def test_ac1_the_synthetic_caption_has_the_pmbus_geometry(tmp_path):
    # top outside the 40 pt window, bottom inside: the case the AC names
    top, bottom = gaps(tmp_path, 47, PMBUS)
    assert top > T.CAPTION_GAP_PT
    assert 0 < bottom < T.CAPTION_GAP_PT


def test_ac1_a_caption_over_two_note_lines_names_the_table(tmp_path):
    # PMBus Part II 1.3.1 page 112: caption, two lines of notes, table
    page = table() + [over(47, PMBUS)] + notes()
    assert captions(tmp_path, [page]) == [[PMBUS]]


@pytest.mark.parametrize(
    ("line", "caption"),
    [
        ("112 Table 4 - Margin numbered", "Table 4 - Margin numbered"),
        ("TABLE 5 - STATUS BITS", "TABLE 5 - STATUS BITS"),
        ("table 6 - Status bits", "table 6 - Status bits"),
        ("Table 21-4, Get Sub-function Data", "Table 21-4, Get Sub-function Data"),
    ],
)
def test_ac1_letter_case_and_a_margin_number_do_not_matter(tmp_path, line, caption):
    page = table() + [over(47, line)] + notes()
    assert captions(tmp_path, [page]) == [[caption]]


@pytest.mark.parametrize(
    "line",
    [
        # round 2 F2: a title that starts with the word "Table", or is
        # only "(continued)", is still a title
        "Table 7 - Table Descriptor Format",
        "Table 4: Tablet mode pins",
        "Table 31 (continued)",
        # round 2 F1: an annex id
        "Table A.1 - Annex codes",
        "Table G-1, Command Number Assignments",
    ],
)
def test_ac1_a_title_starting_with_table_and_an_annex_id_are_taken(tmp_path, line):
    page = table() + [over(47, line)] + notes()
    assert captions(tmp_path, [page]) == [[line]]


@pytest.mark.parametrize("gap", [42, 49])
def test_ac1_any_line_ending_inside_40_points_is_reached(tmp_path, gap):
    # tops 42 and 49 pt up are both past the window; the bottoms lie 32
    # and 39 pt up
    page = table() + [over(gap, "Table 7 - Limits")]
    assert captions(tmp_path, [page]) == [["Table 7 - Limits"]]


def test_ac1_a_table_over_the_caption_is_not_a_table_between(tmp_path):
    # the upper table ends above the caption, so nothing lies between the
    # caption and the lower table; the upper one has no caption at all
    upper = table(top=TOP + 150, rows=[["X", "Y", "Z"]])
    page = upper + [over(47, "Table 7 - Lower")] + notes() + table()
    assert captions(tmp_path, [page]) == [[None, "Table 7 - Lower"]]


def test_ac1_the_table_command_prints_the_caption(
    catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    page = [over(47, PMBUS), *notes(), *table()]
    pdf = pdfgen.write_pdf(tmp_path / "pmbus.pdf", [page])
    scripted.responses[URL] = ok(pdf.read_bytes())
    assert main(["--catalog", str(catalog_file), "fetch", "DSP0236"]) == 0
    capsys.readouterr()
    code = main(["--catalog", str(catalog_file), "table", "DSP0236", "--page", "1"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert [ln for ln in out.splitlines() if ln.startswith("table: ")] == [
        f"table: {PMBUS} | ruled | page 1 | 3 columns | 3 rows"
    ]


# ------------------------------------------------------------------ AC-2


def test_ac2_a_figure_line_is_not_taken_by_the_fallback(tmp_path):
    # prose, so the Figure rule leaves it too: the table has no caption
    page = table() + [over(47, "Figure 24 shows a large request.")] + notes()
    assert captions(tmp_path, [page]) == [[None]]


def test_ac2_a_figure_keeps_its_caption_under_prose_starting_with_figure(tmp_path):
    # DSP0274 Figure 24: a prose line that starts like a caption ends
    # within 40 pt over the drawing, whose own caption lies under it
    page = table() + [
        over(47, "Figure 24 - A request larger than the buffer goes in chunks,"),
        over(25, "each of them acknowledged by the Responder before the"),
        over(12, "next one is sent."),
        under(30, "Figure 24 - Large request flow"),
    ]
    assert captions(tmp_path, [page]) == [["Figure 24 - Large request flow"]]


@pytest.mark.parametrize(
    "text",
    [
        "Table 3 lists the fields below.",
        "Table 31 and Table 32 list the commands.",
        "45 Table 3 lists the fields below.",
        "Tables in this clause use hexadecimal codes.",
        # round 1 F1: prose whose text after the id does not start lowercase
        "Table 12, Table 13 and Table 14 list the commands.",
        "Table 3 (above) lists the fields.",
        "45 Table 12, Table 13 and Table 14 list the commands.",
        # round 3: the same prose with annex ids
        "Table A.1, Table A.2 and Table A.3 list the codes.",
    ],
)
def test_ac2_prose_starting_with_table_is_not_taken(tmp_path, text):
    page = table() + [over(47, text)] + notes()
    assert captions(tmp_path, [page]) == [[None]]


def test_ac2_a_caption_ending_more_than_40_points_up_is_not_taken(tmp_path):
    _, bottom = gaps(tmp_path, 53, "Table 9 - Too far")
    assert bottom > T.CAPTION_GAP_PT
    page = table() + [over(53, "Table 9 - Too far")] + notes()
    assert captions(tmp_path, [page]) == [[None]]


def test_ac2_a_caption_with_another_table_between_is_not_taken(tmp_path):
    # a one-row table lies 14 to 30 pt over the lower table and its
    # caption 13 pt over that: the caption ends 33 pt over the lower
    # table, with its own table between
    small_top = TOP + 30
    page = (
        table(top=small_top, rows=[["X", "Y", "Z"]])
        + [over(13, "Table 1 - Small", top=small_top)]
        + table()
    )
    assert captions(tmp_path, [page]) == [["Table 1 - Small", None]]


# ------------------------------------------------------------------ AC-3


def test_ac3_a_table_caption_in_the_window_is_kept(tmp_path):
    page = table() + [
        over(47, "Table 8 - Further up"),
        over(25, "Table 9 - In the window"),
        over(12, "byte data field"),
    ]
    assert captions(tmp_path, [page]) == [["Table 9 - In the window"]]


def test_ac3_a_figure_caption_in_the_window_is_kept(tmp_path):
    # the window rule comes first: its Figure line stands though a
    # `Table` line ends within 40 pt further up
    page = table() + [
        over(47, "Table 8 - Further up"),
        over(25, "Figure 12 - Request Format"),
        over(12, "byte data field"),
    ]
    assert captions(tmp_path, [page]) == [["Figure 12 - Request Format"]]


def test_ac3_the_figure_rule_comes_before_the_fallback(tmp_path):
    page = (
        table()
        + [over(47, "Table 8 - Further up")]
        + notes()
        + [under(30, "Figure 3 - Packet format")]
    )
    assert captions(tmp_path, [page]) == [["Figure 3 - Packet format"]]


def test_ac3_the_fallback_comes_before_the_page_before(tmp_path):
    # page 1 ends with a `Table` caption; page 2's table has its own
    # caption ending within 40 pt over it
    got = on_page_2(
        tmp_path,
        "Table 3 - Other",
        [over(47, "Table 4 - Own", top=PAGE_TOP), *notes(top=PAGE_TOP)],
    )
    assert got == ["Table 4 - Own"]


# ------------------------------------------------------------------ AC-4


@pytest.mark.parametrize(
    ("line", "caption"),
    [
        ("TABLE 5 - REGISTER MAP", "TABLE 5 - REGISTER MAP"),
        ("table 5 - register map", "table 5 - register map"),
        ("61 TABLE 1 - THREAT MODEL", "TABLE 1 - THREAT MODEL"),
        ("Table 5 - Register map", "Table 5 - Register map"),
        ("TABLE IV - ROMAN NUMBERED", "TABLE IV - ROMAN NUMBERED"),
    ],
)
def test_ac4_the_page_before_rule_takes_table_in_any_letter_case(
    tmp_path, line, caption
):
    assert on_page_2(tmp_path, line) == [caption]


@pytest.mark.parametrize(
    "line", ["FIGURE 5: TIMEOUT INTERVALS", "figure 5: timeout intervals"]
)
def test_ac4_a_figure_line_in_any_letter_case_is_still_not_taken(tmp_path, line):
    assert on_page_2(tmp_path, line) == [None]


@pytest.mark.parametrize("line", ["table.", "table below:", "tables below."])
def test_ac4_a_wrapped_sentence_ending_in_table_is_not_a_caption(tmp_path, line):
    # round 1 F2: reading `Table` in any letter case must not take the
    # last line of a sentence wrapped before the word "table"; develop
    # did not take these lines either
    assert on_page_2(tmp_path, line) == [None]


@pytest.mark.parametrize(
    "line",
    [
        "Table 21-4, Get Sub-function Data",
        "Table G-1, Command Number Assignments",
        "Table B-2 - Register map",
        "Table 20-, Get Device ID Command",
        # round 2 F1: a dotted annex id, two annex letters, a Roman numeral
        "Table A.1 - Annex codes",
        "Table AA-1 - Annex codes",
        "Table II - Roman numbered",
    ],
)
def test_ac4_the_id_forms_develop_took_are_still_taken(tmp_path, line):
    # the id the page-before rule wants after `Table` covers a section
    # number, an appendix letter, IPMI's cut-off `20-,`, the annex ids
    # extract.py reads as captions and a Roman numeral
    assert on_page_2(tmp_path, line) == [line]


# ------------------------------------------------------------------ AC-6


def test_ac6_tables_version_is_12_and_a_version_11_store_is_not_served(tmp_path):
    assert T.TABLES_VERSION == 14
    pdf = pdfgen.write_pdf(
        tmp_path / "doc.pdf", [table() + [over(47, PMBUS)] + notes()]
    )
    with T.Reader(pdf) as r:
        found = r.logical_tables(1)
    vdir = tmp_path / "v"
    vdir.mkdir()
    path = T.store(vdir, [1], found)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tables_version"] == 14
    assert [t["caption"] for t in data["tables"]] == [PMBUS]
    assert T.stored_for_page(vdir, 1) is not None

    # what version 11 stored for this page: no caption
    data["tables_version"] = 11
    for t in data["tables"]:
        t["caption"] = None
    path.write_text(json.dumps(data), encoding="utf-8", newline="")
    assert T.stored_for_page(vdir, 1) is None  # read again, not trusted

    T.store(vdir, [1], found)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tables_version"] == 14
    (stored,) = T.stored_for_page(vdir, 1)
    assert stored.caption == PMBUS


def test_ac6_the_table_command_reads_a_version_11_store_again(
    catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    page = [over(47, PMBUS), *notes(), *table()]
    pdf = pdfgen.write_pdf(tmp_path / "pmbus.pdf", [page])
    scripted.responses[URL] = ok(pdf.read_bytes())
    argv = ["--catalog", str(catalog_file)]
    assert main([*argv, "fetch", "DSP0236"]) == 0
    assert main([*argv, "table", "DSP0236", "--page", "1"]) == 0
    first = capsys.readouterr().out

    store = library.specs / "mctp" / "DSP0236" / "1.3.3" / T.TABLES_NAME
    data = json.loads(store.read_text(encoding="utf-8"))
    data["tables_version"] = 11
    for t in data["tables"]:
        t["caption"] = None
    store.write_text(json.dumps(data), encoding="utf-8", newline="")

    code = main([*argv, "table", "DSP0236", "--page", "1"])
    out = capsys.readouterr().out
    assert code == 0, out
    lines = [ln for ln in out.splitlines() if ln.startswith("table: ")]
    assert lines == [f"table: {PMBUS} | ruled | page 1 | 3 columns | 3 rows"]
    assert lines[0] in first
    data = json.loads(store.read_text(encoding="utf-8"))
    assert data["tables_version"] == 14
    assert [t["caption"] for t in data["tables"]] == [PMBUS]


# ------------------------------------------------------------------ AC-8


def test_ac8_pmbus_ii_records_no_limit_for_table_31():
    limits = load_catalog().get("PMBUS-II").limits
    assert "Table 31" not in limits
    assert "caption" not in limits


def test_ac8_support_md_shows_what_the_catalog_records_for_pmbus_ii():
    limits = load_catalog().get("PMBUS-II").limits
    text = (ROOT / "docs" / "SUPPORT.md").read_text(encoding="utf-8")
    (row,) = [ln for ln in text.splitlines() if ln.startswith("| `PMBUS-II` ")]
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    assert cells[-1] == (limits or "-")
    assert "Table 31" not in row
