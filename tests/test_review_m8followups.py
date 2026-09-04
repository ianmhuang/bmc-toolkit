"""Reviewer acceptance tests for the M8 follow-ups (fix/m8-followups).

Black-box against extract_pdf, the catalog model, the CLI table and the
refresh writer. Every test here fails on main and passes on the branch.
Round 2 added the cases for the round-1 findings: many tall glyphs beside a
two-line cell, the contents-page threshold with repeats, the `catalog DOC`
listing on a same-day tie, and whitespace in the Document cell. Round 3
added the round-2 finding: a two-line cell whose lower line starts further
left than the upper one (outdented, centred, right-aligned), and a
same-size subscript run that must still ride its line.
"""

import json
import tomllib

import pytest

from bmc_toolkit.spec import extract as ex
from bmc_toolkit.spec import listing as L
from bmc_toolkit.spec import refresh as R
from bmc_toolkit.spec.catalog import load_catalog, parse_catalog
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import MINI_CATALOG

pytest.importorskip("pypdfium2")


def _page_lines(text: str, n: int) -> list[str]:
    marker = ex.PAGE_MARKER.format(n=n)
    start = text.index(marker) + len(marker) + 1
    end = text.find("=== page", start)
    return text[start : end if end >= 0 else None].splitlines()


def _run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ------------------------------------------------------------------- AC-1


def test_ac1_tall_value_on_the_right_leaves_a_two_line_cell_on_the_left(tmp_path):
    # Mirror image of the DSP0222 p.98 layout: the two-line comment sits in
    # the left column, the large monospace-style value in the right one, and
    # a third body-size column follows. The tall box overlaps both comment
    # lines by more than half their height; the comment lines overlap each
    # other by less than half and must stay two lines, in reading order.
    items = [
        (72, 700, "Returned when the Set Link parameters ask"),
        (72, 689.6, "for an unsupported EEE configuration"),
        (330, 695, "0x0909", 15),
        (420, 700, "Set Link EEE Conflict"),
    ]
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "row.pdf", [items]))
    lines = _page_lines(r.text, 1)
    assert len(lines) == 2, lines
    assert lines[0].startswith("Returned when the Set Link parameters ask")
    assert "0x0909" in lines[0] and "Set Link EEE Conflict" in lines[0]
    assert lines[1].strip() == "for an unsupported EEE configuration"


def test_ac1_three_body_lines_beside_one_tall_glyph_stay_three(tmp_path):
    # A row with a three-line cell and one oversized glyph in another column
    # (a bracket, a big code) whose box overlaps the first two lines by more
    # than half their height: three lines, in reading order.
    items = [
        (72, 692, "{", 20),
        (120, 700, "first line of the cell text"),
        (120, 689.6, "second line of the cell text"),
        (120, 679.2, "third line of the cell text"),
    ]
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "three.pdf", [items]))
    lines = [ln.strip() for ln in _page_lines(r.text, 1)]
    joined = " ".join(lines)
    assert "first line of the cell text" in joined
    assert "second line of the cell text" in joined
    assert "third line of the cell text" in joined
    texts = [ln.replace("{", "").strip() for ln in lines]
    assert texts == [
        "first line of the cell text",
        "second line of the cell text",
        "third line of the cell text",
    ], lines


def test_ac1_superscripts_still_join_while_the_tall_cell_stays_apart(tmp_path):
    # Both rules on one page: a superscript and a subscript ride their body
    # line (the existing behaviour), and further down the tall-cell row of
    # the test above still comes out as two lines.
    items = [
        (72, 740, "I"),
        (79, 744, "2", 6),
        (84, 740, "C address"),
        (140, 737, "7", 6),
        (146, 740, "bits"),
        (72, 700, "Returned when the Set Link parameters ask"),
        (72, 689.6, "for an unsupported EEE configuration"),
        (330, 695, "0x0909", 15),
    ]
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "sup.pdf", [items]))
    lines = _page_lines(r.text, 1)
    assert len(lines) == 3, lines
    assert lines[0].replace(" ", "") == "I2Caddress7bits"
    assert lines[1].startswith("Returned when the Set Link parameters ask")
    assert lines[2].strip() == "for an unsupported EEE configuration"


