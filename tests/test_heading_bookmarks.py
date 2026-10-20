"""A top-level bookmark without a clause number between two numbered
top-level bookmarks is not an Outline entry, so it neither owns the lines
under it nor ends the clause it sits in (DSP0134 3.10.0 bookmarks every
abbreviation of clause 4 and some example lines of clause 7 at level 0)."""

import json
from pathlib import Path

import pytest

from bmc_toolkit.spec import extract as ex
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok
from tests.test_extract import _contents_document

pytest.importorskip("pypdfium2")

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
LIBRARY_DOC = ROOT / "docs" / "LIBRARY.md"
URL = "https://example.test/DSP0236_1.3.3.pdf"


def outline_of(tmp_path, bookmarks):
    """Outline (level, title) pairs of a PDF with one page per bookmark."""
    pages = [pdfgen.plain_page([f"page {i}"]) for i in range(len(bookmarks))]
    marks = [(level, title, i) for i, (level, title) in enumerate(bookmarks)]
    pdf = pdfgen.write_pdf(tmp_path / "h.pdf", pages, bookmarks=marks)
    return [(e["level"], e["title"]) for e in ex.extract_pdf(pdf).outline]


# ------------------------------------------------------------------- AC-1


def test_ac1_unnumbered_top_level_entries_between_clauses_are_dropped(tmp_path):
    got = outline_of(
        tmp_path,
        [
            (0, "1 Scope"),
            (0, "2 Abbreviations"),
            (0, "BMC"),
            (0, "Baseboard Management Controller"),
            (0, "3 Structures"),
            (1, "3.1 Group Associations"),
            (0, "EXAMPLE 3:"),
            (0, "4 Annexes"),
        ],
    )
    assert got == [
        (0, "1 Scope"),
        (0, "2 Abbreviations"),
        (0, "3 Structures"),
        (1, "3.1 Group Associations"),
        (0, "4 Annexes"),
    ]


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def abbreviated_pdf(tmp_path):
    """`2 Symbols` on page 2 runs to page 3 with an abbreviation bookmarked
    at level 0 on each; `3 Structures` with `3.1 Group` on page 4 runs to
    page 5, where `EXAMPLE 3:` is bookmarked at level 0; `4 Annex` on
    page 6. The way DSP0134 3.10.0 has it."""
    pages = [
        pdfgen.plain_page(["1 Scope", "Scope text."]),
        pdfgen.plain_page(["2 Symbols", "BMC", "Baseboard Management Controller"]),
        pdfgen.plain_page(["CPU", "Central Processing Unit"]),
        pdfgen.plain_page(["3 Structures", "3.1 Group", "Group text."]),
        pdfgen.plain_page(["EXAMPLE 3:", "The groupHandle names the group."]),
        pdfgen.plain_page(["4 Annex", "Annex text."]),
    ]
    return pdfgen.write_pdf(
        tmp_path / "abbreviated.pdf",
        pages,
        bookmarks=[
            (0, "1 Scope", 0),
            (0, "2 Symbols", 1),
            (0, "BMC", 1),
            (0, "Baseboard Management Controller", 1),
            (0, "CPU", 2),
            (0, "Central Processing Unit", 2),
            (0, "3 Structures", 3),
            (1, "3.1 Group", 3),
            (0, "EXAMPLE 3:", 4),
            (0, "4 Annex", 5),
        ],
    ).read_bytes()


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    scripted.responses[URL] = ok(abbreviated_pdf(tmp_path))
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out


@pytest.mark.parametrize(
    "query, line",
    [
        ("2", "0 | 2 Symbols | pages 2-3"),
        ("3", "0 | 3 Structures | pages 4-5"),
        ("3.1", "1 | 3.1 Group | pages 4-5"),
    ],
    ids=["clause", "clause-with-example", "subclause"],
)
def test_ac1_sections_run_on_past_the_dropped_entries(
    held, catalog_file, capsys, query, line
):
    code, out = run(capsys, "section", "DSP0236", query, catalog_file=catalog_file)
    assert code == 0, out
    assert line in out.splitlines(), out


@pytest.mark.parametrize(
    "pattern, section",
    [
        ("Baseboard Management", "2 Symbols"),
        ("Central Processing", "2 Symbols"),
        ("groupHandle", "3.1 Group"),
    ],
    ids=["same-page", "next-page", "example"],
)
def test_ac1_lines_under_the_dropped_entries_belong_to_the_clause(
    held, catalog_file, capsys, pattern, section
):
    code, out = run(capsys, "find", "DSP0236", pattern, catalog_file=catalog_file)
    assert code == 0, out
    hits = out.strip().splitlines()
    assert hits and all(h.split(" | ")[1] == section for h in hits), out


# ------------------------------------------------------------------- AC-2


