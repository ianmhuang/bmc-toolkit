"""Extraction geometry, line numbers, outlines, and the files written."""

import json

import pytest

from bmc_toolkit.spec import extract as ex
from tests import pdfgen

pytest.importorskip("pypdfium2")


def page_lines(text: str, n: int) -> list[str]:
    marker = ex.PAGE_MARKER.format(n=n)
    start = text.index(marker) + len(marker) + 1
    end = text.find("=== page", start)
    return text[start : end if end >= 0 else None].splitlines()


# ------------------------------------------------------------------ layout


def test_page_markers_and_reading_order(tmp_path):
    pdf = pdfgen.write_pdf(
        tmp_path / "a.pdf",
        [
            pdfgen.plain_page(["first line", "second line"]),
            pdfgen.plain_page(["page two"]),
        ],
    )
    r = ex.extract_pdf(pdf)
    assert r.pages == 2
    lines = r.text.splitlines()
    assert lines[0] == "=== page 1 ==="
    assert lines[1:3] == ["first line", "second line"]
    assert lines[3] == "=== page 2 ==="
    assert lines[4] == "page two"
    assert r.text.endswith("\n")


def test_two_columns_stay_aligned_across_rows(tmp_path):
    rows = [
        ("Request Data", "1", "Group Extension"),
        ("", "2", "Parameter Selector"),
        ("Response Data", "1", "Completion Code"),
    ]
    items = []
    y = 700.0
    for a, b, c in rows:
        if a:
            items.append((72, y, a))
        items.append((200, y, b))
        items.append((230, y, c))
        y -= 14
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "t.pdf", [items]))
    lines = page_lines(r.text, 1)
    cols_b = [ln.index(b) for ln, (_, b, _) in zip(lines, rows, strict=True)]
    cols_c = [ln.index(c) for ln, (_, _, c) in zip(lines, rows, strict=True)]
    assert len(set(cols_b)) == 1, lines
    assert len(set(cols_c)) == 1, lines
    assert lines[0].startswith("Request Data")
    assert lines[1].startswith(" ")


def test_words_keep_single_spaces_and_wide_gaps_grow(tmp_path):
    items = [(72, 700, "Get Device ID"), (300, 700, "NetFn App")]
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "w.pdf", [items]))
    line = page_lines(r.text, 1)[0]
    assert line.startswith("Get Device ID")
    assert "  " not in line[: len("Get Device ID")]
    gap = line[len("Get Device ID") : line.index("NetFn")]
    assert gap.strip() == "" and len(gap) > 10


def test_descenders_do_not_split_lines(tmp_path):
    items = [(72, 700, "Capabilities and Configuration Commands")]
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "d.pdf", [items]))
    assert page_lines(r.text, 1) == ["Capabilities and Configuration Commands"]


# ------------------------------------------------------------ line numbers


def test_margin_numbers_are_removed_and_mapped(tmp_path):
    lines = ["MSB", "most significant byte", "", "PCIe", "Peripheral", "Express"]
    page = pdfgen.numbered_page(680, lines)
    page.insert(0, (72, 760, "MCTP Base Specification"))
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "n.pdf", [page]))
    got = page_lines(r.text, 1)
    assert got[0] == "MCTP Base Specification"
    assert got[1:] == lines
    assert r.numbered_pages == 1
    lm = r.linemap["pages"]["1"]
    assert (lm["first"], lm["last"]) == (680, 685)
    assert lm["lines"] == {str(i): 680 + i - 1 for i in range(1, 7)}


def test_right_aligned_numbers_of_mixed_width(tmp_path):
    # 98, 99, 100, 101, 102: right edges align, left edges differ by a digit.
    items = []
    y = 700.0
    for i, n in enumerate(range(98, 103)):
        width = 5.56 * len(str(n))  # Helvetica digit advance at 10pt
        items.append((54 - width, y, str(n)))
        items.append((72, y, f"text line {i}"))
        y -= 14
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "r.pdf", [items]))
    assert r.numbered_pages == 1
    assert page_lines(r.text, 1) == [f"text line {i}" for i in range(5)]