def test_ac1_many_tall_glyphs_still_leave_the_two_line_cell_apart(tmp_path):
    # Round 2: the tall cell carries far more glyphs (24) than either line
    # of the two-line cell (12 and 10). A reference chosen by glyph count
    # would flip to the tall box and merge the second line; AC-1 says the
    # lines stay apart "whatever the number of tall glyphs".
    items = [
        (72, 695, "0xE0 0xE1 0xE2 0xE3 0xE4 0xE5", 15),
        (330, 700, "Reserved for"),
        (330, 689.6, "vendor use"),
    ]
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "many.pdf", [items]))
    lines = _page_lines(r.text, 1)
    assert len(lines) == 2, lines
    assert "0xE0" in lines[0] and "0xE5" in lines[0]
    assert lines[0].replace(" ", "").endswith("Reservedfor"), lines
    assert lines[1].replace(" ", "") == "vendoruse", lines


def test_ac1_outdented_lower_line_stays_whole_and_below(tmp_path):
    # Round 3 (round-2 F1): the lower line of the cell starts 10 pt further
    # left than the upper one, so its first glyph has nothing over it. The
    # line must not lose that glyph to the upper line: two lines, the lower
    # one complete. On main the tall value bridges both lines into one.
    items = [
        (72, 695, "0x0909", 15),
        (340, 700, "Set Link"),
        (330, 689.6, "EEE only"),
    ]
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "outdent.pdf", [items]))
    lines = _page_lines(r.text, 1)
    assert len(lines) == 2, lines
    assert "0x0909" in lines[0] and lines[0].endswith("Set Link"), lines
    assert lines[1].strip() == "EEE only", lines


def test_ac1_centred_cell_wider_below_on_both_sides_stays_two_lines(tmp_path):
    # A centred two-line cell: the lower line sticks out on both sides of
    # the upper one, and a third body-size column follows on the upper
    # baseline. Two lines, the third column on the first.
    items = [
        (72, 695, "0x0909", 15),
        (350, 700, "Set Link"),
        (330, 689.6, "unsupported EEE mode"),
        (450, 700, "Comment"),
    ]
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "centred.pdf", [items]))
    lines = _page_lines(r.text, 1)
    assert len(lines) == 2, lines
    assert "0x0909" in lines[0] and "Set Link" in lines[0] and "Comment" in lines[0]
    assert lines[1].strip() == "unsupported EEE mode", lines


def test_ac1_right_aligned_cell_with_a_longer_lower_line_stays_two_lines(tmp_path):
    # A right-aligned two-line cell: both lines end at the same x, the lower
    # one is longer, so every leading glyph of the lower line lies left of
    # the upper line's start. Helvetica 10 pt: "EEE configuration" from 330
    # ends near 410; "Conflict" is 33.3 pt wide and starts at 376.7.
    items = [
        (72, 695, "0x0909", 15),
        (376.7, 700, "Conflict"),
        (330, 689.6, "EEE configuration"),
    ]
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "right.pdf", [items]))
    lines = _page_lines(r.text, 1)
    assert len(lines) == 2, lines
    assert "0x0909" in lines[0] and lines[0].endswith("Conflict"), lines
    assert lines[1].strip() == "EEE configuration", lines


def test_ac1_same_size_subscript_run_still_rides_its_line_beside_a_split_cell(
    tmp_path,
):
    # Two rows on one page. Row 1: a body-size subscript ("DD" lowered by
    # 2 pt after "0.7V", then "[1]" back on the baseline) has nothing over
    # it and must stay on its line, as it always did. Row 2: the outdented
    # two-line cell beside a tall value must split. Both at once, so the
    # whole-run rule is checked in both directions.
    items = [
        (72, 740, "0.7V"),
        (93, 738, "DD"),
        (108, 740, "[1]"),
        (72, 695, "0x0909", 15),
        (340, 700, "Set Link"),
        (330, 689.6, "EEE only"),
    ]
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "vdd.pdf", [items]))
    lines = _page_lines(r.text, 1)
    assert len(lines) == 3, lines
    assert lines[0].replace(" ", "") == "0.7VDD[1]", lines
    assert lines[1].endswith("Set Link"), lines
    assert lines[2].strip() == "EEE only", lines


