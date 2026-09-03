"""Reviewer acceptance tests for find, section, page and the cite: line
(AC-1, AC-2, AC-4, AC-5, AC-6, AC-9), black-box through the CLI on synthetic
PDFs. No network: the scripted client serves the bytes."""

import json

import pytest

from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ZIP_BYTES, ok

pytest.importorskip("pypdfium2")

URL = "https://example.test/DSP0236_1.3.3.pdf"


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def numbered_doc(tmp_path):
    """Three DMTF-style numbered pages (100-117) with bookmarks."""
    page1 = pdfgen.numbered_page(
        100,
        [
            "Running header text",
            "1 Introduction",
            "This document describes the widget bus.",
            "2 Scope",
            "The scope covers frobnication only.",
            "Frobnicate command summary",
        ],
    )
    page2 = pdfgen.numbered_page(
        106,
        [
            "Scope continues here",
            "3 Commands",
            "3.1 Frobnicate",
            "Frobnicate sets the FROB bit.",
            "Reserved fields are zero.",
            "3.2 Reset",
        ],
    )
    page3 = pdfgen.numbered_page(
        112,
        [
            "Reset clears the FROB bit.",
            "Reserved fields are zero.",
            "3.10 Extra",
            "row a",
            "row b",
            "row c",
        ],
    )
    return pdfgen.write_pdf(
        tmp_path / "numbered.pdf",
        [page1, page2, page3],
        bookmarks=[
            (0, "1 Introduction", 0),
            (0, "2 Scope", 0),
            (0, "3 Commands", 1),
            (1, "3.1 Frobnicate", 1),
            (1, "3.2 Reset", 1),
            (1, "3.10 Extra", 2),
        ],
    ).read_bytes()


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    scripted.responses[URL] = ok(numbered_doc(tmp_path))
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


def fetch_plain(catalog_file, scripted, tmp_path, capsys, pages):
    pdf = pdfgen.write_pdf(tmp_path / "plain.pdf", pages)
    scripted.responses[URL] = ok(pdf.read_bytes())
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out


# ---------------------------------------------------------------- AC-1


