"""Reviewer acceptance tests for figure regions (AC-7) and page rendering
(AC-8), black-box through the CLI and the files the tool writes."""

import json
import struct
import sys
import zlib

import pytest

from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok

pytest.importorskip("pypdfium2")

URL = "https://example.test/DSP0236_1.3.3.pdf"


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def hold(catalog_file, scripted, tmp_path, capsys, pages, name="doc.pdf"):
    pdf = pdfgen.write_pdf(tmp_path / name, pages)
    scripted.responses[URL] = ok(pdf.read_bytes())
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out


def page_texts(vdir, page):
    """The Extract lines of one page, by index."""
    text = (vdir / "extract.txt").read_text("utf-8")
    block = text.split(f"=== page {page} ===\n", 1)[1]
    block = block.split("=== page ", 1)[0]
    return block.split("\n")


DIAGRAM = [
    (72, 740, "Figure 1 shows the topology"),
    ("rect", 100, 500, 120, 60),
    ("rect", 300, 500, 120, 60),
    ("line", 220, 530, 300, 560),  # the only diagonal segment
    (110, 525, "Bus owner"),  # inside the left box
    (72, 400, "Text below the figure"),
]

TABLE = [(72, 720, "Table 1 - Codes")]
for _i in range(5):
    _y = 700 - _i * 20
    TABLE.append(("line", 72, _y, 500, _y))
    TABLE.append((80, _y + 6, f"row {_i}"))
TABLE.append(("rect", 72, 600, 428, 100))
TABLE.append(("line", 200, 600, 200, 700))


# ---------------------------------------------------------------- AC-7


def test_extraction_records_a_region_for_a_diagram_and_the_lines_inside(
    catalog_file, library, scripted, tmp_path, capsys
):
    hold(catalog_file, scripted, tmp_path, capsys, [DIAGRAM, [(72, 700, "plain")]])
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    figures = json.loads((vdir / "figures.json").read_text("utf-8"))
    assert list(figures["pages"]) == ["1"]  # the plain page records nothing
    entry = figures["pages"]["1"]
    (box,) = entry["regions"]
    x0, y0, x1, y1 = box
    assert x0 <= 100 and y0 <= 500 and x1 >= 420 and y1 >= 560
    texts = page_texts(vdir, 1)
    assert [texts[i].strip() for i in entry["lines"]] == ["Bus owner"]
    meta = json.loads((vdir / "extract.json").read_text("utf-8"))
    assert meta["figure_pages"] == 1
    assert meta["extractor_version"] >= 3  # bumped past M2's 2


def test_find_and_page_mark_lines_inside_a_figure(
    catalog_file, library, scripted, tmp_path, capsys
):
    hold(catalog_file, scripted, tmp_path, capsys, [DIAGRAM])
    code, out = run(capsys, "find", "DSP0236", "bus owner", catalog_file=catalog_file)
    assert code == 0, out
    assert out.strip() == "DSP0236 p.1 | - | [figure] Bus owner"
    code, out = run(capsys, "find", "DSP0236", "below", catalog_file=catalog_file)
    assert "[figure]" not in out
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()[1:]
    marked = [ln for ln in lines if "[figure]" in ln]
    assert len(marked) == 1 and "Bus owner" in marked[0]
    assert not any("[figure]" in ln for ln in lines if "below" in ln)


def test_a_table_of_rules_and_rectangles_is_not_a_figure(
    catalog_file, library, scripted, tmp_path, capsys
):
    hold(catalog_file, scripted, tmp_path, capsys, [TABLE])
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    assert not (vdir / "figures.json").exists()
    meta = json.loads((vdir / "extract.json").read_text("utf-8"))
    assert meta["figure_pages"] == 0
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0 and "[figure]" not in out


def test_a_raster_image_is_a_region(catalog_file, library, scripted, tmp_path, capsys):
    hold(
        catalog_file,
        scripted,
        tmp_path,
        capsys,
        [[("image", 150, 300, 200, 150), (160, 350, "caption in image"), (72, 700, "body")]],
    )
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    figures = json.loads((vdir / "figures.json").read_text("utf-8"))
    entry = figures["pages"]["1"]
    (box,) = entry["regions"]
    assert box[0] <= 150 and box[1] <= 300 and box[2] >= 350 and box[3] >= 450
    texts = page_texts(vdir, 1)
    assert [texts[i].strip() for i in entry["lines"]] == ["caption in image"]