def test_ac1_extractor_version_bumped_so_old_extracts_are_stale(tmp_path):
    # A Library entry extracted by the previous extractor (version 3) must
    # no longer count as current, so `status` reports it stale.
    vdir = tmp_path / "v"
    vdir.mkdir()
    (vdir / ex.EXTRACT_NAME).write_text("=== page 1 ===\nx\n", encoding="utf-8")
    meta = {"extractor_version": 3, "pages": 1}
    (vdir / ex.META_NAME).write_text(json.dumps(meta), encoding="utf-8")
    assert ex.EXTRACTOR_VERSION > 3
    assert not ex.is_current(vdir)
    meta["extractor_version"] = ex.EXTRACTOR_VERSION
    (vdir / ex.META_NAME).write_text(json.dumps(meta), encoding="utf-8")
    assert ex.is_current(vdir)


# ------------------------------------------------------------------- AC-2


_ENTRIES = [
    ("1", "Introduction", 1),
    ("1.1", "Scope", 1),
    ("1.2", "Audience", 2),
    ("2", "Overview", 2),
    ("2.1", "Architecture", 3),
    ("2.2", "Interfaces", 3),
    ("3", "Commands", 4),
    ("3.1", "Get Capabilities", 4),
    ("3.2", "Get Power", 5),
]


def _contents_page():
    contents = [(72, 740, "Table of Contents")]
    y = 720.0
    for num, title, page in _ENTRIES:
        contents.append((72, y, f"{num} {title} " + "." * 40 + f" {page}"))
        y -= 14
    return contents


def _document_pages(contents_twice: bool = False):
    """Cover, contents (once or twice), five body pages with a footer number."""
    pages = [[(200, 700, "Cover")], _contents_page()]
    if contents_twice:
        pages.append(_contents_page())
    for printed in range(1, 6):
        pages.append(
            [
                (72, 700, f"Body of printed page {printed}"),
                (300, 40, f"Version 1.5 {printed} of 5"),
            ]
        )
    return pages


def test_ac2_anchor_only_bookmarks_fall_back_to_the_contents_pages(tmp_path):
    plain = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "plain.pdf", _document_pages()))
    assert plain.outline_source == "contents"  # the reference outline
    anchored = pdfgen.write_pdf(
        tmp_path / "anchored.pdf",
        _document_pages(),
        bookmarks=[
            (0, "Ref_DSP0236", 2),
            (0, "OLE_LINK1", 4),
            (0, "ref_IETF_RFC5234", 5),
            (0, "https://example.test/standards/DSP0218_1.0.0.pdf", 3),
        ],
    )
    r = ex.extract_pdf(anchored)
    assert r.outline_source == "contents"
    assert r.outline == plain.outline
    assert len(r.outline) == len(_ENTRIES)


def test_ac2_anchor_only_bookmarks_and_no_contents_page_give_none(tmp_path):
    pdf = pdfgen.write_pdf(
        tmp_path / "a.pdf",
        [pdfgen.plain_page(["one"]), pdfgen.plain_page(["two"])],
        bookmarks=[(0, "Ref_DSP0236", 0), (0, "OLE_LINK1", 1)],
    )
    r = ex.extract_pdf(pdf)
    assert r.outline == []
    assert r.outline_source == "none"
    assert r.page_offset is None


