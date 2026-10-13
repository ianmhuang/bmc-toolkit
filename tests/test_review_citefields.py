"""Reviewer acceptance tests for the lines field of a ``table`` Citation
(AC-1, and the printed half of AC-7).

The expected form is not written down here. It is read from the ``cite:``
line the ``table`` command prints for a synthetic ruled PDF, with the
table's index replaced by ``K``; SKILL.md and docs/COMMANDS.md have to
describe the field in that form wherever they describe it. On develop both
files gave ``table K`` for a field the tool prints as ``lines table K``, so
the document tests fail there; the tool's own output is the same on both
sides.
"""

import re
from pathlib import Path

import pytest

from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok

pytest.importorskip("pypdfium2")
pytest.importorskip("pdfplumber")

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
COMMANDS = ROOT / "docs" / "COMMANDS.md"

URL = "https://example.test/DSP0236_1.3.3.pdf"
WIDTHS = [100, 80, 200]
HEADER = ["Name", "Code", "Meaning"]

# A code span that names a table by its index K: `table K`, `lines table K`
INDEX_SPAN = re.compile(r"`((?:[a-z]+ )*table K)`")
INDEX_MENTION = re.compile(r"\btable K\b")


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def flat(text):
    """Text on one line, so a form is found across a line break."""
    return " ".join(text.split())


def grid(x, top, widths, heights, cells):
    """A ruled table the way Word draws it: thin filled rectangles as
    rules, one text item per cell; ``top`` is the table's top edge."""
    items = []
    xs = [x]
    for w in widths:
        xs.append(xs[-1] + w)
    ys = [top]
    for h in heights:
        ys.append(ys[-1] - h)
    for y in ys:
        items.append(("fill", x, y - 0.3, sum(widths), 0.6))
    for cx in xs:
        items.append(("fill", cx - 0.3, top - sum(heights), 0.6, sum(heights)))
    for r, row in enumerate(cells):
        for c, text in enumerate(row):
            items.append((xs[c] + 3, ys[r] - 11, text))
    return items


def document(tmp_path):
    """Page 1: a heading, a captioned ruled table, a second heading below
    it. Page 2: prose only."""
    page1 = [
        (72, 760, "Spec Title"),
        (300, 40, "Page 1"),
        (72, 740, "5 Codes"),
        (72, 714, "Table 1 - Codes"),
    ]
    page1 += grid(
        72,
        700,
        WIDTHS,
        [16] * 3,
        [HEADER, ["Temperature", "01h", "degrees"], ["Voltage", "02h", "volts"]],
    )
    page1 += [(72, 640, "5.1 After the table")]
    page2 = [
        (72, 760, "Spec Title"),
        (300, 40, "Page 2"),
        (72, 700, "6 Nothing ruled here"),
    ]
    return pdfgen.write_pdf(
        tmp_path / "doc.pdf",
        [page1, page2],
        bookmarks=[
            (0, "5 Codes", 0),
            (1, "5.1 After the table", 0),
            (0, "6 Nothing ruled here", 1),
        ],
    ).read_bytes()


@pytest.fixture
def printed_form(catalog_file, library, scripted, tmp_path, capsys):
    """The lines field ``table`` prints, its index written as ``K``."""
    scripted.responses[URL] = ok(document(tmp_path))
    code, out = run(
        capsys, "fetch", "DSP0236", "--no-extract", catalog_file=catalog_file
    )
    assert code == 0, out
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0, out
    cites = [ln for ln in out.splitlines() if ln.startswith("cite: ")]
    assert len(cites) == 1, out
    fields = cites[0].split(" | ")
    assert len(fields) == 7, fields
    assert fields[3] == "PDF page 1"
    # AC-7: the helper prints what it printed; the index sits behind `lines`
    assert re.fullmatch(r"lines table \d+", fields[4]), fields[4]
    return re.sub(r"\d+$", "K", fields[4])


def citation_definition():
    text = SKILL.read_text("utf-8")
    start = text.index("- **Citation**:")
    return flat(text[start : text.index("\n## ", start)])


def citation_rules():
    text = SKILL.read_text("utf-8")
    start = text.index("\n## Citation rules\n")
    return flat(text[start : text.index("\n## ", start + 1)])


def table_row():
    rows = [
        line
        for line in SKILL.read_text("utf-8").splitlines()
        if line.startswith("| `table DOC")
    ]
    assert len(rows) == 1, rows
    return rows[0]


@pytest.mark.parametrize("path", [SKILL, COMMANDS], ids=lambda p: p.name)
def test_document_names_the_field_the_way_table_prints_it(path, printed_form):
    """AC-1: every description of the field is the printed form, and
    nothing names it without `lines`."""
    text = flat(path.read_text("utf-8"))
    described = INDEX_SPAN.findall(text)
    assert described, f"{path.name} does not describe the field"
    assert set(described) == {printed_form}, described
    # no mention outside the code spans counted above
    assert len(INDEX_MENTION.findall(text)) == len(described)


@pytest.mark.parametrize(
    "place",
    [citation_definition, table_row, citation_rules],
    ids=["definition", "table row", "citation rules"],
)
def test_each_place_in_skill_md_gives_the_printed_form(place, printed_form):
    """AC-1: the Citation definition, the `table` row of the command table
    and the Citation rules each describe the field, each as printed."""
    described = INDEX_SPAN.findall(place())
    assert described, "the field is not described here"
    assert set(described) == {printed_form}, described
