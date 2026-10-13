"""Reviewer acceptance tests for the section a `table` Citation names
(AC-1 to AC-5, AC-7): the Outline entry in force where the table starts on
its first page. Black-box through the CLI on synthetic PDFs. One is shaped
like the reported case: a page with printed line numbers that starts inside
one section and holds two more headings, each followed by a captioned and an
uncaptioned table. No network: the scripted client serves the bytes."""

import json

import pytest

from bmc_toolkit.spec import tables as tables_mod
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok

pytest.importorskip("pypdfium2")
pytest.importorskip("pdfplumber")

URL = "https://example.test/DSP0236_1.3.3.pdf"
WIDTHS = [100, 80, 200]
HEADER = ["Name", "Code", "Meaning"]
ROW = ["Temperature", "01h", "degrees"]


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def grid(x, top, widths, heights, cells):
    """A ruled table drawn the way Word does (thin filled rectangles); `top`
    is its top edge in PDF points, origin bottom-left."""
    items = []
    total_w = sum(widths)
    total_h = sum(heights)
    xs = [x]
    for w in widths:
        xs.append(xs[-1] + w)
    ys = [top]
    for h in heights:
        ys.append(ys[-1] - h)
    for y in ys:
        items.append(("fill", x, y - 0.3, total_w, 0.6))
    for cx in xs:
        items.append(("fill", cx - 0.3, top - total_h, 0.6, total_h))
    for r, row in enumerate(cells):
        for c, text in enumerate(row):
            items.append((xs[c] + 3, ys[r] - 11, text))
    return items


def small(top):
    """A header and one row, 32 points tall."""
    return grid(72, top, WIDTHS, [16, 16], [HEADER, ROW])


def furniture(n):
    return [(72, 760, "Spec Title"), (300, 40, f"Page {n}")]


def numbered(y, number, text):
    """A body line with its printed line number in the margin."""
    return [(37, y, str(number)), (72, y, text)]


def terminus_doc(tmp_path):
    """Page 2 starts inside `9.1 Terminus` (heading on page 1) and holds
    the headings of 9.1.1 and 9.1.2; under each, a captioned table and one
    without a caption. Every body line carries a printed line number."""
    page1 = furniture(1) + pdfgen.numbered_page(
        300, ["9 Commands", "9.1 Terminus", "A terminus answers these commands."]
    )
    page2 = furniture(2) + [
        *numbered(740, 303, "More text about the terminus."),
        *numbered(720, 304, "9.1.1 SetTID command"),
        *numbered(704, 305, "Table 1 - SetTID request"),
        *small(690),
        *small(640),
        *numbered(590, 306, "9.1.2 GetTID command"),
        *numbered(574, 307, "Table 2 - GetTID request"),
        *small(560),
        *small(510),
    ]
    page3 = furniture(3) + pdfgen.numbered_page(
        308, ["9.2 Next command", "Text of the next command."], top=700.0
    )
    return pdfgen.write_pdf(
        tmp_path / "terminus.pdf",
        [page1, page2, page3],
        bookmarks=[
            (0, "9 Commands", 0),
            (1, "9.1 Terminus", 0),
            (2, "9.1.1 SetTID command", 1),
            (2, "9.1.2 GetTID command", 1),
            (1, "9.2 Next command", 2),
        ],
    ).read_bytes()


def quoted_doc(tmp_path):
    """The text under `5.1 Set` quotes the caption of the table that sits
    under `5.2 Get` further down the page."""
    page = furniture(1) + [
        (72, 740, "5 Codes"),
        (72, 724, "5.1 Set"),
        (72, 708, "Table 2 - Get format below gives the reply."),
        (72, 692, "Table 1 - Set format"),
        *small(680),
        (72, 624, "5.2 Get"),
        (72, 608, "Table 2 - Get format"),
        *small(596),
    ]
    return pdfgen.write_pdf(
        tmp_path / "quoted.pdf",
        [page],
        bookmarks=[(0, "5 Codes", 0), (1, "5.1 Set", 0), (1, "5.2 Get", 0)],
    ).read_bytes()


