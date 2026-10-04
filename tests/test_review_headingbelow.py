"""Reviewer acceptance tests for AC-1's "the last entry whose heading is
above the table": a section whose heading is on the page below the table
does not own the table, whatever the text above the table says. Black-box
through the CLI on synthetic one-page PDFs. No network.

The tables have no caption and follow a heading that is not the one in
force at the top of the page, so the base branch fails them too (it names
the page top). The last test repeats the case on a page with printed line
numbers, where the table reader's lines carry those numbers in front."""

import pytest

from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok

pytest.importorskip("pypdfium2")
pytest.importorskip("pdfplumber")

URL = "https://example.test/DSP0236_1.3.3.pdf"
WIDTHS = [100, 80, 200]
CELLS = [["Name", "Code", "Meaning"], ["Temperature", "01h", "degrees"]]


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def small(top, x=72):
    """A ruled table of a header and one row; `top` is its top edge in PDF
    points, origin bottom-left."""
    items = []
    xs = [x]
    for w in WIDTHS:
        xs.append(xs[-1] + w)
    ys = [top, top - 16, top - 32]
    for y in ys:
        items.append(("fill", x, y - 0.3, sum(WIDTHS), 0.6))
    for cx in xs:
        items.append(("fill", cx - 0.3, top - 32, 0.6, 32))
    for r, row in enumerate(CELLS):
        for c, text in enumerate(row):
            items.append((xs[c] + 3, ys[r] - 11, text))
    return items


def table_sections(pdf, catalog_file, library, scripted, capsys):
    scripted.responses[URL] = ok(pdf)
    code, out = run(
        capsys, "fetch", "DSP0236", "--no-extract", catalog_file=catalog_file
    )
    assert code == 0, out
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0, out
    return [
        tuple(line.split(" | ")[2:5])
        for line in out.splitlines()
        if line.startswith("cite: ")
    ]


def test_ac1_text_starting_with_the_number_of_a_later_section_does_not_place_it(
    catalog_file, library, scripted, tmp_path, capsys
):
    # the table is under `5.1 Set`; `6 Next` starts below it. The sentence
    # above the table starts with "6 " and is not that heading.
    page = [
        (72, 760, "Spec Title"),
        (72, 740, "5 Codes"),
        (72, 724, "5.1 Set"),
        (72, 708, "6 bytes follow the header in this format."),
        *small(690),
        (72, 630, "6 Next"),
        (72, 614, "Text of the next section."),
    ]
    pdf = pdfgen.write_pdf(
        tmp_path / "number.pdf",
        [page],
        bookmarks=[(0, "5 Codes", 0), (1, "5.1 Set", 0), (0, "6 Next", 0)],
    ).read_bytes()
    assert table_sections(pdf, catalog_file, library, scripted, capsys) == [
        ("5.1 Set", "PDF page 1", "lines table 1")
    ]


def test_ac1_text_naming_a_later_section_by_its_title_does_not_place_it(
    catalog_file, library, scripted, tmp_path, capsys
):
    # the first table is under `5.1 Set`; the sentence above it refers to
    # `5.2 Get`, whose heading is below the table
    page = [
        (72, 760, "Spec Title"),
        (72, 740, "5 Codes"),
        (72, 724, "5.1 Set"),
        (72, 708, "The reply format is in 5.2 Get below."),
        *small(690),
        (72, 634, "5.2 Get"),
        *small(616),
    ]
    pdf = pdfgen.write_pdf(
        tmp_path / "title.pdf",
        [page],
        bookmarks=[(0, "5 Codes", 0), (1, "5.1 Set", 0), (1, "5.2 Get", 0)],
    ).read_bytes()
    assert table_sections(pdf, catalog_file, library, scripted, capsys) == [
        ("5.1 Set", "PDF page 1", "lines table 1"),
        ("5.2 Get", "PDF page 1", "lines table 2"),
    ]


def numbered(y, number, text):
    """A body line with its printed line number in the margin."""
    return [(37, y, str(number)), (72, y, text)]


def test_ac1_a_later_section_named_above_the_table_on_a_line_numbered_page(
    catalog_file, library, scripted, tmp_path, capsys
):
    # every body line has a printed line number (20-25). The first table is
    # under `9.1 SetTID command`; the sentence above it names
    # `9.2 GetTID command`, whose heading is below the table
    page = [
        *numbered(740, 20, "9 Commands"),
        *numbered(724, 21, "9.1 SetTID command"),
        *numbered(708, 22, "The reply is described in 9.2 GetTID command below."),
        *small(690),
        *numbered(630, 23, "9.2 GetTID command"),
        *small(612),
        *numbered(556, 24, "Closing text."),
        *numbered(540, 25, "More closing text."),
    ]
    pdf = pdfgen.write_pdf(
        tmp_path / "numbered.pdf",
        [page],
        bookmarks=[
            (0, "9 Commands", 0),
            (1, "9.1 SetTID command", 0),
            (1, "9.2 GetTID command", 0),
        ],
    ).read_bytes()
    assert table_sections(pdf, catalog_file, library, scripted, capsys) == [
        ("9.1 SetTID command", "PDF page 1", "lines table 1"),
        ("9.2 GetTID command", "PDF page 1", "lines table 2"),
    ]
    # the premise: the page was read as one with printed line numbers
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[0].split(" | ")[4] == "lines 20-25"
