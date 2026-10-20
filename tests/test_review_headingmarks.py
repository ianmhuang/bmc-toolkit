"""Reviewer acceptance tests for unnumbered top-level bookmarks
(fix/heading-bookmarks).

AC-1: a top-level bookmark without a clause number that lies between the
first and the last numbered top-level bookmark is not an Outline entry.
AC-2: one before the first or after the last is kept, so is an unnumbered
entry below the top level, every entry of an Outline with fewer than two
numbered top-level entries, and an Outline parsed from the contents pages.
AC-3: each of the listed clause and annex forms counts as numbered, and
since round 2 so do Roman-numeral and digit annex labels (``Appendix II``,
``Annex 1``), while a word that merely starts with a Roman letter after
``Annex`` does not. AC-4: the extractor version is 8 and a version 7
extract is not current.
Black-box through ``extract_pdf`` on synthetic PDFs; the contents-page case
stubs ``parse_contents`` since the real parser yields numbered lines only.
"""

import json

import pytest

from bmc_toolkit.spec import extract as ex
from tests import pdfgen
from tests.test_extract import _contents_document

pytest.importorskip("pypdfium2")


def extracted(tmp_path, bookmarks, pages=None, name="o.pdf"):
    """The extraction of a PDF whose bookmarks are ``(level, title, page)``
    with ``page`` 0-based; one plain page per bookmark unless given."""
    if pages is None:
        pages = [pdfgen.plain_page([f"page {i}"]) for i in range(len(bookmarks))]
    pdf = pdfgen.write_pdf(tmp_path / name, pages, bookmarks=bookmarks)
    return ex.extract_pdf(pdf)


def outline_of(tmp_path, marks):
    """``(level, title)`` of the Outline of a PDF with one page per mark."""
    bookmarks = [(level, title, i) for i, (level, title) in enumerate(marks)]
    return [(e["level"], e["title"]) for e in extracted(tmp_path, bookmarks).outline]


# ------------------------------------------------------------------- AC-1

ABBREVIATIONS = [
    "BMC",
    "Baseboard Management Controller",
    "I2C",
    "EXAMPLE 3:",
    "Example 1: SMIC Interface in I/O Space",
    "Tables",
    "Bibliography",
]


@pytest.mark.parametrize("title", ABBREVIATIONS)
def test_ac1_an_unnumbered_top_level_entry_between_clauses_is_dropped(
    tmp_path, title
):
    r = extracted(tmp_path, [(0, "1 Scope", 0), (0, title, 1), (0, "2 Terms", 2)])
    assert r.outline_source == "bookmarks"
    assert [e["title"] for e in r.outline] == ["1 Scope", "2 Terms"]


def test_ac1_the_dropped_entries_leave_the_others_as_they_were(tmp_path):
    # the Outline equals that of the same document without the stray
    # bookmarks: same titles, levels, pages and order
    headings = [
        (0, "1 Scope", 0),
        (0, "2 Abbreviations", 1),
        (0, "3 Structures", 3),
        (1, "3.1 Group Associations", 3),
        (2, "3.1.1 Handles", 4),
        (0, "ANNEX A (informative) Notes", 5),
    ]
    with_strays = [
        headings[0],
        headings[1],
        (0, "BMC", 1),
        (0, "Baseboard Management Controller", 1),
        (0, "NIC", 2),
        (0, "Network Interface Card", 2),
        headings[2],
        headings[3],
        headings[4],
        (0, "EXAMPLE 3:", 4),
        headings[5],
    ]
    pages = [pdfgen.plain_page([f"page {i}"]) for i in range(6)]
    plain = extracted(tmp_path, headings, pages, name="plain.pdf")
    strayed = extracted(tmp_path, with_strays, pages, name="stray.pdf")
    assert strayed.outline_source == "bookmarks"
    assert strayed.outline == plain.outline
    assert len(strayed.outline) == 6


def test_ac1_the_rule_runs_after_the_caption_rule(tmp_path):
    # a caption is dropped as a caption wherever it lies; an unnumbered
    # entry only between clauses: both gone, nothing else touched
    r = extracted(
        tmp_path,
        [
            (0, "Foreword", 0),
            (0, "1 Scope", 1),
            (0, "Table 1 – Codes", 1),
            (0, "BMC", 2),
            (0, "2 Terms", 3),
            (0, "Figure 1 – Flow", 3),
        ],
    )
    assert [e["title"] for e in r.outline] == ["Foreword", "1 Scope", "2 Terms"]


# ------------------------------------------------------------------- AC-2


def test_ac2_entries_before_the_first_numbered_one_are_kept(tmp_path):
    marks = [
        (0, "Foreword"),
        (0, "Introduction"),
        (0, "1 Scope"),
        (0, "2 Terms"),
    ]
    assert outline_of(tmp_path, marks) == marks


def test_ac2_entries_after_the_last_numbered_one_are_kept(tmp_path):
    marks = [
        (0, "1 Scope"),
        (0, "2 Terms"),
        (0, "Bibliography"),
        (0, "Index"),
    ]
    assert outline_of(tmp_path, marks) == marks


def test_ac2_an_entry_after_the_last_clause_and_its_children_is_kept(tmp_path):
    # "between" is by position among the entries: a top-level entry after
    # the last numbered one is kept even when nested entries follow that one
    marks = [
        (0, "1 Scope"),
        (0, "2 Terms"),
        (1, "2.1 Definitions"),
        (1, "Notation"),
        (0, "Bibliography"),
    ]
    assert outline_of(tmp_path, marks) == marks


