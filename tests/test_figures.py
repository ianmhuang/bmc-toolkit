"""Figure regions recorded at extraction time (AC-7)."""

import json

import pytest

from bmc_toolkit.spec import extract as ex
from tests import pdfgen

pytest.importorskip("pypdfium2")


def regions_of(tmp_path, name, items):
    r = ex.extract_pdf(pdfgen.write_pdf(tmp_path / name, [items]))
    return r, r.figures["pages"].get("1")


def test_diagonal_drawing_with_its_boxes_becomes_a_region(tmp_path):
    items = [
        (72, 740, "Figure 1 shows the topology"),
        ("rect", 100, 500, 120, 60),  # a box of the diagram
        ("rect", 300, 500, 120, 60),
        ("line", 220, 530, 300, 560),  # a diagonal connector
        (110, 525, "Bus owner"),  # text inside the left box
        (72, 400, "Text below the figure"),
    ]
    r, page = regions_of(tmp_path, "d.pdf", items)
    assert page is not None and r.figure_pages == 1
    (box,) = page["regions"]
    assert box[0] <= 100 and box[2] >= 420 and box[1] <= 500 and box[3] >= 560
    texts = r.text.splitlines()[1:]
    inside = [texts[i].strip() for i in page["lines"]]
    assert inside == ["Bus owner"]


def test_raster_image_is_a_region_and_text_over_it_is_inside(tmp_path):
    items = [
        ("image", 150, 300, 200, 150),
        (160, 350, "caption in image"),
        (72, 700, "body"),
    ]
    r, page = regions_of(tmp_path, "i.pdf", items)
    assert page["regions"] == [[150.0, 300.0, 350.0, 450.0]]
    texts = r.text.splitlines()[1:]
    assert [texts[i].strip() for i in page["lines"]] == ["caption in image"]


def test_header_logo_image_is_not_a_figure(tmp_path):
    items = [
        ("image", 72, 728, 68, 28),
        (150, 735, "Running header"),
        (72, 600, "body"),
    ]
    _, page = regions_of(tmp_path, "logo.pdf", items)
    assert page is None


def test_table_of_rules_and_rectangles_is_not_a_figure(tmp_path):
    items = [(72, 720, "Table 1 - Codes")]
    for i in range(5):
        y = 700 - i * 20
        items.append(("line", 72, y, 500, y))
        items.append((80, y + 6, f"row {i}"))
    items.append(("rect", 72, 600, 428, 100))
    items.append(("line", 200, 600, 200, 700))
    r, page = regions_of(tmp_path, "t.pdf", items)
    assert page is None and r.figure_pages == 0


def test_bullet_sized_drawings_are_ignored(tmp_path):
    items = [
        (90, 700, "item one"),
        ("line", 72, 698, 80, 704),
        ("line", 80, 704, 72, 710),
    ]
    items += [(90, 680, "item two"), ("curve", 72, 682, 76, 688, 80, 682, 72, 682)]
    _, page = regions_of(tmp_path, "b.pdf", items)
    assert page is None


def test_rounded_rectangle_behind_code_is_not_a_drawing(tmp_path):
    # four edges and four small corner curves, as a code-span background
    x0, y0, x1, y1, c = 100, 600, 300, 640, 4
    items = [
        ("line", x0 + c, y0, x1 - c, y0),
        ("curve", x1 - c, y0, x1, y0, x1, y0 + c, x1, y0 + c),
        ("line", x1, y0 + c, x1, y1 - c),
        ("curve", x1, y1 - c, x1, y1, x1 - c, y1, x1 - c, y1),
        ("line", x1 - c, y1, x0 + c, y1),
        ("curve", x0 + c, y1, x0, y1, x0, y1 - c, x0, y1 - c),
        ("line", x0, y1 - c, x0, y0 + c),
        ("curve", x0, y0 + c, x0, y0, x0 + c, y0, x0 + c, y0),
        (110, 615, "/redfish/v1/Systems"),
    ]
    _, page = regions_of(tmp_path, "c.pdf", items)
    assert page is None


def test_large_curve_is_a_drawing(tmp_path):
    items = [("curve", 100, 400, 150, 600, 350, 600, 400, 400), (200, 500, "arc label")]
    _, page = regions_of(tmp_path, "a.pdf", items)
    assert page is not None and page["lines"] == [0]


def test_page_backdrop_never_joins_a_region(tmp_path):
    items = [
        ("rect", 0, 0, 612, 792),  # a white page background
        ("line", 100, 100, 200, 200),
        ("line", 200, 200, 100, 300),
        (72, 700, "far away text"),
    ]
    _, page = regions_of(tmp_path, "p.pdf", items)
    assert page is not None
    (box,) = page["regions"]
    assert box[3] < 400 and page["lines"] == []


def test_figure_regions_geometry_without_pdf():
    seeds = [
        (100.0, 100.0, 110.0, 110.0),
        (115.0, 100.0, 125.0, 110.0),
    ]  # two arrowheads
    rules = [(100.0, 80.0, 300.0, 100.0), (0.0, 0.0, 612.0, 792.0)]  # a box, a backdrop
    got = ex.figure_regions(seeds, rules, 612.0 * 792.0)
    assert got == [(100.0, 80.0, 300.0, 110.0)]
    assert ex.figure_regions(seeds, [], 612.0 * 792.0) == []  # too small alone
    far = [(100.0, 100.0, 140.0, 140.0), (400.0, 400.0, 440.0, 440.0)]
    assert len(ex.figure_regions(far, [], 612.0 * 792.0)) == 2


def test_files_written_and_removed(tmp_path):
    vdir = tmp_path / "v"
    vdir.mkdir()
    pdf = pdfgen.write_pdf(
        vdir / "original.pdf",
        [[("image", 100, 100, 100, 100), (72, 700, "x")]],
    )
    r = ex.extract_pdf(pdf)
    ex.write_result(vdir, r)
    figures = json.loads((vdir / "figures.json").read_text("utf-8"))
    assert figures == r.figures
    meta = json.loads((vdir / "extract.json").read_text("utf-8"))
    assert meta["figure_pages"] == 1 and meta["extractor_version"] == 3
    renders = vdir / "renders"
    renders.mkdir()
    (renders / "page-1.png").write_bytes(b"x")
    ex.remove_derived(vdir)
    assert not (vdir / "figures.json").exists() and not renders.exists()
    # a re-run that finds no figure removes a stale figures.json
    (vdir / "figures.json").write_text("{}", "utf-8")
    ex.write_result(
        vdir,
        ex.extract_pdf(
            pdfgen.write_pdf(vdir / "original.pdf", [pdfgen.plain_page(["y"])])
        ),
    )
    assert not (vdir / "figures.json").exists()


def test_figure_pass_failure_keeps_the_text(tmp_path, monkeypatch):
    def boom(page, raw):
        raise RuntimeError("pdfium hiccup")

    monkeypatch.setattr(ex, "page_figures", boom)
    r = ex.extract_pdf(
        pdfgen.write_pdf(tmp_path / "f.pdf", [pdfgen.plain_page(["kept"])])
    )
    assert "kept" in r.text and r.figure_pages == 0
