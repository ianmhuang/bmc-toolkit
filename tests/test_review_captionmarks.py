"""Reviewer acceptance tests for caption bookmarks (fix/caption-bookmarks).

AC-1: a bookmark whose title is a table or figure caption is not an Outline
entry, while a title that only mentions a table or figure is kept. AC-2:
when dropping the captions leaves the bookmarks unusable, the Outline comes
from the contents pages. AC-4: an extraction made by version 6 is stale.
Black-box through ``extract_pdf`` on synthetic PDFs; the version pin is the
one thing AC-4 asks for by value.
"""

import json

import pytest

from bmc_toolkit.spec import extract as ex
from tests import pdfgen
from tests.test_extract import _contents_document, _pages_of

pytest.importorskip("pypdfium2")


def extracted_outline(tmp_path, bookmarks, pages=None, name="o.pdf"):
    """The Outline of a PDF whose bookmarks are ``(level, title, page_index)``;
    one plain page per bookmark unless ``pages`` is given."""
    if pages is None:
        pages = [pdfgen.plain_page([f"page {i}"]) for i in range(len(bookmarks))]
    pdf = pdfgen.write_pdf(tmp_path / name, pages, bookmarks=bookmarks)
    return ex.extract_pdf(pdf)


# ------------------------------------------------------------------- AC-1

CAPTIONS = [
    "Table 69 – GetPDR command format",  # en dash
    "Figure 24 — Sensor state transitions",  # em dash
    "Table 1 - SMBIOS Entry Point structure",  # hyphen
    "Table A.1 – Annex codes",  # letter prefix, dotted
    "Table 6-2: DCMI Capabilities parameters",  # hyphenated number, colon
    "Figure 3.2a. Timing",  # letter suffix, period
    "Table 12–Codes",  # no spaces around the dash
    "Figure 7 : Flow",  # space before the colon
]

MENTIONS = [
    "Tables",
    "Figures",
    "Table of Contents",
    "Table of Figures",
    "Table 100 describes the format of this PDR.",
    "Figure 3 shows the message flow",
    "3 Table formats",
    "Example 1: SMIC Interface in I/O Space",
]


@pytest.mark.parametrize("title", CAPTIONS)
def test_ac1_a_caption_bookmark_is_not_an_outline_entry(tmp_path, title):
    r = extracted_outline(
        tmp_path, [(0, "1 Scope", 0), (0, title, 1), (0, "2 Commands", 2)]
    )
    assert r.outline_source == "bookmarks"
    assert [e["title"] for e in r.outline] == ["1 Scope", "2 Commands"]


@pytest.mark.parametrize("title", MENTIONS)
def test_ac1_a_title_that_only_mentions_a_table_or_figure_is_kept(tmp_path, title):
    r = extracted_outline(
        tmp_path, [(0, "1 Scope", 0), (0, title, 1), (0, "2 Commands", 2)]
    )
    assert r.outline_source == "bookmarks"
    assert [e["title"] for e in r.outline] == ["1 Scope", title, "2 Commands"]


def test_ac1_a_nested_caption_bookmark_is_dropped_too(tmp_path):
    # DSP0248 bookmarks captions at level 0; the rule is about the title,
    # so a caption filed under its section goes the same way
    r = extracted_outline(
        tmp_path,
        [
            (0, "2 Commands", 0),
            (1, "2.1 GetPDR", 0),
            (2, "Table 1 – GetPDR format", 1),
            (1, "2.2 FindPDR", 2),
        ],
    )
    titles = [e["title"] for e in r.outline]
    assert titles == ["2 Commands", "2.1 GetPDR", "2.2 FindPDR"]


def test_ac1_the_other_entries_are_unchanged(tmp_path):
    # the Outline with the captions bookmarked equals the Outline of the
    # same document without them: same titles, levels and pages, same order
    headings = [
        (0, "1 Scope", 0),
        (0, "2 Commands", 1),
        (1, "2.1 GetPDR", 1),
        (1, "2.2 FindPDR", 3),
        (0, "3 Annex", 4),
    ]
    with_captions = [
        headings[0],
        headings[1],
        headings[2],
        (0, "Table 1 – GetPDR format", 1),
        (0, "Figure 1 – GetPDR flow", 2),
        headings[3],
        (0, "Table 2 – FindPDR format", 3),
        headings[4],
    ]
    pages = [pdfgen.plain_page([f"page {i}"]) for i in range(5)]
    plain = extracted_outline(tmp_path, headings, pages, name="plain.pdf")
    captioned = extracted_outline(tmp_path, with_captions, pages, name="cap.pdf")
    assert captioned.outline_source == "bookmarks"
    assert captioned.outline == plain.outline
    assert len(captioned.outline) == 5


