"""Acceptance tests for the extractor: AC-3 to AC-8 and AC-12.

Black-box through ``extract_pdf`` and ``write_result``. Every PDF is
generated in ``tmp_path`` by ``tests.pdfgen`` (standard library only);
nothing here reads the Library or the network.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("pypdfium2")

from bmc_toolkit.spec import extract as ex  # noqa: E402
from tests import pdfgen  # noqa: E402

MARKER_HEAD = "=== page "
MARKER_TAIL = " ==="


def pages_of(text: str) -> dict[int, list[str]]:
    """{physical page: its lines} parsed from the Extract's markers."""
    pages: dict[int, list[str]] = {}
    current = None
    for line in text.split("\n"):
        if line.startswith(MARKER_HEAD) and line.endswith(MARKER_TAIL):
            current = int(line[len(MARKER_HEAD) : -len(MARKER_TAIL)])
            assert current not in pages, f"page {current} marked twice"
            pages[current] = []
        elif current is not None:
            pages[current].append(line)
    for lines in pages.values():
        while lines and lines[-1] == "":
            lines.pop()
    return pages


def extract_to(tmp_path, pages, bookmarks=None, name="doc.pdf"):
    """Extract a generated PDF and also write the files into a fresh directory."""
    vdir = tmp_path / "v"
    vdir.mkdir(exist_ok=True)
    pdf = pdfgen.write_pdf(vdir / name, pages, bookmarks=bookmarks)
    result = ex.extract_pdf(pdf)
    ex.write_result(vdir, result)
    return result, vdir


def read_json(path):
    return json.loads(path.read_text("utf-8"))


# ------------------------------------------------------------------- AC-3


def test_every_physical_page_gets_a_marker_in_order_even_when_empty(tmp_path):
    pages = [pdfgen.plain_page(["one"]), [], pdfgen.plain_page(["three"])]
    r, vdir = extract_to(tmp_path, pages)
    text = (vdir / "extract.txt").read_text("utf-8")
    markers = [ln for ln in text.split("\n") if ln.startswith(MARKER_HEAD)]
    assert markers == ["=== page 1 ===", "=== page 2 ===", "=== page 3 ==="]
    got = pages_of(text)
    assert got[1] == ["one"]
    assert got[2] == []  # an empty page is still marked
    assert got[3] == ["three"]
    assert r.pages == 3
    assert text.index("=== page 1 ===") < text.index("one") < text.index("=== page 2 ===")


def test_reading_order_is_top_to_bottom_then_left_to_right(tmp_path):
    # Content-stream order is deliberately scrambled.
    items = [
        (72, 660, "third"),
        (300, 700, "right"),
        (72, 680, "second"),
        (72, 700, "first"),
    ]
    r, _ = extract_to(tmp_path, [items])
    lines = pages_of(r.text)[1]
    assert len(lines) == 3
    assert lines[0].startswith("first")
    assert lines[0].rstrip().endswith("right")
    assert lines[0].index("first") < lines[0].index("right")
    assert lines[1] == "second"
    assert lines[2] == "third"


def test_table_columns_keep_their_character_positions_across_rows(tmp_path):
    rows = [
        ("Request Data", "1", "Completion Code"),
        ("", "2", "Device ID"),
        ("", "3:4", "Manufacturer ID"),
        ("Response Data", "5", "Aux Firmware Rev"),
    ]
    items = []
    y = 700.0
    for a, b, c in rows:
        if a:
            items.append((72, y, a))
        items.append((190, y, b))
        items.append((240, y, c))
        y -= 14
    r, _ = extract_to(tmp_path, [items])
    lines = pages_of(r.text)[1]
    assert len(lines) == len(rows), lines
    col_b = {ln.index(b) for ln, (_, b, _) in zip(lines, rows, strict=True)}
    col_c = {ln.index(c) for ln, (_, _, c) in zip(lines, rows, strict=True)}
    assert len(col_b) == 1, lines
    assert len(col_c) == 1, lines
    assert lines[0].startswith("Request Data")
    assert lines[1].startswith(" ") and lines[1].lstrip().startswith("2")
    assert lines[3].startswith("Response Data")


def test_horizontal_gap_is_rendered_proportionally(tmp_path):
    near = [(72, 700, "left"), (172, 700, "right")]
    far = [(72, 680, "left"), (272, 680, "right")]
    r, _ = extract_to(tmp_path, [near + far])
    lines = pages_of(r.text)[1]
    assert len(lines) == 2
    col_near = lines[0].index("right")
    col_far = lines[1].index("right")
    assert col_near > len("left") + 1  # a wide gap is more than one space
    # twice the gap in points is (about) twice the column offset
    assert abs(col_far - 2 * col_near) <= 2, (col_near, col_far)
    assert "  " not in lines[0][: len("left")]


# ------------------------------------------------------------ AC-5, AC-6


