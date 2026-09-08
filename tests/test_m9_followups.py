"""M9 follow-ups: the refresh text scan (F1, F2 of the M10 review), the
catalog wording (F3 to F5), and the row cap of very long tables."""

import json
import re
from pathlib import Path

import pytest

from bmc_toolkit.spec import listing as L
from bmc_toolkit.spec import refresh as R
from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import ROW_CAP, main
from tests import pdfgen

# ------------------------------------------------------------ refresh (F1, F2)


def test_refresh_docs_say_insert_not_append(capsys):
    assert "inserts each" in R.__doc__
    assert "append" not in R.__doc__.split("``append_versions``")[0].lower()
    with pytest.raises(SystemExit):
        main(["refresh", "--help"])
    out = " ".join(capsys.readouterr().out.split())  # argparse wraps help text
    assert "insert the new entries into the catalog, in publication order" in out


@pytest.mark.parametrize(
    "line, expected",
    [
        ('version = "1.0"', "1.0"),
        ('published = "2020-01-01"  # confirmed by hand', "2020-01-01"),
        ("version = '2.0 rev 1.1'", "2.0 rev 1.1"),
        ("version = 'lit'   # a literal string", "lit"),
    ],
)
def test_key_line_reads_comments_and_literal_strings(line, expected):
    m = R._KEY_LINE.match(line)
    assert m is not None
    value = m.group("basic") if m.group("basic") is not None else m.group("literal")
    assert value == expected


def test_key_line_does_not_read_escapes_or_multiline_strings():
    assert R._KEY_LINE.match('version = "a\\"b"') is None
    assert R._KEY_LINE.match('version = """x"""') is None
    assert R._KEY_LINE.match("published = 2020-01-01") is None


CATALOG_WITH_COMMENTS = """schema_version = 1

[families.mctp]
title = "MCTP"
publisher = "DMTF"

[[documents]]
id = "DSP0236"
family = "mctp"
title = "MCTP Base"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.3.0"  # first
url = "https://example.test/DSP0236_1.3.0.pdf"
type = "pdf"
published = '2020-01-01'

[[documents.versions]]
version = "1.3.3"
url = "https://example.test/DSP0236_1.3.3.pdf"
type = "pdf"
published = "2023-01-01"   # reupload
"""


