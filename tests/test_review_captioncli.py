"""Reviewer acceptance tests for caption bookmarks through the CLI.

AC-3: a section followed in the bookmarks by a caption entry keeps its page
range and its lines: ``section`` prints the range, ``find`` and ``page``
file the lines under the table in the section, ``table --page`` cites the
section and not the caption. AC-4: a Library extracted by version 6 is
re-extracted on next use. No network: the scripted client serves the PDF.
"""

import json

import pytest

from bmc_toolkit.spec import extract as ex
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok
from tests.test_tables import HEADER, ROWS_1, furniture, ruled_table

pytest.importorskip("pypdfium2")

URL = "https://example.test/DSP0236_1.3.3.pdf"
WIDTHS = [100, 80, 200]


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def captioned_document(tmp_path):
    """Page 1: ``1 Scope``. Page 2: ``2 Commands``, ``2.1 GetPDR``, a
    captioned ruled table, prose. Page 3: more of 2.1's prose. Page 4
    opens with ``2.2 FindPDR`` as its first line (no running header there,
    so 2.1 ends on page 3). The caption is bookmarked at level 0 between
    2.1 and 2.2, the way DSP0248 bookmarks every caption; the page text
    spells its dash as a hyphen since pdfgen draws page text in Latin-1."""
    pages = [
        furniture(1) + [(72, 740, "1 Scope"), (72, 724, "Scope text here.")],
        furniture(2)
        + [
            (72, 740, "2 Commands"),
            (72, 724, "2.1 GetPDR"),
            (72, 708, "Table 1 - GetPDR format"),
            *ruled_table(72, 696, WIDTHS, [16] * 3, [HEADER, *ROWS_1]),
            (72, 600, "Prose after the table."),
        ],
        furniture(3) + [(72, 740, "The recordHandle selects the record.")],
        [(72, 740, "2.2 FindPDR"), (72, 724, "FindPDR text here.")],
    ]
    return pdfgen.write_pdf(
        tmp_path / "captioned.pdf",
        pages,
        bookmarks=[
            (0, "1 Scope", 0),
            (0, "2 Commands", 1),
            (1, "2.1 GetPDR", 1),
            (0, "Table 1 – GetPDR format", 1),
            (1, "2.2 FindPDR", 3),
        ],
    ).read_bytes()


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    scripted.responses[URL] = ok(captioned_document(tmp_path))
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


def cite_sections(out):
    return [
        ln.split(" | ")[2] for ln in out.splitlines() if ln.startswith("cite: ")
    ]


def hit_sections(out):
    return [ln.split(" | ")[1] for ln in out.splitlines() if " | " in ln]


# ------------------------------------------------------------------- AC-3


def test_ac3_the_caption_is_not_in_the_outline_file(held):
    outline = json.loads((held / ex.OUTLINE_NAME).read_text(encoding="utf-8"))
    assert [e["title"] for e in outline] == [
        "1 Scope",
        "2 Commands",
        "2.1 GetPDR",
        "2.2 FindPDR",
    ]


def test_ac3_section_runs_to_the_page_before_the_next_heading(
    held, catalog_file, capsys
):
    code, out = run(capsys, "section", "DSP0236", "2.1", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip() == "1 | 2.1 GetPDR | pages 2-3"
    # the caption is not a section a title query finds
    code, out = run(capsys, "section", "DSP0236", "GetPDR", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip() == "1 | 2.1 GetPDR | pages 2-3"


def test_ac3_find_files_the_lines_under_the_table_in_the_section(
    held, catalog_file, capsys
):
    code, out = run(
        capsys, "find", "DSP0236", "recordHandle", catalog_file=catalog_file
    )
    assert code == 0, out
    assert hit_sections(out) == ["2.1 GetPDR"], out
    code, out = run(
        capsys, "find", "DSP0236", "after the table", catalog_file=catalog_file
    )
    assert code == 0, out
    assert hit_sections(out) == ["2.1 GetPDR"], out


def test_ac3_page_cites_the_section_for_the_page_under_the_table(
    held, catalog_file, capsys
):
    code, out = run(capsys, "page", "DSP0236", "3", catalog_file=catalog_file)
    assert code == 0, out
    assert cite_sections(out) == ["2.1 GetPDR"], out
    # page 2 spans the entry owning its top (1 Scope runs on past the
    # running header) and the headings on it, never the caption
    code, out = run(capsys, "page", "DSP0236", "2", catalog_file=catalog_file)
    assert code == 0, out
    assert cite_sections(out) == ["1 Scope; 2 Commands; 2.1 GetPDR"], out
    # the section's pages, as page --section prints them
    code, out = run(
        capsys, "page", "DSP0236", "--section", "2.1", catalog_file=catalog_file
    )
    assert code == 0, out
    pages = [ln.split(" | ")[3] for ln in out.splitlines() if ln.startswith("cite: ")]
    assert pages == ["PDF page 2", "PDF page 3"], out


def test_ac3_a_table_cites_the_section_not_its_caption(held, catalog_file, capsys):
    pytest.importorskip("pdfplumber")
    code, out = run(
        capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file
    )
    assert code == 0, out
    assert cite_sections(out) == ["2.1 GetPDR"], out


# ------------------------------------------------------------------- AC-4


def test_ac4_a_version_6_library_is_re_extracted_on_next_use(
    held, catalog_file, capsys
):
    meta_path = held / ex.META_NAME
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["extractor_version"] = 6
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    outline_path = held / ex.OUTLINE_NAME
    outline = json.loads(outline_path.read_text(encoding="utf-8"))
    outline.insert(3, {"level": 0, "title": "Table 1 – GetPDR format", "page": 2})
    outline_path.write_text(json.dumps(outline), encoding="utf-8")
    # a reading command finds the Extract stale and makes it anew
    code, out = run(capsys, "section", "DSP0236", "2.1", catalog_file=catalog_file)
    assert code == 0, out
    assert "1 | 2.1 GetPDR | pages 2-3" in out.splitlines(), out
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["extractor_version"] == ex.EXTRACTOR_VERSION == 7
    outline = json.loads(outline_path.read_text(encoding="utf-8"))
    assert "Table 1 – GetPDR format" not in [e["title"] for e in outline]