def long_doc(tmp_path):
    """Under `5.3 Long`, a table without a caption that starts at the bottom
    of page 1 and carries on at the top of page 2; below it on page 2 the
    heading `6 Next` and one more table."""
    page1 = furniture(1) + [
        (72, 740, "5 Codes"),
        (72, 724, "Codes are listed by sensor type."),
        (72, 216, "5.3 Long"),
        *grid(
            72,
            200,
            WIDTHS,
            [16] * 3,
            [HEADER, ROW, ["Voltage", "02h", "volts"]],
        ),
    ]
    page2 = furniture(2) + [
        *grid(
            72,
            740,
            WIDTHS,
            [16] * 3,
            [HEADER, ["Current", "03h", "amps"], ["Fan", "04h", "rpm"]],
        ),
        (72, 660, "6 Next"),
        (72, 644, "Text of the next section."),
        *small(620),
    ]
    return pdfgen.write_pdf(
        tmp_path / "long.pdf",
        [page1, page2],
        bookmarks=[(0, "5 Codes", 0), (1, "5.3 Long", 0), (0, "6 Next", 1)],
    ).read_bytes()


def hold(pdf, catalog_file, library, scripted, capsys):
    scripted.responses[URL] = ok(pdf)
    code, out = run(
        capsys, "fetch", "DSP0236", "--no-extract", catalog_file=catalog_file
    )
    assert code == 0, out
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


@pytest.fixture
def terminus(catalog_file, library, scripted, tmp_path, capsys):
    return hold(terminus_doc(tmp_path), catalog_file, library, scripted, capsys)


def cites(out):
    """(section, page field, lines field) of every `cite:` line."""
    return [
        tuple(line.split(" | ")[2:5])
        for line in out.splitlines()
        if line.startswith("cite: ")
    ]


def captions(out):
    return [
        line.split(" | ")[0][len("table: ") :]
        for line in out.splitlines()
        if line.startswith("table: ")
    ]


SET = "9.1.1 SetTID command"
GET = "9.1.2 GetTID command"


# ---------------------------------------------------------------- AC-1


def test_ac1_each_table_names_the_heading_above_it_on_a_numbered_page(
    terminus, catalog_file, capsys
):
    code, out = run(
        capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file
    )
    assert code == 0, out
    assert captions(out) == [
        "Table 1 - SetTID request",
        "-",
        "Table 2 - GetTID request",
        "-",
    ]
    # the tables without a caption read `9.1 Terminus`, the section at the
    # top of the page, before the change
    assert cites(out) == [
        (SET, "PDF page 2", "lines table 1"),
        (SET, "PDF page 2", "lines table 2"),
        (GET, "PDF page 2", "lines table 3"),
        (GET, "PDF page 2", "lines table 4"),
    ]


# ---------------------------------------------------------------- AC-7


def test_ac7_table_output_differs_in_the_section_field_only(
    terminus, catalog_file, capsys
):
    code, out = run(
        capsys,
        "table",
        "DSP0236",
        "--page",
        "2",
        "--index",
        "2",
        catalog_file=catalog_file,
    )
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].split(" | ") == [
        "cite: mctp",
        "DSP0236 1.3.3",
        SET,  # the one field that changed
        "PDF page 2",
        "lines table 2",
        URL,
        str(terminus),
    ]
    assert lines[1:] == [
        "table: - | ruled | page 2 | 3 columns | 2 rows",
        "Name        | Code | Meaning",
        "------------+------+--------",
        "Temperature | 01h  | degrees",
    ]


def test_ac7_page_and_find_name_sections_as_before(terminus, catalog_file, capsys):
    # guard: this also holds on the base branch
    code, out = run(capsys, "page", "DSP0236", "2", catalog_file=catalog_file)
    assert code == 0, out
    fields = out.splitlines()[0].split(" | ")
    assert fields[2] == f"9.1 Terminus; {SET}; {GET}"
    assert fields[3] == "PDF page 2"
    assert out.count("cite:") == 1
    code, out = run(
        capsys, "find", "DSP0236", "GetTID request", catalog_file=catalog_file
    )
    assert code == 0, out
    hits = [ln for ln in out.splitlines() if ln.startswith("DSP0236 p.")]
    assert len(hits) == 1
    assert hits[0].startswith("DSP0236 p.2")
    assert hits[0].split(" | ")[1] == GET


# ---------------------------------------------------------------- AC-2


