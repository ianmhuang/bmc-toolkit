"""Reviewer acceptance tests for rules drawn as path curves through the
CLI (AC-1, AC-2, AC-4, AC-6): ``table`` prints a curve-ruled table as
``ruled``, a cells table with a curve grid over it prints as before, a
page holding only curve boxes, a diagonal and an arc exits 2, and a
version 3 ``tables.json`` is read again from the PDF. Synthetic PDFs
only; the scripted client keeps the network out."""

import json

import pytest

from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok
from tests.test_review_curvefill import (
    HEADER,
    ROWS_1,
    ROWS_2,
    WIDTHS,
    boxed,
    curve_rules,
    curve_table,
    diagram,
    furniture,
)

pytest.importorskip("pypdfium2")
pytest.importorskip("pdfplumber")

URL = "https://example.test/DSP0236_1.3.3.pdf"


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def document(tmp_path):
    """Page 1: a captioned table whose rules are all curves. Page 2: a
    block diagram drawn with curves. Page 3: a captioned cells table with
    the same grid stroked over it as curves."""
    page1 = furniture(1) + [(72, 714, "Table 1 - Codes")]
    page1 += curve_table(72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_1])
    page2 = furniture(2) + diagram()
    page3 = furniture(3) + [(72, 714, "Table 2 - Boxed")]
    page3 += boxed(72, 700, WIDTHS, [16] * 3, [HEADER, *ROWS_2])
    page3 += curve_rules(72, 700, WIDTHS, [16] * 3)
    return pdfgen.write_pdf(tmp_path / "doc.pdf", [page1, page2, page3])


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    scripted.responses[URL] = ok(document(tmp_path).read_bytes())
    for argv in (["fetch", "DSP0236"], ["extract", "DSP0236"]):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


# ------------------------------------------------------------------ AC-1


def test_ac1_table_prints_a_curve_ruled_table(held, catalog_file, capsys):
    code, out = run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith("cite: mctp | DSP0236 1.3.3 | ")
    assert lines[0].split(" | ")[3:5] == ["PDF page 1", "lines table 1"]
    assert lines[1] == "table: Table 1 - Codes | ruled | page 1 | 3 columns | 3 rows"
    assert lines[2] == "Name        | Code | Meaning"
    assert lines[3] == "------------+------+--------"
    assert lines[4:] == [
        "Temperature | 01h  | degrees",
        "Voltage     | 02h  | volts",
    ]
    assert out.count("cite:") == 1


# ------------------------------------------------------------------ AC-2


def test_ac2_a_cells_table_under_a_curve_grid_prints_as_cells(
    held, catalog_file, capsys
):
    code, out = run(capsys, "table", "DSP0236", "--page", "3", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[1] == (
        "table: Table 2 - Boxed | cells (no ruling lines) | page 3 | 3 columns | 3 rows"
    )
    assert lines[2] == "Name    | Code | Meaning"
    assert lines[4:] == [
        "Current | 03h  | amps",
        "Fan     | 04h  | rpm",
    ]
    assert out.count("cite:") == 1


# ------------------------------------------------------------------ AC-4


def test_ac4_table_on_a_curve_diagram_exits_2(held, catalog_file, capsys):
    code, out = run(capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file)
    assert code == 2
    assert out.startswith("no table on page 2 of DSP0236 1.3.3; ")
    assert "cite:" not in out


# ------------------------------------------------------------------ AC-6


def test_ac6_the_store_records_version_4_and_the_drawing(held, catalog_file, capsys):
    for n in ("1", "3"):
        code, out = run(capsys, "table", "DSP0236", "--page", n, catalog_file=catalog_file)
        assert code == 0, out
    data = json.loads((held / "tables.json").read_text("utf-8"))
    assert data["tables_version"] == 4
    assert {1, 3} <= set(data["pages_done"])
    drawn = {(t["first"], t["index"]): t["drawn"] for t in data["tables"]}
    assert drawn == {(1, 1): "ruled", (3, 1): "cells"}


def test_ac6_cli_reads_the_pdf_again_over_a_version_3_store(held, catalog_file, capsys):
    code, out = run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert code == 0, out
    path = held / "tables.json"
    data = json.loads(path.read_text("utf-8"))
    assert data["tables_version"] == 4
    # a store the previous version wrote: it never saw the curve rules, so
    # its rows for the page are wrong (here: a stale row and a stale count)
    data["tables_version"] = 3
    (entry,) = data["tables"]
    entry["rows"] = [HEADER, ["Stale", "00h", "STALE ROW"]]
    entry["row_pages"] = [1, 1]
    path.write_text(json.dumps(data), "utf-8")
    code, out = run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert code == 0, out
    assert "STALE ROW" not in out
    assert out.splitlines()[1].endswith("| 3 columns | 3 rows")
    data = json.loads(path.read_text("utf-8"))
    assert data["tables_version"] == 4
    (entry,) = data["tables"]
    assert entry["rows"] == [HEADER, *ROWS_1]
