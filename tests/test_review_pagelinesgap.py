"""Review tests for the word gap in the lines around a table
(fix/page-lines-word-gap).

DSP0274 draws a heading's number and its title as two runs about 2 pt
apart with no space character; at pdfplumber's default x_tolerance (3 pt)
`page_lines` joined them (`10.32.2.1.2GetCSR structure`), so the heading
was not recognised and the table named the section above it. The AC:
`page_lines` breaks upright characters into words at WORD_GAP_PT and
leaves characters that are not upright at the default (AC-1), a table
under such a heading names it (AC-2), a caption whose title is such a run
keeps its space (AC-3), rotated glyphs read as before (AC-4), and
TABLES_VERSION 8 retires every version 7 store (AC-5).

The runs are placed from Helvetica's AFM advance widths (what pdfminer
uses for the base-14 fonts), so a gap written here is the gap pdfplumber
measures; the first test checks that."""

import json

import pytest

from bmc_toolkit.spec import tables as T
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok
from tests.test_tables import HEADER, ROWS_1, furniture, ruled_table

pdfplumber = pytest.importorskip("pdfplumber")
pytest.importorskip("pypdfium2")

# Helvetica advance widths, per 1000 em, for the characters the runs use
AFM = {
    " ": 278,
    "-": 333,
    ".": 278,
    "1": 556,
    "2": 556,
    "3": 556,
    "7": 556,
    "C": 722,
    "G": 778,
    "R": 722,
    "S": 667,
    "T": 611,
    "a": 556,
    "b": 556,
    "c": 500,
    "d": 556,
    "e": 556,
    "f": 278,
    "i": 222,
    "l": 222,
    "r": 333,
    "s": 500,
    "t": 278,
    "u": 556,
}

GAP = 2.1  # DMTF's distance between two runs that carry no space
KERN = 0.5  # a kerning gap, well inside a word
ROTATED = (0, 1, -1, 0)
URL = "https://example.test/DSP0236_1.3.3.pdf"
WIDTHS = [100, 80, 200]


def width(text: str, size: int = 10) -> float:
    return sum(AFM[ch] for ch in text) * size / 1000


def runs(x, y, words, gap, size=10):
    """``words`` drawn left to right as separate runs ``gap`` pt apart with
    no space character between them."""
    items = []
    for word in words:
        items.append((x, y, word, size))
        x += width(word, size) + gap
    return items


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def heading_page():
    """`7 Messages`, body text, then heading 7.2.1 as its number and its
    title in two runs a word gap apart, a caption whose title is a run of
    its own, and a small ruled table."""
    return furniture(1) + [
        (72, 740, "7 Messages"),
        (72, 724, "Text of the chapter."),
        *runs(72, 704, ["7.2.1", "GetCSR structure"], GAP),
        *runs(72, 688, ["Table 3 -", "GetCSR fields"], GAP),
        *ruled_table(72, 676, WIDTHS, [16] * 2, [HEADER, ROWS_1[0]]),
    ]


BOOKMARKS = [(0, "7 Messages", 0), (1, "7.2.1 GetCSR structure", 0)]


def heading_pdf(tmp_path):
    return pdfgen.write_pdf(tmp_path / "heading.pdf", [heading_page()], BOOKMARKS)


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    """The heading PDF fetched as DSP0236 1.3.3; its version directory."""
    scripted.responses[URL] = ok(heading_pdf(tmp_path).read_bytes())
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


def line_texts(path) -> list[str]:
    with pdfplumber.open(path) as pdf:
        return [ln.text for ln in T.page_lines(pdf.pages[0])]


def cites(out: str) -> list[tuple[str, ...]]:
    """(section, page field, lines field) of every `cite:` line."""
    return [
        tuple(ln.split(" | ")[2:5])
        for ln in out.splitlines()
        if ln.startswith("cite: ")
    ]


def captions(out: str) -> list[str]:
    return [ln.split(" | ")[0] for ln in out.splitlines() if ln.startswith("table: ")]


# ------------------------------------------------------------------ AC-1


