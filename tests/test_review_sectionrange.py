"""Reviewer acceptance tests for the section follow-ups closed before 1.0.0:
a section's end page stops before a page the next heading opens (AC-2),
and an approximate Outline entry counts on the page its heading is found
on (AC-3). Black-box through the CLI on a synthetic PDF; ``Version`` is
used directly for the Outlines an extractor run cannot produce. No
network: the scripted client serves the bytes."""

import json
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


def range_doc(tmp_path):
    """Four numbered pages. 1 and 2 are on page 1; 3 Commands and 3.1 start
    on page 2 (3 Commands is its second line); 4 Transport opens page 3 (its
    heading is the first line); 5 Annex is the second line of page 4."""
    page1 = pdfgen.numbered_page(
        1,
        [
            "1 Introduction",
            "Intro text here.",
            "More intro text.",
            "2 Scope",
            "Scope text here.",
        ],
    )
    page2 = pdfgen.numbered_page(
        6,
        [
            "Scope text continues.",
            "3 Commands",
            "3.1 Get Device ID",
            "Get Device ID returns the id.",
        ],
    )
    page3 = pdfgen.numbered_page(10, ["4 Transport", "The transport carries bytes."])
    page4 = pdfgen.numbered_page(
        12, ["Annex material follows.", "5 Annex", "Annex text here."]
    )
    return pdfgen.write_pdf(
        tmp_path / "range.pdf",
        [page1, page2, page3, page4],
        bookmarks=[
            (0, "1 Introduction", 0),
            (0, "2 Scope", 0),
            (0, "3 Commands", 1),
            (1, "3.1 Get Device ID", 1),
            (0, "4 Transport", 2),
            (0, "5 Annex", 3),
        ],
    ).read_bytes()


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    scripted.responses[URL] = ok(range_doc(tmp_path))
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


def cite_fields(out, index=0):
    cites = [ln for ln in out.splitlines() if ln.startswith("cite:")]
    return cites[index].split(" | ")


def cite_pages(out):
    return [ln.split(" | ")[3] for ln in out.splitlines() if ln.startswith("cite:")]


def make_version(pages, outline):
    return se.Version(
        family="mctp",
        document="DSP0236",
        version="1.3.3",
        path=Path("/lib/specs/mctp/DSP0236/1.3.3"),
        origin="https://example.test/DSP0236_1.3.3.pdf",
        pages=pages,
        outline=outline,
    )


def set_outline_page(vdir, title, page, approximate):
    """Rewrite one Outline entry as a contents page would have placed it;
    the Extract stays current, so the reading commands read it as is."""
    path = vdir / "outline.json"
    outline = json.loads(path.read_text(encoding="utf-8"))
    for entry in outline:
        if entry["title"] == title:
            entry["page"] = page
            if approximate:
                entry["approximate"] = True
            else:
                entry.pop("approximate", None)
    path.write_text(json.dumps(outline), encoding="utf-8")


# ---------------------------------------------------------------- AC-2


