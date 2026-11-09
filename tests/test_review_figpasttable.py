"""Review tests for the Figure caption under a drawing read as a table,
when another table starts within 40 points under that caption
(fix/figure-caption-past-table).

The AC: table A, a `Figure N` line under it, a `Table M` line, then table
B starting within 40 pt under the Figure line: A is named by the Figure
line and B by the Table line (AC-1). A stays without a caption when B
takes the Figure line itself, or a line between them that is not a
numbered caption (AC-2). TABLES_VERSION is 15 and a version 14 store is
read again (AC-6).

Geometry: pdfgen places text by its baseline in PDF points, origin
bottom-left; a 10 pt Helvetica line's top lies about 8 pt above the
baseline and its bottom about 2 pt below it. Table B's top is given as a
distance under the Figure line's bottom, and the AC-1 cases measure that
distance again through the Reader. Every case writes its own PDF."""

import json

import pytest

from bmc_toolkit.spec import tables as T
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok
from tests.test_tables import WIDTHS, cell_table, ruled_table

pytest.importorskip("pdfplumber")

ASCENT = 8
LINE_H = 10
ROW_H = 16
A_TOP = 640
A_BOTTOM = A_TOP - 2 * ROW_H
FIGURE_GAP = 12  # the Figure line's top lies this far under table A
FIGURE_BOTTOM = A_BOTTOM - FIGURE_GAP - LINE_H
OWN_GAP = 12  # table B's own line has its top this far over table B
PACKET = [["+0", "+1", "+2", "+3"], ["RSVD", "Version", "Dest", "Src"]]
CODES = [["Name", "Code", "Meaning"], ["Temp", "01h", "degrees"]]
FIGURE = "Figure 8. VID Format Data Bytes"
TABLE = "Table 3. VID Types"
URL = "https://example.test/DSP0236_1.3.3.pdf"

FORMS = [
    (FIGURE, TABLE),
    ("Figure 63: SMBus during suspend", "Table 13: SMBus Suspend parameters"),
    ("Figure 4 - Packet fields", "Table 7 - Field codes"),
]


def drawing():
    """Table A: a byte layout drawn as tiled boxes, no caption over it."""
    return cell_table(72, A_TOP, [60] * 4, [ROW_H, ROW_H], PACKET)


def figure_line(text):
    """The line under table A, its top FIGURE_GAP points under A's bottom."""
    return (72, A_BOTTOM - FIGURE_GAP - ASCENT, text)


def b_top(start):
    """Table B's top, ``start`` points under the Figure line's bottom."""
    return FIGURE_BOTTOM - start


def table_b(start):
    return ruled_table(72, b_top(start), WIDTHS, [ROW_H, ROW_H], CODES)


def own_line(start, text):
    """A line right over table B, between the Figure line and B."""
    return (72, b_top(start) + OWN_GAP - ASCENT, text)


def page_with(figure, own, start):
    """Table A, the Figure line, table B's own line (or none), table B."""
    lines = [figure_line(figure)]
    if own is not None:
        lines.append(own_line(start, own))
    return drawing() + lines + table_b(start)


def read(tmp_path, page, name="doc.pdf"):
    pdf = pdfgen.write_pdf(tmp_path / name, [page])
    with T.Reader(pdf) as r:
        return r.logical_tables(1)


def captions(tmp_path, page, name="doc.pdf"):
    return [t.caption for t in read(tmp_path, page, name)]


def start_under(tmp_path, page, figure):
    """How far the lower table starts under the bottom of the line
    ``figure``, as the Reader measures both."""
    pdf = pdfgen.write_pdf(tmp_path / "geometry.pdf", [page])
    with T.Reader(pdf) as r:
        info = r.page(1)
        assert len(info.tables) == 2
        lower = max(info.tables, key=lambda t: t.top)
        (line,) = [ln for ln in info.lines if ln.text == figure]
        return lower.top - line.bottom


# ------------------------------------------------------------------ AC-1


@pytest.mark.parametrize("start", [16, 26, 38])
@pytest.mark.parametrize(("figure", "table"), FORMS)
def test_ac1_the_figure_line_names_the_drawing_past_a_captioned_table(
    tmp_path, figure, table, start
):
    page = page_with(figure, table, start)
    # the case the AC names: B starts within 40 pt under the Figure line
    assert 0 < start_under(tmp_path, page, figure) <= T.CAPTION_GAP_PT
    first, second = read(tmp_path, page)
    assert (first.caption, second.caption) == (figure, table)
    assert (first.rows, second.rows) == (PACKET, CODES)
    assert (first.index, second.index) == (1, 2)


def test_ac1_a_ruled_table_over_the_figure_line_is_named_the_same_way(tmp_path):
    # the two tables drawn the other way round: A ruled, B tiled boxes
    top = b_top(26)
    page = ruled_table(72, A_TOP, WIDTHS, [ROW_H, ROW_H], CODES)
    page += [figure_line(FIGURE), (72, top + OWN_GAP - ASCENT, TABLE)]
    page += cell_table(72, top, [60] * 4, [ROW_H, ROW_H], PACKET)
    assert 0 < start_under(tmp_path, page, FIGURE) <= T.CAPTION_GAP_PT
    first, second = read(tmp_path, page)
    assert (first.drawn, second.drawn) == (T.RULED, T.CELLS)
    assert (first.caption, second.caption) == (FIGURE, TABLE)


def test_ac1_the_table_line_reads_as_on_the_page_without_the_figure_line(tmp_path):
    # B's caption does not depend on the Figure line over it
    with_figure = captions(tmp_path, page_with(FIGURE, TABLE, 26), "with.pdf")
    without = drawing() + [own_line(26, TABLE)] + table_b(26)
    assert with_figure == [FIGURE, TABLE]
    assert captions(tmp_path, without, "without.pdf") == [None, TABLE]