def test_ac2_mixed_outline_keeps_only_the_real_headings(tmp_path):
    pdf = pdfgen.write_pdf(
        tmp_path / "m.pdf",
        [pdfgen.plain_page(["one"]), pdfgen.plain_page(["two"]), pdfgen.plain_page(["3"])],
        bookmarks=[
            (0, "1 Scope", 0),
            (0, "Ref_DSP0236", 0),
            (1, "1.1 GET_VERSION request", 0),
            (0, "OLE_LINK7", 1),
            (0, "2 Overview", 1),
            (0, "_Toc123456", 2),
        ],
    )
    r = ex.extract_pdf(pdf)
    assert r.outline_source == "bookmarks"
    assert [(e["level"], e["title"], e["page"]) for e in r.outline] == [
        (0, "1 Scope", 1),
        (1, "1.1 GET_VERSION request", 1),
        (0, "2 Overview", 2),
    ]


def test_ac2_bookmarks_all_on_one_page_of_a_longer_document_are_no_outline(tmp_path):
    pdf = pdfgen.write_pdf(
        tmp_path / "one.pdf",
        _document_pages(),
        bookmarks=[(0, "Mark2", 3), (0, "RefISO", 3), (0, "SMBus", 3)],
    )
    r = ex.extract_pdf(pdf)
    assert r.outline_source == "contents"
    assert [e["title"] for e in r.outline][:2] == ["1 Introduction", "1.1 Scope"]
    assert r.page_offset == 2


def test_ac2_a_single_bookmark_and_a_one_page_document_keep_their_bookmarks(tmp_path):
    single = pdfgen.write_pdf(
        tmp_path / "s.pdf",
        [pdfgen.plain_page(["one"]), pdfgen.plain_page(["two"])],
        bookmarks=[(0, "Mark2", 1)],
    )
    r = ex.extract_pdf(single)
    assert r.outline_source == "bookmarks"
    assert [e["title"] for e in r.outline] == ["Mark2"]
    one_page = pdfgen.write_pdf(
        tmp_path / "p.pdf",
        [pdfgen.plain_page(["only page"])],
        bookmarks=[(0, "Foreword", 0), (0, "Scope", 0)],
    )
    r = ex.extract_pdf(one_page)
    assert r.outline_source == "bookmarks"
    assert [e["title"] for e in r.outline] == ["Foreword", "Scope"]
    # the anchor rule still applies to a one-page document
    mixed = pdfgen.write_pdf(
        tmp_path / "q.pdf",
        [pdfgen.plain_page(["only page"])],
        bookmarks=[(0, "Foreword", 0), (0, "OLE_LINK1", 0)],
    )
    r = ex.extract_pdf(mixed)
    assert [e["title"] for e in r.outline] == ["Foreword"]


# ------------------------------------------------------------------- AC-3


def test_ac3_contents_printed_twice_give_each_entry_once(tmp_path):
    once = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "once.pdf", _document_pages()))
    twice = ex.extract_pdf(
        pdfgen.write_pdf(tmp_path / "twice.pdf", _document_pages(contents_twice=True))
    )
    assert once.outline_source == twice.outline_source == "contents"
    assert len(once.outline) == len(_ENTRIES)
    titles = [e["title"] for e in twice.outline]
    assert titles == [f"{n} {t}" for n, t, _ in _ENTRIES]
    assert len(titles) == len(set(titles))
    # the physical pages agree with the single-contents document, shifted by
    # the extra contents page
    assert [e["page"] for e in twice.outline] == [e["page"] + 1 for e in once.outline]


def test_ac3_reprinted_contents_page_with_additions_keeps_the_additions():
    # Round 2: a second contents page that repeats the first ten entries and
    # adds two. The repeats appear once; the two additions are not lost to
    # the eight-matching-lines threshold that makes a page a contents page.
    first = [f"{n} Section {n} " + "." * 30 + f" {n + 4}" for n in range(1, 11)]
    reprinted = list(first) + [
        "11 Annex " + "." * 30 + " 30",
        "12 Index " + "." * 30 + " 31",
    ]
    entries = ex.parse_contents([first, reprinted])
    titles = [e["title"] for e in entries]
    assert titles == [f"{n} Section {n}" for n in range(1, 11)] + ["11 Annex", "12 Index"]
    assert [e["printed"] for e in entries][-2:] == [30, 31]


