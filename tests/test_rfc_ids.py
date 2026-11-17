"""RFC ids the catalog would mishandle are refused with a reason (T82):
an id in another case or with a separator, a value with a trailing
newline, a bare or all-zero RFC0, a hand-written rfc listing key that is
not the number, and the padded-id check placed with the other id checks."""

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


@pytest.mark.parametrize(
    "doc_id", ["RFC 1111", "RFC-1111", "rfc_1111", "Rfc  1111", "RFC\\t1111"]
)
def test_an_rfc_id_with_a_separator_is_refused(tmp_path, doc_id):
    # review 1 of #141, F1: "RFC 793" is the usual citation form
    with pytest.raises(CatalogError) as info:
        load_catalog(write(tmp_path, with_id(doc_id)))
    message = str(info.value)
    assert ".id" in message and "not an RFC id" in message, message
    assert "RFC793" in message


@pytest.mark.parametrize("doc_id", ["RFC-notes", "RFCs", "RFC1111bis"])
def test_an_id_that_only_starts_like_an_rfc_still_loads(tmp_path, doc_id):
    cat = load_catalog(write(tmp_path, with_id(doc_id)))
    assert cat.get(doc_id).listing == ""


@pytest.mark.parametrize("zeros", ["RFC00", "RFC000"])
def test_an_all_zero_id_is_not_told_about_a_leading_zero(tmp_path, zeros):
    # review 1 of #141, F2: dropping the zero as told would give RFC0
    with pytest.raises(CatalogError) as info:
        load_catalog(write(tmp_path, with_id(zeros)))
    assert "not an RFC id" in str(info.value)
    assert "no leading zero (" not in str(info.value)
    text = RFC_CATALOG.replace('["RFC3333"]', f'["{zeros}"]')
    with pytest.raises(CatalogError) as info:
        load_catalog(write(tmp_path, text))
    assert "expected an RFC id" in str(info.value)
    # a zero before a non-zero number keeps the leading-zero reason
    with pytest.raises(CatalogError, match="no leading zero"):
        load_catalog(write(tmp_path, with_id("RFC001111")))


@pytest.mark.parametrize("key", ["0793", "RFC793", "abc", "7 93", "793a"])
def test_an_rfc_listing_key_must_be_the_number(tmp_path, key):
    text = RFC_CATALOG.replace(
        'id = "RFC1111"', f'id = "RFC1111"\nlisting = "rfc:{key}"'
    )
    with pytest.raises(CatalogError) as info:
        load_catalog(write(tmp_path, text))
    message = str(info.value)
    assert ".listing" in message and "rfc:793" in message, message


def test_a_hand_written_rfc_listing_with_the_number_loads(tmp_path):
    text = RFC_CATALOG.replace('id = "RFC1111"', 'id = "RFC1111"\nlisting = "rfc:793"')
    assert load_catalog(write(tmp_path, text)).get("RFC1111").listing == "rfc:793"


def test_a_published_date_with_a_trailing_newline_is_refused(tmp_path):
    text = RFC_CATALOG.replace(
        'published = "2026-03-01"', 'published = "2026-03-01\\n"'
    )
    with pytest.raises(CatalogError, match="published"):
        load_catalog(write(tmp_path, text))


def test_an_owner_with_a_trailing_newline_is_refused(tmp_path):
    repo = (
        '\n[[repos]]\nid = "acme-thing"\nowner = "acme{end}"\n'
        'url = "https://example.test/acme-thing.git"\ntopics = ["acme"]\n'
    )
    good = load_catalog(write(tmp_path, RFC_CATALOG + repo.format(end="")))
    assert good is not None
    with pytest.raises(CatalogError, match="owner"):
        load_catalog(write(tmp_path, RFC_CATALOG + repo.format(end="\\n")))


def test_the_shipped_rfcs_keep_their_listings():
    cat = load_catalog()
    ietf = [d for d in cat.documents if d.family == "ietf"]
    assert ietf and all(d.listing == f"rfc:{d.id[3:]}" for d in ietf)
    assert cat.get("RFC5246").obsoleted_by == ("RFC8446", "RFC9846")
