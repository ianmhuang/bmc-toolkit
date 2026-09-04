"""The table command through the CLI: output, the store, its error paths,
and the store going away with the original."""

import pytest

from bmc_toolkit.spec import tables as tables_mod
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok
from tests.test_tables import HEADER, ROWS_1, ROWS_2, furniture, ruled_table

pytest.importorskip("pypdfium2")
pytest.importorskip("pdfplumber")

URL = "https://example.test/DSP0236_1.3.3.pdf"
WIDTHS = [100, 80, 200]


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def table_pdf(tmp_path):
    """A table across pages 1-2 under a bookmarked section, a plain page 3."""
    page1 = furniture(1) + [(72, 740, "5 Codes"), (72, 214, "Table 1 - Codes")]
    page1 += ruled_table(72, 200, WIDTHS, [16] * 3, [HEADER, *ROWS_1])
    page2 = furniture(2) + ruled_table(72, 740, WIDTHS, [16] * 3, [HEADER, *ROWS_2])
    page3 = furniture(3) + [(72, 700, "6 Nothing ruled here")]
    return pdfgen.write_pdf(
        tmp_path / "codes.pdf",
        [page1, page2, page3],
        bookmarks=[(0, "5 Codes", 0), (0, "6 Nothing ruled here", 2)],
    ).read_bytes()


@pytest.fixture
def fetched(catalog_file, library, scripted, tmp_path, capsys):
    scripted.responses[URL] = ok(table_pdf(tmp_path))
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


@pytest.fixture
def held(fetched, catalog_file, capsys):
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return fetched


def test_table_prints_cite_table_line_and_grid(held, catalog_file, capsys):
    code, out = run(
        capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file
    )
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(
        "cite: mctp | DSP0236 1.3.3 | 5 Codes | PDF pages 1-2 | lines table 1 | "
        f"{URL} | "
    )
    assert lines[0].endswith(str(held))
    assert lines[1] == "table: Table 1 - Codes | ruled | pages 1-2 | 3 columns | 5 rows"
    assert lines[2] == "Name        | Code | Meaning"
    assert lines[3] == "------------+------+--------"
    assert lines[4:] == [
        "Temperature | 01h  | degrees",
        "Voltage     | 02h  | volts",
        "Current     | 03h  | amps",
        "Fan         | 04h  | rpm",
    ]
    assert (held / tables_mod.TABLES_NAME).is_file()


def test_table_reads_the_store_unless_forced(held, catalog_file, capsys):
    code, first = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0, first
    (held / "original.pdf").unlink()
    code, again = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 0 and again == first
    # the table runs onto page 2, so that page is answered from the store too
    code, out = run(
        capsys, "table", "DSP0236", "--page", "2", catalog_file=catalog_file
    )
    assert code == 0 and out == first
    # page 3 was never read: the store does not answer for it
    code, out = run(
        capsys, "table", "DSP0236", "--page", "3", catalog_file=catalog_file
    )
    assert code == 1 and out.startswith("cannot read tables of DSP0236 1.3.3: ")
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", "--force", catalog_file=catalog_file
    )
    assert code == 1 and out.startswith("cannot read tables of DSP0236 1.3.3: ")


def test_table_index_selects_one_table(held, catalog_file, capsys):
    code, out = run(
        capsys,
        "table",
        "DSP0236",
        "--page",
        "1",
        "--index",
        "1",
        catalog_file=catalog_file,
    )
    assert code == 0 and out.startswith("cite: ")
    code, out = run(
        capsys,
        "table",
        "DSP0236",
        "--page",
        "1",
        "--index",
        "2",
        catalog_file=catalog_file,
    )
    assert code == 2
    assert out.strip() == "page 1 has 1 table(s); --index 2 is out of range"
    code, out = run(
        capsys,
        "table",
        "DSP0236",
        "--page",
        "1",
        "--index",
        "0",
        catalog_file=catalog_file,
    )
    assert code == 2 and out.strip() == "--index counts from 1"


def test_table_without_a_ruled_table_exits_2(held, catalog_file, capsys):
    code, out = run(
        capsys, "table", "DSP0236", "--page", "3", catalog_file=catalog_file
    )
    assert code == 2
    assert out.strip() == (
        "no table on page 3 of DSP0236 1.3.3; read the page with: "
        "bmcspec page DSP0236 3, or look at it with: bmcspec render DSP0236 --page 3"
    )
    code, out = run(
        capsys, "table", "DSP0236", "--page", "9", catalog_file=catalog_file
    )
    assert code == 2 and out.strip() == "page 9 is outside DSP0236 1.3.3 (pages 1-3)"


def test_table_shares_the_reading_error_paths(fetched, catalog_file, capsys):
    code, out = run(capsys, "table", "IPMI", "--page", "1", catalog_file=catalog_file)
    assert (
        code == 2
        and out.strip() == "IPMI is not in the Library; run: bmcspec fetch IPMI"
    )
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 2 and "is not extracted" in out


def test_table_without_pdfplumber_says_how_to_install(
    held, catalog_file, capsys, monkeypatch
):
    def missing():
        raise ImportError("pdfplumber is not installed")

    monkeypatch.setattr(tables_mod, "_require_pdfplumber", missing)
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 2
    assert out.strip() == (
        "cannot read tables: pdfplumber is not installed; "
        "run: pip install -r requirements.txt"
    )


def test_store_goes_away_with_the_original_and_with_a_new_extract(
    held, catalog_file, capsys
):
    store = held / tables_mod.TABLES_NAME
    run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert store.is_file()
    code, out = run(capsys, "extract", "DSP0236", "--force", catalog_file=catalog_file)
    assert code == 0, out
    assert not store.exists()
    run(capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file)
    assert store.is_file()
    code, out = run(capsys, "fetch", "DSP0236", "--force", catalog_file=catalog_file)
    assert code == 0, out
    assert not store.exists()
