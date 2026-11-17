"""Reviewer acceptance tests for T82: RFC ids the catalog would silently
mishandle are refused with a reason.

Black-box through ``load_catalog`` and the ``catalog`` command, on synthetic
catalogs and on the shipped one; nothing reaches the network. Every test
opens with an assertion the base branch fails: there a lower-case RFC id of
an IETF family loads without a listing, an ``obsoleted_by`` entry ending in
a newline is stored as written, the padded-id check runs after the version
checks, and a bare ``RFC0`` is told about a leading zero.
"""

import re

import pytest

from bmc_toolkit.spec import cli
from bmc_toolkit.spec.catalog import DEFAULT_CATALOG, CatalogError, load_catalog
from tests.conftest import MINI_CATALOG

# the leading-zero reason of T81.4 AC-8 ("RFC ids take no leading zero")
LEADING_ZERO = "no leading zero"

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
url = "https://example.test/zebra.txt"
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


def ietf_catalog(*documents: str) -> str:
    return MINI_CATALOG + IETF_FAMILY + "".join(documents)


# ------------------------------------------------- AC-1: another case


@pytest.mark.parametrize("doc_id", ["rfc793", "Rfc793", "rFC5246", "RFc10000"])
def test_ac1_an_rfc_id_in_another_case_is_a_catalog_error(
    tmp_path, library, capsys, doc_id
):
    path = write(
        tmp_path,
        ietf_catalog(document("RFC2222", "ietf"), document(doc_id, "ietf")),
    )
    message = refusal(path)
    # it names the id as written and the key it sits in
    assert f"'{doc_id}'" in message, message
    assert ".id" in message, message
    # and says how RFC ids are written: RFC and digits (RFC793)
    assert "RFC" in message and "digits" in message, message
    assert "RFC793" in message, message
    # through the CLI: exit 1 (malformed catalog) with the message, no traceback
    code, out = run(capsys, path, "catalog")
    assert code == 1, out
    assert doc_id in out and "RFC793" in out, out
    assert "Traceback" not in out


def test_ac1_an_explicit_listing_does_not_rescue_the_id(tmp_path):
    """The id is what is refused (it is cited as written, so it is not
    normalised): naming the listing by hand does not make it load."""
    path = write(
        tmp_path,
        ietf_catalog(document("rfc793", "ietf", 'listing = "rfc:793"')),
    )
    message = refusal(path)
    assert "'rfc793'" in message and "RFC793" in message, message


def test_ac1_only_an_rfc_id_in_another_case_is_refused(tmp_path):
    lower = write(tmp_path, ietf_catalog(document("rfc793", "ietf")), "lower.toml")
    assert "'rfc793'" in refusal(lower)
    # the same RFC written as the RFC Editor lists it loads with its listing
    good = write(tmp_path, ietf_catalog(document("RFC793", "ietf")), "good.toml")
    assert load_catalog(good).get("RFC793").listing == "rfc:793"
    # an id that is no RFC id at all still loads, with no listing, as before
    for n, other in enumerate(("BCP14", "bcp14", "STD7", "zebra-notes")):
        path = write(
            tmp_path, ietf_catalog(document(other, "ietf")), f"other-{n}.toml"
        )
        doc = load_catalog(path).get(other)
        assert doc is not None and doc.id == other, other
        assert doc.listing == "", other
    # AC-1 speaks of an IETF family: under another publisher the id is a
    # name like any other
    vendor = write(
        tmp_path, ietf_catalog(document("rfc793", "vendor")), "vendor.toml"
    )
    doc = load_catalog(vendor).get("rfc793")
    assert doc.id == "rfc793" and doc.listing == ""


# ------------------------------------------- AC-2: the whole string


@pytest.mark.parametrize(
    "value, index",
    [
        ('["RFC8446\\n"]', 0),
        ('["RFC3333", "RFC8446\\n"]', 1),
        ('["RFC8446\\n", "RFC3333"]', 0),
    ],
    ids=["alone", "second-entry", "first-entry"],
)
def test_ac2_an_obsoleted_by_entry_ending_in_a_newline_is_refused(
    tmp_path, library, capsys, value, index
):
    path = write(
        tmp_path,
        ietf_catalog(document("RFC2222", "ietf", f"obsoleted_by = {value}")),
    )
    message = refusal(path)
    assert f"obsoleted_by[{index}]" in message, message
    code, out = run(capsys, path, "catalog", "RFC2222")
    assert code == 1, out
    assert "obsoleted_by" in out, out
    assert "Traceback" not in out


def test_ac2_no_entry_is_stored_with_anything_around_the_id(tmp_path):
    newline = write(
        tmp_path,
        ietf_catalog(document("RFC2222", "ietf", 'obsoleted_by = ["RFC8446\\n"]')),
        "newline.toml",
    )
    assert "obsoleted_by" in refusal(newline)
    # every other value that is more than the id is refused as well
    for n, entry in enumerate(
        ("RFC8446\\r\\n", "RFC8446 ", " RFC8446", "RFC8446\\t", "\\nRFC8446")
    ):
        path = write(
            tmp_path,
            ietf_catalog(
                document("RFC2222", "ietf", f'obsoleted_by = ["{entry}"]')
            ),
            f"around-{n}.toml",
        )
        assert "obsoleted_by[0]" in refusal(path), entry
    # and what does load is stored exactly as the id
    good = write(
        tmp_path,
        ietf_catalog(
            document("RFC2222", "ietf", 'obsoleted_by = ["RFC8446", "RFC9846"]')
        ),
        "good.toml",
    )
    stored = tuple(load_catalog(good).get("RFC2222").obsoleted_by)
    assert stored == ("RFC8446", "RFC9846")
    assert all(re.fullmatch(r"RFC[1-9][0-9]*", s) for s in stored)


