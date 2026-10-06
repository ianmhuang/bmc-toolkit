"""Glyphs of very different sizes do not merge two lines into one: micro
text is a line of its own, an oversized box never anchors a line, and boxes
of near sizes stacked one under the other are two lines. The second
line-number pass is stricter while only one page is numbered, and neither
pass reads a superscript digit as a number."""

import pytest

from bmc_toolkit.spec import extract as ex
from tests import pdfgen

pytest.importorskip("pypdfium2")

# Body lines low on the page, so the page's median glyph size is body size.
BODY = [(72, 300 - 14 * i, f"Body text line number {i} of the page") for i in range(8)]
SIX = ["a", "b", "c", "d", "e", "f"]


def page_lines(text: str, n: int = 1) -> list[str]:
    marker = ex.PAGE_MARKER.format(n=n)
    start = text.index(marker) + len(marker) + 1
    end = text.find("=== page", start)
    return text[start : end if end >= 0 else None].splitlines()


def lines_of(tmp_path, items) -> list[str]:
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "p.pdf", [items + BODY]))
    return [ln for ln in page_lines(r.text) if not ln.strip().startswith("Body text")]


# ------------------------------------------------------------------- AC-1


def test_ac1_micro_marker_inside_a_body_line_is_a_line_of_its_own(tmp_path):
    # TPM2-P1: a 1 pt "End of Note" whose box lies inside the body line's
    # box was spliced into a word ("WhEnd of Noteen").
    got = lines_of(
        tmp_path,
        [
            (72, 700, "When the TPM receives TPM2_Startup(), it becomes operational."),
            (80, 707, "End of Note", 1),
        ],
    )
    assert [ln.strip() for ln in got] == [
        "End of Note",
        "When the TPM receives TPM2_Startup(), it becomes operational.",
    ], got


def test_ac1_small_text_of_normal_width_still_joins_its_line(tmp_path):
    # PI 1.10: backticks set 2 pt high but of normal width stay inline.
    got = lines_of(
        tmp_path,
        [
            (72, 700, "If"),
            (84, 707, "``", 2, (5, 0, 0, 1)),
            (100, 700, "EFI_BUFFER_TOO_SMALL is returned, the buffer was too small."),
        ],
    )
    assert len(got) == 1, got
    assert got[0].split()[:3] == ["If", "``", "EFI_BUFFER_TOO_SMALL"], got


def test_ac1_micro_run_between_two_runs_of_a_line_does_not_split_it(tmp_path):
    # The micro run sorts between the two runs of one line (by the top of
    # their boxes); the second run still joins the line, not the marker.
    got = lines_of(
        tmp_path,
        [
            (200, 701, "Get Session Challenge, Rs", 9),
            (80, 700, "End of Note", 1),
            (120, 699, "session ID]", 7),
        ],
    )
    assert [ln.split() for ln in got] == [
        ["End", "of", "Note"],
        ["session", "ID]", "Get", "Session", "Challenge,", "Rs"],
    ], got


# ------------------------------------------------------------------- AC-2


def test_ac2_tall_symbol_in_a_caption_does_not_pull_the_next_line_in(tmp_path):
    # ESPI 1.6 p91: a symbol whose box is four times the body height joins
    # the caption; the column heads below it were read into the caption.
    got = lines_of(
        tmp_path,
        [
            (72, 700, "Table 18: CRC Byte with Input Data (", 12),
            (300, 696, "o", 48),
            (330, 700, "Denotes Logical XOR)", 12),
            (150, 685, "1st Clock      2nd Clock      3rd Clock"),
        ],
    )
    assert len(got) == 2, got
    assert (
        got[0].split()
        == "Table 18: CRC Byte with Input Data ( o Denotes Logical XOR)".split()
    )
    assert got[1].split() == ["1st", "Clock", "2nd", "Clock", "3rd", "Clock"]


def test_ac2_tall_symbol_inside_a_table_row_stays_in_that_row(tmp_path):
    # ESPI's table body: the symbol's box starts just below its own row, so
    # it comes after the row and joins it; the rows stay as they were.
    got = lines_of(
        tmp_path,
        [
            (100, 600, "Q2      D7"),
            (180, 608, "o", 48),
            (220, 600, "D6"),
            (100, 586, "Q3      D7"),
        ],
    )
    assert [ln.split() for ln in got] == [["Q2", "D7", "o", "D6"], ["Q3", "D7"]], got


# ------------------------------------------------------------------- AC-3


def test_ac3_index_letter_beside_two_entries_leaves_them_two_lines(tmp_path):
    # ACPI 6.5 p1164: the next section's letter in the right column overlaps
    # the 9 pt entry above and the 8 pt entry below by more than half; the
    # two entries, one under the other, were read as one interleaved line.
    got = lines_of(
        tmp_path,
        [
            (112, 425, "(ACPI), 16", 9),
            (72, 413, "Advanced Programmable Interrupt Controller", 8),
            (311, 418, "E", 14),
        ],
    )
    assert [ln.split() for ln in got] == [
        ["(ACPI),", "16", "E"],
        ["Advanced", "Programmable", "Interrupt", "Controller"],
    ], got