def test_find_hit_line_has_page_printed_line_section_and_text(held, catalog_file, capsys):
    code, out = run(capsys, "find", "DSP0236", "frobnicate", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip().splitlines() == [
        "DSP0236 p.1 line 105 | 2 Scope | Frobnicate command summary",
        "DSP0236 p.2 line 108 | 3.1 Frobnicate | 3.1 Frobnicate",
        "DSP0236 p.2 line 109 | 3.1 Frobnicate | Frobnicate sets the FROB bit.",
    ]


def test_find_zero_hits_prints_no_hits_and_exits_0(held, catalog_file, capsys):
    code, out = run(capsys, "find", "DSP0236", "unobtainium", catalog_file=catalog_file)
    assert code == 0 and out.strip() == "no hits"


def test_find_case_and_regex_flags(held, catalog_file, capsys):
    code, out = run(
        capsys, "find", "DSP0236", "frob bit", "--case", catalog_file=catalog_file
    )
    assert code == 0 and out.strip() == "no hits"
    code, out = run(
        capsys, "find", "DSP0236", "FROB bit", "--case", catalog_file=catalog_file
    )
    assert code == 0 and len(out.strip().splitlines()) == 2
    # a literal by default: the parentheses and the bar are not regex syntax
    code, out = run(
        capsys, "find", "DSP0236", "FROB (bit|byte)", catalog_file=catalog_file
    )
    assert out.strip() == "no hits"
    code, out = run(
        capsys, "find", "DSP0236", "FROB (bit|byte)", "--regex", catalog_file=catalog_file
    )
    assert code == 0 and len(out.strip().splitlines()) == 2


def test_find_context_prints_surrounding_lines(held, catalog_file, capsys):
    code, out = run(
        capsys,
        "find",
        "DSP0236",
        "sets the FROB",
        "--context",
        "1",
        catalog_file=catalog_file,
    )
    assert code == 0, out
    lines = out.strip().splitlines()
    assert lines[0].startswith("DSP0236 p.2 line 109 | 3.1 Frobnicate |")
    assert "3.1 Frobnicate" in lines[1] and "108" in lines[1]
    assert "Reserved fields are zero." in lines[2] and "110" in lines[2]


def test_find_max_caps_hits_and_reports_the_rest(held, catalog_file, capsys):
    code, out = run(
        capsys,
        "find",
        "DSP0236",
        "reserved fields",
        "--max",
        "1",
        catalog_file=catalog_file,
    )
    assert code == 0
    lines = out.strip().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("DSP0236 p.2 line 110 |")
    assert lines[1].startswith("1 more hit")


def test_find_default_cap_is_50(catalog_file, library, scripted, tmp_path, capsys):
    lines = [f"needle {chr(97 + i % 26)}{chr(97 + i // 26)}" for i in range(55)]
    fetch_plain(
        catalog_file,
        scripted,
        tmp_path,
        capsys,
        [pdfgen.plain_page(lines, top=770.0, step=13.0)],
    )
    code, out = run(capsys, "find", "DSP0236", "needle", catalog_file=catalog_file)
    assert code == 0, out
    printed = out.strip().splitlines()
    hits = [ln for ln in printed if ln.startswith("DSP0236 p.1 |")]
    assert len(hits) == 50
    assert printed[-1].startswith("5 more hit")
    code, out = run(
        capsys, "find", "DSP0236", "needle", "--max", "60", catalog_file=catalog_file
    )
    assert len([ln for ln in out.splitlines() if ln.startswith("DSP0236 p.1 |")]) == 55


# ---------------------------------------------------------------- AC-2


def test_owning_section_before_any_heading_is_dash(held, catalog_file, capsys):
    code, out = run(capsys, "find", "DSP0236", "running header", catalog_file=catalog_file)
    assert out.strip() == "DSP0236 p.1 line 100 | - | Running header text"


def test_owning_section_carries_over_from_the_previous_page(held, catalog_file, capsys):
    code, out = run(capsys, "find", "DSP0236", "scope continues", catalog_file=catalog_file)
    assert out.strip() == "DSP0236 p.2 line 106 | 2 Scope | Scope continues here"
    code, out = run(capsys, "find", "DSP0236", "reset clears", catalog_file=catalog_file)
    assert out.strip() == "DSP0236 p.3 line 112 | 3.2 Reset | Reset clears the FROB bit."


def test_body_text_above_a_heading_does_not_claim_it(
    catalog_file, library, scripted, tmp_path, capsys
):
    """AC-2: on the same page the owner changes where the entry's title
    appears as a heading; a body line that merely mentions the title of a
    later section (round-1 F3) must not move the boundary up."""
    lines = [
        "Intro",
        "see Overview below for the details",
        "intro body text",
        "Overview",
        "overview body text",
    ]
    pdf = pdfgen.write_pdf(
        tmp_path / "steal.pdf",
        [pdfgen.plain_page(lines)],
        bookmarks=[(0, "Intro", 0), (0, "Overview", 0)],
    )
    scripted.responses[URL] = ok(pdf.read_bytes())
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    code, out = run(capsys, "find", "DSP0236", "body text", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip().splitlines() == [
        "DSP0236 p.1 | Intro | intro body text",
        "DSP0236 p.1 | Overview | overview body text",
    ]
    code, out = run(capsys, "find", "DSP0236", "see overview", catalog_file=catalog_file)
    assert out.strip() == "DSP0236 p.1 | Intro | see Overview below for the details"


def test_empty_outline_prints_dash_everywhere(
    catalog_file, library, scripted, tmp_path, capsys
):
    fetch_plain(
        catalog_file, scripted, tmp_path, capsys, [pdfgen.plain_page(["alpha beta"])]
    )
    code, out = run(capsys, "find", "DSP0236", "beta", catalog_file=catalog_file)
    assert out.strip() == "DSP0236 p.1 | - | alpha beta"
    code, out = run(capsys, "section", "DSP0236", "alpha", catalog_file=catalog_file)
    assert code == 0 and out.strip() == "no matching section"
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert out.splitlines()[0].split(" | ")[2] == "-"


def test_approximate_entries_carry_a_tilde(
    catalog_file, library, scripted, tmp_path, capsys
):
    contents = [(72, 740, "Contents")]
    y = 720.0
    for num, title, page in [
        ("1", "Intro", 1),
        ("1.1", "Scope", 1),
        ("2", "Overview", 2),
        ("2.1", "Arch", 2),
        ("3", "Commands", 3),
        ("3.1", "Get", 3),
        ("3.2", "Set", 3),
        ("4", "Errors", 4),
    ]:
        contents.append((72, y, f"{num} {title} ............ {page}"))
        y -= 14
    body = [[(72, 700, "body text without any number")] for _ in range(5)]
    fetch_plain(catalog_file, scripted, tmp_path, capsys, [contents] + body)
    code, out = run(capsys, "section", "DSP0236", "4", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip() == "0 | 4 Errors | pages ~4-6"
    code, out = run(capsys, "find", "DSP0236", "body text", catalog_file=catalog_file)
    hits = out.strip().splitlines()
    assert len(hits) == 5
    assert hits[-1].startswith("DSP0236 p.6 | ~4 Errors |")
    code, out = run(capsys, "page", "DSP0236", "5", catalog_file=catalog_file)
    assert out.splitlines()[0].split(" | ")[2] == "~4 Errors"


# ---------------------------------------------------------------- AC-4


def test_section_by_number_prefix_on_a_dot_boundary(held, catalog_file, capsys):
    code, out = run(capsys, "section", "DSP0236", "3.1", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip() == "1 | 3.1 Frobnicate | pages 2-2"  # not 3.10
    code, out = run(capsys, "section", "DSP0236", "3", catalog_file=catalog_file)
    assert out.strip().splitlines() == [
        "0 | 3 Commands | pages 2-3",
        "1 | 3.1 Frobnicate | pages 2-2",
        "1 | 3.2 Reset | pages 2-3",
        "1 | 3.10 Extra | pages 3-3",
    ]


def test_section_by_title_words_case_insensitively(held, catalog_file, capsys):
    code, out = run(capsys, "section", "DSP0236", "FROBNICATE", catalog_file=catalog_file)
    assert code == 0 and out.strip() == "1 | 3.1 Frobnicate | pages 2-2"
    code, out = run(capsys, "section", "DSP0236", "widget", catalog_file=catalog_file)
    assert code == 0 and out.strip() == "no matching section"


# ---------------------------------------------------------------- AC-5 / AC-6


def test_page_prints_cite_header_then_numbered_lines(held, catalog_file, capsys):
    code, out = run(capsys, "page", "DSP0236", "2", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].split(" | ") == [
        "cite: mctp",
        "DSP0236 1.3.3",
        "2 Scope",
        "PDF page 2",
        "lines 106-111",
        URL,
        str(held),
    ]
    assert lines[1] == " 106  Scope continues here"
    assert lines[3] == " 108  3.1 Frobnicate"
    assert len(lines) == 7


def test_page_range_and_section_forms(held, catalog_file, capsys):
    code, out = run(capsys, "page", "DSP0236", "1", "--to", "3", catalog_file=catalog_file)
    assert code == 0, out
    cites = [ln for ln in out.splitlines() if ln.startswith("cite:")]
    assert [c.split(" | ")[3] for c in cites] == ["PDF page 1", "PDF page 2", "PDF page 3"]
    code, out = run(
        capsys, "page", "DSP0236", "--section", "3.1", catalog_file=catalog_file
    )
    assert code == 0, out
    cites = [ln for ln in out.splitlines() if ln.startswith("cite:")]
    assert len(cites) == 1 and "PDF page 2" in cites[0]
    code, out = run(
        capsys, "page", "DSP0236", "--section", "nothing here", catalog_file=catalog_file
    )
    assert code != 0


def test_page_outside_the_document_exits_2(held, catalog_file, capsys):
    code, out = run(capsys, "page", "DSP0236", "4", catalog_file=catalog_file)
    assert code == 2 and "4" in out
    code, out = run(capsys, "page", "DSP0236", "0", catalog_file=catalog_file)
    assert code == 2


def test_page_refuses_more_than_10_pages_unless_max_pages(
    catalog_file, library, scripted, tmp_path, capsys
):
    pages = [pdfgen.plain_page([f"page text {chr(97 + i)}"]) for i in range(12)]
    fetch_plain(catalog_file, scripted, tmp_path, capsys, pages)
    code, out = run(capsys, "page", "DSP0236", "1", "--to", "11", catalog_file=catalog_file)
    assert code == 2 and "cite:" not in out
    code, out = run(capsys, "page", "DSP0236", "1", "--to", "10", catalog_file=catalog_file)
    assert code == 0 and out.count("cite:") == 10
    code, out = run(
        capsys,
        "page",
        "DSP0236",
        "1",
        "--to",
        "11",
        "--max-pages",
        "11",
        catalog_file=catalog_file,
    )
    assert code == 0 and out.count("cite:") == 11
    # without a Line Map the cite says "lines -" and lines carry no prefix
    code, out = run(capsys, "page", "DSP0236", "3", catalog_file=catalog_file)
    lines = out.splitlines()
    assert lines[0].split(" | ")[4] == "lines -"
    assert lines[1] == "page text c"


def test_cite_origin_is_user_provided_for_a_dropin(
    catalog_file, library, tmp_path, capsys
):
    mine = tmp_path / "mine.pdf"
    mine.write_bytes(numbered_doc(tmp_path))
    code, out = run(
        capsys,
        "add",
        str(mine),
        "--document",
        "DSP0236",
        "--version",
        "1.3.3",
        catalog_file=catalog_file,
    )
    assert code == 0, out
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    fields = out.splitlines()[0].split(" | ")
    assert fields[5] == "user-provided"
    assert fields[6] == str(library.specs / "mctp" / "DSP0236" / "1.3.3")


# ---------------------------------------------------------------- AC-9


@pytest.mark.parametrize("command", ["find", "section", "page", "render"])
def test_error_paths_are_shared_by_the_reading_commands(
    command, catalog_file, library, scripted, tmp_path, capsys
):
    argv = {
        "find": ["find", "DSP0236", "x"],
        "section": ["section", "DSP0236", "x"],
        "page": ["page", "DSP0236", "1"],
        "render": ["render", "DSP0236", "--page", "1"],
    }[command]

    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 2 and "fetch DSP0236" in out
    scripted.responses[URL] = ok(numbered_doc(tmp_path))
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 2 and "extract DSP0236" in out
    code, out = run(capsys, *argv, "--version", "1.3.2", catalog_file=catalog_file)
    assert code == 2 and "1.3.3" in out
    run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0, out
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    meta_path = vdir / "extract.json"
    meta = json.loads(meta_path.read_text("utf-8"))
    meta["extractor_version"] = 2  # what M2 wrote
    meta_path.write_text(json.dumps(meta), "utf-8")
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 2 and "extract DSP0236" in out
    # AC-7: status shows the old Extract as not current (round-1 F1)
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0, out
    row = next(ln for ln in out.splitlines() if "DSP0236" in ln)
    cells = [c.strip() for c in row.split("\t")]
    assert "stale" in cells and "extracted" not in cells


def test_status_shows_a_current_extract_as_extracted(held, catalog_file, capsys):
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0, out
    row = next(ln for ln in out.splitlines() if "DSP0236" in ln)
    cells = [c.strip() for c in row.split("\t")]
    assert "extracted" in cells and "stale" not in cells


def test_zip_bundle_is_refused_with_exit_2(catalog_file, library, scripted, capsys):
    scripted.responses["https://example.test/bundle_2026.1.zip"] = ok(
        ZIP_BYTES, "application/zip"
    )
    run(capsys, "fetch", "BUNDLE", catalog_file=catalog_file)
    for argv in (
        ["find", "BUNDLE", "x"],
        ["section", "BUNDLE", "x"],
        ["page", "BUNDLE", "1"],
        ["render", "BUNDLE", "--page", "1"],
    ):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert code == 2 and "bundle" in out.lower()
