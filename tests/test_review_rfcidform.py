"""Reviewer acceptance tests for T82: RFC ids the catalog would silently
mishandle are refused with a reason.

Black-box through ``load_catalog`` and the ``catalog`` command, on synthetic
catalogs and on the shipped one; nothing reaches the network. Every test
holds an assertion the base branch fails: there a lower-case RFC id of
an IETF family loads without a listing, an ``obsoleted_by`` entry ending in
a newline is stored as written, the padded-id check runs after the version
checks, a bare or all-zero ``RFC0`` is told about a leading zero, ``RFC 793``
loads without a listing, an ``rfc:`` listing takes any key, and a repository
owner ending in a newline loads.
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


def ietf_doc(tmp_path, doc_id: str, name: str = "catalog.toml", extra: str = ""):
    """A catalog file with ``doc_id`` as a document of the IETF family."""
    return write(tmp_path, ietf_catalog(document(doc_id, "ietf", extra)), name)


REPO = """
[[repos]]
id = "{repo_id}"
owner = "{owner}"
url = "https://example.test/acme-thing.git"
topics = ["acme"]
"""


def repo_catalog(tmp_path, name: str, repo_id: str, owner: str):
    """A catalog file with one vendor tree; the values are TOML text."""
    text = MINI_CATALOG + REPO.format(repo_id=repo_id, owner=owner)
    return write(tmp_path, text, name)


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


# ------------------------------- AC-7: a separator before the number

SEPARATED = ["RFC 793", "RFC-793", "rfc_793", "Rfc  793", "rfc-793", "RFC 0793"]


@pytest.mark.parametrize("doc_id", SEPARATED)
def test_ac7_a_separated_rfc_id_is_refused(tmp_path, library, capsys, doc_id):
    path = ietf_doc(tmp_path, doc_id)
    message = refusal(path)
    assert f"'{doc_id}'" in message and ".id" in message, message
    # refused as not an RFC id, with the form an RFC id takes
    assert "not an RFC id" in message and "RFC793" in message, message
    code, out = run(capsys, path, "catalog")
    assert code == 1, out
    assert doc_id in out and "RFC793" in out, out
    assert "Traceback" not in out


def test_ac7_an_id_that_only_starts_with_rfc_still_loads(tmp_path):
    spaced = ietf_doc(tmp_path, "RFC 793", "spaced.toml")
    assert "not an RFC id" in refusal(spaced)
    # RFC followed by anything but separators and digits is a name
    others = ("RFC-notes", "RFCs", "RFC1111bis", "RFC", "RFC-793bis")
    for n, other in enumerate(others):
        path = ietf_doc(tmp_path, other, f"other-{n}.toml")
        doc = load_catalog(path).get(other)
        assert doc is not None and doc.id == other, other
        assert doc.listing == "", other
    # AC-7 speaks of an IETF family: elsewhere the id is a name like any other
    text = ietf_catalog(document("RFC 793", "vendor"))
    doc = load_catalog(write(tmp_path, text, "vendor.toml")).get("RFC 793")
    assert doc.id == "RFC 793" and doc.listing == ""


# ------------------------------------------- AC-8: nothing but zeros

ALL_ZERO = ["RFC00", "RFC000", "RFC00000"]


@pytest.mark.parametrize("zeros", ALL_ZERO)
def test_ac8_an_all_zero_id_is_not_an_rfc_id(tmp_path, zeros):
    message = refusal(ietf_doc(tmp_path, zeros))
    assert f"'{zeros}'" in message and ".id" in message, message
    assert "not an RFC id" in message, message
    assert LEADING_ZERO not in message, message


@pytest.mark.parametrize("zeros", ALL_ZERO)
def test_ac8_an_all_zero_obsoleted_by_entry_is_not_an_rfc_id(tmp_path, zeros):
    extra = f'obsoleted_by = ["{zeros}"]'
    message = refusal(ietf_doc(tmp_path, "RFC2222", extra=extra))
    assert "obsoleted_by[0]" in message, message
    assert "expected an RFC id" in message, message
    assert LEADING_ZERO not in message, message


def test_ac8_zeros_before_a_number_keep_the_leading_zero_reason(tmp_path):
    zero = ietf_doc(tmp_path, "RFC00", "zero.toml")
    assert LEADING_ZERO not in refusal(zero)
    for n, padded in enumerate(("RFC0793", "RFC00959", "RFC0010")):
        message = refusal(ietf_doc(tmp_path, padded, f"id-{n}.toml"))
        assert f"'{padded}'" in message and ".id" in message, message
        assert LEADING_ZERO in message, message
        extra = f'obsoleted_by = ["{padded}"]'
        message = refusal(ietf_doc(tmp_path, "RFC2222", f"e-{n}.toml", extra))
        assert "obsoleted_by[0]" in message and padded in message, message
        assert LEADING_ZERO in message, message


# ------------------------------------- AC-9: the key of an rfc listing

BAD_KEYS = ["0793", "RFC793", "abc", "00793", "rfc793", "793bis"]


@pytest.mark.parametrize("key", BAD_KEYS)
def test_ac9_an_rfc_listing_key_is_the_number(tmp_path, library, capsys, key):
    path = ietf_doc(tmp_path, "RFC793", extra=f'listing = "rfc:{key}"')
    message = refusal(path)
    # it names the key it sits in and the form the listing takes
    assert ".listing" in message and "rfc:793" in message, message
    code, out = run(capsys, path, "catalog")
    assert code == 1, out
    assert "listing" in out and "rfc:793" in out, out
    assert "Traceback" not in out


def test_ac9_a_hand_written_rfc_listing_with_the_number_loads(tmp_path):
    bad = ietf_doc(tmp_path, "RFC1111", "bad.toml", 'listing = "rfc:0793"')
    assert ".listing" in refusal(bad)
    good = ietf_doc(tmp_path, "RFC1111", "good.toml", 'listing = "rfc:793"')
    assert load_catalog(good).get("RFC1111").listing == "rfc:793"
    # the rule is the listing's, whatever the family of the document
    text = ietf_catalog(document("ZEBRA", "vendor", 'listing = "rfc:09110"'))
    assert ".listing" in refusal(write(tmp_path, text, "vendor-bad.toml"))
    text = ietf_catalog(document("ZEBRA", "vendor", 'listing = "rfc:9110"'))
    cat = load_catalog(write(tmp_path, text, "vendor.toml"))
    assert cat.get("ZEBRA").listing == "rfc:9110"
    # and only of the rfc source: another source keeps its own keys
    text = ietf_catalog(document("RFC6666", "ietf", 'listing = "nvme:0793"'))
    cat = load_catalog(write(tmp_path, text, "nvme.toml"))
    assert cat.get("RFC6666").listing == "nvme:0793"


# --------------------------- AC-10: the other whole-string patterns


def test_ac10_an_owner_ending_in_a_newline_is_refused(tmp_path, library, capsys):
    # on the base branch this pair loads, the newline kept in the owner
    path = repo_catalog(tmp_path, "newline.toml", "acme\\n-thing", "acme\\n")
    message = refusal(path)
    assert ".owner" in message, message
    code, out = run(capsys, path, "catalog")
    assert code == 1, out
    assert "owner" in out and "Traceback" not in out, out
    # with an ordinary id it is the owner that is named, not the id
    path = repo_catalog(tmp_path, "plain.toml", "acme-thing", "acme\\n")
    assert ".owner" in refusal(path)
    for n, owner in enumerate(("acme\\r\\n", "acme ", " acme", "acme\\t")):
        path = repo_catalog(tmp_path, f"around-{n}.toml", "acme-thing", owner)
        assert ".owner" in refusal(path), owner
    # the same vendor tree with the owner as a plain name loads
    good = repo_catalog(tmp_path, "good.toml", "acme-thing", "acme")
    repo = load_catalog(good).get_repo("acme-thing")
    assert repo is not None and repo.owner == "acme"


def test_ac10_a_date_and_a_dsp_id_are_whole_strings_too(tmp_path):
    # the base branch fails here: its owner pattern lets a final newline by
    path = repo_catalog(tmp_path, "owner.toml", "acme\\n-thing", "acme\\n")
    assert ".owner" in refusal(path)
    old = 'published = "2026-03-01"'
    for n, end in enumerate(("\\n", "\\r\\n", " ")):
        text = document("RFC2222", "ietf")
        assert old in text
        text = text.replace(old, f'published = "2026-03-01{end}"')
        path = write(tmp_path, ietf_catalog(text), f"date-{n}.toml")
        assert ".published" in refusal(path), end
    # a DMTF document's implied listing still takes the whole id, any case
    text = ietf_catalog(document("dsp0240", "mctp"), document("DSP0240x", "mctp"))
    cat = load_catalog(write(tmp_path, text, "dsp.toml"))
    assert cat.get("DSP0236").listing == "dmtf:DSP0236"
    assert cat.get("dsp0240").listing == "dmtf:DSP0240"
    assert cat.get("DSP0240x").listing == ""
