"""The section a `cite:` line names: the one a table starts in, and for
`page --section` the sections each page spans; plus the wording that
describes both."""

import json
import re
from pathlib import Path

import pytest

from bmc_toolkit.spec import search as search_mod
from bmc_toolkit.spec import tables as tables_mod
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok
from tests.test_tables import HEADER, ROWS_1, ROWS_2, furniture, ruled_table

pytest.importorskip("pypdfium2")
pytest.importorskip("pdfplumber")

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
COMMANDS = ROOT / "docs" / "COMMANDS.md"

URL = "https://example.test/DSP0236_1.3.3.pdf"
WIDTHS = [100, 80, 200]
TWO = [16] * 2
THREE = [16] * 3


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def small(top):
    return ruled_table(72, top, WIDTHS, TWO, [HEADER, ROWS_1[0]])


def sections_pdf(tmp_path):
    """Page 1: under `5.1 Set` a captioned table and one without a caption,
    the same under `5.2 Get` (whose caption the text under `5 Codes`
    quotes), then under `5.3 Long` a table without a caption that runs onto
    page 2. Page 2: the rest of it, then `6 Next` and a table."""
    page1 = furniture(1) + [
        (72, 740, "5 Codes"),
        (72, 724, "The second format is shown in Table 2 - Get format below."),
        (72, 704, "5.1 Set"),
        (72, 688, "Table 1 - Set format"),
        *small(676),
        *small(626),
        (72, 578, "5.2 Get"),
        (72, 562, "Table 2 - Get format"),
        *small(550),
        *small(500),
        (72, 240, "5.3 Long"),
        *ruled_table(72, 200, WIDTHS, THREE, [HEADER, *ROWS_1]),
    ]
    page2 = furniture(2) + [
        *ruled_table(72, 740, WIDTHS, THREE, [HEADER, *ROWS_2]),
        (72, 660, "6 Next"),
        (72, 644, "Text of the next section."),
        *small(620),
    ]
    return pdfgen.write_pdf(
        tmp_path / "sections.pdf",
        [page1, page2],
        bookmarks=[
            (0, "5 Codes", 0),
            (1, "5.1 Set", 0),
            (1, "5.2 Get", 0),
            (1, "5.3 Long", 0),
            (0, "6 Next", 1),
        ],
    ).read_bytes()


def hold(pdf, catalog_file, library, scripted, capsys):
    scripted.responses[URL] = ok(pdf)
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    return hold(sections_pdf(tmp_path), catalog_file, library, scripted, capsys)


def table_cites(out):
    """(section, page field, lines field) of every `cite:` line."""
    return [
        tuple(line.split(" | ")[2:5])
        for line in out.splitlines()
        if line.startswith("cite: ")
    ]


def test_a_table_gets_the_section_it_starts_in(held, catalog_file, capsys):
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0, out
    assert table_cites(out) == [
        ("5.1 Set", "PDF page 1", "lines table 1"),
        # no caption: the heading above it, not the top of the page
        ("5.1 Set", "PDF page 1", "lines table 2"),
        # its caption is quoted under `5 Codes` first
        ("5.2 Get", "PDF page 1", "lines table 3"),
        ("5.2 Get", "PDF page 1", "lines table 4"),
        ("5.3 Long", "PDF pages 1-2", "lines table 5"),
    ]
    captions = [ln.split(" | ")[0] for ln in out.splitlines() if ln[:7] == "table: "]
    assert captions == [
        "table: Table 1 - Set format",
        "table: -",
        "table: Table 2 - Get format",
        "table: -",
        "table: -",
    ]


def test_a_table_over_pages_keeps_the_section_of_its_first_part(
    held, catalog_file, capsys
):
    code, out = run(
        capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file
    )
    assert code == 0, out
    assert table_cites(out) == [
        ("5.3 Long", "PDF pages 1-2", "lines table 5"),
        # the top of page 2 is still `5.3 Long`; its heading is above it
        ("6 Next", "PDF page 2", "lines table 2"),
    ]