def test_margin_line_numbers_are_removed_and_recorded_per_page(tmp_path):
    first_text = ["alpha", "beta", "", "delta", "epsilon", "zeta"]
    second_text = ["eta", "theta", "iota", "kappa", "lambda"]
    page1 = pdfgen.numbered_page(120, first_text)
    page1.insert(0, (72, 760, "MCTP Base Specification"))
    page2 = pdfgen.numbered_page(126, second_text)
    r, vdir = extract_to(tmp_path, [page1, page2])
    got = pages_of((vdir / "extract.txt").read_text("utf-8"))
    assert got[1] == ["MCTP Base Specification", *first_text]
    assert got[2] == second_text
    for lines in got.values():
        for ln in lines:
            assert not ln.strip().isdigit(), ln
            assert not (ln.split() and ln.split()[0].isdigit()), ln

    linemap = read_json(vdir / "linemap.json")
    assert set(linemap["pages"]) == {"1", "2"}
    p1, p2 = linemap["pages"]["1"], linemap["pages"]["2"]
    assert (p1["first"], p1["last"]) == (120, 125)
    assert (p2["first"], p2["last"]) == (126, 130)
    assert list(p1["lines"].values()) == list(range(120, 126))
    assert list(p2["lines"].values()) == list(range(126, 131))
    # keys index the page's Extract lines; the header is not one of them
    keys = sorted(int(k) for k in p1["lines"])
    assert keys == list(range(keys[0], keys[0] + 6))
    base = keys[0] - 1  # 0-based or 1-based, either way the header is skipped
    assert base in (0, 1)
    for k, number in p1["lines"].items():
        assert got[1][int(k) - base] == first_text[number - 120]

    meta = read_json(vdir / "extract.json")
    assert meta["line_numbers"] is True
    assert r.numbered_pages == 2


def test_numbered_list_at_the_text_margin_is_not_line_numbers(tmp_path):
    items = [(72, 720, "The sequence is:")]
    y = 706.0
    for n in range(1, 8):
        items.append((72, y, str(n)))
        items.append((92, y, f"step number {n}"))
        y -= 14
    items.append((72, y - 14, "End of list."))
    r, vdir = extract_to(tmp_path, [items])
    lines = pages_of(r.text)[1]
    assert lines[0] == "The sequence is:"
    for i in range(1, 8):
        assert lines[i].startswith(str(i)), lines
        assert lines[i].rstrip().endswith(f"step number {i}")
    assert not (vdir / "linemap.json").exists()
    assert read_json(vdir / "extract.json")["line_numbers"] is False


def test_numbers_inside_the_body_are_not_line_numbers_whatever_the_text(tmp_path):
    # Same text pattern as a DMTF page, but the integers sit in a table
    # column far from the left margin: geometry, not the pattern, decides.
    items = [(72, 720, "Table 5, Sensor Type Codes")]
    y = 706.0
    for n in range(1, 9):
        items.append((200, y, str(n)))
        items.append((230, y, f"sensor type {n}"))
        y -= 14
    r, vdir = extract_to(tmp_path, [items])
    lines = pages_of(r.text)[1]
    assert lines[1].lstrip().startswith("1")
    assert lines[8].lstrip().startswith("8")
    assert not (vdir / "linemap.json").exists()


def test_margin_numbers_must_strictly_increase(tmp_path):
    items = []
    y = 700.0
    for n in (1, 2, 2, 3, 4, 5):
        items.append((37, y, str(n)))
        items.append((72, y, "text"))
        y -= 14
    r, vdir = extract_to(tmp_path, [items])
    assert not (vdir / "linemap.json").exists()
    assert all(ln.startswith(str(n)) for ln, n in zip(pages_of(r.text)[1], (1, 2, 2, 3, 4, 5), strict=True))


def test_numbering_that_restarts_on_the_next_page_is_not_continued(tmp_path):
    page1 = pdfgen.numbered_page(1, [f"line {i}" for i in range(8)])
    page2 = pdfgen.numbered_page(1, [f"other {i}" for i in range(8)])
    r, vdir = extract_to(tmp_path, [page1, page2])
    got = pages_of(r.text)
    assert got[1] == [f"line {i}" for i in range(8)]
    assert got[2][0].startswith("1")  # page 2 keeps its numbers
    linemap = read_json(vdir / "linemap.json")
    assert list(linemap["pages"]) == ["1"]


def test_document_without_line_numbers_is_identical_with_detector_off(
    tmp_path, monkeypatch
):
    items = [(72, 740, "1 Introduction"), (72, 726, "2 Scope")]
    y = 700.0
    for n in range(1, 7):
        items.append((72, y, str(n)))
        items.append((90, y, f"item {n}"))
        y -= 14
    table = [(72, 560, "Table 1")]
    for n in range(10, 17):
        table.append((150, 546 - (n - 10) * 14, str(n)))
        table.append((200, 546 - (n - 10) * 14, "code"))
    pdf = pdfgen.write_pdf(tmp_path / "plain.pdf", [items, table])
    with_detector = ex.extract_pdf(pdf).text
    assert "1 Introduction" in with_detector
    monkeypatch.setattr(ex, "detect_line_numbers", lambda page, previous: False)
    assert ex.extract_pdf(pdf).text == with_detector


