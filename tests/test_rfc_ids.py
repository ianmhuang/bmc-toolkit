"""RFC ids the catalog would mishandle are refused with a reason (T82):
an id in another case, a value with a trailing newline, a bare RFC0, and
the padded-id check placed with the other id checks."""

import pytest

from bmc_toolkit.spec.catalog import CatalogError, load_catalog
from tests.test_rfc_obsoleted import RFC_CATALOG


def write(tmp_path, text):
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


def with_id(new_id):
    return RFC_CATALOG.replace('id = "RFC1111"', f'id = "{new_id}"')


@pytest.mark.parametrize("doc_id", ["rfc1111", "Rfc1111", "rFC1111"])
def test_an_rfc_id_in_another_case_is_refused(tmp_path, doc_id):
    with pytest.raises(CatalogError) as info:
        load_catalog(write(tmp_path, with_id(doc_id)))
    message = str(info.value)
    assert f"'{doc_id}'" in message and ".id" in message
    assert "upper case" in message and "RFC793" in message


def test_an_id_that_is_no_rfc_id_still_loads_without_a_listing(tmp_path):
    cat = load_catalog(write(tmp_path, with_id("BCP14")))
    assert cat.get("BCP14").listing == ""


@pytest.mark.parametrize("value", ['"RFC3333\\n"', '"RFC3333\\r\\n"', '"RFC3333 "'])
def test_an_obsoleted_by_entry_must_be_the_whole_id(tmp_path, value):
    text = RFC_CATALOG.replace('["RFC3333"]', f"[{value}]")
    with pytest.raises(CatalogError, match=r"obsoleted_by\[0\]"):
        load_catalog(write(tmp_path, text))


def test_a_padded_id_is_reported_before_a_bad_version(tmp_path):
    text = with_id("RFC01111").replace(
        'published = "2026-03-01"', 'published = "March 2026"'
    )
    with pytest.raises(CatalogError, match="RFC01111.*no leading zero"):
        load_catalog(write(tmp_path, text))


def test_rfc0_is_not_an_rfc_id_and_gets_no_leading_zero_reason(tmp_path):
    with pytest.raises(CatalogError) as info:
        load_catalog(write(tmp_path, with_id("RFC0")))
    assert "not an RFC id" in str(info.value)
    assert "no leading zero (" not in str(info.value)
    text = RFC_CATALOG.replace('["RFC3333"]', '["RFC0"]')
    with pytest.raises(CatalogError) as info:
        load_catalog(write(tmp_path, text))
    assert "expected an RFC id" in str(info.value)


def test_the_shipped_rfcs_keep_their_listings():
    cat = load_catalog()
    ietf = [d for d in cat.documents if d.family == "ietf"]
    assert ietf and all(d.listing == f"rfc:{d.id[3:]}" for d in ietf)
    assert cat.get("RFC5246").obsoleted_by == ("RFC8446", "RFC9846")
