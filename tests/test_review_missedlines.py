"""Acceptance tests for the pages whose printed line numbers the Extract
missed (AC-1, AC-2, AC-4, AC-5).

Black-box through ``extract_pdf`` and ``write_result`` on synthetic PDFs from
``tests.pdfgen``. Every test holds an assertion that fails on the base
branch, where a page the page-by-page rules turn down has no Line Map entry.
A recovered page is always followed by a numbered page here, so both bounds
AC-1 names exist.
"""

import json

import pytest

from bmc_toolkit.spec import extract as ex
from tests import pdfgen

pytest.importorskip("pypdfium2")

MARGIN_X = 37.0  # where pdfgen.numbered_page prints its numbers
BODY_X = 72.0
SIX = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"]
FIVE = ["eta", "theta", "iota", "kappa", "lambda"]


def page_lines(text: str, n: int) -> list[str]:
    """The lines of physical page ``n`` in the Extract text."""
    marker = ex.PAGE_MARKER.format(n=n)
    start = text.index(marker) + len(marker) + 1
    end = text.find("=== page ", start)
    return text[start : end if end >= 0 else None].splitlines()


def margin_lines(numbers, text="Body line", top=700.0):
    """Text lines, each behind an integer in the margin column, top down."""
    items = []
    for i, n in enumerate(numbers):
        y = top - 14 * i
        items += [(MARGIN_X, y, str(n)), (BODY_X, y, f"{text} {i}")]
    return items


def table_page(numbers, rows=5, footer=None):
    """A page a table fills: a text line behind each margin number, then
    ``rows`` table rows that start with a byte offset, then a footer that
    starts with the page number. The offsets and the page number start a
    line, but right of the margin column."""
    items = []
    y = 720.0
    for n in numbers:
        items += [(MARGIN_X, y, str(n)), (BODY_X, y, f"Row text {n}")]
        y -= 14
    for off in range(rows):
        items += [(75, y, str(off)), (120, y, "uint8"), (200, y, f"field at {off}")]
        y -= 14
    if footer is not None:
        items += [(BODY_X, 40, str(footer)), (284, 40, "Published")]
    return items


def extract(tmp_path, pages, name="doc.pdf"):
    return ex.extract_pdf(pdfgen.write_pdf(tmp_path / name, pages))


def entry(first, count, at=0):
    """The Line Map entry of ``count`` consecutive numbers from ``first``,
    the first of them on line ``at`` of the page."""
    return {
        "first": first,
        "last": first + count - 1,
        "lines": {str(at + i): first + i for i in range(count)},
    }


# ------------------------------------------------------------------- AC-1


def test_ac1_short_pages_after_a_page_left_unnumbered_get_their_entries(tmp_path):
    pages = [
        pdfgen.numbered_page(100, SIX),
        margin_lines([106, 108]),  # 107 is missing: this page stays as it is
        margin_lines([109, 110], text="Key"),
        [(MARGIN_X, 700, "111"), (BODY_X, 700, "Only line")],
        pdfgen.numbered_page(112, SIX),
    ]
    r = extract(tmp_path, pages)
    lm = r.linemap["pages"]
    # the base branch stops at page 2: 109 does not continue 105
    assert list(lm) == ["1", "3", "4", "5"]
    assert lm["3"] == entry(109, 2)
    assert lm["4"] == entry(111, 1)
    assert page_lines(r.text, 3) == ["Key 0", "Key 1"]
    assert page_lines(r.text, 4) == ["Only line"]
    assert r.numbered_pages == 4
    # the page left unnumbered keeps its numbers in the text
    assert [ln.split() for ln in page_lines(r.text, 2)] == [
        ["106", "Body", "line", "0"],
        ["108", "Body", "line", "1"],
    ]


def test_ac1_a_short_page_is_numbered_without_continuing_the_count(tmp_path):
    # the page before has no numbers at all, and 106-107 are printed nowhere:
    # 108-109 stand in the column, are consecutive and lie between 105 and 110
    pages = [
        pdfgen.numbered_page(100, SIX),
        pdfgen.plain_page(["A drawing fills this page."]),
        margin_lines([108, 109], text="After"),
        pdfgen.numbered_page(110, SIX),
    ]
    r = extract(tmp_path, pages)
    lm = r.linemap["pages"]
    assert list(lm) == ["1", "3", "4"]
    assert lm["3"] == entry(108, 2)
    assert page_lines(r.text, 3) == ["After 0", "After 1"]
    assert page_lines(r.text, 2) == ["A drawing fills this page."]


# ------------------------------------------------------------------- AC-2


def test_ac2_margin_numbers_are_taken_although_other_integers_outnumber_them(
    tmp_path,
):
    # five margin numbers, eight byte offsets and the page number of the
    # footer: thirteen integers start a line, five of them in the margin
    pages = [
        pdfgen.numbered_page(100, SIX),
        table_page([106, 107, 108, 109, 110], rows=8, footer=2),
        pdfgen.numbered_page(111, SIX),
    ]
    r = extract(tmp_path, pages)
    lm = r.linemap["pages"]
    assert list(lm) == ["1", "2", "3"]
    # the offsets and the page number get no entry
    assert lm["2"] == entry(106, 5)
    got = page_lines(r.text, 2)
    assert len(got) == 14
    assert got[:5] == [f"Row text {n}" for n in range(106, 111)]
    # ... and stay in the text
    assert [ln.split()[:2] for ln in got[5:13]] == [
        [str(off), "uint8"] for off in range(8)
    ]
    assert got[13].split() == ["2", "Published"]
    assert r.numbered_pages == 3