# ------------------------------------------------------------------- AC-4


def test_extraction_needs_no_pdfplumber_and_records_seconds(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pdfplumber", None)  # import would fail
    r, vdir = extract_to(tmp_path, [pdfgen.plain_page(["hello", "world"])])
    assert pages_of(r.text)[1] == ["hello", "world"]
    meta = read_json(vdir / "extract.json")
    assert isinstance(meta["seconds"], (int, float))
    assert 0 <= meta["seconds"] < 60
    assert meta["pages"] == 1


# ------------------------------------------------------------------- AC-7


def test_outline_from_bookmarks_is_a_flat_list_of_level_title_page(tmp_path):
    pages = [
        pdfgen.plain_page(["cover"]),
        pdfgen.plain_page(["1 Scope", "text"]),
        pdfgen.plain_page(["2 Commands", "2.1 Get Device ID"]),
    ]
    bookmarks = [
        (0, "1 Scope", 1),
        (1, "1.1 Purpose", 1),
        (0, "2 Commands", 2),
        (1, "2.1 Get Device ID", 2),
        (2, "2.1.1 Request", 2),
    ]
    r, vdir = extract_to(tmp_path, pages, bookmarks=bookmarks)
    outline = read_json(vdir / "outline.json")
    assert outline == [
        {"level": 0, "title": "1 Scope", "page": 2},
        {"level": 1, "title": "1.1 Purpose", "page": 2},
        {"level": 0, "title": "2 Commands", "page": 3},
        {"level": 1, "title": "2.1 Get Device ID", "page": 3},
        {"level": 2, "title": "2.1.1 Request", "page": 3},
    ]
    meta = read_json(vdir / "extract.json")
    assert meta["outline_source"] == "bookmarks"
    assert r.outline_source == "bookmarks"


# ------------------------------------------------------------------- AC-8

ENTRIES = [
    ("1", "Introduction", 1),
    ("1.1", "Scope", 1),
    ("1.2", "Terms and Abbreviations", 2),
    ("2", "Overview", 2),
    ("2.1", "Architecture", 3),
    ("2.1.1", "Deep Section", 3),
    ("3", "Commands", 4),
    ("3.1", "Get Capabilities", 4),
    ("3.2", "Get Power Reading", 5),
]


def contents_document(front_pages: int):
    """``front_pages`` unnumbered pages (the last is the contents), then five
    body pages whose text and footer carry the printed page number."""
    contents = [(72, 740, "Contents")]
    y = 720.0
    for num, title, printed in ENTRIES:
        contents.append((72, y, f"{num} {title} .......... {printed}"))
        y -= 14
    pages = [[(200, 700, "Cover Page")]]
    pages += [[(72, 700, "Legal notice")] for _ in range(front_pages - 2)]
    pages.append(contents)
    for printed in range(1, 6):
        pages.append(
            [
                (72, 700, f"Body of printed page {printed}"),
                (500, 40, f"Page {printed}"),
            ]
        )
    return pages


def test_outline_from_contents_pages_maps_printed_to_physical_pages(tmp_path):
    offset = 3  # cover, legal notice, contents; printed 1 is physical 4
    r, vdir = extract_to(tmp_path, contents_document(offset))
    outline = read_json(vdir / "outline.json")
    assert read_json(vdir / "extract.json")["outline_source"] == "contents"
    assert len(outline) == len(ENTRIES)
    for entry, (num, title, printed) in zip(outline, ENTRIES, strict=True):
        assert title in entry["title"], entry
        assert num in entry["title"], entry
        assert entry["page"] == printed + offset, entry
        assert entry["level"] == num.count("."), entry
    assert r.outline_source == "contents"


def test_bookmarks_take_precedence_over_contents_pages(tmp_path):
    pages = contents_document(3)
    r, vdir = extract_to(tmp_path, pages, bookmarks=[(0, "Only bookmark", 4)])
    assert read_json(vdir / "extract.json")["outline_source"] == "bookmarks"
    assert read_json(vdir / "outline.json") == [
        {"level": 0, "title": "Only bookmark", "page": 5}
    ]


def test_no_bookmarks_and_no_contents_gives_empty_outline_and_still_succeeds(
    tmp_path,
):
    pages = [pdfgen.plain_page(["Just some text", "and nothing else"])]
    r, vdir = extract_to(tmp_path, pages)
    assert read_json(vdir / "outline.json") == []
    meta = read_json(vdir / "extract.json")
    assert meta["outline_source"] == "none"
    assert meta["pages"] == 1
    assert (vdir / "extract.txt").read_text("utf-8").startswith("=== page 1 ===\n")
    assert r.outline == []