@pytest.mark.parametrize(
    "marks",
    [
        [(0, "1 Scope"), (1, "Overview"), (0, "2 Terms")],
        [(0, "1 Scope"), (1, "1.1 Purpose"), (2, "EXAMPLE 1:"), (0, "2 Terms")],
        [(0, "1 Scope"), (1, "BMC"), (1, "Baseboard Management"), (0, "2 Terms")],
    ],
    ids=["level-1", "level-2", "abbreviations-nested"],
)
def test_ac2_unnumbered_entries_below_the_top_level_are_kept(tmp_path, marks):
    assert outline_of(tmp_path, marks) == marks


@pytest.mark.parametrize(
    "marks",
    [
        [(0, "Overview"), (0, "Details"), (0, "Summary")],
        [(0, "Overview"), (0, "1 Scope"), (0, "Details"), (0, "Summary")],
        [(0, "1 Scope"), (0, "Details"), (1, "2.1 Nested")],
    ],
    ids=["none-numbered", "one-numbered", "one-numbered-top-level"],
)
def test_ac2_an_outline_with_fewer_than_two_numbered_entries_is_kept(
    tmp_path, marks
):
    assert outline_of(tmp_path, marks) == marks


def test_ac2_a_contents_page_outline_is_not_judged(tmp_path, monkeypatch):
    parsed = [
        {"level": 0, "title": "1 Introduction", "printed": 1},
        {"level": 0, "title": "Overview", "printed": 2},
        {"level": 0, "title": "2 Overview", "printed": 2},
        {"level": 0, "title": "Notes", "printed": 3},
        {"level": 0, "title": "3 Commands", "printed": 4},
    ]
    monkeypatch.setattr(ex, "parse_contents", lambda pages: parsed)
    pdf, _entries = _contents_document(tmp_path, 2)
    r = ex.extract_pdf(pdf)
    assert r.outline_source == "contents"
    assert [e["title"] for e in r.outline] == [
        "1 Introduction",
        "Overview",
        "2 Overview",
        "Notes",
        "3 Commands",
    ]


# ------------------------------------------------------------------- AC-3

NUMBERED = [
    "7 Structure definitions",
    "7.15 Group Associations (Type 14)",
    "1. Introduction",
    "35b. Command Forwarding Commands",
    "A.2 Examples",
    "C1-1 IPMI Device Information - BMC Interface",
    "E-1 Notation",
    "ANNEX A (informative) Conformance guidelines",
    "Annex A. Sanitize Operation Considerations (Informative)",
    "Appendix C1 - Locating IPMI System Interfaces via SM BIOS Tables",
    "Appendix A— Acronyms",
    # round 2 (F3): Roman-numeral and digit annex labels
    "Appendix II Notes",
    "ANNEX IV (informative) Conformance",
    "Annex VIII Examples",
    "Annex 1 Overview",
    "Appendix 12 - Tables",
]


@pytest.mark.parametrize("title", NUMBERED)
def test_ac3_a_numbered_title_between_clauses_is_kept(tmp_path, title):
    marks = [(0, "1 Scope"), (0, title), (0, "99 Last")]
    assert outline_of(tmp_path, marks) == marks


@pytest.mark.parametrize(
    "title",
    [
        "3.1",
        "Appendix",
        "Annexes",
        "Appendixes and notes",
        "Annex Introduction",
        "Appendix Values",
        "A note on terms",
    ],
    ids=[
        "bare-number",
        "appendix-word",
        "annexes",
        "appendixes",
        "annex-then-word-starting-I",
        "appendix-then-word-starting-V",
        "article",
    ],
)
def test_ac3_a_title_that_only_looks_numbered_is_dropped(tmp_path, title):
    # the Roman-numeral alternative must not read the first letter of an
    # ordinary word ("Introduction", "Values") as a label
    marks = [(0, "1 Scope"), (0, title), (0, "2 Terms")]
    assert outline_of(tmp_path, marks) == [(0, "1 Scope"), (0, "2 Terms")]


def test_ac2_children_of_a_dropped_entry_stay_under_the_clause_above(tmp_path):
    # round 1 F1, accepted as documented: only the unnumbered top-level
    # entry goes; its nested entries stay and follow the previous clause
    got = outline_of(
        tmp_path,
        [
            (0, "1 Scope"),
            (0, "Revision History"),
            (1, "Version 1.1"),
            (2, "Changes"),
            (0, "2 Terms"),
        ],
    )
    assert got == [
        (0, "1 Scope"),
        (1, "Version 1.1"),
        (2, "Changes"),
        (0, "2 Terms"),
    ]


@pytest.mark.parametrize("title", NUMBERED)
def test_ac3_a_numbered_title_bounds_the_middle(tmp_path, title):
    # a numbered title is also a bound: an unnumbered entry between it and
    # another clause is dropped, one after it (when last) is kept
    marks = [(0, "1 Scope"), (0, "BMC"), (0, title), (0, "Bibliography")]
    assert outline_of(tmp_path, marks) == [
        (0, "1 Scope"),
        (0, title),
        (0, "Bibliography"),
    ]


# ------------------------------------------------------------------- AC-4


def test_ac4_the_extractor_version_is_eight():
    assert ex.EXTRACTOR_VERSION == 8


def test_ac4_a_version_7_extraction_is_not_current(tmp_path):
    vdir = tmp_path / "v"
    vdir.mkdir()
    (vdir / ex.EXTRACT_NAME).write_text("=== page 1 ===\nx\n", encoding="utf-8")
    (vdir / ex.META_NAME).write_text(
        json.dumps({"extractor_version": 7}), encoding="utf-8"
    )
    assert not ex.is_current(vdir)
    (vdir / ex.META_NAME).write_text(
        json.dumps({"extractor_version": ex.EXTRACTOR_VERSION}), encoding="utf-8"
    )
    assert ex.is_current(vdir)
