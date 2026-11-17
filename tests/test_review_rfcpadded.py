"""Reviewer acceptance tests for T81.4 AC-8 (review 2 of #139, F10): an RFC
id written with a leading zero.

Black-box through ``load_catalog`` and the ``catalog`` command, on synthetic
catalogs; nothing reaches the network. Every test needs the refusal the
base branch lacks: there ``RFC0793`` in an IETF family loads without a
listing, and a padded ``obsoleted_by`` entry is refused without the reason.
"""

import pytest

from bmc_toolkit.spec import cli
from bmc_toolkit.spec.catalog import CatalogError, load_catalog
from tests.conftest import MINI_CATALOG

# what both errors have to say (AC-8: "RFC ids take no leading zero")
REASON = "no leading zero"

IETF_FAMILY = """
[families.ietf]
title = "IETF Requests for Comments"
publisher = "IETF"
"""


def document(doc_id: str, family: str, extra: str = "") -> str:
    """One catalog document with a single text version."""
    return f"""
[[documents]]
id = "{doc_id}"
family = "{family}"
title = "The zebra protocol ({doc_id})"
access = "open"
fetch = "direct"
{extra}

[[documents.versions]]
version = "March 2026"
url = "https://example.test/{doc_id.lower()}.txt"
type = "txt"
published = "2026-03-01"
"""


def write(tmp_path, text: str, name: str = "catalog.toml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8", newline="")
    return path


def run(capsys, catalog, *argv):
    code = cli.main(["--catalog", str(catalog), *argv])
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def refusal(path) -> str:
    with pytest.raises(CatalogError) as info:
        load_catalog(path)
    return str(info.value)


# ------------------------------------------------------------ document id


@pytest.mark.parametrize("padded", ["RFC0793", "RFC00959", "RFC01111"])
def test_ac8_a_padded_rfc_id_in_an_ietf_family_is_a_catalog_error(
    tmp_path, library, capsys, padded
):
    path = write(
        tmp_path,
        MINI_CATALOG
        + IETF_FAMILY
        + document("RFC2222", "ietf")
        + document(padded, "ietf"),
    )
    message = refusal(path)
    # it names the id and says why
    assert padded in message, message
    assert REASON in message, message
    # through the CLI: exit 1 (malformed catalog) with the message, no traceback
    code, out = run(capsys, path, "catalog")
    assert code == 1, out
    assert padded in out and REASON in out, out
    assert "Traceback" not in out


def test_ac8_a_padded_id_is_refused_even_when_it_names_its_listing(tmp_path):
    """The id is what is refused: an explicit ``listing`` does not rescue it."""
    path = write(
        tmp_path,
        MINI_CATALOG
        + IETF_FAMILY
        + document("RFC0793", "ietf", 'listing = "rfc:793"'),
    )
    message = refusal(path)
    assert "RFC0793" in message and REASON in message, message


def test_ac8_only_the_padding_is_refused(tmp_path):
    padded = write(
        tmp_path,
        MINI_CATALOG + IETF_FAMILY + document("RFC0793", "ietf"),
        "padded.toml",
    )
    assert REASON in refusal(padded)
    # the same RFC as the RFC Editor lists it loads, and so do ids with a
    # zero that is not leading
    good = write(
        tmp_path,
        MINI_CATALOG
        + IETF_FAMILY
        + document("RFC793", "ietf")
        + document("RFC1001", "ietf")
        + document("RFC8010", "ietf", 'obsoleted_by = ["RFC9000", "RFC10000"]'),
        "good.toml",
    )
    cat = load_catalog(good)
    assert cat.get("RFC793").listing == "rfc:793"
    assert cat.get("RFC1001").listing == "rfc:1001"
    assert cat.get("RFC8010").listing == "rfc:8010"
    assert tuple(cat.get("RFC8010").obsoleted_by) == ("RFC9000", "RFC10000")
    # AC-8 speaks of an IETF family: under another publisher the id is a
    # name like any other and has no RFC listing
    other = write(
        tmp_path,
        MINI_CATALOG + IETF_FAMILY + document("RFC0793", "vendor"),
        "other.toml",
    )
    assert load_catalog(other).get("RFC0793").listing == ""


# ----------------------------------------------------------- obsoleted_by


@pytest.mark.parametrize(
    "value, entry",
    [
        ('["RFC08446"]', "RFC08446"),
        ('["RFC3333", "RFC05555"]', "RFC05555"),
        ('["RFC0793"]', "RFC0793"),
    ],
    ids=["alone", "second-entry", "the-example"],
)
def test_ac8_a_padded_obsoleted_by_entry_gets_the_same_reason(
    tmp_path, library, capsys, value, entry
):
    path = write(
        tmp_path,
        MINI_CATALOG
        + IETF_FAMILY
        + document("RFC2222", "ietf", f"obsoleted_by = {value}"),
    )
    message = refusal(path)
    assert "obsoleted_by" in message, message
    assert entry in message, message
    assert REASON in message, message
    code, out = run(capsys, path, "catalog", "RFC2222")
    assert code == 1, out
    assert "obsoleted_by" in out and REASON in out, out
    assert "Traceback" not in out


def test_ac8_the_reason_is_given_only_to_an_entry_that_is_padded(tmp_path):
    padded = write(
        tmp_path,
        MINI_CATALOG
        + IETF_FAMILY
        + document("RFC2222", "ietf", 'obsoleted_by = ["RFC08446"]'),
        "padded.toml",
    )
    assert REASON in refusal(padded)
    # an entry that is malformed another way is still refused, naming the
    # field, without being told about a zero it does not have
    for n, value in enumerate(('["rfc3333"]', '["DSP0236"]', "[3333]", '["RFC"]')):
        path = write(
            tmp_path,
            MINI_CATALOG
            + IETF_FAMILY
            + document("RFC2222", "ietf", f"obsoleted_by = {value}"),
            f"other-{n}.toml",
        )
        message = refusal(path)
        assert "obsoleted_by" in message, (value, message)
        assert REASON not in message, (value, message)
