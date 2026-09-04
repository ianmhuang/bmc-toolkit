"""Source Catalog parsing, validation, and version resolution."""

import tomllib

import pytest

from bmc_toolkit.spec.catalog import CatalogError, load_catalog, parse_catalog
from tests.conftest import MINI_CATALOG


def _parse(text: str):
    return parse_catalog(tomllib.loads(text))


def test_loads_documents_and_families(catalog):
    assert set(catalog.families) == {"mctp", "ipmi", "vendor"}
    assert catalog.families["mctp"].publisher == "DMTF"
    assert [d.id for d in catalog.documents] == ["DSP0236", "IPMI", "BUNDLE", "SECRET"]


def test_lookup_is_case_insensitive(catalog):
    assert catalog.get("dsp0236").id == "DSP0236"
    assert catalog.get(" Ipmi ").id == "IPMI"
    assert catalog.get("nope") is None


def test_latest_ignores_wip_unless_asked(catalog):
    doc = catalog.get("DSP0236")
    assert doc.latest().version == "1.3.3"
    assert doc.latest(include_wip=True).version == "1.4.0"


def test_latest_by_date_not_by_order():
    text = MINI_CATALOG.replace(
        'version = "1.3.2"\nurl = "https://example.test/DSP0236_1.3.2.pdf"\n'
        'type = "pdf"\npublished = "2024-01-02"',
        'version = "1.3.2"\nurl = "https://example.test/DSP0236_1.3.2.pdf"\n'
        'type = "pdf"\npublished = "2024-12-31"',
    )
    doc = _parse(text).get("DSP0236")
    assert doc.latest().version == "1.3.2"


def test_latest_none_when_only_wip():
    text = MINI_CATALOG.replace(
        'published = "2024-01-02"', 'published = "2024-01-02"\nwip = true'
    ).replace('published = "2024-03-25"', 'published = "2024-03-25"\nwip = true')
    doc = _parse(text).get("DSP0236")
    assert doc.latest() is None
    assert doc.latest(include_wip=True).version == "1.4.0"


def test_find_version_exact_string(catalog):
    doc = catalog.get("IPMI")
    assert doc.find_version("2.0 rev 1.1").url.endswith("rev1-1.pdf")
    assert doc.find_version("2.0") is None


def test_by_family(catalog):
    assert [d.id for d in catalog.by_family("mctp")] == ["DSP0236", "BUNDLE"]


@pytest.mark.parametrize(
    "mutation, needle",
    [
        (("schema_version = 1", "schema_version = 2"), "schema_version"),
        (
            (
                'family = "mctp"\ntitle = "MCTP Base',
                'family = "nope"\ntitle = "MCTP Base',
            ),
            "documents[0].family",
        ),
        (
            (
                'access = "open"\nfetch = "direct"\n\n[[documents.versions]]\n'
                'version = "1.3.2"',
                'access = "paid"\nfetch = "direct"\n\n[[documents.versions]]\n'
                'version = "1.3.2"',
            ),
            "documents[0].access",
        ),
        (('fetch = "wayback"', 'fetch = "ftp"'), "documents[1].fetch"),
        (
            ('published = "2024-01-02"', 'published = "Jan 2 2024"'),
            "documents[0].versions[0].published",
        ),
        (('type = "zip"', 'type = "docx"'), "documents[2].versions[0].type"),
        (('version = "1.3.3"', 'version = "1.3.2"'), "duplicate version"),
        (('id = "BUNDLE"', 'id = "dsp0236"'), "duplicate id"),
        (
            ('url = "https://example.test/DSP0236_1.3.2.pdf"', 'url = ""'),
            "documents[0].versions[0].url",
        ),
        (
            ('title = "IPMI Specification v2.0"', "title = 7"),
            "documents[1].title: expected str",
        ),
    ],
)
def test_malformed_catalog_names_the_key(mutation, needle):
    old, new = mutation
    assert old in MINI_CATALOG
    with pytest.raises(CatalogError) as exc:
        _parse(MINI_CATALOG.replace(old, new, 1))
    assert needle in str(exc.value)