# ------------------------------------------------------------------- AC-4


@pytest.mark.parametrize(
    "numbers",
    [
        pytest.param([105, 106], id="starts at the last number before"),
        pytest.param([108, 109, 110], id="reaches the first number after"),
        pytest.param([107, 107], id="a number twice"),
        pytest.param([108, 107], id="descending"),
        pytest.param([106, 107, 109], id="a gap"),
        pytest.param([106, 107, 2], id="another integer in the column"),
    ],
)
def test_ac4_numbers_that_do_not_fit_leave_the_page_as_it_was(tmp_path, numbers):
    odd = margin_lines(numbers)
    pages = [
        pdfgen.numbered_page(100, SIX),
        odd,
        pdfgen.numbered_page(110, SIX),
        table_page([116, 117], footer=4),  # this one fits: only the base misses it
        pdfgen.numbered_page(118, SIX),
    ]
    r = extract(tmp_path, pages)
    lm = r.linemap["pages"]
    assert list(lm) == ["1", "3", "4", "5"]
    assert lm["4"] == entry(116, 2)
    got = page_lines(r.text, 2)
    assert [ln.split()[0] for ln in got] == [str(n) for n in numbers]
    # its text is what the page gives in a document without a Line Map
    alone = extract(tmp_path, [odd], "alone.pdf")
    assert alone.numbered_pages == 0
    assert got == page_lines(alone.text, 1)


def test_ac4_a_page_before_the_first_numbered_page_is_left_alone(tmp_path):
    # no numbered page before it: 98-99 lie between nothing
    pages = [
        margin_lines([98, 99], text="Front"),
        pdfgen.numbered_page(100, SIX),
        table_page([106, 107]),
        pdfgen.numbered_page(108, SIX),
    ]
    r = extract(tmp_path, pages)
    assert list(r.linemap["pages"]) == ["2", "3", "4"]
    assert [ln.split()[0] for ln in page_lines(r.text, 1)] == ["98", "99"]


def test_ac4_without_a_numbered_page_there_is_no_line_map(tmp_path):
    missed = [table_page([106, 107]), margin_lines([108])]
    led = [pdfgen.numbered_page(100, SIX), *missed, pdfgen.numbered_page(109, SIX)]
    with_column = extract(tmp_path, led, "led.pdf")
    # between numbered pages the two pages are numbered ...
    assert list(with_column.linemap["pages"]) == ["1", "2", "3", "4"]
    # ... and in a document none of whose pages shows the number column the
    # same pages, and one with four numbers in a row, are left alone
    vdir = tmp_path / "v"
    vdir.mkdir()
    pdf = pdfgen.write_pdf(
        vdir / "original.pdf", [*missed, margin_lines([109, 110, 111, 112])]
    )
    r = ex.extract_pdf(pdf)
    ex.write_result(vdir, r)
    assert r.numbered_pages == 0
    assert r.linemap == {"pages": {}}
    assert not (vdir / ex.LINEMAP_NAME).exists()
    meta = json.loads((vdir / ex.META_NAME).read_text("utf-8"))
    assert meta["line_numbers"] is False
    assert meta["line_numbered_pages"] == 0
    assert page_lines(r.text, 1)[0].split() == ["106", "Row", "text", "106"]
    assert page_lines(r.text, 2)[0].split()[0] == "108"
    assert [ln.split()[0] for ln in page_lines(r.text, 3)] == [
        "109",
        "110",
        "111",
        "112",
    ]


# ------------------------------------------------------------------- AC-5


def test_ac5_pages_numbered_before_keep_their_entry_and_text(tmp_path):
    figure = [
        (MARGIN_X, 700, "113"),
        (BODY_X, 700, "Key: D = device"),
        (200, 600, "D1"),
        (300, 600, "D2"),
    ]
    pages = [
        [(BODY_X, 760, "Spec header"), *pdfgen.numbered_page(100, SIX)],
        table_page([106, 107], footer=2),  # the one page the base misses
        pdfgen.numbered_page(108, FIVE),
        figure,  # a short page the base numbers: it continues 112
        pdfgen.numbered_page(114, SIX),
    ]
    r = extract(tmp_path, pages)
    lm = r.linemap["pages"]
    assert lm["2"] == entry(106, 2)
    # what the base branch records and prints for the other four pages
    assert lm["1"] == entry(100, 6, at=1)
    assert page_lines(r.text, 1) == ["Spec header", *SIX]
    assert lm["3"] == entry(108, 5)
    assert page_lines(r.text, 3) == FIVE
    assert lm["4"] == entry(113, 1)
    fourth = page_lines(r.text, 4)
    assert fourth[0] == "Key: D = device"
    assert fourth[1].split() == ["D1", "D2"]
    assert lm["5"] == entry(114, 6)
    assert page_lines(r.text, 5) == SIX
    assert list(lm) == ["1", "2", "3", "4", "5"]
