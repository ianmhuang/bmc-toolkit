"""Review acceptance tests: glyphs of very different sizes keep lines apart.

AC-1 micro text is a line of its own and cannot split a line; AC-2 a box
taller than ANCHOR_CAP of the page's median glyph height never anchors a
line; AC-3 stacked boxes of near sizes are two lines, rotated glyphs
excepted; AC-4 the second line-number pass trusts a column seen on one page
only when nothing else starts as far left; AC-5 a superscript digit is not
a line-number candidate; AC-6 a version-5 Extract is stale.

The grouping tests feed glyph boxes straight to ``_group_lines`` the way
``tests/test_extract.py`` does: the criteria are stated in box heights and
widths, and boxes built by hand are exact where a rendered PDF depends on a
font's metrics.
"""

import json

import pytest

from bmc_toolkit.spec import extract as ex

UNIT = 5.0  # the page's median glyph width handed to _group_lines


def glyphs(text, x, y0, size, width=None, height=None):
    """One box per non-space character of ``text`` set left to right from
    ``x`` with its bottom at ``y0``; a space leaves a gap and the marker
    ``_page_chars`` puts on the character after a space."""
    w = size * 0.5 if width is None else width
    h = size if height is None else height
    out = []
    after_space = False
    for ch in text:
        if ch == " ":
            after_space = True
            x += w
            continue
        out.append((x, y0, x + w, y0 + h, (" " + ch) if after_space else ch))
        after_space = False
        x += w
    return out


def words(lines):
    return [" ".join(seg.text for seg in ln.segments).split() for ln in lines]


# ------------------------------------------------------------------- AC-1


def test_ac1_micro_marker_inside_a_body_line_is_a_line_of_its_own():
    # A 1.4 pt "End of Note" (0.7 pt wide glyphs) whose box lies inside a
    # 10 pt body line: under a quarter of the page's median height and
    # width both ways, so it is a line of its own and the body line is whole.
    body_text = "When the TPM receives TPM2_Startup(), it becomes operational."
    body = glyphs(body_text, 72, 700, 10)
    marker = glyphs("End of Note", 80, 703, 1.4, width=0.7)
    got = words(ex._group_lines(body + marker, UNIT))
    assert got == [["End", "of", "Note"], body_text.split()], got


def test_ac1_micro_run_between_two_runs_of_one_line_does_not_split_it():
    # The marker sorts between the two size runs of one line; the second
    # run still tries the ordinary line before the marker and joins it.
    first = glyphs("Get Session Challenge, Rs", 200, 701, 9, width=4.5)
    marker = glyphs("End of Note", 80, 700.5, 1.4, width=0.7)
    second = glyphs("session ID]", 120, 699, 7, width=3.5)
    got = words(ex._group_lines(first + marker + second, UNIT))
    assert got == [
        ["End", "of", "Note"],
        ["session", "ID]", "Get", "Session", "Challenge,", "Rs"],
    ], got


def test_ac1_small_text_of_normal_width_is_not_micro_and_joins():
    # 2 pt high but of body width (PI 1.10's stretched backticks): not
    # micro text, so it stays inline.
    body = glyphs("If", 72, 700, 10) + glyphs(
        "EFI_BUFFER_TOO_SMALL is returned, the buffer was too small.", 100, 700, 10
    )
    ticks = glyphs("``", 84, 707, 2, width=5)
    got = words(ex._group_lines(body + ticks, UNIT))
    assert len(got) == 1, got
    assert got[0][:3] == ["If", "``", "EFI_BUFFER_TOO_SMALL"], got


# ------------------------------------------------------------------- AC-2


def test_ac2_box_over_the_anchor_cap_joins_but_does_not_anchor_the_line():
    # A 48 pt symbol box (four times the 12 pt caption) joins the caption
    # on the overlap rule; the 10 pt column heads below overlap the symbol
    # by more than half their height but not the caption, so they are the
    # next line.
    caption = glyphs("Table 18: CRC Byte with Input Data (", 72, 697, 12, width=6)
    symbol = [(300, 686, 324, 734, "o")]
    tail = glyphs("Denotes Logical XOR)", 330, 697, 12, width=6)
    heading = glyphs("1st Clock      2nd Clock      3rd Clock", 150, 683, 10)
    got = words(ex._group_lines(caption + symbol + tail + heading, UNIT))
    assert got == [
        "Table 18: CRC Byte with Input Data ( o Denotes Logical XOR)".split(),
        ["1st", "Clock", "2nd", "Clock", "3rd", "Clock"],
    ], got


