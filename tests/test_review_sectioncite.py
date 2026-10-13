"""Reviewer acceptance tests for `page DOC --section Q` (AC-6): every page
of the range starts with the `cite:` line `page DOC N` prints for it, the
pages chosen and the text under each line stay as they were. Black-box
through the CLI on a synthetic PDF whose section 7.1 starts in the middle of
one page and ends in the middle of the next. No network."""

import pytest

from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok

pytest.importorskip("pypdfium2")

URL = "https://example.test/DSP0236_1.3.3.pdf"

PAGE_2 = "6 Symbols; 7 Exchanges; 7.1 Requests"
PAGE_3 = "7.1 Requests; 7.2 Responses"


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def exchanges_doc(tmp_path):
    """Page 2 ends section 6 and holds the headings of 7 and 7.1; page 3
    continues 7.1 and holds the heading of 7.2; page 4 opens with 8."""
    page1 = pdfgen.numbered_page(
        1, ["Front matter", "6 Symbols", "Term one means the first thing."]
    )
    page2 = pdfgen.numbered_page(
        4,
        [
            "Term two means the second thing.",
            "7 Exchanges",
            "An exchange is one question and one answer.",
            "7.1 Requests",
            "The asking side sends a code.",
        ],
    )
    page3 = pdfgen.numbered_page(
        9,
        [
            "The asking side may try again.",
            "7.2 Responses",
            "The answering side repeats the code.",
        ],
    )
    page4 = pdfgen.numbered_page(12, ["8 Binding", "The binding carries the bytes."])
    return pdfgen.write_pdf(
        tmp_path / "exchanges.pdf",
        [page1, page2, page3, page4],
        bookmarks=[
            (0, "6 Symbols", 0),
            (0, "7 Exchanges", 1),
            (1, "7.1 Requests", 1),
            (1, "7.2 Responses", 2),
            (0, "8 Binding", 3),
        ],
    ).read_bytes()


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    scripted.responses[URL] = ok(exchanges_doc(tmp_path))
    code, out = run(
        capsys, "fetch", "DSP0236", "--no-extract", catalog_file=catalog_file
    )
    assert code == 0, out
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


def cite_lines(out):
    return [ln for ln in out.splitlines() if ln.startswith("cite:")]


def single(capsys, n, catalog_file):
    code, out = run(capsys, "page", "DSP0236", str(n), catalog_file=catalog_file)
    assert code == 0, out
    return out


@pytest.mark.parametrize("query", ["7.1", "7", "requests"])
def test_ac6_every_page_of_the_range_gets_the_cite_line_page_n_prints(
    held, catalog_file, capsys, query
):
    code, out = run(
        capsys, "page", "DSP0236", "--section", query, catalog_file=catalog_file
    )
    assert code == 0, out
    lines = cite_lines(out)
    # the pages chosen: 7 and 7.1 both run from page 2 to page 3
    assert [ln.split(" | ")[3] for ln in lines] == ["PDF page 2", "PDF page 3"]
    # each page's own sections; both read the queried section alone before
    assert [ln.split(" | ")[2] for ln in lines] == [PAGE_2, PAGE_3]
    assert [ln.split(" | ")[4] for ln in lines] == ["lines 4-8", "lines 9-11"]
    # the same line, and the same text under it, as `page N` gives
    pages = [single(capsys, n, catalog_file) for n in (2, 3)]
    assert out == "\n".join(pages)
    code, ranged = run(
        capsys, "page", "DSP0236", "2", "--to", "3", catalog_file=catalog_file
    )
    assert code == 0 and out == ranged


def test_ac6_a_one_page_section_lists_what_that_page_spans(held, catalog_file, capsys):
    # 7.2 starts on page 3 and ends there: 8 opens page 4
    code, out = run(
        capsys, "page", "DSP0236", "--section", "7.2", catalog_file=catalog_file
    )
    assert code == 0, out
    assert out == single(capsys, 3, catalog_file)
    (line,) = cite_lines(out)
    assert line.split(" | ")[2:4] == [PAGE_3, "PDF page 3"]
    assert "8 Binding" not in out


def test_ac6_the_refusals_of_page_section_are_unchanged(held, catalog_file, capsys):
    # guard: this also holds on the base branch
    code, out = run(
        capsys, "page", "DSP0236", "--section", "99", catalog_file=catalog_file
    )
    assert code == 2 and "no matching section" in out
    code, out = run(
        capsys,
        "page",
        "DSP0236",
        "--section",
        "7.1",
        "--max-pages",
        "1",
        catalog_file=catalog_file,
    )
    assert code == 2 and "pages 2-3 are 2 pages" in out
    assert "cite:" not in out