def test_an_extract_from_the_previous_extractor_is_redone(
    catalog_file, library, scripted, tmp_path, capsys
):
    hold(catalog_file, scripted, tmp_path, capsys, [DIAGRAM])
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert out.startswith("skipped")  # current: nothing to do
    meta_path = vdir / "extract.json"
    meta = json.loads(meta_path.read_text("utf-8"))
    meta["extractor_version"] = 2
    meta.pop("figure_pages")
    meta_path.write_text(json.dumps(meta), "utf-8")
    (vdir / "figures.json").unlink()
    code, out = run(capsys, "find", "DSP0236", "bus", catalog_file=catalog_file)
    assert code == 2  # refused until re-extracted
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0 and out.startswith("extracted")
    assert (vdir / "figures.json").exists()
    assert json.loads(meta_path.read_text("utf-8"))["figure_pages"] == 1


# ---------------------------------------------------------------- AC-8


def png_header(data):
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert data[12:16] == b"IHDR"
    width, height, depth, colour = struct.unpack(">IIBB", data[16:26])
    return width, height, depth, colour


def test_render_writes_a_png_with_stdlib_only_and_prints_a_cite_line(
    catalog_file, library, scripted, tmp_path, capsys, monkeypatch
):
    hold(catalog_file, scripted, tmp_path, capsys, [DIAGRAM, [(72, 700, "two")]])
    monkeypatch.setitem(sys.modules, "PIL", None)  # importing Pillow would fail
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    code, out = run(capsys, "render", "DSP0236", "--page", "2", catalog_file=catalog_file)
    assert code == 0, out
    png = vdir / "renders" / "page-2.png"
    assert png.is_file()
    lines = out.strip().splitlines()
    assert str(png) in lines[0]
    cite = [ln for ln in lines if ln.startswith("cite:")]
    assert len(cite) == 1
    fields = cite[0].split(" | ")
    assert fields[0] == "cite: mctp"
    assert fields[1] == "DSP0236 1.3.3"
    assert fields[3] == "PDF page 2"
    assert fields[4] == "lines rendered page"
    assert fields[5] == URL
    assert fields[6] == str(vdir)
    data = png.read_bytes()
    width, height, depth, colour = png_header(data)
    assert (width, height) == (612 * 2, 792 * 2)  # default scale 2 at 72 dpi
    assert (depth, colour) == (8, 2)  # 8-bit RGB
    idat = data.index(b"IDAT")
    length = struct.unpack(">I", data[idat - 4 : idat])[0]
    raw = zlib.decompress(data[idat + 4 : idat + 4 + length])
    assert len(raw) == height * (1 + width * 3)
    assert data.endswith(b"IEND\xae\x42\x60\x82")


def test_render_reuses_an_existing_file_unless_force(
    catalog_file, library, scripted, tmp_path, capsys
):
    hold(catalog_file, scripted, tmp_path, capsys, [DIAGRAM])
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    png = vdir / "renders" / "page-1.png"
    run(capsys, "render", "DSP0236", "--page", "1", catalog_file=catalog_file)
    before = png.read_bytes()
    png.write_bytes(b"sentinel")
    code, out = run(capsys, "render", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert code == 0 and png.read_bytes() == b"sentinel"  # reused, not rewritten
    assert "cite:" in out
    code, out = run(
        capsys,
        "render",
        "DSP0236",
        "--page",
        "1",
        "--force",
        "--scale",
        "1",
        catalog_file=catalog_file,
    )
    assert code == 0, out
    after = png.read_bytes()
    assert after != b"sentinel" and after != before
    assert png_header(after)[:2] == (612, 792)


def test_render_page_outside_the_document_exits_2(
    catalog_file, library, scripted, tmp_path, capsys
):
    hold(catalog_file, scripted, tmp_path, capsys, [DIAGRAM])
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    code, out = run(capsys, "render", "DSP0236", "--page", "2", catalog_file=catalog_file)
    assert code == 2 and "2" in out
    assert not (vdir / "renders" / "page-2.png").exists()
    code, out = run(capsys, "render", "DSP0236", "--page", "0", catalog_file=catalog_file)
    assert code == 2
