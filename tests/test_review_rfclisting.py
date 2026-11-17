"""Reviewer acceptance tests for the RFC Editor check (T81.3), part one:
the ``rfc`` listing source and the catalog's ``obsoleted_by`` (AC-1, AC-2),
reading ``rfcN.json`` (AC-3), what ``check`` and a reading command's due
Freshness Check print and record (AC-4), and ``[library] offline`` (AC-7).

Black-box through the CLI and ``Listings`` with a scripted client that
serves synthetic JSON (AC-9); nothing reaches the network. Every test
needs behaviour the base branch lacks: there an RFC has no listing, so it
is ``unchecked`` and no ``rfcN.json`` is ever requested.
"""

import json

import pytest

from bmc_toolkit.spec import cli
from bmc_toolkit.spec import listing as L
from bmc_toolkit.spec.catalog import CatalogError, load_catalog
from bmc_toolkit.spec.fetch import Response
from tests.conftest import MINI_CATALOG, ScriptedClient, ok

# The after-output check as shipped, taken at import time: conftest's
# autouse fixture replaces it with a no-op for every test.
REAL_CHECK = cli._check_when_due

DMTF_PUBLISHED = "https://www.dmtf.org/standards/published_documents"
URL_134 = "https://example.test/DSP0236_1.3.4.pdf"
PUBLISHED_HTML = f"""
<html><body><table><thead><tr>
<th>DSP</th><th>Version</th><th>Title</th><th>Comments</th><th>DSP</th>
</tr></thead><tbody>
<tr><td>DSP0236</td><td>1.3.4</td><td><a href="{URL_134}">MCTP Base</a></td>
<td>Standard</td><td><a href="/dsp/DSP0236">View</a></td></tr>
</tbody></table></body></html>
"""


def json_url(n) -> str:
    return f"https://www.rfc-editor.org/rfc/rfc{n}.json"


def txt_url(n) -> str:
    return f"https://www.rfc-editor.org/rfc/rfc{n}.txt"


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
url = "https://www.rfc-editor.org/rfc/{doc_id.lower()}.txt"
type = "txt"
published = "2026-03-01"
"""


KNOWN = 'obsoleted_by = ["RFC3333", "RFC5555"]'

# RFC1111 records no obsoleting RFC; RFC2222 records two.
RFC_CATALOG = (
    MINI_CATALOG
    + """
[families.ietf]
title = "IETF Requests for Comments"
publisher = "IETF"
"""
    + document("RFC1111", "ietf")
    + document("RFC2222", "ietf", KNOWN)
)

RFC_BODY = "\n".join(
    [
        "Network Working Group                                         A. Writer",
        "Request for Comments: 1111                                     Example",
        "",
        "1.  Introduction",
        "",
        "   The zebra protocol is defined here.",
        "",
    ]
).encode("utf-8")


def sentence(doc_id: str, *obsoleting: int) -> str:
    """AC-4's line: several obsoleting RFCs joined by ``; ``."""
    listed = "; ".join(f"RFC{n} ({txt_url(n)})" for n in obsoleting)
    return f"obsoleted {doc_id}: the RFC Editor lists it as obsoleted by {listed}"


def rfc_json(*ids) -> Response:
    """A synthetic rfcN.json: the fields around ``obsoleted_by`` are made up."""
    body = {"doc_id": "RFC0000", "title": "synthetic", "obsoleted_by": list(ids)}
    return ok(json.dumps(body).encode("utf-8"), "application/json")


def write(tmp_path, text: str, name: str = "catalog.toml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8", newline="")
    return path


@pytest.fixture
def rfc_catalog(tmp_path):
    return write(tmp_path, RFC_CATALOG)


@pytest.fixture
def checking(monkeypatch):
    """The after-output Freshness Check, on."""
    monkeypatch.setattr(cli, "_check_when_due", REAL_CHECK)


def run(capsys, catalog, *argv):
    code = cli.main(["--catalog", str(catalog), *argv])
    return code, capsys.readouterr().out


