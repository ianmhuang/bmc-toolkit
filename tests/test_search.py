"""Reading an extracted version: page splitting, owning sections, section
lookup, search hits, Citation lines and page formatting. No PDF involved."""

from pathlib import Path

import pytest

from bmc_toolkit.spec import search as se
from bmc_toolkit.spec.library import Holding


def make_version(**overrides) -> se.Version:
    base = dict(
        family="mctp",
        document="DSP0236",
        version="1.3.3",
        path=Path("/lib/specs/mctp/DSP0236/1.3.3"),
        origin="https://example.test/DSP0236_1.3.3.pdf",
        pages=[
            ["MCTP Base Specification", "1 Introduction", "intro text", "2 Scope"],
            [
                "scope text continues",
                "3 Commands",
                "3.1  Get Device ID",
                "Get Device ID  06h  01h",
                "",
            ],
            ["Figure 1 - Topology", "box A", "box B"],
        ],
        outline=[
            {"level": 0, "title": "1 Introduction", "page": 1},
            {"level": 0, "title": "2 Scope", "page": 1},
            {"level": 0, "title": "3 Commands", "page": 2},
            {"level": 1, "title": "3.1 Get Device ID", "page": 2},
            {"level": 0, "title": "A Annex", "page": 3, "approximate": True},
        ],
        linemap={
            "2": {
                "first": 40,
                "last": 43,
                "lines": {"0": 40, "1": 41, "2": 42, "3": 43},
            },
        },
        figures={"3": {"regions": [[72.0, 500.0, 300.0, 700.0]], "lines": [1, 2]}},
    )
    base.update(overrides)
    return se.Version(**base)


# --------------------------------------------------------------- pages


def test_split_pages_keeps_blank_lines_and_drops_final_newline():
    text = "=== page 1 ===\na\n\nb\n=== page 2 ===\nc\n"
    assert se.split_pages(text) == [["a", "", "b"], ["c"]]


def test_split_pages_rejects_missing_or_reordered_markers():
    with pytest.raises(se.SearchError):
        se.split_pages("no markers here\n")
    with pytest.raises(se.SearchError):
        se.split_pages("=== page 1 ===\na\n=== page 3 ===\nb\n")


# ------------------------------------------------------------ sections


def test_section_number_and_label():
    assert se.Section("20.1 Get Device ID", 5).number == "20.1"
    assert se.Section("A.2 Annex", 5).number == "A.2"
    assert se.Section("Introduction", 5).number == ""
    assert se.Section("3 Commands", 2, approximate=True).label == "~3 Commands"


def test_owning_section_before_first_heading_is_none():
    v = make_version()
    assert v.owning_section(1, 0) is None  # the running header


def test_owning_section_on_the_same_page_uses_heading_position():
    v = make_version()
    assert v.owning_section(1, 2).title == "1 Introduction"
    assert v.owning_section(1, 3).title == "2 Scope"


def test_owning_section_carries_over_from_an_earlier_page():
    v = make_version()
    assert v.owning_section(2, 0).title == "2 Scope"
    assert v.owning_section(2, 1).title == "3 Commands"
    assert v.owning_section(2, 2).title == "3.1 Get Device ID"
    assert v.owning_section(2, 3).title == "3.1 Get Device ID"


def test_owning_section_falls_back_to_the_section_number():
    # the bookmark's wording differs from the heading: the number decides
    v = make_version()
    v.outline[3]["title"] = "3.1 Get Device ID command"
    assert v.owning_section(2, 1).title == "3 Commands"
    assert v.owning_section(2, 2).title == "3.1 Get Device ID command"


def test_owning_section_heading_not_found_on_page_counts_from_the_top():
    v = make_version()
    v.outline[3]["title"] = "Device identification"  # no number, not on the page
    assert v.owning_section(2, 0).title == "Device identification"


def test_owning_section_marks_approximate_entries():
    v = make_version()
    sec = v.owning_section(3, 1)
    assert sec.approximate and sec.label == "~A Annex"


def test_empty_outline_gives_no_section():
    v = make_version(outline=[])
    assert v.owning_section(2, 1) is None


def test_match_sections_by_number_prefix_on_dot_boundary():
    v = make_version(
        outline=[
            {"level": 0, "title": "8 Base protocol", "page": 1},
            {"level": 1, "title": "8.1 Overview", "page": 1},
            {"level": 2, "title": "8.1.2 Details", "page": 2},
            {"level": 1, "title": "8.10 Dropped", "page": 2},
            {"level": 0, "title": "9 Other", "page": 3},
        ]
    )
    titles = [s.title for s, _ in v.match_sections("8.1")]
    assert titles == ["8.1 Overview", "8.1.2 Details"]
    assert [s.title for s, _ in v.match_sections("8.1.")] == titles
    assert [s.title for s, _ in v.match_sections("8")] == [
        "8 Base protocol",
        "8.1 Overview",
        "8.1.2 Details",
        "8.10 Dropped",
    ]