def test_the_runs_lie_a_word_gap_apart_as_pdfplumber_measures_them(tmp_path):
    # guard for the geometry every other test relies on
    with pdfplumber.open(heading_pdf(tmp_path)) as pdf:
        chars = pdf.pages[0].chars
    by_top: dict[int, list] = {}
    for c in chars:
        by_top.setdefault(round(c["top"]), []).append(c)
    lines = {
        "".join(c["text"] for c in sorted(group, key=lambda c: c["x0"])): sorted(
            group, key=lambda c: c["x0"]
        )
        for group in by_top.values()
    }
    assert "7.2.1GetCSR structure" in lines  # no space character is drawn
    assert "Table 3 -GetCSR fields" in lines
    for text in ["7.2.1GetCSR structure", "Table 3 -GetCSR fields"]:
        line = lines[text]
        at = text.index("G")  # the first character of the second run
        gap = line[at]["x0"] - line[at - 1]["x1"]
        assert gap == pytest.approx(GAP, abs=0.05)
        assert T.WORD_GAP_PT < gap < 3  # splits at the new gap, joined at the default


def test_upright_runs_a_word_gap_apart_are_two_words(tmp_path):
    texts = line_texts(heading_pdf(tmp_path))
    assert "7.2.1 GetCSR structure" in texts
    assert "Table 3 - GetCSR fields" in texts
    assert not any("7.2.1GetCSR" in t for t in texts)
    assert not any("-GetCSR" in t for t in texts)


def test_a_kerning_gap_stays_inside_a_word(tmp_path):
    page = runs(72, 700, ["a", "b", "c"], KERN) + runs(72, 680, ["Get", "CSR"], 1.5)
    path = pdfgen.write_pdf(tmp_path / "kern.pdf", [page])
    assert line_texts(path) == ["abc", "GetCSR"]


def test_upright_runs_split_on_a_line_that_also_holds_rotated_glyphs(tmp_path):
    # the rule is per character, not per cell as in _extract: the rotated
    # pair beside the upright runs does not put the line back to 3 pt
    page = runs(72, 700, ["7.2.1", "GetCSR"], GAP) + [
        (300, 696, "t", 10, ROTATED),
        (302.2, 696, "t", 10, ROTATED),
    ]
    path = pdfgen.write_pdf(tmp_path / "mixed.pdf", [page])
    texts = line_texts(path)
    joined = " ".join(texts)
    assert "7.2.1 GetCSR" in joined
    assert "7.2.1GetCSR" not in joined
    assert "tt" in joined  # the rotated glyphs are still one word


# ------------------------------------------------------------------ AC-2


def test_a_table_under_a_heading_set_in_two_runs_names_that_heading(
    held, catalog_file, capsys
):
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0, out
    assert cites(out) == [("7.2.1 GetCSR structure", "PDF page 1", "lines table 1")]


# ------------------------------------------------------------------ AC-3


def test_a_caption_title_set_as_its_own_run_keeps_its_space(
    held, catalog_file, capsys
):
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0, out
    assert captions(out) == ["table: Table 3 - GetCSR fields"]


# ------------------------------------------------------------------ AC-4


def test_rotated_glyphs_a_word_gap_apart_read_as_at_the_default(tmp_path):
    # pdfplumber reads characters that are not upright in columns of chars
    # whose x0 lie within x_tolerance: two glyphs turned 90 degrees with x0
    # 2.2 pt apart are one column at 3 pt and two at WORD_GAP_PT
    page = [
        (72, 700, "Upright"),
        (300, 600, "t", 10, ROTATED),
        (302.2, 600, "s", 10, ROTATED),
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
        assert len(default) == 1 and len(narrow) == 2  # the rule bites here
        texts = [ln.text for ln in T.page_lines(p)]
    assert "Upright" in texts
    rotated = [t for t in texts if t != "Upright"]
    assert rotated == default


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
    assert T.stored_for_page(held, 1) is not None  # the current version is served

    # what version 7 stored for this page: the section above the heading
    data["tables_version"] = 7
    for table in data["tables"]:
        table["section"] = "7 Messages"
    store.write_text(json.dumps(data), "utf-8", newline="")
    assert T.stored_for_page(held, 1) is None  # not served

    code, again = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0, again
    assert again == first
    assert cites(again) == [("7.2.1 GetCSR structure", "PDF page 1", "lines table 1")]
    data = json.loads(store.read_text("utf-8"))
    assert data["tables_version"] == 8
    assert data["pages_done"] == [1]
    assert [t["section"] for t in data["tables"]] == ["7.2.1 GetCSR structure"]