def test_ac1_a_numbered_figure_caption_over_the_table_under_is_its_own(tmp_path):
    # round 1 F1: table B's own caption is a numbered `Figure` line (NVMe
    # captions its tables that way); it is B's own as a `Table` line is,
    # so the Figure line under the drawing names the drawing
    figure, own = "Figure 7: Packet layout", "Figure 8: Field codes"
    for start in (16, 26, 38):
        page = page_with(figure, own, start)
        assert 0 < start_under(tmp_path, page, figure) <= T.CAPTION_GAP_PT
        first, second = read(tmp_path, page, f"own{start}.pdf")
        assert (first.caption, second.caption) == (figure, own), start
        assert (first.rows, second.rows) == (PACKET, CODES), start


# ------------------------------------------------------------------ AC-2


def test_ac2_a_table_that_takes_the_figure_line_itself_keeps_it(tmp_path):
    # NVMe captions a table "Figure N" above it: nothing between the line
    # and table B, so the line is B's and table A has no caption
    figure = "Figure 3 - Codes"
    alone = page_with(figure, None, 26)
    assert captions(tmp_path, alone, "alone.pdf") == [None, figure]
    # the same page once B has a numbered caption of its own (AC-1)
    own = page_with(figure, "Table 5 - Codes", 26)
    assert captions(tmp_path, own, "own.pdf") == [figure, "Table 5 - Codes"]


def test_ac2_a_line_that_is_not_a_numbered_caption_still_blocks(tmp_path):
    # a wrapped Figure caption whose last word, "Table", stands alone over
    # table B: B takes that word and A gets nothing from the Figure line
    figure = "Figure 49: Request Message SQE Mapping"
    wrapped = page_with(figure, "Table", 26)
    assert captions(tmp_path, wrapped, "wrapped.pdf") == [None, "Table"]
    # the same page with a numbered caption in that place (AC-1)
    numbered = page_with(figure, "Table 9: Request fields", 26)
    assert captions(tmp_path, numbered, "numbered.pdf") == [
        figure,
        "Table 9: Request fields",
    ]


def test_ac2_a_prose_line_that_starts_with_figure_still_blocks(tmp_path):
    # the line over table B starts with "Figure" and a number but is a
    # sentence, not a numbered caption: B takes it as on develop and the
    # Figure line stays off the drawing
    figure = "Figure 3 - Codes"
    prose = "Figure 9 shows the codes"
    page = page_with(figure, prose, 26)
    assert captions(tmp_path, page, "prose.pdf") == [None, prose]
    # the same page with a numbered Figure caption in that place (AC-1)
    numbered = page_with(figure, "Figure 9: Field codes", 26)
    assert captions(tmp_path, numbered, "numbered.pdf") == [
        figure,
        "Figure 9: Field codes",
    ]


# ------------------------------------------------------------------ AC-6


def test_ac6_tables_version_is_15_and_a_version_14_store_is_not_served(tmp_path):
    assert T.TABLES_VERSION == 15
    found = read(tmp_path, page_with(FIGURE, TABLE, 26))
    vdir = tmp_path / "v"
    vdir.mkdir()
    path = T.store(vdir, [1], found)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tables_version"] == 15
    assert {t["index"]: t["caption"] for t in data["tables"]} == {1: FIGURE, 2: TABLE}
    assert T.stored_for_page(vdir, 1) is not None

    # what version 14 stored for this page: no caption for the drawing
    data["tables_version"] = 14
    for t in data["tables"]:
        if t["index"] == 1:
            t["caption"] = None
    path.write_text(json.dumps(data), encoding="utf-8", newline="")
    assert T.stored_for_page(vdir, 1) is None  # read again, not trusted

    T.store(vdir, [1], found)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tables_version"] == 15
    stored = T.stored_for_page(vdir, 1)
    assert {t.index: t.caption for t in stored} == {1: FIGURE, 2: TABLE}


def test_ac1_ac6_the_table_command_names_both_and_reads_a_version_14_store_again(
    catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    pdf = pdfgen.write_pdf(tmp_path / "pmbus.pdf", [page_with(FIGURE, TABLE, 26)])
    scripted.responses[URL] = ok(pdf.read_bytes())
    argv = ["--catalog", str(catalog_file)]
    assert main([*argv, "fetch", "DSP0236"]) == 0
    capsys.readouterr()
    expected = [
        f"table: {FIGURE} | cells (no ruling lines) | page 1 | 4 columns | 2 rows",
        f"table: {TABLE} | ruled | page 1 | 3 columns | 2 rows",
    ]

    code = main([*argv, "table", "DSP0236", "--page", "1"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert [ln for ln in out.splitlines() if ln.startswith("table: ")] == expected

    store = library.specs / "mctp" / "DSP0236" / "1.3.3" / T.TABLES_NAME
    data = json.loads(store.read_text(encoding="utf-8"))
    assert data["tables_version"] == 15
    data["tables_version"] = 14
    for t in data["tables"]:
        if t["index"] == 1:
            t["caption"] = None
    store.write_text(json.dumps(data), encoding="utf-8", newline="")

    code = main([*argv, "table", "DSP0236", "--page", "1"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert [ln for ln in out.splitlines() if ln.startswith("table: ")] == expected
    data = json.loads(store.read_text(encoding="utf-8"))
    assert data["tables_version"] == 15
    assert {t["index"]: t["caption"] for t in data["tables"]} == {1: FIGURE, 2: TABLE}
