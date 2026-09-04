"""Reviewer acceptance tests for M8a, part 1: version-level access, manual
entries without versions, Known Limits, and the gated paths of ``catalog``,
``fetch``, ``add`` and ``check`` (AC-1 to AC-8).

Black-box through the public interface: the catalog parser and the CLI with
a scripted HTTP client; nothing touches the network.
"""

import tomllib

import pytest

from bmc_toolkit.spec.catalog import (
    SCHEMA_VERSION,
    CatalogError,
    load_catalog,
    parse_catalog,
)
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG, PDF_BYTES, ok

BUS_131_URL = "https://example.test/bus-1.3.1.pdf"
BUS_12_URL = "https://example.test/bus-1.2.pdf"

# Appended to MINI_CATALOG (documents 0-3: DSP0236, IPMI, BUNDLE, SECRET):
#   4 BUS       open direct, 1.2 and 1.3.1 open, 1.4 and 1.5 gated, no URL
#   5 NDA-ONLY  member manual, no versions at all
#   6 ALLGATED  gated direct, one version inheriting the tier, no URL
EXTRA = f"""
[[documents]]
id = "BUS"
family = "mctp"
title = "A bus specification whose newest revisions are gated"
access = "open"
fetch = "direct"
limits = "Tables are images."
notes = "Newer revisions on request."

[[documents.versions]]
version = "1.2"
url = "{BUS_12_URL}"
type = "pdf"
published = "2010-09-06"

[[documents.versions]]
version = "1.3.1"
url = "{BUS_131_URL}"
type = "pdf"
published = "2015-03-13"

[[documents.versions]]
version = "1.4"
url = ""
type = "pdf"
published = "2021-06-01"
access = "gated"

[[documents.versions]]
version = "1.5"
url = ""
type = "pdf"
published = "2025-01-01"
access = "gated"

[[documents]]
id = "NDA-ONLY"
family = "vendor"
title = "A member document registered without versions"
access = "member"
fetch = "manual"

[[documents]]
id = "ALLGATED"
family = "vendor"
title = "A document with only gated versions"
access = "gated"
fetch = "direct"

[[documents.versions]]
version = "2.0"
url = ""
type = "pdf"
published = "2020-01-01"
"""

CATALOG_TEXT = MINI_CATALOG + EXTRA


def _parse(text: str):
    return parse_catalog(tomllib.loads(text))