def test_ac3_superscript_of_a_near_size_still_joins_its_line(tmp_path):
    # A 7 pt superscript is within NEAR_SIZE of the 10 pt base but sits
    # beside it, not under or over it.
    got = lines_of(
        tmp_path,
        [(72, 700, "I"), (78, 704, "2", 7), (82, 700, "C address 7 bits")],
    )
    assert len(got) == 1, got
    assert got[0].replace(" ", "") == "I2Caddress7bits", got


def test_ac3_rotated_glyphs_stacked_in_the_margin_do_not_split_a_line(tmp_path):
    # IPMI 2.0 p171: two rotated glyphs of near sizes, one above the other,
    # sort between the two runs of one line; they are not two lines.
    got = lines_of(
        tmp_path,
        [
            (30, 449.6, "it", 8, (0, -1, 1, 0)),
            (200, 448.4, "Get Session Challenge, Rs", 9),
            (120, 446.5, "session ID]", 7),
        ],
    )
    assert len(got) == 1, got
    assert got[0].split()[1:] == [
        "session",
        "ID]",
        "Get",
        "Session",
        "Challenge,",
        "Rs",
    ]


# ------------------------------------------------------------------- AC-4


def _one_numbered_page_then(second):
    return [pdfgen.numbered_page(100, SIX), second]


def test_ac4_lone_column_page_with_a_line_further_left_is_not_numbered(tmp_path):
    # Only page 1 passes the page-by-page rules; page 2 has two consecutive
    # integers in its number column, but a line starts further left.
    second = [
        (37, 700, "110"),
        (72, 700, "Some text"),
        (37, 686, "111"),
        (72, 686, "More text"),
        (30, 660, "A note set further left than the numbers"),
    ]
    r = ex.extract_pdf(
        pdfgen.write_pdf(tmp_path / "d.pdf", _one_numbered_page_then(second))
    )
    assert list(r.linemap["pages"]) == ["1"]
    assert page_lines(r.text, 2)[0].split()[:2] == ["110", "Some"]


def test_ac4_lone_column_page_without_one_is_still_numbered(tmp_path):
    second = [
        (37, 700, "110"),
        (72, 700, "Some text"),
        (37, 686, "111"),
        (72, 686, "More"),
    ]
    r = ex.extract_pdf(
        pdfgen.write_pdf(tmp_path / "d.pdf", _one_numbered_page_then(second))
    )
    assert r.linemap["pages"]["2"]["lines"] == {"0": 110, "1": 111}


def test_ac4_two_numbered_pages_recover_as_before(tmp_path):
    # With two first-pass pages the column is trusted as before, even with a
    # line further left on the recovered page (a wide table, DSP0267 p60).
    second = [
        (37, 700, "112"),
        (72, 700, "Table title"),
        (30, 686, "Command        Code      Requirement"),
    ]
    pages = [pdfgen.numbered_page(100, SIX), pdfgen.numbered_page(106, SIX), second]
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "d.pdf", pages))
    assert r.linemap["pages"]["3"]["lines"] == {"0": 112}


# ------------------------------------------------------------------- AC-5


def test_ac5_detect_skips_a_line_starting_with_a_superscript_digit(tmp_path):
    # Every line starting with a digit is a candidate, wherever it starts;
    # int() cannot read "²" although str.isdigit() holds for it.
    items = pdfgen.numbered_page(100, SIX) + [(72, 600, "²"), (100, 600, "footnote")]
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "d.pdf", [items]))
    assert r.linemap["pages"]["1"]["first"] == 100
    assert page_lines(r.text)[-1].split() == ["²", "footnote"]


def test_ac5_recover_skips_a_line_starting_with_a_superscript_digit():
    def line(y, *segments, number=None):
        return ex.Line(y, segments[0][0], [ex.Segment(*s) for s in segments], number)

    numbered = [
        ex.PageText(i, [line(700, (72, 120, "text"), number=n)], 5.0, 72.0)
        for i, n in ((0, 100), (1, 101))
    ]
    for page in numbered:
        page.numbered = True
        page.number_boxes.append((37.0, 50.0))
    third = ex.PageText(
        2,
        [
            line(700, (37, 42, "²"), (72, 120, "text")),
            line(686, (37, 50, "102"), (72, 120, "text")),
        ],
        5.0,
        37.0,
    )
    assert ex.recover_line_numbers([*numbered, third]) == 1
    assert [ln.number for ln in third.lines] == [None, 102]


# ------------------------------------------------------------------- AC-6


def test_ac6_a_version_5_extract_is_stale(tmp_path):
    # Extracts made before these rules re-extract on next use.
    vdir = tmp_path / "v"
    vdir.mkdir()
    (vdir / ex.EXTRACT_NAME).write_text("=== page 1 ===\nx\n", encoding="utf-8")
    (vdir / ex.META_NAME).write_text('{"extractor_version": 5}', encoding="utf-8")
    assert not ex.is_current(vdir)