def test_document_without_versions_is_rejected():
    text = MINI_CATALOG + (
        '\n[[documents]]\nid = "EMPTY"\nfamily = "mctp"\ntitle = "x"\n'
        'access = "open"\nfetch = "direct"\nversions = []\n'
    )
    with pytest.raises(CatalogError) as exc:
        _parse(text)
    assert "versions" in str(exc.value)


def test_manual_fetch_allows_empty_url():
    text = MINI_CATALOG.replace('url = "https://example.test/secret.pdf"', 'url = ""')
    assert _parse(text).get("SECRET").versions[0].url == ""


def test_invalid_toml_is_a_catalog_error(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text("schema_version = [", encoding="utf-8")
    with pytest.raises(CatalogError) as exc:
        load_catalog(path)
    assert "not valid TOML" in str(exc.value)


def test_missing_file_is_a_catalog_error(tmp_path):
    with pytest.raises(CatalogError) as exc:
        load_catalog(tmp_path / "absent.toml")
    assert "not found" in str(exc.value)


def test_impossible_date_is_rejected():
    text = MINI_CATALOG.replace('published = "2024-01-02"', 'published = "2024-13-45"')
    with pytest.raises(CatalogError) as exc:
        _parse(text)
    assert "documents[0].versions[0].published" in str(exc.value)


def test_searched_with_is_optional_and_validated(catalog):
    assert catalog.get("IPMI").searched_with == ()
    text = MINI_CATALOG.replace(
        'title = "IPMI Specification v2.0"',
        'title = "IPMI Specification v2.0"\nsearched_with = [" dsp0236 "]',
    )
    assert _parse(text).get("IPMI").searched_with == ("dsp0236",)
    with pytest.raises(CatalogError) as exc:
        _parse(text.replace('[" dsp0236 "]', '["NOPE"]'))
    assert "searched_with[0]: unknown document 'NOPE'" in str(exc.value)
    with pytest.raises(CatalogError) as exc:
        _parse(text.replace('[" dsp0236 "]', '["ipmi"]'))
    assert "cannot list itself" in str(exc.value)
    with pytest.raises(CatalogError) as exc:
        _parse(text.replace('[" dsp0236 "]', "[1]"))
    assert "expected a document id" in str(exc.value)
    with pytest.raises(CatalogError) as exc:
        _parse(text.replace('[" dsp0236 "]', '"DSP0236"'))
    assert "searched_with: expected list" in str(exc.value)


# ------------------------------------------------ M8 follow-ups: date ties


def _two_versions(first: str, second: str, second_date: str = "2025-12-08") -> str:
    return f"""
schema_version = 1

[families.spdm]
title = "SPDM"
publisher = "DMTF"

[[documents]]
id = "DSP0276"
family = "spdm"
title = "Secured Messages over MCTP"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "{first}"
url = "https://example.test/{first}.pdf"
type = "pdf"
published = "2025-12-08"

[[documents.versions]]
version = "{second}"
url = "https://example.test/{second}.pdf"
type = "pdf"
published = "{second_date}"
"""


def test_same_day_tie_goes_to_the_higher_version_whatever_the_order():
    for first, second in (("1.3.0", "2.0.0"), ("2.0.0", "1.3.0")):
        doc = _parse(_two_versions(first, second)).get("DSP0276")
        assert doc.latest().version == "2.0.0", (first, second)
        assert doc.newest_open().version == "2.0.0", (first, second)


def test_version_tie_compares_numbers_not_strings():
    doc = _parse(_two_versions("1.10", "1.9")).get("DSP0276")
    assert doc.latest().version == "1.10"
    doc = _parse(_two_versions("Rev 1.0 Ver 1.2", "Rev 1.2 Ver 1.0")).get("DSP0276")
    assert doc.latest().version == "Rev 1.2 Ver 1.0"


def test_same_day_tie_without_numbers_keeps_catalog_order():
    doc = _parse(_two_versions("draft", "final")).get("DSP0276")
    assert doc.latest().version == "final"
    doc = _parse(_two_versions("final", "draft")).get("DSP0276")
    assert doc.latest().version == "draft"


def test_a_later_date_still_beats_a_higher_version():
    doc = _parse(_two_versions("2.0.0", "1.3.1", "2026-01-15")).get("DSP0276")
    assert doc.latest().version == "1.3.1"