@pytest.fixture
def cat_file(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(CATALOG_TEXT, encoding="utf-8", newline="")
    return path


@pytest.fixture
def cat(cat_file):
    return load_catalog(cat_file)


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ---------------------------------------------------------------- AC-1


def test_ac1_schema_version_is_still_one_and_the_catalog_loads(cat):
    assert SCHEMA_VERSION == 1
    assert "schema_version = 1" in CATALOG_TEXT
    assert [d.id for d in cat.documents] == [
        "DSP0236",
        "IPMI",
        "BUNDLE",
        "SECRET",
        "BUS",
        "NDA-ONLY",
        "ALLGATED",
    ]


def test_ac1_version_access_resolves_to_the_document_tier_when_absent(cat):
    bus = cat.get("BUS")
    assert [(v.version, v.access) for v in bus.versions] == [
        ("1.2", "open"),
        ("1.3.1", "open"),
        ("1.4", "gated"),
        ("1.5", "gated"),
    ]
    # a version without its own tier inherits the document's, whatever it is
    assert cat.get("ALLGATED").versions[0].access == "gated"
    assert cat.get("SECRET").versions[0].access == "confidential"
    assert all(v.access == "open" for v in cat.get("DSP0236").versions)
    # the document's own tier is untouched by its versions
    assert bus.access == "open"


def test_ac1_unknown_version_tier_names_the_version_key():
    bad = CATALOG_TEXT.replace(
        'published = "2021-06-01"\naccess = "gated"',
        'published = "2021-06-01"\naccess = "paywall"',
    )
    assert bad != CATALOG_TEXT
    with pytest.raises(CatalogError, match=r"documents\[4\]\.versions\[2\]\.access"):
        _parse(bad)


def test_ac1_newest_open_skips_gated_and_wip_versions(cat):
    bus = cat.get("BUS")
    assert bus.latest().version == "1.5"
    assert bus.newest_open().version == "1.3.1"
    # DSP0236's newest entry is an open WIP: newest_open ignores it too
    assert cat.get("DSP0236").newest_open().version == "1.3.3"
    assert cat.get("ALLGATED").newest_open() is None
    assert cat.get("NDA-ONLY").newest_open() is None


# ---------------------------------------------------------------- AC-2


def test_ac2_open_version_of_a_direct_document_still_needs_a_url():
    bad = CATALOG_TEXT.replace(f'url = "{BUS_131_URL}"', 'url = ""')
    with pytest.raises(CatalogError, match=r"documents\[4\]\.versions\[1\]\.url"):
        _parse(bad)


def test_ac2_open_version_of_a_wayback_document_still_needs_a_url():
    bad = CATALOG_TEXT.replace('url = "https://example.test/ipmi-v2-rev1-1.pdf"', 'url = ""')
    with pytest.raises(CatalogError, match=r"documents\[1\]\.versions\[0\]\.url"):
        _parse(bad)


def test_ac2_gated_version_may_omit_the_url_and_keep_it(cat):
    # the shipped-style entries above parse: no URL on the gated versions
    assert [v.url for v in cat.get("BUS").versions[2:]] == ["", ""]
    # a gated version may still carry a URL (a registration page)
    with_url = CATALOG_TEXT.replace(
        'version = "1.5"\nurl = ""', 'version = "1.5"\nurl = "https://example.test/reg"'
    )
    doc = _parse(with_url).get("BUS")
    assert doc.find_version("1.5").url == "https://example.test/reg"
    assert doc.find_version("1.5").access == "gated"
    # the manual rule is unchanged: SECRET's version may have any URL or none
    no_url = CATALOG_TEXT.replace('url = "https://example.test/secret.pdf"', 'url = ""')
    assert _parse(no_url).get("SECRET").versions[0].url == ""


# ---------------------------------------------------------------- AC-3


def test_ac3_manual_document_without_versions_loads(cat):
    doc = cat.get("NDA-ONLY")
    assert doc.fetch == "manual" and doc.access == "member"
    assert doc.versions == ()
    assert doc.latest() is None
    assert doc.latest(include_wip=True) is None
    assert doc.find_version("1.0") is None


@pytest.mark.parametrize("method", ["direct", "wayback"])
def test_ac3_fetchable_document_without_versions_is_an_error(method):
    bad = CATALOG_TEXT.replace(
        'access = "member"\nfetch = "manual"', f'access = "member"\nfetch = "{method}"'
    )
    assert bad != CATALOG_TEXT
    with pytest.raises(CatalogError, match=r"documents\[5\].*versions"):
        _parse(bad)
    empty = bad.replace(
        f'access = "member"\nfetch = "{method}"',
        f'access = "member"\nfetch = "{method}"\nversions = []',
    )
    with pytest.raises(CatalogError, match=r"documents\[5\].*versions"):
        _parse(empty)


# ---------------------------------------------------------------- AC-4


def test_ac4_limits_is_optional_and_separate_from_notes(cat):
    bus = cat.get("BUS")
    assert bus.limits == "Tables are images."
    assert bus.notes == "Newer revisions on request."
    assert cat.get("DSP0236").limits == ""
    assert cat.get("NDA-ONLY").limits == ""


def test_ac4_catalog_doc_prints_limits_only_when_present(cat_file, capsys):
    code, out, _ = run(capsys, "catalog", "BUS", catalog_file=cat_file)
    assert code == 0
    assert "limits: Tables are images." in out.splitlines()
    assert "notes: Newer revisions on request." in out.splitlines()
    code, out, _ = run(capsys, "catalog", "DSP0236", catalog_file=cat_file)
    assert code == 0
    assert not any(ln.startswith("limits:") for ln in out.splitlines())


# ---------------------------------------------------------------- AC-5


def test_ac5_catalog_doc_lists_resolved_access_per_version(cat_file, capsys):
    code, out, _ = run(capsys, "catalog", "BUS", catalog_file=cat_file)
    assert code == 0
    rows = [ln.split("\t") for ln in out.splitlines() if ln.startswith("\t")]
    # newest first; the version and its resolved tier are both columns
    assert [(r[1], r[-1]) for r in rows] == [
        ("1.5", "gated"),
        ("1.4", "gated"),
        ("1.3.1", "open"),
        ("1.2", "open"),
    ]
    # the inherited tier shows the same way
    code, out, _ = run(capsys, "catalog", "SECRET", catalog_file=cat_file)
    rows = [ln.split("\t") for ln in out.splitlines() if ln.startswith("\t")]
    assert [(r[1], r[-1]) for r in rows] == [("0.9", "confidential")]


def test_ac5_manual_document_without_versions_prints_the_add_hint(cat_file, capsys):
    code, out, _ = run(capsys, "catalog", "NDA-ONLY", catalog_file=cat_file)
    assert code == 0
    lines = out.splitlines()
    assert "latest: -" in lines
    assert (
        "versions: (none listed; add any version with: bmcspec add FILE "
        "--document NDA-ONLY --version V)"
    ) in lines
    assert not any(ln.startswith("\t") for ln in lines)


# ---------------------------------------------------------------- AC-6


def _assert_gated_message(out, doc_id, version, tier):
    lines = out.splitlines()
    assert lines, out
    assert doc_id in lines[0] and version in lines[0] and tier in lines[0]
    # the Drop-in instruction: where to save the file and what to run
    assert any("original.pdf" in ln for ln in lines)
    assert any("scan" in ln for ln in lines)


def test_ac6_fetch_of_a_gated_latest_downloads_nothing_and_names_newest_open(
    cat_file, library, scripted, capsys
):
    code, out, _ = run(capsys, "fetch", "BUS", catalog_file=cat_file)
    assert code == 2
    assert scripted.calls == []
    _assert_gated_message(out, "BUS", "1.5", "gated")
    assert "newest open version: 1.3.1; fetch it with --version 1.3.1" in out
    assert "no open version is listed" not in out
    assert not library.root.exists()


def test_ac6_fetch_of_a_requested_gated_version_behaves_the_same(
    cat_file, library, scripted, capsys
):
    code, out, _ = run(
        capsys, "fetch", "BUS", "--version", "1.4", catalog_file=cat_file
    )
    assert code == 2
    assert scripted.calls == []
    _assert_gated_message(out, "BUS", "1.4", "gated")
    assert "newest open version: 1.3.1; fetch it with --version 1.3.1" in out


def test_ac6_fetch_of_a_document_without_open_versions_says_so(
    cat_file, library, scripted, capsys
):
    code, out, _ = run(capsys, "fetch", "ALLGATED", catalog_file=cat_file)
    assert code == 2
    assert scripted.calls == []
    _assert_gated_message(out, "ALLGATED", "2.0", "gated")
    assert "no open version is listed" in out
    assert "newest open version" not in out


def test_ac6_the_named_open_version_then_fetches(cat_file, library, scripted, capsys):
    scripted.responses[BUS_131_URL] = ok(PDF_BYTES)
    code, out, _ = run(
        capsys, "fetch", "BUS", "--version", "1.3.1", catalog_file=cat_file
    )
    assert code == 0, out
    assert "fetched BUS 1.3.1 via direct" in out
    assert scripted.calls == [BUS_131_URL]
    assert library.find("BUS", "1.3.1") is not None


def test_ac6_fetch_all_takes_the_newest_open_version_with_one_note(
    cat_file, library, scripted, capsys
):
    scripted.responses[BUS_131_URL] = ok(PDF_BYTES)
    scripted.responses["https://example.test/DSP0236_1.3.3.pdf"] = ok(PDF_BYTES)
    code, out, _ = run(capsys, "fetch", "--all", catalog_file=cat_file)
    lines = out.splitlines()
    bus_notes = [ln for ln in lines if ln.startswith("note:") and "BUS" in ln]
    assert len(bus_notes) == 1
    assert "1.5" in bus_notes[0] and "gated" in bus_notes[0]
    assert "fetched BUS 1.3.1 via direct" in lines
    assert "fetched DSP0236 1.3.3 via direct" in lines
    assert library.find("BUS", "1.3.1") is not None
    # the gated versions were never attempted, nor an empty URL
    assert BUS_131_URL in scripted.calls
    assert "" not in scripted.calls
    assert not any("BUS 1.5" in ln or "BUS 1.4" in ln for ln in lines)
    # a document without any open version, and a manual one, are not fetched
    outcome_lines = [ln for ln in lines if ln.startswith(("fetched", "failed", "skipped"))]
    assert not any("ALLGATED" in ln or "NDA-ONLY" in ln or "SECRET" in ln for ln in outcome_lines)
    summary = [ln for ln in lines if ln.startswith("summary:")]
    assert len(summary) == 1 and "fetched 2" in summary[0]
    # IPMI and BUNDLE have no scripted response and fail, hence exit 2
    assert code == 2


# ---------------------------------------------------------------- AC-7


def test_ac7_add_any_version_to_a_manual_document_without_versions(
    cat_file, library, tmp_path, capsys
):
    src = tmp_path / "member.pdf"
    src.write_bytes(PDF_BYTES)
    code, out, _ = run(
        capsys,
        "add",
        str(src),
        "--document",
        "NDA-ONLY",
        "--version",
        "5B (2024)",
        catalog_file=cat_file,
    )
    assert code == 0, out
    assert "added NDA-ONLY 5B (2024) as Drop-in" in out
    held = library.find("NDA-ONLY", "5B (2024)")
    assert held is not None and held.dropin
    code, out, _ = run(capsys, "status", catalog_file=cat_file)
    assert code == 0
    rows = [ln.split("\t") for ln in out.splitlines() if "\tNDA-ONLY\t" in ln]
    assert len(rows) == 1
    assert rows[0][:4] == ["vendor", "NDA-ONLY", "5B (2024)", "dropin"]


# ---------------------------------------------------------------- AC-8


def test_ac8_check_lists_manual_documents_separately_with_their_tier(
    cat_file, library, scripted, capsys
):
    code, out, _ = run(capsys, "check", catalog_file=cat_file)
    assert code == 0
    lines = out.splitlines()
    unchecked = [ln for ln in lines if ln.startswith("unchecked: ")]
    assert unchecked == ["unchecked: IPMI, BUNDLE, BUS, ALLGATED (no publisher listing)"]
    manual = [ln for ln in lines if ln.startswith("unchecked (manual): ")]
    assert manual == [
        "unchecked (manual): SECRET (confidential), NDA-ONLY (member) "
        "(never fetched by the tool)"
    ]
    # DSP0236 has an (implied DMTF) listing: checked, not unchecked
    assert "DSP0236" not in unchecked[0] and "DSP0236" not in manual[0]
    summary = [ln for ln in lines if ln.startswith("summary: ")]
    assert len(summary) == 1
    assert summary[0].endswith("unchecked 6")  # 4 hand-maintained + 2 manual


def test_ac8_check_of_one_document_prints_neither_line(
    cat_file, library, scripted, capsys
):
    code, out, _ = run(capsys, "check", "DSP0236", catalog_file=cat_file)
    assert code == 0
    assert "unchecked" not in out