def test_section_ends_before_a_page_the_next_heading_opens(held, catalog_file, capsys):
    # 4 Transport is the first line of page 3: page 3 holds nothing of 3
    # Commands or of 3.1, so both end on page 2
    code, out = run(capsys, "section", "DSP0236", "3", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip().splitlines() == [
        "0 | 3 Commands | pages 2-2",
        "1 | 3.1 Get Device ID | pages 2-2",
    ]


def test_section_keeps_the_page_when_the_next_heading_is_lower_or_absent(
    held, catalog_file, capsys
):
    # 3 Commands is the second line of page 2: page 2 still holds 2 Scope
    code, out = run(capsys, "section", "DSP0236", "2", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip() == "0 | 2 Scope | pages 1-2"
    # 5 Annex is the second line of page 4: page 4 still holds 4 Transport
    code, out = run(capsys, "section", "DSP0236", "4", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip() == "0 | 4 Transport | pages 3-4"
    # the last entry runs to the last page
    code, out = run(capsys, "section", "DSP0236", "5", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip() == "0 | 5 Annex | pages 4-4"


def test_page_section_prints_only_the_pages_holding_the_section(
    held, catalog_file, capsys
):
    code, out = run(
        capsys, "page", "DSP0236", "--section", "3", catalog_file=catalog_file
    )
    assert code == 0, out
    assert cite_pages(out) == ["PDF page 2"]
    assert cite_fields(out)[2] == "3 Commands"
    assert "4 Transport" not in out  # page 3 is not printed
    code, out = run(
        capsys, "page", "DSP0236", "--section", "3.1", catalog_file=catalog_file
    )
    assert code == 0, out
    assert cite_pages(out) == ["PDF page 2"]
    # a heading lower on the next page: that page is still printed
    code, out = run(
        capsys, "page", "DSP0236", "--section", "2", catalog_file=catalog_file
    )
    assert code == 0, out
    assert cite_pages(out) == ["PDF page 1", "PDF page 2"]
    assert cite_fields(out, 0)[2] == "2 Scope"
    assert cite_fields(out, 1)[2] == "2 Scope"


def test_an_entry_starting_on_the_page_the_next_one_opens_keeps_that_page():
    # 2.1 is a contents-page entry whose heading is not on page 2; 2.2 opens
    # page 2: 2.1 still ends on page 2, the page it starts on
    v = make_version(
        pages=[["2 Scope", "text"], ["2.2 More", "text"], ["3 Next", "text"]],
        outline=[
            {"level": 0, "title": "2 Scope", "page": 1},
            {"level": 1, "title": "2.1 Lines", "page": 2},
            {"level": 1, "title": "2.2 More", "page": 2},
            {"level": 0, "title": "3 Next", "page": 3},
        ],
    )
    ends = {s.title: end for _, s, end in v.match_sections("2")}
    assert ends == {"2 Scope": 2, "2.1 Lines": 2, "2.2 More": 2}
    # the next heading not found on its page (a contents-page entry): the
    # end page is unchanged
    v = make_version(
        pages=[["1 First", "text"], ["body only", "text"]],
        outline=[
            {"level": 0, "title": "1 First", "page": 1},
            {"level": 0, "title": "2 Second", "page": 2},
        ],
    )
    assert {s.title: end for _, s, end in v.match_sections("1")} == {"1 First": 2}


# ---------------------------------------------------------------- AC-3


def test_an_approximate_entry_placed_one_page_early_starts_at_its_heading():
    pages = [
        ["1 Intro", "intro text"],
        ["still intro", "more intro"],
        ["2 Scope", "scope text"],
        ["3 Next", "next text"],
    ]
    outline = [
        {"level": 0, "title": "1 Intro", "page": 1},
        {"level": 0, "title": "2 Scope", "page": 2, "approximate": True},
        {"level": 0, "title": "3 Next", "page": 4},
    ]
    v = make_version(pages, outline)
    # the heading is on page 3: page 2 belongs to 1 Intro top to bottom
    assert v.owning_section(2, 0).title == "1 Intro"
    assert v.owning_section(2, 1).title == "1 Intro"
    assert v.owning_section(3, 0).label == "~2 Scope"
    assert [s.label for s in v.spanned_sections(2)] == ["1 Intro"]
    assert [s.label for s in v.spanned_sections(3)] == ["~2 Scope"]
    assert v.cite(2, "-").split(" | ")[2] == "1 Intro"
    assert v.cite(3, "-").split(" | ")[2] == "~2 Scope"
    # a search hit on page 2 is 1 Intro's, one on page 3 is 2 Scope's
    hits = list(v.find("intro"))
    assert [(h.page, h.section.title) for h in hits] == [
        (1, "1 Intro"),
        (1, "1 Intro"),
        (2, "1 Intro"),
        (2, "1 Intro"),
    ]
    assert [h.section.label for h in v.find("scope text")] == ["~2 Scope"]


def test_an_approximate_entry_placed_one_page_late_starts_at_its_heading():
    pages = [
        ["1 Intro", "intro text"],
        ["still intro", "more intro"],
        ["2 Scope", "scope text"],
        ["3 Next", "next text"],
    ]
    outline = [
        {"level": 0, "title": "1 Intro", "page": 1},
        {"level": 0, "title": "2 Scope", "page": 4, "approximate": True},
        {"level": 0, "title": "3 Next", "page": 4},
    ]
    v = make_version(pages, outline)
    # the heading is on page 3, the page before: 2 Scope owns page 3
    assert v.owning_section(3, 0).label == "~2 Scope"
    assert v.owning_section(4, 0).title == "3 Next"
    assert [s.label for s in v.spanned_sections(3)] == ["~2 Scope"]
    assert [s.label for s in v.spanned_sections(4)] == ["3 Next"]
    assert [s.label for s in v.spanned_sections(2, 4)] == [
        "1 Intro",
        "~2 Scope",
        "3 Next",
    ]


def test_exact_and_well_placed_entries_are_unchanged():
    pages = [
        ["1 Intro", "intro text"],
        ["still intro", "more intro"],
        ["2 Scope", "scope text"],
        ["3 Next", "next text"],
    ]
    # an exact entry on a page without its heading is taken as placed
    v = make_version(
        pages,
        [
            {"level": 0, "title": "1 Intro", "page": 1},
            {"level": 0, "title": "2 Scope", "page": 2},
            {"level": 0, "title": "3 Next", "page": 4},
        ],
    )
    assert v.owning_section(2, 0).title == "2 Scope"
    assert [s.title for s in v.spanned_sections(2)] == ["2 Scope"]
    assert [s.title for s in v.spanned_sections(3)] == ["2 Scope"]
    assert v.cite(2, "-").split(" | ")[2] == "2 Scope"
    # an approximate entry whose heading is on its own page
    v = make_version(
        pages,
        [
            {"level": 0, "title": "1 Intro", "page": 1},
            {"level": 0, "title": "2 Scope", "page": 3, "approximate": True},
            {"level": 0, "title": "3 Next", "page": 4},
        ],
    )
    assert v.owning_section(2, 1).title == "1 Intro"
    assert v.owning_section(3, 0).label == "~2 Scope"
    assert [s.label for s in v.spanned_sections(2)] == ["1 Intro"]
    assert [s.label for s in v.spanned_sections(3)] == ["~2 Scope"]
    assert v.cite(3, "-").split(" | ")[2] == "~2 Scope"
    # an approximate entry whose heading is nowhere near stays where the
    # Outline put it, and one placed outside the document is left alone
    v = make_version(
        pages,
        [
            {"level": 0, "title": "1 Intro", "page": 1},
            {"level": 0, "title": "9 Gone", "page": 2, "approximate": True},
            {"level": 0, "title": "3 Next", "page": 4},
        ],
    )
    assert v.owning_section(2, 0).label == "~9 Gone"
    assert v.placed_page(se.Section("9 Gone", 2, approximate=True)) == 2
    assert v.placed_page(se.Section("9 Gone", 7, approximate=True)) == 7
    assert v.placed_page(se.Section("9 Gone", 0, approximate=True)) == 0


def test_ranges_run_between_placed_pages_and_never_start_on_a_contents_page():
    # round 2: match_sections starts an approximate entry where its heading
    # is and ends the one before it there too, as owning_section does
    pages = [
        ["1 Intro", "intro text"],
        ["still intro", "more intro"],
        ["2 Scope", "scope text"],
        ["3 Next", "next text"],
    ]
    # placed one page early: 2 Scope starts on page 3 and 1 Intro ends on
    # page 2 (2 Scope opens page 3)
    v = make_version(
        pages,
        [
            {"level": 0, "title": "1 Intro", "page": 1},
            {"level": 0, "title": "2 Scope", "page": 2, "approximate": True},
            {"level": 0, "title": "3 Next", "page": 4},
        ],
    )
    got = {s.label: (s.page, end) for _, s, end in v.match_sections("2")}
    assert got == {"~2 Scope": (3, 3)}
    got = {s.label: (s.page, end) for _, s, end in v.match_sections("1")}
    assert got == {"1 Intro": (1, 2)}
    # placed one page late: 2 Scope starts on page 3, the page before
    v = make_version(
        pages,
        [
            {"level": 0, "title": "1 Intro", "page": 1},
            {"level": 0, "title": "2 Scope", "page": 4, "approximate": True},
            {"level": 0, "title": "3 Next", "page": 4},
        ],
    )
    got = {s.label: (s.page, end) for _, s, end in v.match_sections("2")}
    assert got == {"~2 Scope": (3, 3)}
    got = {s.label: (s.page, end) for _, s, end in v.match_sections("1")}
    assert got == {"1 Intro": (1, 2)}
    # a contents line naming the entry on the page before is not its
    # heading: the entry stays on its Outline page and no range starts on
    # the contents page
    v = make_version(
        pages=[["Contents", "1 Intro ...... 1", "2 Overview ...... 2"], ["body"]],
        outline=[
            {"level": 0, "title": "1 Intro", "page": 2, "approximate": True},
            {"level": 0, "title": "2 Overview", "page": 2, "approximate": True},
        ],
    )
    assert v.placed_page(se.Section("2 Overview", 2, approximate=True)) == 2
    got = {s.label: (s.page, end) for _, s, end in v.match_sections("overview")}
    assert got == {"~2 Overview": (2, 2)}
    assert v.spanned_sections(1) == []
    assert v.cite(1, "-").split(" | ")[2] == "-"


def test_a_contents_line_with_a_wide_gap_is_not_a_heading_either():
    # round 3: the contents-line rule is the extractor's own (a section
    # number, a title, dot leaders or a wide gap, then a page number), so a
    # contents page without dot leaders is refused the same way, while a
    # heading that merely ends in a number is still a heading
    pages = [["Contents", "1 Intro      1", "2 Overview      2"], ["body"]]
    outline = [
        {"level": 0, "title": "1 Intro", "page": 2, "approximate": True},
        {"level": 0, "title": "2 Overview", "page": 2, "approximate": True},
    ]
    v = make_version(pages, outline)
    assert v.placed_page(se.Section("2 Overview", 2, approximate=True)) == 2
    assert v.spanned_sections(1) == []
    assert v.cite(1, "-").split(" | ")[2] == "-"
    # "2 Overview 2" has neither leaders nor a gap: a heading ending in a
    # number, found on the page before, places the entry there
    v = make_version(
        pages=[["1 Intro", "2 Overview 2", "text"], ["body"]],
        outline=[
            {"level": 0, "title": "1 Intro", "page": 1},
            {"level": 0, "title": "2 Overview", "page": 2, "approximate": True},
        ],
    )
    assert v.placed_page(se.Section("2 Overview", 2, approximate=True)) == 1
    assert [s.label for s in v.spanned_sections(1)] == ["1 Intro", "~2 Overview"]
    assert v.owning_section(2, 0).label == "~2 Overview"


def test_the_cli_section_and_page_agree_with_cite_on_an_approximate_entry(
    held, catalog_file, capsys
):
    # round 2: a contents page put 4 Transport on page 2; its heading opens
    # page 3. section and page --section start it on page 3, and 3 Commands
    # ends on page 2, the page before the one 4 Transport opens
    set_outline_page(held, "4 Transport", 2, approximate=True)
    code, out = run(capsys, "section", "DSP0236", "4", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip() == "0 | 4 Transport | pages ~3-4"
    code, out = run(capsys, "section", "DSP0236", "3", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip().splitlines() == [
        "0 | 3 Commands | pages 2-2",
        "1 | 3.1 Get Device ID | pages 2-2",
    ]
    code, out = run(
        capsys, "page", "DSP0236", "--section", "4", catalog_file=catalog_file
    )
    assert code == 0, out
    assert cite_pages(out) == ["PDF page 3", "PDF page 4"]
    assert cite_fields(out, 0)[2] == "~4 Transport"
    assert "3.1 Get Device ID" not in out  # page 2 is not printed
    code, out = run(
        capsys, "page", "DSP0236", "--section", "3", catalog_file=catalog_file
    )
    assert code == 0, out
    assert cite_pages(out) == ["PDF page 2"]
    assert cite_fields(out)[2] == "3 Commands"
    # placed one page late: 3 Commands' heading is the second line of page
    # 2, so it starts there and 2 Scope keeps page 2
    set_outline_page(held, "4 Transport", 3, approximate=False)
    set_outline_page(held, "3 Commands", 3, approximate=True)
    code, out = run(capsys, "section", "DSP0236", "3", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip().splitlines() == [
        "0 | 3 Commands | pages ~2-2",
        "1 | 3.1 Get Device ID | pages 2-2",
    ]
    code, out = run(capsys, "section", "DSP0236", "2", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip() == "0 | 2 Scope | pages 1-2"
    code, out = run(
        capsys, "page", "DSP0236", "--section", "3", catalog_file=catalog_file
    )
    assert code == 0, out
    assert cite_pages(out) == ["PDF page 2"]
    assert cite_fields(out)[2] == "~3 Commands"


def test_the_cli_cites_an_approximate_entry_where_its_heading_is(
    held, catalog_file, capsys
):
    # a contents page put 4 Transport on page 2; its heading opens page 3
    set_outline_page(held, "4 Transport", 2, approximate=True)
    code, out = run(capsys, "page", "DSP0236", "2", catalog_file=catalog_file)
    assert code == 0, out
    assert cite_fields(out)[2] == "2 Scope; 3 Commands; 3.1 Get Device ID"
    code, out = run(capsys, "page", "DSP0236", "3", catalog_file=catalog_file)
    assert code == 0, out
    assert cite_fields(out)[2] == "~4 Transport"
    # the last line of page 2 is 3.1's, not 4 Transport's
    code, out = run(
        capsys, "find", "DSP0236", "returns the id", catalog_file=catalog_file
    )
    assert code == 0, out
    assert out.strip() == (
        "DSP0236 p.2 line 9 | 3.1 Get Device ID | Get Device ID returns the id."
    )
    code, out = run(
        capsys, "find", "DSP0236", "carries bytes", catalog_file=catalog_file
    )
    assert code == 0, out
    assert out.strip() == (
        "DSP0236 p.3 line 11 | ~4 Transport | The transport carries bytes."
    )
    # the contents page put 3 Commands one page late: page 2 lists it
    set_outline_page(held, "4 Transport", 3, approximate=False)
    set_outline_page(held, "3 Commands", 3, approximate=True)
    code, out = run(capsys, "page", "DSP0236", "2", catalog_file=catalog_file)
    assert code == 0, out
    assert cite_fields(out)[2] == "2 Scope; ~3 Commands; 3.1 Get Device ID"
    # an exact entry on the wrong page is read as before
    set_outline_page(held, "3 Commands", 3, approximate=False)
    code, out = run(capsys, "page", "DSP0236", "2", catalog_file=catalog_file)
    assert code == 0, out
    assert cite_fields(out)[2] == "2 Scope; 3.1 Get Device ID"