def test_ac2_tall_symbol_inside_a_table_row_stays_in_that_row():
    # The symbol's box starts just under its row, so it comes after the row
    # and joins it; the row below stays apart as before.
    row1 = glyphs("Q2      D7", 100, 598, 10) + glyphs("D6", 220, 598, 10)
    symbol = [(180, 596, 204, 644, "o")]
    row2 = glyphs("Q3      D7", 100, 584, 10)
    got = words(ex._group_lines(row1 + symbol + row2, UNIT))
    assert got == [["Q2", "D7", "o", "D6"], ["Q3", "D7"]], got


# ------------------------------------------------------------------- AC-3


def test_ac3_near_size_entries_bridged_by_a_larger_letter_stay_two_lines():
    # 8.9 pt and 8.4 pt index entries, one under the other, both overlapped
    # by more than half their height by a 13.7 pt letter in the other
    # column. The letter anchors the line; the lower entry is stacked on
    # the upper one within NEAR_SIZE, so it is the next line.
    upper = glyphs("(ACPI), 16", 112, 423.6, 8.9, width=4.45)
    lower = glyphs("Advanced Programmable Interrupt Controller", 72, 411.2, 8.4, 4.2)
    letter = [(311, 415, 318, 428.7, "E")]
    got = words(ex._group_lines(upper + letter + lower, UNIT))
    assert got == [
        ["(ACPI),", "16", "E"],
        ["Advanced", "Programmable", "Interrupt", "Controller"],
    ], got


@pytest.mark.parametrize("size", [6, 7])
def test_ac3_superscript_beside_its_base_still_joins(size):
    # A raised digit sits beside "I" and "C", over neither; 7 pt is within
    # NEAR_SIZE of the 10 pt base, 6 pt is not, and both join.
    width = size / 2
    chars = (
        glyphs("I", 72, 700, 10)
        + glyphs("2", 77, 710 - size, size, width=width)
        + glyphs("C address 7 bits", 77 + width, 700, 10)
    )
    got = words(ex._group_lines(chars, UNIT))
    assert got == [["I2C", "address", "7", "bits"]], got


def test_ac3_rotated_glyphs_stacked_in_the_margin_do_not_split_the_line():
    # Two rotated glyphs (boxes wider than tall, heights within NEAR_SIZE)
    # one above the other in the margin, sorting between the two size runs
    # of one body line: the stacking rule across sizes does not apply to a
    # rotated box, so the line stays one.
    rotated = [(30, 451, 38, 452.8, "i"), (30, 448.3, 38, 450.5, "t")]
    first = glyphs("Get Session Challenge, Rs", 200, 448.4, 9, width=4.5)
    second = glyphs("session ID]", 120, 446.5, 7, width=3.5)
    got = words(ex._group_lines(rotated + first + second, UNIT))
    assert got == [
        ["it", "session", "ID]", "Get", "Session", "Challenge,", "Rs"]
    ], got


# ------------------------------------------------------------------- AC-4


def line(y, *segments, number=None):
    return ex.Line(y, segments[0][0], [ex.Segment(*s) for s in segments], number)


def numbered_page(index, first):
    """A page the first pass numbered: six lines, numbers already moved off
    into the Line Map, number boxes at x 37-48."""
    lines = [
        line(700 - 14 * i, (72, 120, f"text {n}"), number=n)
        for i, n in enumerate(range(first, first + 6))
    ]
    page = ex.PageText(index, lines, 5.0, 72.0)
    page.numbered = True
    page.number_boxes.extend([(37.0, 48.0)] * 6)
    return page


def column_page(index, numbers, extra=()):
    """A page the first pass turned down: ``numbers`` start lines in the
    column at x 37, plus ``extra`` lines given as (y, x0, x1, text)."""
    lines = [
        line(700 - 14 * i, (37, 48, str(n)), (72, 120, "text"))
        for i, n in enumerate(numbers)
    ]
    lines += [line(y, (x0, x1, text)) for y, x0, x1, text in extra]
    return ex.PageText(index, lines, 5.0, 37.0)