def test_numbered_list_at_text_margin_is_not_line_numbers(tmp_path):
    items = [(72, 720, "This process includes:")]
    y = 706.0
    for n in range(1, 8):
        items.append((72, y, str(n)))
        items.append((90, y, f"step {n}"))
        y -= 14
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "l.pdf", [items]))
    assert r.numbered_pages == 0
    assert page_lines(r.text, 1)[1].startswith("1")


def test_table_column_of_sequential_codes_is_not_line_numbers(tmp_path):
    # A code column far from the margin (IPMI sensor unit codes) must stay.
    items = [(72, 720, "Table 43, Sensor Unit Type Codes")]
    y = 706.0
    for code in range(0, 8):
        items.append((154, y, str(code)))
        items.append((200, y, "unit"))
        y -= 14
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "c.pdf", [items]))
    assert r.numbered_pages == 0


def test_non_consecutive_numbers_are_not_line_numbers(tmp_path):
    items = []
    y = 700.0
    for n in (10, 12, 13, 14, 15, 16):
        items.append((37, y, str(n)))
        items.append((72, y, "text"))
        y -= 14
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "g.pdf", [items]))
    assert r.numbered_pages == 0


def test_short_run_accepted_only_when_it_continues(tmp_path):
    first = pdfgen.numbered_page(100, ["a", "b", "c", "d", "e", "f"])
    figure = [
        (37, 700, "106"),
        (72, 700, "Key: D = device"),
        (200, 600, "D1"),
        (300, 600, "D2"),
    ]
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "s.pdf", [first, figure]))
    assert r.numbered_pages == 2
    assert page_lines(r.text, 2)[0] == "Key: D = device"
    assert r.linemap["pages"]["2"]["first"] == 106
    # the same short page alone is not numbered
    r2 = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "s2.pdf", [figure]))
    assert r2.numbered_pages == 0


def test_numbering_must_continue_across_pages(tmp_path):
    first = pdfgen.numbered_page(100, ["a", "b", "c", "d", "e", "f"])
    restart = pdfgen.numbered_page(1, ["x", "y", "z", "w", "v", "u"])
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / "k.pdf", [first, restart]))
    assert list(r.linemap["pages"]) == ["1"]


def test_plain_document_is_identical_with_detector_off(tmp_path, monkeypatch):
    pages = [pdfgen.plain_page(["1. Introduction", "Text here", "2. Scope", "More"])]
    pdf = pdfgen.write_pdf(tmp_path / "p.pdf", pages)
    with_detector = ex.extract_pdf(pdf).text
    monkeypatch.setattr(ex, "detect_line_numbers", lambda page, prev: False)
    assert ex.extract_pdf(pdf).text == with_detector


# ----------------------------------------------------------------- outline


def test_outline_from_bookmarks(tmp_path):
    pdf = pdfgen.write_pdf(
        tmp_path / "b.pdf",
        [pdfgen.plain_page(["one"]), pdfgen.plain_page(["two"])],
        bookmarks=[(0, "1 Scope", 0), (1, "1.1  Detail", 0), (0, "2 Commands", 1)],
    )
    r = ex.extract_pdf(pdf)
    assert r.outline_source == "bookmarks"
    assert r.outline == [
        {"level": 0, "title": "1 Scope", "page": 1},
        {"level": 1, "title": "1.1 Detail", "page": 1},
        {"level": 0, "title": "2 Commands", "page": 2},
    ]
    assert r.page_offset is None


