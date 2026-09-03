"""Library layout, Drop-ins, and scanning."""

import json
from pathlib import Path

from bmc_toolkit.spec.library import resolve_library, safe_name


def test_resolve_library_default_and_override(tmp_path):
    assert resolve_library(env={}) == (Path.home() / ".bmc-specs").resolve()
    assert resolve_library(env={"BMC_SPEC_LIBRARY": str(tmp_path)}) == tmp_path
    assert (
        resolve_library(env={"BMC_SPEC_LIBRARY": "  "})
        == (Path.home() / ".bmc-specs").resolve()
    )


def test_safe_name_keeps_dots_and_replaces_the_rest():
    assert safe_name("1.3.3") == "1.3.3"
    assert safe_name("2.0 rev 1.1") == "2.0_rev_1.1"
    assert safe_name("Rev 2.1 / Ver 1.1") == "Rev_2.1_Ver_1.1"
    assert safe_name("   ") == "unnamed"


def test_ensure_reports_creation_once(library):
    assert library.ensure() is True
    assert library.specs.is_dir()
    assert library.ensure() is False


def test_store_writes_original_and_meta(library):
    vdir = library.store(
        "mctp",
        "DSP0236",
        "1.3.3",
        b"%PDF-1.7 data",
        "pdf",
        url="https://example.test/x.pdf",
        method="direct",
    )
    assert vdir == library.specs / "mctp" / "DSP0236" / "1.3.3"
    assert (vdir / "original.pdf").read_bytes() == b"%PDF-1.7 data"
    meta = json.loads((vdir / "meta.json").read_text("utf-8"))
    assert meta["document"] == "DSP0236"
    assert meta["version"] == "1.3.3"
    assert meta["url"] == "https://example.test/x.pdf"
    assert meta["fetch_method"] == "direct"
    assert meta["size"] == len(b"%PDF-1.7 data")
    assert len(meta["sha256"]) == 64
    assert meta["dropin"] is False
    assert meta["fetched_at"].endswith("+00:00")
    assert not list(vdir.glob("*.part"))


def test_find_matches_document_case_insensitively(library):
    library.store(
        "ipmi", "IPMI", "2.0 rev 1.1", b"%PDF", "pdf", url=None, method="wayback"
    )
    hit = library.find("ipmi", "2.0 rev 1.1")
    assert hit is not None
    assert hit.path.name == "2.0_rev_1.1"
    assert hit.original.name == "original.pdf"
    assert library.find("IPMI", "2.0") is None


def test_add_dropin_copies_file_without_url(library, tmp_path):
    src = tmp_path / "vendor.pdf"
    src.write_bytes(b"%PDF-1.4 secret")
    vdir = library.add_dropin(src, "vendor", "SECRET", "0.9", "pdf")
    meta = json.loads((vdir / "meta.json").read_text("utf-8"))
    assert meta["dropin"] is True
    assert meta["url"] is None
    assert meta["fetch_method"] == "dropin"
    assert (vdir / "original.pdf").read_bytes() == b"%PDF-1.4 secret"
    assert src.exists()


def test_unregistered_lists_originals_without_meta(library):
    library.ensure()
    a = library.specs / "mctp" / "DSP0236" / "1.3.2"
    a.mkdir(parents=True)
    (a / "original.pdf").write_bytes(b"%PDF")
    b = library.specs / "mctp" / "DSP0236" / "1.3.3"
    b.mkdir(parents=True)
    (b / "original.pdf").write_bytes(b"%PDF")
    (b / "meta.json").write_text("{}", encoding="utf-8")
    c = library.specs / "mctp" / "DSP0237" / "1.2.0"
    c.mkdir(parents=True)
    (c / "original.pdf.part").write_bytes(b"partial")
    found = list(library.unregistered())
    assert [(v.name, o.name) for v, o in found] == [("1.3.2", "original.pdf")]


def test_holdings_skip_unreadable_meta(library):
    library.ensure()
    bad = library.specs / "mctp" / "DSP0236" / "1.0.0"
    bad.mkdir(parents=True)
    (bad / "meta.json").write_text("not json", encoding="utf-8")
    library.store("mctp", "DSP0236", "1.3.3", b"%PDF", "pdf", url="u", method="direct")
    assert [h.version for h in library.holdings()] == ["1.3.3"]


def test_store_refuses_directory_collision(library):
    import pytest

    from bmc_toolkit.spec.library import LibraryError

    library.store("mctp", "DSP0236", "1.0 a", b"%PDF", "pdf", url="u", method="direct")
    with pytest.raises(LibraryError) as exc:
        library.store(
            "mctp", "DSP0236", "1.0_a", b"%PDF", "pdf", url="u", method="direct"
        )
    assert "already holds version '1.0 a'" in str(exc.value)
    # the same version string is fine (that is what --force relies on)
    library.store("mctp", "DSP0236", "1.0 a", b"%PDF2", "pdf", url="u", method="direct")


def test_file_matches_type(tmp_path):
    from bmc_toolkit.spec.library import file_matches_type

    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.7 x")
    zipf = tmp_path / "a.zip"
    zipf.write_bytes(b"PK\x03\x04rest")
    html = tmp_path / "b.pdf"
    html.write_bytes(b"<html>")
    assert file_matches_type(pdf, "pdf")
    assert file_matches_type(zipf, "zip")
    assert not file_matches_type(html, "pdf")
    assert not file_matches_type(pdf, "zip")
    assert not file_matches_type(tmp_path / "missing.pdf", "pdf")


def test_replacing_an_original_clears_other_originals_and_derived(library, tmp_path):
    vdir = library.store(
        "mctp", "DSP0236", "1.3.3", b"%PDF", "pdf", url="u", method="direct"
    )
    for name in ("extract.txt", "extract.json", "outline.json", "linemap.json"):
        (vdir / name).write_text("x", "utf-8")
    src = tmp_path / "bundle.zip"
    src.write_bytes(b"PK\x03\x04 zip")
    library.add_dropin(src, "mctp", "DSP0236", "1.3.3", "zip")
    assert sorted(p.name for p in vdir.iterdir()) == ["meta.json", "original.zip"]
    # and the other direction, via store
    library.store(
        "mctp", "DSP0236", "1.3.3", b"%PDF again", "pdf", url="u", method="direct"
    )
    assert sorted(p.name for p in vdir.iterdir()) == ["meta.json", "original.pdf"]


def test_extract_meta_property(library, tmp_path):
    vdir = library.store(
        "mctp", "DSP0236", "1.3.3", b"%PDF", "pdf", url="u", method="direct"
    )
    holding = library.find("DSP0236", "1.3.3")
    assert holding.extract_meta is None
    (vdir / "extract.json").write_text('{"outline_source": "bookmarks"}', "utf-8")
    assert holding.extract_meta is None  # no extract.txt yet
    (vdir / "extract.txt").write_text("=== page 1 ===\n", "utf-8")
    assert holding.extract_meta == {"outline_source": "bookmarks"}
