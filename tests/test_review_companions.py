"""Reviewer acceptance tests for searched_with companions (AC-3): the
Catalog key, the note for a missing companion, companion hits first,
--only. Black-box through the CLI on synthetic PDFs."""

import pytest

from bmc_toolkit.spec.catalog import CatalogError, load_catalog, parse_catalog
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import MINI_CATALOG, ROOT, ok

pytest.importorskip("pypdfium2")

IPMI_URL = "https://example.test/ipmi-v2-rev1-1.pdf"
UPDATE_URL = "https://example.test/ipmi-update.pdf"

UPDATE_DOC = """
[[documents]]
id = "IPMI-UPDATE"
family = "ipmi"
title = "IPMI Specification Update"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "Errata 7"
url = "https://example.test/ipmi-update.pdf"
type = "pdf"
published = "2015-04-01"
"""


def companion_catalog(searched_with='searched_with = ["IPMI-UPDATE"]'):
    return (
        MINI_CATALOG.replace(
            'title = "IPMI Specification v2.0"',
            'title = "IPMI Specification v2.0"\n' + searched_with,
        ).replace('fetch = "wayback"', 'fetch = "direct"')
        + UPDATE_DOC
    )


def parse(text):
    import tomllib

    return parse_catalog(tomllib.loads(text))


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


@pytest.fixture
def cat(tmp_path):
    path = tmp_path / "companion.toml"
    path.write_text(companion_catalog(), encoding="utf-8", newline="")
    return path


def one_page_pdf(tmp_path, name, lines):
    return pdfgen.write_pdf(tmp_path / name, [pdfgen.plain_page(lines)]).read_bytes()


# ------------------------------------------------------------- catalog key


def test_searched_with_is_optional_and_must_name_a_known_other_document():
    assert parse(MINI_CATALOG).get("IPMI").searched_with == ()
    assert parse(companion_catalog()).get("IPMI").searched_with == ("IPMI-UPDATE",)
    with pytest.raises(CatalogError):
        parse(companion_catalog('searched_with = ["NO-SUCH-DOC"]'))
    with pytest.raises(CatalogError):
        parse(companion_catalog('searched_with = ["IPMI"]'))


def test_shipped_catalog_searches_ipmi_with_its_update():
    shipped = load_catalog(ROOT / "bmc_toolkit" / "spec" / "catalog.toml")
    assert "IPMI-UPDATE" in shipped.get("IPMI").searched_with
    assert shipped.get("IPMI-UPDATE") is not None


# ------------------------------------------------------------------- find


def test_missing_companion_gets_a_note_naming_the_fetch_command(
    cat, library, scripted, tmp_path, capsys
):
    scripted.responses[IPMI_URL] = ok(
        one_page_pdf(tmp_path, "ipmi.pdf", ["Get Device ID NetFn App", "other"])
    )
    run(capsys, "fetch", "IPMI", catalog_file=cat)
    code, out = run(capsys, "extract", "IPMI", catalog_file=cat)
    assert code == 0, out
    code, out = run(capsys, "find", "IPMI", "get device id", catalog_file=cat)
    assert code == 0, out
    lines = out.strip().splitlines()
    notes = [ln for ln in lines if ln.startswith("note:")]
    # fewer round trips change: find tries to fetch the companion itself
    # (no route here) and reports that as notes, then searches the base
    assert "note: failed IPMI-UPDATE Errata 7" in notes
    assert any("IPMI-UPDATE" in n and "Save it as: " in n for n in notes)
    hits = [ln for ln in lines if not ln.startswith("note:")]
    assert hits == ["IPMI p.1 | - | Get Device ID NetFn App"]


def test_held_companion_hits_come_first_prefixed_by_their_id(
    cat, library, scripted, tmp_path, capsys
):
    scripted.responses[IPMI_URL] = ok(
        one_page_pdf(tmp_path, "ipmi.pdf", ["Get Device ID NetFn App", "other"])
    )
    scripted.responses[UPDATE_URL] = ok(
        one_page_pdf(tmp_path, "upd.pdf", ["Get Device ID errata", "more"])
    )
    for doc in ("IPMI", "IPMI-UPDATE"):
        run(capsys, "fetch", doc, "--no-extract", catalog_file=cat)
    run(capsys, "extract", "IPMI", catalog_file=cat)
    # held but not extracted: find extracts the companion itself (fewer
    # round trips change), says so in a note, and searches both
    code, out = run(capsys, "find", "IPMI", "get device id", catalog_file=cat)
    assert code == 0, out
    lines = out.strip().splitlines()
    assert lines[0].startswith("note: extracted IPMI-UPDATE Errata 7")
    assert lines[1:] == [
        "IPMI-UPDATE p.1 | - | Get Device ID errata",
        "IPMI p.1 | - | Get Device ID NetFn App",
    ]
    code, out = run(capsys, "find", "IPMI", "get device id", catalog_file=cat)
    assert code == 0, out
    assert out.strip().splitlines() == [
        "IPMI-UPDATE p.1 | - | Get Device ID errata",
        "IPMI p.1 | - | Get Device ID NetFn App",
    ]
    # a pattern that only the companion has still counts as hits
    code, out = run(capsys, "find", "IPMI", "errata", catalog_file=cat)
    assert code == 0 and out.strip() == "IPMI-UPDATE p.1 | - | Get Device ID errata"


def test_only_restricts_the_search_to_the_named_document(
    cat, library, scripted, tmp_path, capsys
):
    scripted.responses[IPMI_URL] = ok(
        one_page_pdf(tmp_path, "ipmi.pdf", ["Get Device ID NetFn App"])
    )
    scripted.responses[UPDATE_URL] = ok(
        one_page_pdf(tmp_path, "upd.pdf", ["Get Device ID errata"])
    )
    for doc in ("IPMI", "IPMI-UPDATE"):
        run(capsys, "fetch", doc, catalog_file=cat)
        run(capsys, "extract", doc, catalog_file=cat)
    code, out = run(capsys, "find", "IPMI", "get device id", "--only", catalog_file=cat)
    assert code == 0, out
    assert out.strip() == "IPMI p.1 | - | Get Device ID NetFn App"
    code, out = run(capsys, "find", "IPMI", "errata", "--only", catalog_file=cat)
    assert code == 0 and out.strip() == "no hits"
    # searching the companion itself does not pull in the base document
    code, out = run(capsys, "find", "IPMI-UPDATE", "get device id", catalog_file=cat)
    assert out.strip() == "IPMI-UPDATE p.1 | - | Get Device ID errata"
