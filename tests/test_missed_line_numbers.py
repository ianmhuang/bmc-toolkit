"""Pages whose margin numbers the page-by-page rules turn down are numbered
from the number column the document's other pages show, and only when the
numbers fit between those of the pages around them."""

import json

import pytest

from bmc_toolkit.spec import extract as ex
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok

pytest.importorskip("pypdfium2")

URL = "https://example.test/DSP0236_1.3.3.pdf"
SIX = ["a", "b", "c", "d", "e", "f"]
OFFSETS = [0, 1, 2, 3, 4]


def page_lines(text: str, n: int) -> list[str]:
    marker = ex.PAGE_MARKER.format(n=n)
    start = text.index(marker) + len(marker) + 1
    end = text.find("=== page", start)
    return text[start : end if end >= 0 else None].splitlines()


def table_page(numbers, offsets=OFFSETS, footer=None, x_number=37.0):
    """A page a table fills: a margin number before each of a few text
    lines, then table rows that start with a byte offset (integers, more of
    them than margin numbers), and the page number at the foot."""
    items = []
    y = 720.0
    for n in numbers:
        items += [(x_number, y, str(n)), (72, y, f"Table text {n}")]
        y -= 14
    for off in offsets:
        items += [(75, y, str(off)), (120, y, "uint8"), (200, y, f"field at {off}")]
        y -= 14
    if footer is not None:
        items += [(72, 40, str(footer)), (284, 40, "Published")]
    return items


def extract(tmp_path, pages, name="d.pdf"):
    return ex.extract_pdf(pdfgen.write_pdf(tmp_path / name, pages))


def test_a_table_page_is_numbered_from_its_margin_numbers(tmp_path):
    pages = [pdfgen.numbered_page(100, SIX), table_page([106, 107], footer=2)]
    r = extract(tmp_path, pages)
    assert r.numbered_pages == 2
    entry = r.linemap["pages"]["2"]
    assert (entry["first"], entry["last"]) == (106, 107)
    assert entry["lines"] == {"0": 106, "1": 107}
    got = page_lines(r.text, 2)
    assert got[:2] == ["Table text 106", "Table text 107"]
    # the byte offsets and the page number are text, not line numbers
    assert [ln.split()[0] for ln in got[2:7]] == ["0", "1", "2", "3", "4"]
    assert got[-1].split() == ["2", "Published"]


def test_short_pages_after_a_page_left_unnumbered_are_numbered(tmp_path):
    gap = table_page([106, 108])  # not consecutive: stays as it is
    short = [(37, 700, "109"), (72, 700, "Key: D = device"), (37, 686, "110")]
    r = extract(tmp_path, [pdfgen.numbered_page(100, SIX), gap, short])
    assert list(r.linemap["pages"]) == ["1", "3"]
    assert r.linemap["pages"]["3"]["lines"] == {"0": 109, "1": 110}
    assert page_lines(r.text, 3)[0] == "Key: D = device"
    assert page_lines(r.text, 2)[0].split() == ["106", "Table", "text", "106"]


def test_every_page_between_two_numbered_pages_is_recovered(tmp_path):
    pages = [
        pdfgen.numbered_page(100, SIX),
        table_page([106, 107], footer=2),
        [(37, 700, "108"), (72, 700, "One line")],
        table_page([109], footer=4),
        pdfgen.numbered_page(110, SIX),
    ]
    r = extract(tmp_path, pages)
    lm = r.linemap["pages"]
    assert [(n, lm[n]["first"], lm[n]["last"]) for n in lm] == [
        ("1", 100, 105),
        ("2", 106, 107),
        ("3", 108, 108),
        ("4", 109, 109),
        ("5", 110, 115),
    ]
    assert r.numbered_pages == 5


def test_right_aligned_margin_numbers_are_recovered_too(tmp_path):
    def right(n, y, text):
        return [(54 - 5.56 * len(str(n)), y, str(n)), (72, y, text)]

    first = [
        item
        for i, n in enumerate(range(96, 102))
        for item in right(n, 700 - 14 * i, "t")
    ]
    second = right(102, 720, "Table text") + right(103, 706, "more")
    for i, off in enumerate(OFFSETS):
        second += [(75, 690 - 14 * i, str(off)), (120, 690 - 14 * i, "uint8")]
    r = extract(tmp_path, [first, second])
    assert r.linemap["pages"]["2"]["lines"] == {"0": 102, "1": 103}
    assert page_lines(r.text, 2)[0] == "Table text"