def _contents_document(tmp_path, offset: int):
    """A cover, a contents page, and body pages whose footer prints its number."""
    contents = [(72, 740, "Table of Contents")]
    entries = [
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
    y = 720.0
    for num, title, page in entries:
        contents.append(
            (72, y, f"{num} {title} ........................................ {page}")
        )
        y -= 14
    pages = [[(200, 700, "Cover")], contents]
    for printed in range(1, 6):
        body = [
            (72, 700, f"Body of printed page {printed}"),
            (300, 40, f"Version 1.5 {printed} of 5"),
        ]
        pages.append(body)
    assert len(pages) == 2 + 5
    pdf = pdfgen.write_pdf(tmp_path / f"c{offset}.pdf", pages)
    return pdf, entries


def test_outline_from_contents_with_page_offset(tmp_path):
    pdf, entries = _contents_document(tmp_path, 2)
    r = ex.extract_pdf(pdf)
    assert r.outline_source == "contents"
    assert r.page_offset == 2  # printed 1 is physical 3
    assert len(r.outline) == len(entries)
    assert r.outline[0] == {"level": 0, "title": "1 Introduction", "page": 3}
    assert r.outline[1] == {"level": 1, "title": "1.1 Scope", "page": 3}
    assert r.outline[-1] == {"level": 1, "title": "3.2 Get Power", "page": 7}


def test_no_bookmarks_no_contents_gives_empty_outline(tmp_path):
    pdf = pdfgen.write_pdf(tmp_path / "e.pdf", [pdfgen.plain_page(["just text"])])
    r = ex.extract_pdf(pdf)
    assert r.outline == [] and r.outline_source == "none"


def test_contents_lines_need_letters_and_no_nested_number():
    lines = [
        "1 Introduction ............ 5",
        "35 1.2. Acknowledgements .......... 7",
        "2 3.4.5 ............ 9",
        "3 Scope     12",
        "4 Overview ..... 13",
        "5 Commands .... 14",
        "6 Errors ....... 15",
        "7 Tables ....... 16",
        "8 Appendix ..... 17",
        "9 Glossary ..... 18",
        "10 Index ....... 19",
    ]
    entries = ex.parse_contents([lines])
    titles = [e["title"] for e in entries]
    assert "1 Introduction" in titles and "3 Scope" in titles
    assert not any("Acknowledgements" in t for t in titles)
    assert not any("3.4.5" in t for t in titles)


def test_contents_page_needs_eight_entries():
    few = ["1 Intro ..... 1", "2 Scope ..... 2"]
    assert ex.parse_contents([few]) == []


# ------------------------------------------------------------------- files


def test_write_result_and_is_current(tmp_path):
    vdir = tmp_path / "v"
    vdir.mkdir()
    pdf = pdfgen.write_pdf(
        vdir / "original.pdf", [pdfgen.numbered_page(1, ["a", "b", "c", "d", "e"])]
    )
    r = ex.extract_pdf(pdf)
    ex.write_result(vdir, r)
    assert (vdir / "extract.txt").read_text("utf-8") == r.text
    assert json.loads((vdir / "outline.json").read_text("utf-8")) == []
    assert json.loads((vdir / "linemap.json").read_text("utf-8")) == r.linemap
    meta = json.loads((vdir / "extract.json").read_text("utf-8"))
    assert meta["extractor_version"] == ex.EXTRACTOR_VERSION
    assert meta["pages"] == 1 and meta["line_numbers"] is True
    assert meta["outline_source"] == "none"
    assert ex.is_current(vdir)
    (vdir / "extract.json").write_text(
        json.dumps({**meta, "extractor_version": ex.EXTRACTOR_VERSION - 1}), "utf-8"
    )
    assert not ex.is_current(vdir)
    ex.remove_derived(vdir)
    assert not (vdir / "extract.txt").exists() and (vdir / "original.pdf").exists()


def test_linemap_file_removed_when_rerun_finds_no_numbers(tmp_path):
    vdir = tmp_path / "v"
    vdir.mkdir()
    (vdir / "linemap.json").write_text("{}", "utf-8")
    pdf = pdfgen.write_pdf(vdir / "original.pdf", [pdfgen.plain_page(["plain"])])
    ex.write_result(vdir, ex.extract_pdf(pdf))
    assert not (vdir / "linemap.json").exists()


def test_space_marker_splits_words_whose_boxes_overlap():
    # 's' at 428.6-432.6, then an 'f' whose advance box starts at 433.3: the
    # geometric gap is below the word threshold, but pdfium saw a space.
    chars = [
        (415.4, 700, 421.9, 710, "T"),
        (420.9, 700, 425.9, 710, "h"),
        (425.9, 700, 428.7, 710, "i"),
        (428.6, 700, 432.6, 710, "s"),
        (433.3, 700, 439.7, 710, " f"),
        (437.8, 700, 440.6, 710, "i"),
        (440.6, 700, 445.0, 710, "e"),
        (445.0, 700, 448.0, 710, "l"),
        (447.8, 700, 453.2, 710, "d"),
    ]
    assert ex._segment(chars, 4.4).text == "This field"
    # without the marker the same boxes glue, which is what the marker fixes
    unmarked = [c[:4] + (c[4].strip(),) for c in chars]
    assert ex._segment(unmarked, 4.4).text == "Thisfield"
