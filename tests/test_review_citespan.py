"""Reviewer acceptance tests for the cite: section field listing every
section a page spans (AC-1 to AC-4), black-box through the CLI on a
synthetic PDF shaped like the reported case (a page that starts inside one
section and holds the headings of the next and its sub-section), and
through ``Version.cite`` for the page-range form no command prints today.
No network: the scripted client serves the bytes."""

from pathlib import Path

import pytest

from bmc_toolkit.spec import search as se
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok

pytest.importorskip("pypdfium2")

URL = "https://example.test/DSP0236_1.3.3.pdf"


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def spanning_doc(tmp_path):
    """Four numbered pages. Page 2 starts inside 6 Symbols and holds the
    headings of 7 and 7.1; page 3 lies within 7.1; page 4 opens with 8."""
    page1 = pdfgen.numbered_page(
        1,
        [
            "Running header",
            "6 Symbols and abbreviated terms",
            "Term one means the first thing.",
            "Term two means the second thing.",
        ],
    )
    page2 = pdfgen.numbered_page(
        5,
        [
            "Term three means the third thing.",
            "7 SPDM message exchanges",
            "An exchange is a request and its response.",
            "7.1 Request and response messages",
            "A request carries a code.",
        ],
    )
    page3 = pdfgen.numbered_page(
        10,
        [
            "A response repeats the code.",
            "A timeout ends the exchange.",
        ],
    )
    page4 = pdfgen.numbered_page(
        12,
        [
            "8 Transport binding",
            "The binding carries the bytes.",
        ],
    )
    return pdfgen.write_pdf(
        tmp_path / "spanning.pdf",
        [page1, page2, page3, page4],
        bookmarks=[
            (0, "6 Symbols and abbreviated terms", 0),
            (0, "7 SPDM message exchanges", 1),
            (1, "7.1 Request and response messages", 1),
            (0, "8 Transport binding", 3),
        ],
    ).read_bytes()


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    scripted.responses[URL] = ok(spanning_doc(tmp_path))
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


def cite_fields(out, index=0):
    cites = [ln for ln in out.splitlines() if ln.startswith("cite:")]
    return cites[index].split(" | ")


# ---------------------------------------------------------------- AC-1


def test_page_starting_mid_section_lists_owner_then_headings_on_it(
    held, catalog_file, capsys
):
    code, out = run(capsys, "page", "DSP0236", "2", catalog_file=catalog_file)
    assert code == 0, out
    fields = cite_fields(out)
    # the entry in force at the top, then 7 and its sub-section 7.1, in
    # Outline order, joined by "; "
    assert fields[2] == (
        "6 Symbols and abbreviated terms; 7 SPDM message exchanges; "
        "7.1 Request and response messages"
    )
    assert fields[3] == "PDF page 2"
    assert fields[4] == "lines 5-9"
    assert out.count("cite:") == 1