@pytest.mark.parametrize(
    "numbers",
    [
        [106, 108],  # not consecutive
        [200, 201],  # not before the next numbered page
        [50, 51],  # not after the numbered page before
        [106, 107, 300],  # one integer of the column out of place
    ],
)
def test_numbers_that_do_not_fit_leave_the_page_as_it_is(tmp_path, numbers):
    odd = table_page(numbers)
    pages = [pdfgen.numbered_page(100, SIX), odd, pdfgen.numbered_page(110, SIX)]
    r = extract(tmp_path, pages)
    assert list(r.linemap["pages"]) == ["1", "3"]
    alone = extract(tmp_path, [odd], "alone.pdf")
    assert page_lines(r.text, 2) == page_lines(alone.text, 1)


def test_integers_outside_the_number_column_are_never_line_numbers(tmp_path):
    # consecutive and in range, but in the table's column, not the margin's
    rows = table_page([], offsets=[107, 108, 109])
    r = extract(tmp_path, [pdfgen.numbered_page(100, SIX), rows])
    assert list(r.linemap["pages"]) == ["1"]
    assert page_lines(r.text, 2)[0].split()[0] == "107"


def test_a_document_without_a_numbered_page_gets_no_line_map(tmp_path):
    pages = [table_page([1, 2]), table_page([3, 4]), [(37, 700, "5"), (72, 700, "x")]]
    r = extract(tmp_path, pages)
    assert r.numbered_pages == 0
    assert r.linemap["pages"] == {}


def test_pages_before_the_first_numbered_page_are_left_alone(tmp_path):
    front = [(37, 700, "98"), (72, 700, "Front matter"), (37, 686, "99")]
    r = extract(tmp_path, [front, pdfgen.numbered_page(100, SIX)])
    assert list(r.linemap["pages"]) == ["2"]


def test_pages_numbered_before_keep_their_entry_and_text(tmp_path):
    first, last = pdfgen.numbered_page(100, SIX), pdfgen.numbered_page(108, SIX)
    with_table = extract(tmp_path, [first, table_page([106, 107]), last])
    without = extract(tmp_path, [first, pdfgen.plain_page(["filler"]), last], "w.pdf")
    for n in ("1", "3"):
        assert with_table.linemap["pages"][n] == without.linemap["pages"][n]
        assert page_lines(with_table.text, int(n)) == page_lines(without.text, int(n))
    assert "2" in with_table.linemap["pages"]
    assert "2" not in without.linemap["pages"]


# ------------------------------------------------------------------ the CLI


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    """DSP0236 with a table page between two numbered pages, extracted."""
    pages = [
        pdfgen.numbered_page(100, SIX),
        table_page([106, 107], footer=2),
        pdfgen.numbered_page(108, SIX),
    ]
    pdf = pdfgen.write_pdf(tmp_path / "t.pdf", pages).read_bytes()
    scripted.responses[URL] = ok(pdf)
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


def test_page_and_find_name_the_recovered_lines(held, catalog_file, capsys):
    code, out = run(capsys, "page", "DSP0236", "2", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].split(" | ")[3:5] == ["PDF page 2", "lines 106-107"]
    assert lines[1] == " 106  Table text 106"
    assert lines[2] == " 107  Table text 107"
    # a table row keeps its offset and has no printed number
    assert lines[3].split()[:2] == ["0", "uint8"]
    code, out = run(
        capsys, "find", "DSP0236", "Table text 107", catalog_file=catalog_file
    )
    assert code == 0, out
    assert out.splitlines()[0].startswith("DSP0236 p.2 line 107 | ")


def test_an_extract_of_the_version_before_is_made_again(held, catalog_file, capsys):
    # the one place that names the number: 4 numbered page by page only
    assert ex.EXTRACTOR_VERSION == 5
    meta_path = held / ex.META_NAME
    meta = json.loads(meta_path.read_text("utf-8"))
    assert meta["extractor_version"] == ex.EXTRACTOR_VERSION
    # what version 4 left: no entry for the table page
    meta_path.write_text(json.dumps({**meta, "extractor_version": 4}), "utf-8")
    linemap_path = held / ex.LINEMAP_NAME
    linemap = json.loads(linemap_path.read_text("utf-8"))
    del linemap["pages"]["2"]
    linemap_path.write_text(json.dumps(linemap), "utf-8")
    code, out = run(capsys, "page", "DSP0236", "2", catalog_file=catalog_file)
    assert code == 0, out
    cite = [ln for ln in out.splitlines() if ln.startswith("cite:")][0]
    assert cite.split(" | ")[4] == "lines 106-107"
    assert json.loads(meta_path.read_text("utf-8"))["extractor_version"] == 5
    # the file keeps its shape: pages, each with first, last and lines
    stored = json.loads(linemap_path.read_text("utf-8"))
    assert set(stored) == {"pages"}
    assert set(stored["pages"]["2"]) == {"first", "last", "lines"}
