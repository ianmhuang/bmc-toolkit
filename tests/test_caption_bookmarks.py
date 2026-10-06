"""A bookmark that is a table or figure caption is not an Outline entry, so
it neither owns the lines under it nor ends the section it sits in
(DSP0248 1.3.1 and DSP0134 3.10.0 bookmark every caption at level 0)."""

import json
from pathlib import Path

import pytest

from bmc_toolkit.spec import extract as ex
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok
from tests.test_extract import _contents_document, _pages_of
from tests.test_tables import HEADER, ROWS_1, furniture, ruled_table

pytest.importorskip("pypdfium2")

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
URL = "https://example.test/DSP0236_1.3.3.pdf"


def outline_titles(tmp_path, titles):
    pages = [pdfgen.plain_page([f"page {i}"]) for i in range(len(titles))]
    bookmarks = [(0, title, i) for i, title in enumerate(titles)]
    pdf = pdfgen.write_pdf(tmp_path / "b.pdf", pages, bookmarks=bookmarks)
    return [e["title"] for e in ex.extract_pdf(pdf).outline]


# ------------------------------------------------------------------- AC-1


@pytest.mark.parametrize(
    "title",
    [
        "Table 1 – SMBIOS 2.1 (32-bit) Entry Point structure",
        "Figure 24 — Sensor state transitions",
        "Table 69 - GetPDR command format",
        "Table A.1 – Annex codes",
        "Table 6-2: DCMI Capabilities parameters",
        "Figure 3.2a. Timing",
    ],
    ids=["en-dash", "em-dash", "hyphen", "annex", "colon", "period"],
)
def test_ac1_a_caption_bookmark_is_dropped(tmp_path, title):
    assert outline_titles(tmp_path, ["1 Scope", title, "2 Commands"]) == [
        "1 Scope",
        "2 Commands",
    ]


@pytest.mark.parametrize(
    "title",
    [
        "Tables",
        "Figures",
        "Table of Contents",
        "Table 100 describes the format of this PDR.",
        "Figure 3 shows the message flow",
        "Example 1: SMIC Interface in I/O Space",
    ],
    ids=["tables", "figures", "contents", "sentence", "mention", "example"],
)
def test_ac1_a_title_that_only_mentions_a_table_is_kept(tmp_path, title):
    assert outline_titles(tmp_path, ["1 Scope", title, "2 Commands"]) == [
        "1 Scope",
        title,
        "2 Commands",
    ]


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
        ],
    )
    r = ex.extract_pdf(captions)
    assert r.outline_source == "contents"
    assert r.outline == contents_only.outline


# ------------------------------------------------------------------- AC-3


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def captioned_pdf(tmp_path):
    """`2.1 GetPDR` on page 2 with a captioned table, its text running on
    to page 3, `2.2 FindPDR` at the top of page 4; the caption is
    bookmarked at level 0 between them, the way DSP0248 has it."""
    widths = [100, 80, 200]
    pages = [
        furniture(1) + [(72, 740, "1 Scope"), (72, 724, "Scope text.")],
        furniture(2)
        + [
            (72, 740, "2 Commands"),
            (72, 724, "2.1 GetPDR"),
            (72, 708, "Table 1 - GetPDR format"),
            *ruled_table(72, 696, widths, [16] * 3, [HEADER, *ROWS_1]),
            (72, 600, "Text after the table."),
        ],
        furniture(3) + [(72, 740, "The recordHandle field selects the record.")],
        [(72, 740, "2.2 FindPDR"), (72, 724, "FindPDR text.")],
    ]
    return pdfgen.write_pdf(
        tmp_path / "captioned.pdf",
        pages,
        bookmarks=[
            (0, "1 Scope", 0),
            (0, "2 Commands", 1),
            (1, "2.1 GetPDR", 1),
            (0, "Table 1 - GetPDR format", 1),
            (1, "2.2 FindPDR", 3),
        ],
    ).read_bytes()


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    scripted.responses[URL] = ok(captioned_pdf(tmp_path))
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out


def cite_section(out):
    cites = [ln for ln in out.splitlines() if ln.startswith("cite: ")]
    return [ln.split(" | ")[2] for ln in cites]


def test_ac3_section_runs_on_past_a_caption_bookmark(held, catalog_file, capsys):
    code, out = run(capsys, "section", "DSP0236", "2.1", catalog_file=catalog_file)
    assert code == 0, out
    assert "1 | 2.1 GetPDR | pages 2-3" in out.splitlines(), out


def test_ac3_lines_under_the_table_belong_to_the_section(held, catalog_file, capsys):
    code, out = run(
        capsys, "find", "DSP0236", "recordHandle", catalog_file=catalog_file
    )
    assert code == 0, out
    hits = out.strip().splitlines()
    assert len(hits) == 1 and hits[0].split(" | ")[1] == "2.1 GetPDR", out

    code, out = run(capsys, "page", "DSP0236", "3", catalog_file=catalog_file)
    assert code == 0, out
    assert cite_section(out) == ["2.1 GetPDR"], out


def test_ac3_a_table_cites_the_section_not_its_caption(held, catalog_file, capsys):
    pytest.importorskip("pdfplumber")
    code, out = run(
        capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file
    )
    assert code == 0, out
    assert cite_section(out) == ["2.1 GetPDR"], out


# ------------------------------------------------------------------- AC-4


def test_ac4_a_version_6_extract_is_stale(tmp_path):
    vdir = tmp_path / "v"
    vdir.mkdir()
    (vdir / ex.EXTRACT_NAME).write_text("=== page 1 ===\nx\n", encoding="utf-8")
    (vdir / ex.META_NAME).write_text(
        json.dumps({"extractor_version": 6}), encoding="utf-8"
    )
    assert not ex.is_current(vdir)


def test_ac4_skill_says_caption_bookmarks_are_not_taken():
    text = SKILL.read_text(encoding="utf-8")
    start = text.index("- **Outline**")
    outline = text[start : text.index("\n- **", start + 1)]
    assert "caption" in outline, outline