def test_ac2_a_caption_quoted_under_another_section_does_not_place_the_table(
    catalog_file, library, scripted, tmp_path, capsys
):
    hold(quoted_doc(tmp_path), catalog_file, library, scripted, capsys)
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0, out
    assert captions(out) == ["Table 1 - Set format", "Table 2 - Get format"]
    # the second read `5.1 Set`, where its caption is quoted, before
    assert cites(out) == [
        ("5.1 Set", "PDF page 1", "lines table 1"),
        ("5.2 Get", "PDF page 1", "lines table 2"),
    ]


# ---------------------------------------------------------------- AC-3


def test_ac3_a_table_over_two_pages_names_the_section_its_first_part_starts_in(
    catalog_file, library, scripted, tmp_path, capsys
):
    hold(long_doc(tmp_path), catalog_file, library, scripted, capsys)
    # asked from the page it continues on: `6 Next` is on that page too
    code, out = run(
        capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file
    )
    assert code == 0, out
    assert captions(out) == ["-", "-"]
    assert cites(out) == [
        ("5.3 Long", "PDF pages 1-2", "lines table 1"),
        ("6 Next", "PDF page 2", "lines table 2"),
    ]
    spanning = out.splitlines()[0]
    assert "table: - | ruled | pages 1-2 | 3 columns | 5 rows" in out
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0, out
    assert [ln for ln in out.splitlines() if ln.startswith("cite: ")] == [spanning]


# ---------------------------------------------------------------- AC-4


def test_ac4_a_heading_the_page_text_lacks_leaves_the_entry_at_the_page_top(
    catalog_file, library, scripted, tmp_path, capsys
):
    # guard: this also holds on the base branch. The Outline places
    # `Appendix Q Register map` on page 2, whose text never says so.
    page1 = furniture(1) + [
        (72, 740, "4 Scope"),
        (72, 724, "This document covers one thing."),
    ]
    page2 = furniture(2) + [(72, 740, "Some text above the table."), *small(700)]
    pdf = pdfgen.write_pdf(
        tmp_path / "worded.pdf",
        [page1, page2],
        bookmarks=[(0, "4 Scope", 0), (0, "Appendix Q Register map", 1)],
    ).read_bytes()
    hold(pdf, catalog_file, library, scripted, capsys)
    code, out = run(
        capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file
    )
    assert code == 0, out
    assert cites(out) == [("Appendix Q Register map", "PDF page 2", "lines table 1")]


def test_ac4_an_empty_outline_prints_a_dash(
    catalog_file, library, scripted, tmp_path, capsys
):
    # guard: this also holds on the base branch
    page = furniture(1) + [(72, 740, "Some text above the table."), *small(700)]
    pdf = pdfgen.write_pdf(tmp_path / "bare.pdf", [page]).read_bytes()
    hold(pdf, catalog_file, library, scripted, capsys)
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0, out
    assert cites(out) == [("-", "PDF page 1", "lines table 1")]


# ---------------------------------------------------------------- AC-5


def test_ac5_a_version_4_store_is_not_trusted_and_keeps_its_keys(
    terminus, catalog_file, capsys
):
    code, fresh = run(
        capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file
    )
    assert code == 0, fresh
    path = terminus / "tables.json"
    data = json.loads(path.read_text("utf-8"))
    assert 2 in data["pages_done"]
    # the file as the previous version left it: its number, its sections
    data["tables_version"] = 4
    for entry in data["tables"]:
        entry["section"] = "STALE SECTION"
    path.write_text(json.dumps(data), "utf-8", newline="")
    # no --force: the page is read again all the same
    code, again = run(
        capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file
    )
    assert code == 0, again
    assert "STALE SECTION" not in again
    assert again == fresh
    data = json.loads(path.read_text("utf-8"))
    assert data["tables_version"] == tables_mod.TABLES_VERSION
    assert data["tables_version"] != 4
    assert 2 in data["pages_done"]
    assert [t["section"] for t in data["tables"]] == [SET, SET, GET, GET]
    # the layout the previous version reads
    assert set(data) == {"tables_version", "pages_done", "tables"}
    for entry in data["tables"]:
        assert set(entry) == {
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
    # and the second call is answered from the store it wrote
    code, stored = run(
        capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file
    )
    assert code == 0 and stored == fresh