def test_ac3_section_lists_a_repeated_entry_once(tmp_path, monkeypatch, capsys):
    from bmc_toolkit.spec.library import Library

    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    library = Library(root)
    catalog_file = tmp_path / "catalog.toml"
    catalog_file.write_text(MINI_CATALOG, encoding="utf-8", newline="")
    pdf_path = pdfgen.write_pdf(tmp_path / "doc.pdf", _document_pages(contents_twice=True))
    code = main(
        [
            "--catalog",
            str(catalog_file),
            "add",
            str(pdf_path),
            "--document",
            "DSP0236",
            "--version",
            "1.3.3",
        ]
    )
    assert code == 0, capsys.readouterr().out
    code = main(["--catalog", str(catalog_file), "extract", "DSP0236"])
    assert code == 0, capsys.readouterr().out
    capsys.readouterr()
    code = main(["--catalog", str(catalog_file), "section", "DSP0236", "Scope"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert out.count("1.1 Scope") == 1, out
    code = main(["--catalog", str(catalog_file), "section", "DSP0236", "3"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert out.count("3 Commands") == 1 and out.count("3.2 Get Power") == 1, out
    assert library.root == root


# ------------------------------------------------------------------- AC-4


def _catalog_with(versions) -> str:
    """A one-document catalog; ``versions`` is [(version, published, access)]."""
    head = """
schema_version = 1

[families.spdm]
title = "SPDM"
publisher = "DMTF"

[[documents]]
id = "DSP0277"
family = "spdm"
title = "Secured Messages Using SPDM"
access = "open"
fetch = "direct"
"""
    blocks = []
    for version, published, access in versions:
        url = f"https://example.test/{version.replace(' ', '_')}.pdf"
        if access != "open":
            url = ""
        block = (
            "\n[[documents.versions]]\n"
            f'version = "{version}"\n'
            f'url = "{url}"\n'
            'type = "pdf"\n'
            f'published = "{published}"\n'
        )
        if access != "open":
            block += f'access = "{access}"\n'
        blocks.append(block)
    return head + "".join(blocks)


def _doc(versions):
    return parse_catalog(tomllib.loads(_catalog_with(versions))).get("DSP0277")


def test_ac4_same_day_tie_goes_to_the_higher_version_in_either_order():
    a = [("1.3.0", "2025-12-08", "open"), ("2.0.0", "2025-12-08", "open")]
    for order in (a, list(reversed(a))):
        doc = _doc(order)
        assert doc.latest().version == "2.0.0", order
        assert doc.newest_open().version == "2.0.0", order


def test_ac4_tie_compares_the_numbers_not_the_strings():
    doc = _doc([("1.10", "2025-12-08", "open"), ("1.9", "2025-12-08", "open")])
    assert doc.latest().version == "1.10"
    doc = _doc([("1.9", "2025-12-08", "open"), ("1.10", "2025-12-08", "open")])
    assert doc.latest().version == "1.10"
    doc = _doc([("2.0", "2025-12-08", "open"), ("2.0.0", "2025-12-08", "open")])
    assert doc.latest().version == "2.0.0"


def test_ac4_non_numeric_tie_keeps_catalog_order_and_a_later_date_wins():
    doc = _doc([("draft", "2025-12-08", "open"), ("final", "2025-12-08", "open")])
    assert doc.latest().version == "final"
    doc = _doc([("final", "2025-12-08", "open"), ("draft", "2025-12-08", "open")])
    assert doc.latest().version == "draft"
    doc = _doc([("2.0.0", "2025-12-08", "open"), ("1.3.1", "2026-01-15", "open")])
    assert doc.latest().version == "1.3.1"


def test_ac4_newest_open_ignores_a_gated_same_day_higher_version():
    doc = _doc([("1.3.0", "2025-12-08", "open"), ("2.0.0", "2025-12-08", "gated")])
    assert doc.latest().version == "2.0.0"
    assert doc.newest_open().version == "1.3.0"
    doc = _doc([("2.0.0", "2025-12-08", "gated"), ("1.3.0", "2025-12-08", "open")])
    assert doc.latest().version == "2.0.0"
    assert doc.newest_open().version == "1.3.0"


def test_ac4_catalog_document_listing_agrees_with_latest_on_a_same_day_tie(
    tmp_path, capsys
):
    # Round 2: `catalog DOC` prints versions newest first; on a same-day tie
    # the order must follow the numbers, whatever the entry order, so that
    # the first listed version is the one the latest: line names.
    a = [("1.3.0", "2025-12-08", "open"), ("2.0.0", "2025-12-08", "open")]
    for order in (a, list(reversed(a))):
        path = tmp_path / "catalog.toml"
        path.write_text(_catalog_with(order), encoding="utf-8", newline="")
        code, out, _err = _run(capsys, "catalog", "DSP0277", catalog_file=path)
        assert code == 0, out
        lines = out.splitlines()
        assert "latest: 2.0.0" in lines, order
        listed = [ln.split("\t")[1] for ln in lines if ln.startswith("\t")]
        assert listed == ["2.0.0", "1.3.0"], (order, listed)


def test_ac4_shipped_latest_is_independent_of_entry_order():
    import dataclasses

    shipped = load_catalog()
    for doc in shipped.documents:
        if not doc.versions:
            continue
        flipped = dataclasses.replace(doc, versions=tuple(reversed(doc.versions)))
        assert doc.latest() == flipped.latest(), doc.id
        assert doc.newest_open() == flipped.newest_open(), doc.id
    assert shipped.get("DSP0276").latest().version == "2.0.0"
    assert shipped.get("DSP0277").latest().version == "2.0.0"


# ------------------------------------------------------------------- AC-5


GOLDEN = """# Golden Questions

Intro text.

| # | Question | Document | Where | Commands |
|---|---|---|---|---|
| G1 | latest | DSP0236 1.3.3 | section 8 | `page DSP0236 24` |
| G2 | older | DSP0236 1.3.2 | section 8 | `page DSP0236 24` |
| G3 | latest again | DSP0236 1.3.3 | section 9 | `find DSP0236 y` |
| G4 | bare id | IPMI | page 1 | `find IPMI x` |
| G5 | two documents | DSP0236 1.3.2; IPMI 2.0 rev 1.1 | page 2 | `find IPMI z` |
| G6 | none | - | - | - |
"""


@pytest.fixture
def mini_file(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(MINI_CATALOG, encoding="utf-8", newline="")
    return path


def _table_rows(out: str) -> dict[str, list[str]]:
    rows = {}
    for ln in out.splitlines()[2:]:
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        doc_id = cells[1].split("`")[1]
        rows[doc_id] = cells
    return rows


def test_ac5_verified_cell_groups_question_ids_per_version(mini_file, tmp_path, capsys):
    golden = tmp_path / "golden.md"
    golden.write_text(GOLDEN, encoding="utf-8", newline="")
    code, out, err = _run(
        capsys, "catalog", "--table", "--golden", str(golden), catalog_file=mini_file
    )
    assert code == 0 and err == ""
    rows = _table_rows(out)
    assert rows["DSP0236"][5] == "G1, G3 (1.3.3); G2, G5 (1.3.2)"
    assert rows["IPMI"][5] == "G4; G5 (2.0 rev 1.1)"
    assert rows["BUNDLE"][5] == "-"
    assert rows["SECRET"][5] == "-"
    # without --golden the table is unchanged: every Verified cell is "-"
    code, plain, err = _run(capsys, "catalog", "--table", catalog_file=mini_file)
    assert code == 0 and err == ""
    assert {r[5] for r in _table_rows(plain).values()} == {"-"}
    assert plain.splitlines()[0] == out.splitlines()[0]


def test_ac5_unknown_document_is_still_reported_and_the_rest_kept(
    mini_file, tmp_path, capsys
):
    golden = tmp_path / "golden.md"
    golden.write_text(
        GOLDEN.replace("| G4 | bare id | IPMI |", "| G4 | bare id | NOPE 1.0 |"),
        encoding="utf-8",
        newline="",
    )
    code, out, err = _run(
        capsys, "catalog", "--table", "--golden", str(golden), catalog_file=mini_file
    )
    assert code == 0
    assert "G4: unknown document 'NOPE'" in err
    rows = _table_rows(out)
    assert rows["IPMI"][5] == "G5 (2.0 rev 1.1)"


def test_ac5_document_cell_splits_on_any_whitespace_between_id_and_version(
    mini_file, tmp_path, capsys
):
    # Round 2: a tab or a run of spaces after the id (a spreadsheet paste)
    # is still "<id> <version>": no unknown-document report, the version
    # named in the Verified cell.
    golden = (
        "# Golden Questions\n\n"
        "| # | Question | Document | Where | Commands |\n"
        "|---|---|---|---|---|\n"
        "| G1 | tab | DSP0236\t1.3.3 | section 1 | `page DSP0236 1` |\n"
        "| G2 | spaces | IPMI    2.0 rev 1.1 | section 2 | `page IPMI 1` |\n"
        "| G3 | both | DSP0236 \t 1.3.2 | section 3 | `page DSP0236 2` |\n"
    )
    path = tmp_path / "golden.md"
    path.write_text(golden, encoding="utf-8", newline="")
    code, out, err = _run(
        capsys, "catalog", "--table", "--golden", str(path), catalog_file=mini_file
    )
    assert code == 0
    assert "unknown document" not in err, err
    rows = _table_rows(out)
    assert rows["DSP0236"][5] == "G1 (1.3.3); G3 (1.3.2)"
    assert rows["IPMI"][5] == "G2 (2.0 rev 1.1)"


def test_ac5_shipped_golden_file_names_a_version_for_every_verified_row(capsys):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    golden = root / "docs" / "golden-questions.md"
    code = main(["catalog", "--table", "--golden", str(golden)])
    out = capsys.readouterr().out
    assert code == 0
    rows = _table_rows(out)
    verified = {k: v[5] for k, v in rows.items() if v[5] != "-"}
    assert verified, "no Verified row at all"
    for doc_id, cell in verified.items():
        for group in cell.split("; "):
            assert group.endswith(")"), (doc_id, cell)
            ids, _, version = group[:-1].partition(" (")
            assert version, (doc_id, cell)
            assert all(q.startswith("G") for q in ids.split(", ")), (doc_id, cell)


# ------------------------------------------------------------------- AC-6


def test_ac6_shipped_catalog_lists_versions_in_publication_then_version_order():
    from bmc_toolkit.spec.catalog import version_numbers

    shipped = load_catalog()
    for doc in shipped.documents:
        keys = [(v.published, version_numbers(v.version)) for v in doc.versions]
        assert keys == sorted(keys), (doc.id, [v.version for v in doc.versions])
    dsp0277 = [v.version for v in shipped.get("DSP0277").versions]
    assert dsp0277.index("1.0.1") < dsp0277.index("1.1.1")
    assert dsp0277.index("1.0.1") > dsp0277.index("1.1.0")  # publication order kept


def test_ac6_refresh_write_appends_same_day_versions_ascending(mini_file):
    seen = [
        L.Seen("2.0.0", "https://example.test/DSP0236_2.0.0.pdf", "2026-08-03"),
        L.Seen("1.3.10", "https://example.test/DSP0236_1.3.10.pdf", "2026-08-03"),
        L.Seen("1.3.9", "https://example.test/DSP0236_1.3.9.pdf", "2026-08-03"),
        L.Seen("1.3.11", "https://example.test/DSP0236_1.3.11.pdf", "2026-09-01"),
    ]
    R.append_versions(mini_file, "DSP0236", seen)
    text = mini_file.read_text("utf-8")
    positions = [text.index(f'version = "{s.version}"') for s in seen]
    # 1.3.9 < 1.3.10 < 2.0.0 (same day, by numbers) < 1.3.11 (later day)
    assert positions[2] < positions[1] < positions[0] < positions[3]
    doc = load_catalog(mini_file).get("DSP0236")
    assert doc.latest().version == "1.3.11"
    assert [v.version for v in doc.versions][-4:] == ["1.3.9", "1.3.10", "2.0.0", "1.3.11"]
