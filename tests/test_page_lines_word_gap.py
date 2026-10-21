"""Word gaps in the lines around a table: `page_lines` breaks upright
words at WORD_GAP_PT, as table cells do. DSP0274 sets a heading's number
about 2 pt from its title (`10.32.2.1.2GetCSR structure`); joined, the
line is not that heading and the table names the section above it."""

import json

import pytest

from bmc_toolkit.spec import tables as T
from tests import pdfgen
from tests.test_table_section import hold, run, small, table_cites
from tests.test_tables import furniture

pdfplumber = pytest.importorskip("pdfplumber")
pytest.importorskip("pypdfium2")

GAP = 2.1  # DMTF's distance between two runs that carry no space
ROTATED = (0, 1, -1, 0)

# Helvetica advance widths at 10 pt
NUMBER = 13.90  # "5.1"
CAPTION_HEAD = 57.25  # "Table 1 - Set"


def heading_page():
    """`5 Codes`, then the `5.1` and `Set` runs of heading 5.1, then a
    captioned table whose title has a run of its own."""
    return furniture(1) + [
        (72, 740, "5 Codes"),
        (72, 724, "Text of the section."),
        (72, 704, "5.1"),
        (72 + NUMBER + GAP, 704, "Set"),
        (72, 688, "Table 1 - Set"),
        (72 + CAPTION_HEAD + GAP, 688, "format"),
        *small(676),
    ]


BOOKMARKS = [(0, "5 Codes", 0), (1, "5.1 Set", 0)]


def heading_pdf(tmp_path):
    return pdfgen.write_pdf(tmp_path / "gap.pdf", [heading_page()], BOOKMARKS)


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    pdf = heading_pdf(tmp_path).read_bytes()
    return hold(pdf, catalog_file, library, scripted, capsys)


def gap_after(chars, first: str, second: str) -> float:
    """x0 of the run starting ``second`` minus x1 of the char before it."""
    text = "".join(c["text"] for c in chars)
    at = text.index(first + second) + len(first)
    return round(chars[at]["x0"] - chars[at - 1]["x1"], 2)


# ------------------------------------------------------------------ AC-1


def test_the_fixture_runs_are_a_word_gap_apart(tmp_path):
    with pdfplumber.open(heading_pdf(tmp_path)) as pdf:
        chars = sorted(pdf.pages[0].chars, key=lambda c: (round(c["top"]), c["x0"]))
    assert gap_after(chars, "5.1", "Set") == pytest.approx(GAP, abs=0.05)
    assert gap_after(chars, "Table 1 - Set", "format") == pytest.approx(GAP, abs=0.05)


def test_upright_runs_a_word_gap_apart_are_separate_words(tmp_path):
    with pdfplumber.open(heading_pdf(tmp_path)) as pdf:
        texts = [ln.text for ln in T.page_lines(pdf.pages[0])]
    assert "5.1 Set" in texts
    assert "Table 1 - Set format" in texts
    assert "5.1Set" not in texts


def test_kerning_gaps_stay_inside_a_word(tmp_path):
    # "a" is 5.56 pt wide: gaps of 0.5 and 1.5 pt are kerning, not spaces
    page = [(72, 700, "a"), (72 + 5.56 + 0.5, 700, "b"), (72 + 11.62 + 1.5, 700, "c")]
    path = pdfgen.write_pdf(tmp_path / "kern.pdf", [page])
    with pdfplumber.open(path) as pdf:
        assert [ln.text for ln in T.page_lines(pdf.pages[0])] == ["abc"]


# ------------------------------------------------------------------ AC-2


def test_a_heading_a_word_gap_from_its_number_names_the_table(
    held, catalog_file, capsys
):
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0, out
    assert table_cites(out) == [("5.1 Set", "PDF page 1", "lines table 1")]


# ------------------------------------------------------------------ AC-3


def test_a_caption_run_a_word_gap_apart_keeps_its_space(held, catalog_file, capsys):
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0, out
    captions = [ln.split(" | ")[0] for ln in out.splitlines() if ln[:7] == "table: "]
    assert captions == ["table: Table 1 - Set format"]


# ------------------------------------------------------------------ AC-4


def test_rotated_characters_keep_the_default_reading(tmp_path):
    # pdfplumber reads characters that are not upright in columns, a column
    # being those whose x0 lie within x_tolerance: two glyphs turned 90
    # degrees with x0 2.2 pt apart are one word at 3 pt, two at WORD_GAP_PT
    page = [
        (72, 700, "Upright"),
        (300, 600, "t", 10, ROTATED),
        (302.2, 600, "e", 10, ROTATED),
    ]
    path = pdfgen.write_pdf(tmp_path / "rot.pdf", [page])
    with pdfplumber.open(path) as pdf:
        p = pdf.pages[0]
        default = [w["text"] for w in p.extract_words() if not w["upright"]]
        narrow = [
            w["text"]
            for w in p.extract_words(x_tolerance=T.WORD_GAP_PT)
            if not w["upright"]
        ]
        assert default != narrow  # the rule bites for these glyphs
        texts = [ln.text for ln in T.page_lines(p)]
    assert "Upright" in texts
    rotated = [t for t in texts if t != "Upright"]
    assert " ".join(rotated) == " ".join(default)


# ------------------------------------------------------------------ AC-5


def test_tables_version_is_8_and_a_version_7_store_is_read_again(
    held, catalog_file, capsys
):
    assert T.TABLES_VERSION == 8
    code, first = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0, first
    store = held / T.TABLES_NAME
    data = json.loads(store.read_text("utf-8"))
    assert data["tables_version"] == 8
    # what version 7 stored for this page: the section above the heading
    data["tables_version"] = 7
    for table in data["tables"]:
        table["section"] = "5 Codes"
    store.write_text(json.dumps(data), "utf-8", newline="")
    assert T.stored_for_page(held, 1) is None
    code, again = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0 and again == first
    data = json.loads(store.read_text("utf-8"))
    assert data["tables_version"] == 8
    assert [t["section"] for t in data["tables"]] == ["5.1 Set"]