def test_a_heading_not_on_the_page_leaves_the_entry_at_the_top(
    catalog_file, library, scripted, tmp_path, capsys
):
    page = furniture(1) + [(72, 740, "Some text above the table."), *small(700)]
    pdf = pdfgen.write_pdf(
        tmp_path / "worded.pdf", [page], bookmarks=[(0, "Annex Z Overview", 0)]
    ).read_bytes()
    hold(pdf, catalog_file, library, scripted, capsys)
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0, out
    assert table_cites(out) == [("Annex Z Overview", "PDF page 1", "lines table 1")]


def test_no_outline_prints_a_dash(catalog_file, library, scripted, tmp_path, capsys):
    page = furniture(1) + [(72, 740, "Some text above the table."), *small(700)]
    pdf = pdfgen.write_pdf(tmp_path / "bare.pdf", [page]).read_bytes()
    hold(pdf, catalog_file, library, scripted, capsys)
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0, out
    assert table_cites(out) == [("-", "PDF page 1", "lines table 1")]


def test_a_store_of_the_previous_version_is_read_again(held, catalog_file, capsys):
    code, first = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0, first
    store = held / tables_mod.TABLES_NAME
    data = json.loads(store.read_text("utf-8"))
    assert data["tables_version"] == tables_mod.TABLES_VERSION
    # what the previous version left: its number, the section at the page top
    data["tables_version"] = 4
    for table in data["tables"]:
        table["section"] = "5 Codes"
    store.write_text(json.dumps(data), "utf-8", newline="")
    code, again = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0 and again == first
    data = json.loads(store.read_text("utf-8"))
    assert data["tables_version"] == tables_mod.TABLES_VERSION != 4
    assert [t["section"] for t in data["tables"]] == [
        "5.1 Set",
        "5.1 Set",
        "5.2 Get",
        "5.2 Get",
        "5.3 Long",
        "6 Next",  # page 2 was read too: the last table of page 1 runs onto it
    ]
    # the keys the previous version reads are all still there
    assert set(data) == {"tables_version", "pages_done", "tables"}
    assert set(data["tables"][0]) == {
        "first",
        "last",
        "index",
        "caption",
        "section",
        "drawn",
        "columns",
        "parts",
        "rows",
        "row_pages",
    }


@pytest.mark.parametrize(("query", "pages"), [("5.1", [1]), ("5.3", [1, 2])])
def test_page_section_prints_the_cite_line_of_each_page(
    held, catalog_file, capsys, query, pages
):
    code, out = run(
        capsys, "page", "DSP0236", "--section", query, catalog_file=catalog_file
    )
    assert code == 0, out
    singles = []
    for n in pages:
        code, single = run(capsys, "page", "DSP0236", str(n), catalog_file=catalog_file)
        assert code == 0, single
        singles.append(single)
    assert out == "\n".join(singles)
    first = out.splitlines()[0]
    assert first.split(" | ")[2] == "5 Codes; 5.1 Set; 5.2 Get; 5.3 Long"


def flat(text):
    return " ".join(text.split())


def test_the_docs_say_which_section_each_command_prints():
    skill = flat(SKILL.read_text("utf-8"))
    commands = flat(COMMANDS.read_text("utf-8"))
    assert "one section for `page --section`" not in skill
    assert "the section the table starts in for `table`" in skill
    assert "names X only" not in commands
    assert "`page --section X` prints the same line for each page" in commands
    assert "the section in force where the table starts" in commands


def test_the_lines_field_is_described_with_its_prefix_everywhere():
    for path in (SKILL, COMMANDS):
        text = flat(path.read_text("utf-8"))
        assert not re.search(r"(?<!lines )rendered page`", text), path.name
        assert "`lines rendered page`" in text, path.name
    row = next(
        line
        for line in SKILL.read_text("utf-8").splitlines()
        if line.startswith("| `render DOC")
    )
    assert "`lines rendered page`" in row
    doc = flat(search_mod.__doc__)
    assert "``lines rendered page``" in doc and "``lines table K``" in doc
    assert not re.search(r"(?<!lines )(rendered page|table K)``", doc)