def test_page_within_one_section_is_unchanged(held, catalog_file, capsys):
    code, out = run(capsys, "page", "DSP0236", "3", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[0] == " | ".join(
        [
            "cite: mctp",
            "DSP0236 1.3.3",
            "7.1 Request and response messages",
            "PDF page 3",
            "lines 10-11",
            URL,
            str(held),
        ]
    )


def test_page_whose_first_line_is_a_heading_lists_that_section_once(
    held, catalog_file, capsys
):
    code, out = run(capsys, "page", "DSP0236", "4", catalog_file=catalog_file)
    assert code == 0, out
    assert cite_fields(out)[2] == "8 Transport binding"


def test_page_range_prints_one_cite_per_page_each_with_its_own_sections(
    held, catalog_file, capsys
):
    code, out = run(
        capsys, "page", "DSP0236", "1", "--to", "3", catalog_file=catalog_file
    )
    assert code == 0, out
    cites = [ln for ln in out.splitlines() if ln.startswith("cite:")]
    assert [c.split(" | ")[2] for c in cites] == [
        "6 Symbols and abbreviated terms",
        "6 Symbols and abbreviated terms; 7 SPDM message exchanges; "
        "7.1 Request and response messages",
        "7.1 Request and response messages",
    ]
    assert [c.split(" | ")[3] for c in cites] == [
        "PDF page 1",
        "PDF page 2",
        "PDF page 3",
    ]


# ---------------------------------------------------------------- AC-3


def test_render_cite_follows_the_page_rule(held, catalog_file, capsys):
    code, out = run(
        capsys, "render", "DSP0236", "--page", "2", catalog_file=catalog_file
    )
    assert code == 0, out
    fields = out.splitlines()[1].split(" | ")
    assert fields[0] == "cite: mctp"
    assert fields[2] == (
        "6 Symbols and abbreviated terms; 7 SPDM message exchanges; "
        "7.1 Request and response messages"
    )
    assert fields[3:5] == ["PDF page 2", "lines rendered page"]


def test_find_hits_keep_their_per_line_section(held, catalog_file, capsys):
    code, out = run(capsys, "find", "DSP0236", "request", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip().splitlines() == [
        "DSP0236 p.2 line 7 | 7 SPDM message exchanges | "
        "An exchange is a request and its response.",
        "DSP0236 p.2 line 8 | 7.1 Request and response messages | "
        "7.1 Request and response messages",
        "DSP0236 p.2 line 9 | 7.1 Request and response messages | "
        "A request carries a code.",
    ]
    assert "; " not in out


# ---------------------------------------------------------------- AC-4


def test_page_section_names_that_section_only_on_every_page(
    held, catalog_file, capsys
):
    # 7 runs from page 2 to page 4 (where 8 begins): three pages, each
    # cite: naming 7 alone, though page 2 also holds 7.1 and page 3 is 7.1
    code, out = run(
        capsys, "page", "DSP0236", "--section", "7", catalog_file=catalog_file
    )
    assert code == 0, out
    cites = [ln for ln in out.splitlines() if ln.startswith("cite:")]
    assert len(cites) == 3
    assert [c.split(" | ")[2] for c in cites] == ["7 SPDM message exchanges"] * 3
    code, out = run(
        capsys, "page", "DSP0236", "--section", "7.1", catalog_file=catalog_file
    )
    assert code == 0, out
    cites = [ln for ln in out.splitlines() if ln.startswith("cite:")]
    assert [c.split(" | ")[2] for c in cites] == [
        "7.1 Request and response messages"
    ] * len(cites)


# ---------------------------------------------------- AC-2 (Version.cite)


def make_version(**overrides) -> se.Version:
    """The same document, built without a PDF, for the range form."""
    base = dict(
        family="mctp",
        document="DSP0236",
        version="1.3.3",
        path=Path("lib") / "specs" / "mctp" / "DSP0236" / "1.3.3",
        origin=URL,
        pages=[
            [
                "Running header",
                "6 Symbols and abbreviated terms",
                "Term one means the first thing.",
            ],
            [
                "Term three means the third thing.",
                "7 SPDM message exchanges",
                "7.1 Request and response messages",
            ],
            ["A response repeats the code."],
            ["8 Transport binding", "The binding carries the bytes."],
        ],
        outline=[
            {"level": 0, "title": "6 Symbols and abbreviated terms", "page": 1},
            {"level": 0, "title": "7 SPDM message exchanges", "page": 2},
            {"level": 1, "title": "7.1 Request and response messages", "page": 2},
            {"level": 0, "title": "8 Transport binding", "page": 4},
        ],
    )
    base.update(overrides)
    return se.Version(**base)


def test_range_cite_lists_the_owner_of_the_first_page_then_every_heading_in_range():
    v = make_version()
    # page 2 starts inside 6; 7 and 7.1 begin on it; 8 begins on page 4
    fields = v.cite(2, lines="table 1", last=4).split(" | ")
    assert fields[2] == (
        "6 Symbols and abbreviated terms; 7 SPDM message exchanges; "
        "7.1 Request and response messages; 8 Transport binding"
    )
    assert fields[3] == "PDF pages 2-4"
    # a range inside one section: that section alone
    fields = v.cite(3, lines="table 1", last=3).split(" | ")
    assert fields[2:4] == ["7.1 Request and response messages", "PDF page 3"]
    # the owner of the first page comes first even when its heading is on
    # an earlier page
    fields = v.cite(1, lines="table 1", last=2).split(" | ")
    assert fields[2] == (
        "6 Symbols and abbreviated terms; 7 SPDM message exchanges; "
        "7.1 Request and response messages"
    )


def test_range_cite_with_an_explicit_section_names_it_alone():
    v = make_version()
    entry = se.Section("7 SPDM message exchanges", 2)
    assert v.cite(2, lines="table 1", last=4, section=entry).split(" | ")[2] == (
        "7 SPDM message exchanges"
    )
    assert v.cite(2, lines="table 1", last=4, section="Table 5 - Codes").split(
        " | "
    )[2] == ("Table 5 - Codes")


def test_range_past_the_last_page_is_clipped_and_an_empty_outline_prints_a_dash():
    v = make_version()
    clipped = v.cite(3, last=9).split(" | ")[2]
    assert clipped == "7.1 Request and response messages; 8 Transport binding"
    assert clipped == v.cite(3, last=4).split(" | ")[2]
    bare = make_version(outline=[])
    assert bare.cite(2).split(" | ")[2] == "-"
    assert bare.cite(2, last=4).split(" | ")[2] == "-"


def test_an_entry_placed_in_the_range_without_its_heading_is_not_added():
    # the bookmark for 7.2 points at page 3 but its heading is not there
    # (a contents-page entry): the range lists only what the pages show
    v = make_version(
        outline=[
            {"level": 0, "title": "6 Symbols and abbreviated terms", "page": 1},
            {"level": 0, "title": "7 SPDM message exchanges", "page": 2},
            {"level": 1, "title": "7.1 Request and response messages", "page": 2},
            {"level": 1, "title": "7.2 Generic message format", "page": 3},
        ]
    )
    assert v.cite(2, lines="table 1", last=3).split(" | ")[2] == (
        "6 Symbols and abbreviated terms; 7 SPDM message exchanges; "
        "7.1 Request and response messages"
    )
    # on its own page it owns the top (nothing else claims it) and is the
    # only entry listed
    assert v.cite(3).split(" | ")[2] == "7.2 Generic message format"