def test_append_versions_places_a_block_after_commented_lines(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(CATALOG_WITH_COMMENTS, "utf-8", newline="")
    seen = [L.Seen("1.3.1", "https://example.test/DSP0236_1.3.1.pdf", "2021-01-01")]
    R.append_versions(path, "DSP0236", seen)
    text = path.read_text("utf-8")
    assert (
        text.index('version = "1.3.0"')
        < text.index('version = "1.3.1"')
        < text.index('version = "1.3.3"')
    )
    assert load_catalog(path).get("DSP0236").latest().version == "1.3.3"


def test_append_versions_refuses_a_block_it_cannot_read(tmp_path):
    path = tmp_path / "catalog.toml"
    broken = CATALOG_WITH_COMMENTS.replace('version = "1.3.3"', 'version = """1.3.3"""')
    path.write_text(broken, "utf-8", newline="")
    seen = [L.Seen("1.3.1", "https://example.test/DSP0236_1.3.1.pdf", "2021-01-01")]
    with pytest.raises(R.UnreadableBlock, match="1.3.3"):
        R.append_versions(path, "DSP0236", seen)
    assert path.read_text("utf-8") == broken  # nothing was edited


def test_refresh_write_skips_a_document_whose_block_it_cannot_place(
    tmp_path, scripted, capsys
):
    path = tmp_path / "catalog.toml"
    broken = CATALOG_WITH_COMMENTS.replace('version = "1.3.3"', 'version = """1.3.3"""')
    broken = broken.replace(
        'fetch = "direct"\n', 'fetch = "direct"\nlisting = "dmtf:DSP0236"\n', 1
    )
    path.write_text(broken, "utf-8", newline="")
    scripted.responses["https://www.dmtf.org/dsp/DSP0236"] = _dmtf_listing()
    code = main(["--catalog", str(path), "refresh", "DSP0236", "--write"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert re.search(
        r"skipped DSP0236: a version block cannot be placed "
        r'\(line \d+: version = """1.3.3"""\)',
        out,
    ), out
    assert "add the entries by hand" in out
    assert path.read_text("utf-8") == broken


def _dmtf_listing():
    from tests.conftest import ok

    html = (
        "<html><body><h1>All Published Versions of DSP0236</h1>"
        "<table><thead><tr><th>Version</th><th>Title</th><th>Publication Date</th>"
        "<th>Comments</th></tr></thead><tbody>"
        '<tr><td>1.3.4</td><td><a href="https://example.test/DSP0236_1.3.4.pdf">'
        "MCTP Base</a></td><td>3 Aug 2026</td><td>Standard</td></tr>"
        "</tbody></table></body></html>"
    )
    return ok(html.encode(), ctype="text/html")


# ---------------------------------------------------------- catalog (F3, F4, F5)


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


def test_dsp0284_limit_names_the_anchor_problem_without_claiming_section_fails(shipped):
    limits = shipped.get("DSP0284").limits
    assert "anchor" in limits
    assert "finds nothing" not in limits
    assert "5.2" in limits and "single letters" in limits


def test_documents_named_defective_in_golden_rows_carry_limits(shipped):
    assert "bookmarks" in shipped.get("OCP-ATTEST").limits
    assert "bookmarks" in shipped.get("DICE-HW").limits
    assert "margin" in shipped.get("SP800-193").limits
    nic = shipped.get("OCP-NIC")
    assert "line-numbered" in nic.limits
    assert "line-numbered" not in nic.notes


def test_sff_notes_say_the_download_number_serves_the_current_revision(shipped):
    for doc_id in ("SFF-8472", "SFF-8636", "SFF-8024"):
        notes = shipped.get(doc_id).notes
        assert "current revision" in notes, doc_id
        assert "refresh" in notes, doc_id


def test_bundle_limits_say_what_is_read_now(shipped):
    assert "registry" in shipped.get("DSP8011").limits
    assert "schema" in shipped.get("DSP8013").limits
    for doc in shipped.documents:
        assert "no ruling lines: page and render" not in (doc.limits or ""), doc.id


def test_no_dmtf_document_is_limited_to_page_for_its_tables(shipped):
    for doc in shipped.documents:
        if doc.id.startswith("DSP") and doc.id not in ("DSP0274", "DSP2053"):
            assert "ruling lines" not in (doc.limits or ""), doc.id


# ------------------------------------------------------ very long tables


pytest.importorskip("pdfplumber")


def _ruled(x, top, widths, heights, cells):
    from tests.test_tables import ruled_table

    return ruled_table(x, top, widths, heights, cells)


def _long_table_pdf(path: Path, rows_per_page: int, pages: int) -> Path:
    """One table over ``pages`` pages, ``rows_per_page`` body rows each,
    the header repeated on every page; running header as furniture."""
    header = ["Name", "Code"]
    doc = []
    n = 0
    for p in range(1, pages + 1):
        rows = []
        for _ in range(rows_per_page):
            n += 1
            rows.append([f"item{n}", f"{n:03d}"])
        height = 12
        top = 740
        items = [(72, 770, "Spec Title"), (300, 30, f"Page {p}")]
        if p == 1:
            items.append((72, top + 14, "Table 9 - Long"))
        items += _ruled(
            72, top, [120, 80], [height] * (rows_per_page + 1), [header, *rows]
        )
        doc.append(items)
    return pdfgen.write_pdf(path, doc)


def test_a_table_longer_than_the_cap_prints_the_pages_rows(
    catalog_file, library, scripted, tmp_path, capsys
):
    from tests.conftest import ok

    per_page = 40
    pages = (ROW_CAP // per_page) + 2  # more body rows than ROW_CAP
    pdf = _long_table_pdf(tmp_path / "long.pdf", per_page, pages)
    url = "https://example.test/DSP0236_1.3.3.pdf"
    scripted.responses[url] = ok(pdf.read_bytes(), ctype="application/pdf")
    for argv in (["fetch", "DSP0236"], ["extract", "DSP0236"]):
        code = main(["--catalog", str(catalog_file), *argv])
        assert code == 0, capsys.readouterr().out
    capsys.readouterr()
    code = main(["--catalog", str(catalog_file), "table", "DSP0236", "--page", "3"])
    out = capsys.readouterr().out
    assert code == 0, out
    lines = out.splitlines()
    total = per_page * pages
    assert lines[1].endswith(f"| pages 1-{pages} | 2 columns | {total + 1} rows")
    first = 2 * per_page + 1
    assert lines[2] == (
        f"note: rows {first}-{first + per_page - 1} of {total}, those starting on "
        f"page 3; the table runs over pages 1-{pages}; --all-rows prints them all"
    )
    assert lines[3].startswith("Name")
    # F2: on the first page the header is not counted as a row
    code = main(["--catalog", str(catalog_file), "table", "DSP0236", "--page", "1"])
    first_page = capsys.readouterr().out.splitlines()
    assert code == 0
    assert first_page[2].startswith(f"note: rows 1-{per_page} of {total}, ")
    assert first_page[3].startswith("Name")
    body_first = [ln for ln in first_page[5:] if ln.startswith("item")]
    assert body_first[0].startswith("item1 ") and len(body_first) == per_page
    body = [ln for ln in lines[5:] if ln.startswith("item")]
    assert body[0].startswith(f"item{first} ") and len(body) == per_page
    code = main(
        [
            "--catalog",
            str(catalog_file),
            "table",
            "DSP0236",
            "--page",
            "3",
            "--all-rows",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "note:" not in out
    assert len([ln for ln in out.splitlines() if ln.startswith("item")]) == total
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    data = json.loads((vdir / "tables.json").read_text("utf-8"))
    (entry,) = data["tables"]
    assert entry["row_pages"][0] == 1 and entry["row_pages"][-1] == pages
    assert len(entry["row_pages"]) == len(entry["rows"])