def test_ac4_lone_column_page_with_a_line_further_left_stays_unnumbered():
    # One first-pass page only; the second page's integers are consecutive
    # and in range, but a line starts as far left as the numbers.
    note = (660, 30, 200, "A note set further left than the numbers")
    page = column_page(1, [110, 111], extra=[note])
    assert ex.recover_line_numbers([numbered_page(0, 100), page]) == 0
    assert [ln.number for ln in page.lines] == [None, None, None]
    assert page.lines[0].segments[0].text == "110"
    assert not page.numbered


def test_ac4_lone_column_page_without_one_is_numbered():
    page = column_page(1, [110, 111])
    assert ex.recover_line_numbers([numbered_page(0, 100), page]) == 1
    assert [ln.number for ln in page.lines] == [110, 111]
    assert [ln.segments[0].text for ln in page.lines] == ["text", "text"]


def test_ac4_with_two_first_pass_pages_a_line_further_left_is_no_bar():
    # Two first-pass pages: the column is trusted as before, so a wide
    # table starting left of the numbers does not stop the recovery.
    heads = (686, 30, 300, "Command        Code      Requirement")
    page = column_page(2, [112], extra=[heads])
    pages = [numbered_page(0, 100), numbered_page(1, 106), page]
    assert ex.recover_line_numbers(pages) == 1
    assert [ln.number for ln in page.lines] == [112, None]


# ------------------------------------------------------------------- AC-5


def test_ac5_detect_does_not_read_a_superscript_digit_as_a_number():
    # "²" satisfies str.isdigit() but int() cannot read it: the line is not
    # a candidate and the page's real numbers are still found.
    lines = [
        line(700 - 14 * i, (37, 48, str(n)), (72, 120, "text"))
        for i, n in enumerate(range(100, 106))
    ]
    lines.append(line(600, (72, 76, "²"), (100, 140, "footnote")))
    page = ex.PageText(0, lines, 5.0, 37.0)
    assert ex.detect_line_numbers(page, None) is True
    assert [ln.number for ln in page.lines] == [100, 101, 102, 103, 104, 105, None]
    assert [seg.text for seg in page.lines[-1].segments] == ["²", "footnote"]


def test_ac5_recover_does_not_read_a_superscript_digit_as_a_number():
    third = ex.PageText(
        2,
        [
            line(700, (37, 42, "²"), (72, 120, "text")),
            line(686, (37, 48, "112"), (72, 120, "text")),
        ],
        5.0,
        37.0,
    )
    pages = [numbered_page(0, 100), numbered_page(1, 106), third]
    assert ex.recover_line_numbers(pages) == 1
    assert [ln.number for ln in third.lines] == [None, 112]
    assert third.lines[0].segments[0].text == "²"


def test_ac5_a_pdf_page_with_a_superscript_line_extracts(tmp_path):
    pytest.importorskip("pypdfium2")
    from tests import pdfgen

    items = pdfgen.numbered_page(100, ["a", "b", "c", "d", "e", "f"])
    items += [(72, 600, "²"), (100, 600, "footnote")]
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "sup.pdf", [items]))
    entry = r.linemap["pages"]["1"]
    assert (entry["first"], entry["last"]) == (100, 105)
    assert "footnote" in r.text


# ------------------------------------------------------------------- AC-6


def test_ac6_an_extract_of_version_5_is_stale(tmp_path):
    vdir = tmp_path / "v"
    vdir.mkdir()
    (vdir / ex.EXTRACT_NAME).write_text("=== page 1 ===\nx\n", encoding="utf-8")
    meta = vdir / ex.META_NAME
    meta.write_text(json.dumps({"extractor_version": 5}), encoding="utf-8")
    assert not ex.is_current(vdir)
    meta.write_text(
        json.dumps({"extractor_version": ex.EXTRACTOR_VERSION}), encoding="utf-8"
    )
    assert ex.is_current(vdir)
    assert ex.EXTRACTOR_VERSION >= 6