def freshness(library) -> dict:
    return json.loads((library.root / "freshness.json").read_text("utf-8"))


# ----------------------------------------------------------------- AC-1


def test_ac1_an_ietf_rfc_defaults_to_the_rfc_listing_unless_it_names_another(
    tmp_path, library, capsys
):
    path = write(
        tmp_path,
        RFC_CATALOG
        + document("RFC6666", "ietf", 'listing = "nvme:zebra-specification"')
        + document("BCP14", "ietf")
        + document("RFC8888", "vendor")
        + document("ZEBRA", "vendor", 'listing = "rfc:9110"'),
    )
    cat = load_catalog(path)
    rfc = cat.get("RFC1111")
    assert rfc.listing == "rfc:1111"
    assert (rfc.listing_source, rfc.listing_key) == ("rfc", "1111")
    assert cat.get("RFC2222").listing == "rfc:2222"
    # it names another: kept as written
    assert cat.get("RFC6666").listing == "nvme:zebra-specification"
    # not "RFC followed by digits", or not a family whose publisher is IETF
    assert cat.get("BCP14").listing == ""
    assert cat.get("RFC8888").listing == ""
    # rfc is a listing source a document can name
    assert cat.get("ZEBRA").listing == "rfc:9110"
    # the DMTF default is what it was
    assert cat.get("DSP0236").listing == "dmtf:DSP0236"
    code, out = run(capsys, path, "catalog", "RFC1111")
    assert code == 0, out
    assert "listing: rfc:1111" in out.splitlines()