def test_ac2_entries_before_the_first_and_after_the_last_clause_are_kept(tmp_path):
    marks = [
        (0, "Foreword"),
        (0, "Introduction"),
        (0, "1 Scope"),
        (0, "2 Terms"),
        (0, "Bibliography"),
    ]
    assert outline_of(tmp_path, marks) == marks


def test_ac2_unnumbered_entries_below_the_top_level_are_kept(tmp_path):
    marks = [
        (0, "1 Scope"),
        (1, "Overview"),
        (2, "EXAMPLE 1:"),
        (0, "2 Terms"),
    ]
    assert outline_of(tmp_path, marks) == marks


def test_ac2_entries_below_a_dropped_one_stay_under_the_clause_above(tmp_path):
    # #100 reviewer F1: only the unnumbered top-level entry goes
    got = outline_of(
        tmp_path,
        [
            (0, "1 Scope"),
            (0, "Revision History"),
            (1, "Version 1.1"),
            (0, "2 Terms"),
        ],
    )
    assert got == [(0, "1 Scope"), (1, "Version 1.1"), (0, "2 Terms")]


@pytest.mark.parametrize(
    "marks",
    [
        [(0, "Overview"), (0, "Details"), (0, "Summary")],
        [(0, "Overview"), (0, "1 Scope"), (0, "Details"), (0, "Summary")],
    ],
    ids=["none-numbered", "one-numbered"],
)
def test_ac2_an_outline_with_fewer_than_two_clauses_is_kept(tmp_path, marks):
    assert outline_of(tmp_path, marks) == marks


def test_ac2_contents_page_entries_are_not_judged(tmp_path, monkeypatch):
    # parse_contents only yields numbered lines today; one without a number
    # between two clauses must still reach the Outline
    parsed = [
        {"level": 0, "title": "1 Introduction", "printed": 1},
        {"level": 0, "title": "Overview", "printed": 2},
        {"level": 0, "title": "2 Overview", "printed": 2},
    ]
    monkeypatch.setattr(ex, "parse_contents", lambda pages: parsed)
    pdf, _entries = _contents_document(tmp_path, 2)
    r = ex.extract_pdf(pdf)
    assert r.outline_source == "contents"
    assert [e["title"] for e in r.outline] == [
        "1 Introduction",
        "Overview",
        "2 Overview",
    ]


# ------------------------------------------------------------------- AC-3


@pytest.mark.parametrize(
    "title",
    [
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
        "Appendix II Notes",
        "ANNEX IV (informative)",
        "Annex 1 Overview",
    ],
    ids=[
        "number",
        "dotted-number",
        "trailing-dot",
        "letter-suffix",
        "annex-number",
        "annex-hyphen",
        "letter-hyphen",
        "ANNEX",
        "Annex-period",
        "Appendix-digit",
        "Appendix-em-dash",
        "Appendix-roman",
        "ANNEX-roman",
        "Annex-digit",
    ],
)
def test_ac3_a_numbered_title_between_clauses_is_kept(tmp_path, title):
    marks = [(0, "1 Scope"), (0, title), (0, "99 Last")]
    assert outline_of(tmp_path, marks) == marks


@pytest.mark.parametrize(
    "title",
    ["3.1", "Appendix", "Annexes", "Appendixes and notes", "A note on terms"],
    ids=["bare-number", "appendix-word", "annexes", "appendixes", "article"],
)
def test_ac3_a_title_that_only_looks_numbered_is_dropped(tmp_path, title):
    marks = [(0, "1 Scope"), (0, title), (0, "2 Terms")]
    assert outline_of(tmp_path, marks) == [(0, "1 Scope"), (0, "2 Terms")]


# ------------------------------------------------------------------- AC-4


def test_ac4_extractor_version_is_8():
    assert ex.EXTRACTOR_VERSION == 8


def test_ac4_a_version_7_extract_is_stale(tmp_path):
    vdir = tmp_path / "v"
    vdir.mkdir()
    (vdir / ex.EXTRACT_NAME).write_text("=== page 1 ===\nx\n", encoding="utf-8")
    (vdir / ex.META_NAME).write_text(
        json.dumps({"extractor_version": 7}), encoding="utf-8"
    )
    assert not ex.is_current(vdir)


# ------------------------------------------------------------------- AC-6


def test_ac6_skill_says_unnumbered_top_level_bookmarks_are_dropped():
    text = SKILL.read_text(encoding="utf-8")
    start = text.index("- **Outline**")
    outline = text[start : text.index("\n- **", start + 1)]
    assert "clause number" in outline, outline


def test_ac6_library_doc_says_unnumbered_top_level_bookmarks_are_dropped():
    text = LIBRARY_DOC.read_text(encoding="utf-8")
    start = text.index("`outline.json`")
    assert "clause number" in text[start : start + 900]