# ------------------------------- AC-3: the padded id is reported first

DEFECTS = {
    "bad-date": ('published = "2026-03-01"', 'published = "March 2026"'),
    "bad-type": ('type = "txt"', 'type = "text"'),
    "bad-access": ('access = "open"', 'access = "public"'),
    "bad-fetch": ('fetch = "direct"', 'fetch = "ftp"'),
    "no-title": ('title = "The zebra protocol (RFC0793)"\n', ""),
}


@pytest.mark.parametrize("defect", list(DEFECTS), ids=list(DEFECTS))
def test_ac3_a_padded_id_is_reported_before_a_later_defect(tmp_path, defect):
    old, new = DEFECTS[defect]
    text = document("RFC0793", "ietf")
    assert old in text
    path = write(tmp_path, ietf_catalog(text.replace(old, new)))
    message = refusal(path)
    assert "RFC0793" in message and ".id" in message, message
    assert LEADING_ZERO in message, message


def test_ac3_the_check_needs_the_family_to_be_ietf(tmp_path):
    old, new = DEFECTS["bad-date"]
    padded = write(
        tmp_path,
        ietf_catalog(document("RFC0793", "ietf").replace(old, new)),
        "ietf.toml",
    )
    assert LEADING_ZERO in refusal(padded)
    # under another publisher the padded id is a name like any other, so
    # the defect that is reported is the version's
    other = write(
        tmp_path,
        ietf_catalog(document("RFC0793", "vendor").replace(old, new)),
        "vendor.toml",
    )
    message = refusal(other)
    assert "published" in message, message
    assert LEADING_ZERO not in message, message


# ------------------------------------------------- AC-4: RFC0 alone


def test_ac4_rfc0_as_a_document_id_is_not_an_rfc_id(tmp_path, library, capsys):
    path = write(tmp_path, ietf_catalog(document("RFC0", "ietf")))
    message = refusal(path)
    assert "'RFC0'" in message and ".id" in message, message
    assert "not an RFC id" in message, message
    assert LEADING_ZERO not in message, message
    code, out = run(capsys, path, "catalog")
    assert code == 1, out
    assert "RFC0" in out and LEADING_ZERO not in out, out
    assert "Traceback" not in out


def test_ac4_rfc0_in_obsoleted_by_is_not_an_rfc_id(tmp_path, library, capsys):
    path = write(
        tmp_path,
        ietf_catalog(document("RFC2222", "ietf", 'obsoleted_by = ["RFC0"]')),
    )
    message = refusal(path)
    assert "obsoleted_by[0]" in message, message
    assert "RFC id" in message, message
    assert LEADING_ZERO not in message, message
    code, out = run(capsys, path, "catalog", "RFC2222")
    assert code == 1, out
    assert "obsoleted_by" in out and LEADING_ZERO not in out, out
    assert "Traceback" not in out


def test_ac4_a_padded_id_keeps_the_leading_zero_reason(tmp_path):
    bare = write(tmp_path, ietf_catalog(document("RFC0", "ietf")), "bare.toml")
    assert LEADING_ZERO not in refusal(bare)
    padded = write(
        tmp_path, ietf_catalog(document("RFC0793", "ietf")), "padded.toml"
    )
    message = refusal(padded)
    assert "RFC0793" in message and LEADING_ZERO in message, message
    listed = write(
        tmp_path,
        ietf_catalog(document("RFC2222", "ietf", 'obsoleted_by = ["RFC0793"]')),
        "listed.toml",
    )
    message = refusal(listed)
    assert "obsoleted_by[0]" in message and LEADING_ZERO in message, message


# --------------------------------------------- AC-5: the shipped catalog


def test_ac5_the_shipped_catalog_passes_the_rule_it_is_now_under(tmp_path):
    shipped = DEFAULT_CATALOG.read_text(encoding="utf-8")
    # the rule is live for the shipped file: one RFC id in lower case and
    # the copy no longer loads
    assert shipped.count('id = "RFC9110"') == 1
    lowered = write(tmp_path, shipped.replace('id = "RFC9110"', 'id = "rfc9110"'))
    assert "'rfc9110'" in refusal(lowered)
    # the file as shipped loads, and every document of an IETF family keeps
    # the listing its id implies
    cat = load_catalog()
    ietf = [d for d in cat.documents if cat.families[d.family].publisher == "IETF"]
    assert {"RFC5246", "RFC9110"} <= {d.id for d in ietf}
    for doc in ietf:
        assert re.fullmatch(r"RFC[1-9][0-9]*", doc.id), doc.id
        assert doc.listing == f"rfc:{doc.id.removeprefix('RFC')}", doc.id
    assert tuple(cat.get("RFC5246").obsoleted_by) == ("RFC8446", "RFC9846")
    for doc in ietf:
        assert all(re.fullmatch(r"RFC[1-9][0-9]*", s) for s in doc.obsoleted_by)