def test_ac1_the_shipped_catalog_shows_the_listing_of_rfc9110(library, capsys):
    code = cli.main(["catalog", "RFC9110"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "listing: rfc:9110" in out.splitlines()


def test_ac1_the_source_is_named_the_rfc_editor_in_the_fetch_reminder(
    rfc_catalog, library, scripted, capsys
):
    # fetch never reads a listing: its note is the reminder to run check,
    # which names the publisher of the document's listing source
    scripted.responses[txt_url(1111)] = ok(RFC_BODY, "text/plain; charset=utf-8")
    code, out = run(capsys, rfc_catalog, "fetch", "RFC1111")
    assert code == 0, out
    assert (
        "note: RFC1111 has never been checked against the RFC Editor; "
        "run: bmcspec check RFC1111"
    ) in out.splitlines()
    assert json_url(1111) not in scripted.calls


# ----------------------------------------------------------------- AC-2


def test_ac2_obsoleted_by_is_loaded_and_printed_when_not_empty(
    rfc_catalog, library, capsys
):
    cat = load_catalog(rfc_catalog)
    assert tuple(cat.get("RFC2222").obsoleted_by) == ("RFC3333", "RFC5555")
    assert tuple(cat.get("RFC1111").obsoleted_by) == ()
    code, out = run(capsys, rfc_catalog, "catalog", "RFC2222")
    assert code == 0, out
    assert any(
        "obsoleted_by" in ln and "RFC3333" in ln and "RFC5555" in ln
        for ln in out.splitlines()
    ), out
    code, out = run(capsys, rfc_catalog, "catalog", "RFC1111")
    assert code == 0, out
    assert "obsoleted_by" not in out


def test_ac2_an_empty_list_loads_like_no_list(tmp_path, library, capsys):
    path = write(tmp_path, RFC_CATALOG.replace(KNOWN, "obsoleted_by = []"))
    assert tuple(load_catalog(path).get("RFC2222").obsoleted_by) == ()
    code, out = run(capsys, path, "catalog", "RFC2222")
    assert code == 0, out
    assert "obsoleted_by" not in out


@pytest.mark.parametrize(
    "value",
    [
        '"RFC3333"',
        '["rfc3333"]',
        '["RFC 3333"]',
        '["RFC"]',
        '["3333"]',
        '["DSP0236"]',
        "[3333]",
        '["RFC3333", ""]',
        '["RFC3333", "RFC5555", "RFC3333"]',
    ],
    ids=[
        "a-string",
        "lowercase",
        "with-a-space",
        "no-digits",
        "digits-only",
        "not-an-rfc",
        "an-integer",
        "an-empty-id",
        "listed-twice",
    ],
)
def test_ac2_anything_else_is_a_catalog_error_naming_the_field(
    tmp_path, library, capsys, value
):
    assert KNOWN in RFC_CATALOG
    path = write(tmp_path, RFC_CATALOG.replace(KNOWN, f"obsoleted_by = {value}"))
    with pytest.raises(CatalogError, match="obsoleted_by"):
        load_catalog(path)
    # through the CLI: a message, not a traceback
    code, out = run(capsys, path, "catalog", "RFC2222")
    assert code != 0, out
    assert "obsoleted_by" in out and "Traceback" not in out


def test_ac2_the_shipped_rfc5246_records_rfc8446_and_rfc9846_and_no_other_does():
    cat = load_catalog()
    assert tuple(cat.get("RFC5246").obsoleted_by) == ("RFC8446", "RFC9846")
    ietf = [d for d in cat.documents if d.family == "ietf"]
    assert ietf, "the shipped catalog has an ietf family"
    assert [d.id for d in ietf if d.obsoleted_by] == ["RFC5246"]
    for doc in ietf:
        assert doc.listing == f"rfc:{doc.id.removeprefix('RFC')}", doc.id


# ----------------------------------------------------------------- AC-3


def test_ac3_reading_the_listing_is_one_get_and_the_ids_are_normalised():
    client = ScriptedClient(
        {json_url(1111): rfc_json("RFC 9846", "rfc8446", " Rfc 7777 ")}
    )
    seen = L.Listings(client).current("rfc:1111")
    assert [(s.version, s.url) for s in seen] == [
        ("RFC9846", txt_url(9846)),
        ("RFC8446", txt_url(8446)),
        ("RFC7777", txt_url(7777)),
    ]
    assert client.calls == [json_url(1111)]


def test_ac3_an_empty_obsoleted_by_lists_nothing():
    client = ScriptedClient({json_url(1111): rfc_json()})
    assert L.Listings(client).current("rfc:1111") == []
    assert client.calls == [json_url(1111)]


UNUSABLE = {
    "http-404": Response(404, {"content-type": "text/html"}, b"Not Found"),
    "http-503": Response(503, {}, b""),
    "no-route": None,
    "empty-body": ok(b"", "application/json"),
    "not-json": ok(b"<html><body>Not Found</body></html>", "text/html"),
    "not-utf-8": ok(b"\xff\xfe{", "application/json"),
    "no-field": ok(b'{"doc_id": "RFC1111"}', "application/json"),
    "null-field": ok(b'{"doc_id": "RFC1111", "obsoleted_by": null}'),
    "a-string-field": ok(b'{"obsoleted_by": "RFC4444"}', "application/json"),
    "a-top-level-list": ok(b'["RFC4444"]', "application/json"),
}


@pytest.mark.parametrize("case", sorted(UNUSABLE))
def test_ac3_an_unusable_answer_makes_the_document_unreachable_with_the_reason(
    rfc_catalog, library, scripted, capsys, case
):
    if UNUSABLE[case] is not None:
        scripted.responses[json_url(1111)] = UNUSABLE[case]
    code, out = run(capsys, rfc_catalog, "check", "RFC1111")
    assert code == 0, out
    assert "Traceback" not in out
    lines = out.splitlines()
    assert lines[0].startswith("unreachable RFC1111: "), out
    assert lines[0].removeprefix("unreachable RFC1111: ").strip(), out
    assert not any(ln.startswith(("obsoleted ", "current ")) for ln in lines), out
    assert lines[-1] == "summary: current 0, newer 0, unreachable 1"
    assert scripted.calls == [json_url(1111)]
    entry = freshness(library)["documents"]["RFC1111"]
    assert entry["problem"] and entry["newer"] == []


# ----------------------------------------------------------------- AC-4


def test_ac4_check_names_the_obsoleting_rfc_and_records_it_like_a_newer_version(
    rfc_catalog, library, scripted, capsys
):
    scripted.responses[json_url(1111)] = rfc_json("RFC4444")
    code, out = run(capsys, rfc_catalog, "check", "RFC1111")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == (
        "obsoleted RFC1111: the RFC Editor lists it as obsoleted by RFC4444 "
        "(https://www.rfc-editor.org/rfc/rfc4444.txt)"
    )
    assert lines[-1] == "summary: current 0, newer 1, unreachable 0"
    assert scripted.calls == [json_url(1111)]
    entry = freshness(library)["documents"]["RFC1111"]
    assert entry["problem"] == ""
    assert entry["catalog_latest"] == "March 2026"
    assert [(n["version"], n["url"]) for n in entry["newer"]] == [
        ("RFC4444", txt_url(4444))
    ]


def test_ac4_several_new_obsoleting_rfcs_are_joined(
    rfc_catalog, library, scripted, capsys
):
    scripted.responses[json_url(1111)] = rfc_json("RFC4444", "RFC 6666")
    code, out = run(capsys, rfc_catalog, "check", "RFC1111")
    assert code == 0, out
    assert out.splitlines()[0] == sentence("RFC1111", 4444, 6666)
    assert out.splitlines()[-1] == "summary: current 0, newer 1, unreachable 0"
    newer = freshness(library)["documents"]["RFC1111"]["newer"]
    assert [n["version"] for n in newer] == ["RFC4444", "RFC6666"]


@pytest.mark.parametrize(
    "ids",
    [
        [],
        ["RFC3333"],
        ["RFC3333", "RFC5555"],
        ["rfc 3333", " RFC5555"],
    ],
    ids=["none", "one-known", "both-known", "known-in-another-spelling"],
)
def test_ac4_an_rfc_with_no_new_obsoleting_rfc_is_current(
    rfc_catalog, library, scripted, capsys, ids
):
    scripted.responses[json_url(2222)] = rfc_json(*ids)
    code, out = run(capsys, rfc_catalog, "check", "RFC2222")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == "current RFC2222 March 2026"
    assert lines[-1] == "summary: current 1, newer 0, unreachable 0"
    assert "obsoleted" not in out
    assert freshness(library)["documents"]["RFC2222"]["newer"] == []


def test_ac4_a_recorded_obsoleting_rfc_is_not_reported_again_beside_a_new_one(
    rfc_catalog, library, scripted, capsys
):
    scripted.responses[json_url(2222)] = rfc_json(
        "RFC3333", "RFC 4444", "RFC5555", "rfc6666"
    )
    code, out = run(capsys, rfc_catalog, "check", "RFC2222")
    assert code == 0, out
    assert out.splitlines()[0] == sentence("RFC2222", 4444, 6666)
    newer = freshness(library)["documents"]["RFC2222"]["newer"]
    assert [n["version"] for n in newer] == ["RFC4444", "RFC6666"]


def test_ac4_ac7_check_over_every_document_counts_the_rfc_and_keeps_the_dmtf_line(
    rfc_catalog, library, scripted, capsys
):
    scripted.responses[DMTF_PUBLISHED] = ok(PUBLISHED_HTML.encode(), "text/html")
    scripted.responses[json_url(1111)] = rfc_json("RFC4444")
    scripted.responses[json_url(2222)] = rfc_json("RFC3333")
    code, out = run(capsys, rfc_catalog, "check")
    assert code == 0, out
    lines = out.splitlines()
    # DMTF prints exactly what it printed before the RFC check existed
    assert (
        f"newer DSP0236: catalog latest 1.3.3, DMTF lists 1.3.4 {URL_134}"
    ) in lines, out
    assert sentence("RFC1111", 4444) in lines
    assert "current RFC2222 March 2026" in lines
    # the RFCs are checked, so they are no longer among the unchecked
    assert "unchecked: IPMI, BUNDLE (no publisher listing)" in lines, out
    assert lines[-1] == "summary: current 1, newer 2, unreachable 0, unchecked 3"
    assert sorted(scripted.calls) == sorted(
        [DMTF_PUBLISHED, json_url(1111), json_url(2222)]
    )


def test_ac4_a_reading_command_notes_the_obsoleting_rfc_once_per_period(
    rfc_catalog, library, scripted, checking, capsys
):
    scripted.responses[txt_url(1111)] = ok(RFC_BODY, "text/plain; charset=utf-8")
    scripted.responses[json_url(1111)] = rfc_json("RFC4444")
    code, out = run(capsys, rfc_catalog, "find", "RFC1111", "zebra")
    assert code == 0, out
    lines = out.splitlines()
    assert any("zebra" in ln for ln in lines[:-1]), out
    # after the answer, the same sentence as check behind "note: "
    assert lines[-1] == "note: " + sentence("RFC1111", 4444)
    assert scripted.calls.count(json_url(1111)) == 1
    assert scripted.calls[-1] == json_url(1111)
    newer = freshness(library)["documents"]["RFC1111"]["newer"]
    assert [(n["version"], n["url"]) for n in newer] == [("RFC4444", txt_url(4444))]
    # recorded like check: the next question within the age asks nobody
    code, out = run(capsys, rfc_catalog, "find", "RFC1111", "zebra")
    assert code == 0, out
    assert "note:" not in out
    assert scripted.calls.count(json_url(1111)) == 1
    # reported, never acted on
    assert txt_url(4444) not in scripted.calls


def test_ac4_a_reading_command_says_nothing_of_a_current_rfc_and_notes_a_failure(
    rfc_catalog, library, scripted, checking, capsys
):
    scripted.responses[txt_url(2222)] = ok(RFC_BODY, "text/plain; charset=utf-8")
    scripted.responses[json_url(2222)] = rfc_json("RFC5555", "RFC3333")
    code, out = run(capsys, rfc_catalog, "find", "RFC2222", "zebra")
    assert code == 0, out
    assert "note:" not in out and "obsoleted" not in out
    assert scripted.calls.count(json_url(2222)) == 1
    # RFC1111's JSON is not JSON: a note, and the exit code stays 0
    scripted.responses[txt_url(1111)] = ok(RFC_BODY, "text/plain; charset=utf-8")
    scripted.responses[json_url(1111)] = ok(b"<html>busy</html>", "text/html")
    code, out = run(capsys, rfc_catalog, "find", "RFC1111", "zebra")
    assert code == 0, out
    assert out.splitlines()[-1].startswith("note: unreachable RFC1111: ")
    assert "Traceback" not in out


# ----------------------------------------------------------------- AC-7


def test_ac7_offline_stops_the_reading_commands_rfc_check(
    rfc_catalog, library, scripted, checking, capsys
):
    scripted.responses[txt_url(1111)] = ok(RFC_BODY, "text/plain; charset=utf-8")
    scripted.responses[json_url(1111)] = rfc_json("RFC4444")
    # control: online, the due check asks the RFC Editor
    code, out = run(capsys, rfc_catalog, "find", "RFC1111", "zebra")
    assert code == 0, out
    assert out.splitlines()[-1] == "note: " + sentence("RFC1111", 4444)
    assert scripted.calls.count(json_url(1111)) == 1
    # due again (never checked), but offline: no request, no note, no record
    (library.root / "freshness.json").unlink()
    (library.root / "config.toml").write_text(
        "[library]\noffline = true\n", encoding="utf-8", newline=""
    )
    code, out = run(capsys, rfc_catalog, "find", "RFC1111", "zebra")
    assert code == 0, out
    assert any("zebra" in ln for ln in out.splitlines()), out
    assert "note:" not in out and "obsoleted" not in out
    assert scripted.calls.count(json_url(1111)) == 1
    if (library.root / "freshness.json").exists():
        entry = freshness(library)["documents"].get("RFC1111", {})
        assert "checked_at" not in entry
    # check is the user asking for the network: it ignores the key
    code, out = run(capsys, rfc_catalog, "check", "RFC1111")
    assert code == 0, out
    assert out.splitlines()[0] == sentence("RFC1111", 4444)
    assert scripted.calls.count(json_url(1111)) == 2