def test_match_sections_by_title_words_case_insensitively():
    v = make_version()
    got = v.match_sections("device id")
    assert [s.title for s, _ in got] == ["3.1 Get Device ID"]
    assert v.match_sections("device nope") == []


def test_match_sections_end_page_is_next_same_or_higher_level_entry():
    v = make_version()
    got = dict((s.title, end) for s, end in v.match_sections("3"))
    assert got["3 Commands"] == 3  # "A Annex" (level 0) starts on page 3
    assert got["3.1 Get Device ID"] == 3
    ((sec, end),) = v.match_sections("annex")
    assert end == 3  # last page of the document


# -------------------------------------------------------------- search


def test_find_literal_is_case_insensitive_and_carries_context():
    v = make_version()
    hits = list(v.find("get device id"))
    assert [h.index for h in hits] == [2, 3]  # the heading and the body line
    hit = hits[1]
    assert (hit.page, hit.index) == (2, 3)
    assert hit.number == 43
    assert hit.section.title == "3.1 Get Device ID"
    assert hit.figure is False


def test_find_case_and_regex_options():
    v = make_version()
    assert list(v.find("get device id", case=True)) == []
    hits = list(v.find(r"box [AB]", regex=True))
    assert [(h.page, h.index) for h in hits] == [(3, 1), (3, 2)]
    assert all(h.figure for h in hits)
    assert all(h.number is None for h in hits)


def test_find_escapes_literal_metacharacters():
    v = make_version(pages=[["a+b", "aab"]])
    assert [h.text for h in v.find("a+b")] == ["a+b"]


# ------------------------------------------------------------ citation


def test_cite_line_fields_in_order():
    v = make_version()
    assert v.cite(2) == (
        "cite: mctp | DSP0236 1.3.3 | 2 Scope | PDF page 2 | lines 40-43 | "
        "https://example.test/DSP0236_1.3.3.pdf | " + str(v.path)
    )
    assert v.cite(1).split(" | ")[2:5] == ["-", "PDF page 1", "lines -"]
    assert v.cite(3).split(" | ")[2] == "~A Annex"
    assert v.cite(3, lines="rendered page").split(" | ")[4] == "lines rendered page"


def test_cite_marks_dropins_as_user_provided(tmp_path):
    vdir = tmp_path / "v"
    vdir.mkdir()
    (vdir / "extract.txt").write_text("=== page 1 ===\nx\n", "utf-8")
    holding = Holding(
        "vendor",
        "OEM",
        "1.0",
        vdir,
        {"dropin": True, "url": None, "file": "original.pdf"},
    )
    v = se.load_version(holding)
    assert v.origin == "user-provided"
    assert v.outline == [] and v.linemap == {} and v.figures == {}
    assert v.cite(1).split(" | ")[5] == "user-provided"


def test_load_version_reads_every_companion_file(tmp_path):
    vdir = tmp_path / "v"
    vdir.mkdir()
    (vdir / "extract.txt").write_text("=== page 1 ===\na\nb\n", "utf-8")
    (vdir / "outline.json").write_text('[{"level":0,"title":"1 A","page":1}]', "utf-8")
    (vdir / "linemap.json").write_text(
        '{"pages": {"1": {"first": 7, "last": 8, "lines": {"0": 7, "1": 8}}}}', "utf-8"
    )
    (vdir / "figures.json").write_text(
        '{"pages": {"1": {"regions": [[0,0,1,1]], "lines": [1]}}}', "utf-8"
    )
    holding = Holding(
        "mctp", "DSP0236", "1.3.3", vdir, {"url": "https://x/y.pdf", "dropin": False}
    )
    v = se.load_version(holding)
    assert v.origin == "https://x/y.pdf"
    assert v.line_number(1, 1) == 8 and v.in_figure(1, 1) and not v.in_figure(1, 0)


def test_load_version_without_extract_is_a_search_error(tmp_path):
    holding = Holding("mctp", "DSP0236", "1.3.3", tmp_path, {})
    with pytest.raises(se.SearchError):
        se.load_version(holding)


# ---------------------------------------------------------------- page


def test_format_page_prefixes_printed_numbers_or_blanks():
    v = make_version(
        linemap={"2": {"first": 40, "last": 41, "lines": {"0": 40, "2": 41}}}
    )
    lines = se.format_page(v, 2)
    assert lines[0] == "  40  scope text continues"
    assert lines[1] == "      3 Commands"
    assert lines[2] == "  41  3.1  Get Device ID"
    assert lines[3] == "      Get Device ID  06h  01h"
    assert lines[4] == ""


def test_format_page_without_linemap_has_no_prefix_and_marks_figures():
    v = make_version()
    lines = se.format_page(v, 3)
    assert lines == ["Figure 1 - Topology", "box A  [figure]", "box B  [figure]"]
