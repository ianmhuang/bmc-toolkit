"""Reviewer acceptance tests for unnumbered top-level bookmarks through
the CLI (fix/heading-bookmarks).

AC-1: with abbreviations and an example line bookmarked at the top level
the way DSP0134 3.10.0 has them, ``section`` prints the clause's full page
range, ``find`` files the lines under them in the clause, and
``outline.json`` holds no such entry. AC-2: ``Bibliography`` after the last
clause is still a section. AC-4: ``status`` reports a version 7 extract as
``stale`` and a reading command re-extracts it. No network: the scripted
client serves the PDF.
"""

import json

import pytest

from bmc_toolkit.spec import extract as ex
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok

pytest.importorskip("pypdfium2")

URL = "https://example.test/DSP0236_1.3.3.pdf"


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def abbreviated_document(tmp_path):
    """Page 1: ``1 Scope``. Pages 2-3: ``2 Terms`` with two abbreviations
    and their expansions, each bookmarked at level 0. Pages 4-5: ``3
    Structures`` with ``3.1 Group``, page 5 opening with ``EXAMPLE 3:``
    bookmarked at level 0. Page 6: ``Annex A`` (the last numbered entry).
    Page 7: ``Bibliography``, unnumbered and after the last clause. Every
    heading is the first line of its page, so a clause ends on the page
    before the next one."""
    pages = [
        pdfgen.plain_page(["1 Scope", "Scope text."]),
        pdfgen.plain_page(["2 Terms", "BMC", "Baseboard Management Controller"]),
        pdfgen.plain_page(["NIC", "Network Interface Card"]),
        pdfgen.plain_page(["3 Structures", "3.1 Group", "Group text."]),
        pdfgen.plain_page(["EXAMPLE 3:", "The groupHandle names the group."]),
        pdfgen.plain_page(["Annex A (informative) Notes", "Annex text."]),
        pdfgen.plain_page(["Bibliography", "Reference list here."]),
    ]
    return pdfgen.write_pdf(
        tmp_path / "abbreviated.pdf",
        pages,
        bookmarks=[
            (0, "1 Scope", 0),
            (0, "2 Terms", 1),
            (0, "BMC", 1),
            (0, "Baseboard Management Controller", 1),
            (0, "NIC", 2),
            (0, "Network Interface Card", 2),
            (0, "3 Structures", 3),
            (1, "3.1 Group", 3),
            (0, "EXAMPLE 3:", 4),
            (0, "Annex A (informative) Notes", 5),
            (0, "Bibliography", 6),
        ],
    ).read_bytes()


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    scripted.responses[URL] = ok(abbreviated_document(tmp_path))
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


def hit_sections(out):
    return [ln.split(" | ")[1] for ln in out.splitlines() if " | " in ln]


# ------------------------------------------------------------------- AC-1


def test_ac1_the_outline_file_holds_no_unnumbered_top_level_entry(held):
    outline = json.loads((held / ex.OUTLINE_NAME).read_text(encoding="utf-8"))
    assert [(e["level"], e["title"], e["page"]) for e in outline] == [
        (0, "1 Scope", 1),
        (0, "2 Terms", 2),
        (0, "3 Structures", 4),
        (1, "3.1 Group", 4),
        (0, "Annex A (informative) Notes", 6),
        (0, "Bibliography", 7),
    ]


@pytest.mark.parametrize(
    "query, line",
    [
        ("2", "0 | 2 Terms | pages 2-3"),
        ("3", "0 | 3 Structures | pages 4-5"),
        ("3.1", "1 | 3.1 Group | pages 4-5"),
    ],
    ids=["abbreviations", "example-line", "subclause"],
)
def test_ac1_section_runs_to_the_next_clause(held, catalog_file, capsys, query, line):
    code, out = run(capsys, "section", "DSP0236", query, catalog_file=catalog_file)
    assert code == 0, out
    assert line in out.splitlines(), out


@pytest.mark.parametrize(
    "query",
    ["BMC", "Baseboard", "NIC", "EXAMPLE"],
    ids=["abbreviation", "expansion", "next-page-abbreviation", "example"],
)
def test_ac1_a_dropped_entry_is_not_a_section_by_title(
    held, catalog_file, capsys, query
):
    code, out = run(capsys, "section", "DSP0236", query, catalog_file=catalog_file)
    titles = [ln.split(" | ")[1] for ln in out.splitlines() if " | " in ln]
    headings = {"1 Scope", "2 Terms", "3 Structures", "3.1 Group"}
    assert all(t in headings for t in titles), out


@pytest.mark.parametrize(
    "pattern, section",
    [
        ("Baseboard Management", "2 Terms"),
        ("Network Interface", "2 Terms"),
        ("groupHandle", "3.1 Group"),
    ],
    ids=["same-page", "next-page", "example"],
)
def test_ac1_find_files_the_lines_under_the_dropped_entries_in_the_clause(
    held, catalog_file, capsys, pattern, section
):
    code, out = run(capsys, "find", "DSP0236", pattern, catalog_file=catalog_file)
    assert code == 0, out
    assert hit_sections(out) == [section], out


# ------------------------------------------------------------------- AC-2


def test_ac2_an_unnumbered_entry_after_the_last_clause_is_a_section(
    held, catalog_file, capsys
):
    code, out = run(
        capsys, "section", "DSP0236", "Bibliography", catalog_file=catalog_file
    )
    assert code == 0, out
    assert any(ln.startswith("0 | Bibliography | ") for ln in out.splitlines()), out
    code, out = run(
        capsys, "find", "DSP0236", "Reference list", catalog_file=catalog_file
    )
    assert code == 0, out
    assert hit_sections(out) == ["Bibliography"], out


# ------------------------------------------------------------------- AC-4


def test_ac4_status_shows_a_version_7_extract_as_stale(held, catalog_file, capsys):
    meta_path = held / ex.META_NAME
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["extractor_version"] = 7
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0, out
    row = next(ln for ln in out.splitlines() if "DSP0236" in ln).split("\t")
    assert row[5] == "stale", out


def test_ac4_a_version_7_library_is_re_extracted_on_next_use(
    held, catalog_file, capsys
):
    meta_path = held / ex.META_NAME
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["extractor_version"] = 7
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    outline_path = held / ex.OUTLINE_NAME
    outline = json.loads(outline_path.read_text(encoding="utf-8"))
    # what version 7 would have written: the abbreviation between the clauses
    outline.insert(2, {"level": 0, "title": "BMC", "page": 2})
    outline_path.write_text(json.dumps(outline), encoding="utf-8")
    code, out = run(capsys, "section", "DSP0236", "2", catalog_file=catalog_file)
    assert code == 0, out
    assert "0 | 2 Terms | pages 2-3" in out.splitlines(), out
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["extractor_version"] == ex.EXTRACTOR_VERSION == 8
    outline = json.loads(outline_path.read_text(encoding="utf-8"))
    assert "BMC" not in [e["title"] for e in outline]
    code, out = run(capsys, "status", catalog_file=catalog_file)
    row = next(ln for ln in out.splitlines() if "DSP0236" in ln).split("\t")
    assert row[5:] == ["extracted", "bookmarks"]