def test_ac1_a_caption_without_text_after_the_dash_is_not_a_caption(tmp_path):
    # AC-1 asks for a dash, colon or period *then text*: a bare "Table 1 –"
    # is not what the rule describes and stays
    r = extracted_outline(
        tmp_path, [(0, "1 Scope", 0), (0, "Table 1 –", 1), (0, "2 Commands", 2)]
    )
    assert [e["title"] for e in r.outline] == ["1 Scope", "Table 1 –", "2 Commands"]


# ------------------------------------------------------------------- AC-2


def test_ac2_only_caption_bookmarks_fall_back_to_the_contents_pages(tmp_path):
    pdf, _entries = _contents_document(tmp_path, 2)
    contents_only = ex.extract_pdf(pdf)
    captions = pdfgen.write_pdf(
        tmp_path / "captions.pdf",
        _pages_of(2),
        bookmarks=[
            (0, "Table 1 – Capabilities", 2),
            (0, "Figure 1 – Power states", 3),
            (0, "Table 2 – Power codes", 4),
            (0, "Table 3: Sensor types", 5),
        ],
    )
    r = ex.extract_pdf(captions)
    assert r.outline_source == "contents"
    assert r.outline == contents_only.outline
    assert r.page_offset == 2


def test_ac2_headings_left_on_one_page_after_the_captions_fall_back(tmp_path):
    # without the captions, the two bookmarks left point at one page of a
    # seven-page document: the one-page rule applies to what is left
    pdf = pdfgen.write_pdf(
        tmp_path / "onepage.pdf",
        _pages_of(2),
        bookmarks=[
            (0, "Mark2", 3),
            (0, "Table 1 – Capabilities", 4),
            (0, "SMBus", 3),
            (0, "Figure 1 – Power states", 5),
        ],
    )
    r = ex.extract_pdf(pdf)
    assert r.outline_source == "contents"
    assert r.outline[0]["title"] == "1 Introduction"
    assert not [e for e in r.outline if e["title"].startswith(("Table", "Figure"))]


def test_ac2_only_caption_bookmarks_and_no_contents_give_no_outline(tmp_path):
    pdf = pdfgen.write_pdf(
        tmp_path / "none.pdf",
        [pdfgen.plain_page(["one"]), pdfgen.plain_page(["two"])],
        bookmarks=[(0, "Table 1 – One", 0), (0, "Figure 1 – Two", 1)],
    )
    r = ex.extract_pdf(pdf)
    assert r.outline == [] and r.outline_source == "none"


def test_ac2_real_headings_with_captions_stay_bookmarks(tmp_path):
    # the fallback is only for bookmarks left unusable: headings on two
    # pages with captions between them are still the Outline's source
    r = extracted_outline(
        tmp_path,
        [
            (0, "1 Scope", 0),
            (0, "Table 1 – Codes", 0),
            (0, "2 Commands", 1),
            (0, "Figure 1 – Flow", 1),
        ],
        pages=[pdfgen.plain_page(["one"]), pdfgen.plain_page(["two"])],
    )
    assert r.outline_source == "bookmarks"
    assert [e["title"] for e in r.outline] == ["1 Scope", "2 Commands"]


# ------------------------------------------------------------------- AC-4


def test_ac4_the_extractor_version_is_seven():
    assert ex.EXTRACTOR_VERSION == 7


def test_ac4_a_version_6_extraction_is_not_current(tmp_path):
    vdir = tmp_path / "v"
    vdir.mkdir()
    (vdir / ex.EXTRACT_NAME).write_text("=== page 1 ===\nx\n", encoding="utf-8")
    (vdir / ex.META_NAME).write_text(
        json.dumps({"extractor_version": 6}), encoding="utf-8"
    )
    assert not ex.is_current(vdir)
    # and the version this code writes is current
    (vdir / ex.META_NAME).write_text(
        json.dumps({"extractor_version": ex.EXTRACTOR_VERSION}), encoding="utf-8"
    )
    assert ex.is_current(vdir)
