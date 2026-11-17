"""RFCs against the RFC Editor's obsoleted-by list (T81.3): the ``rfc``
listing source, the catalog's ``obsoleted_by``, and what ``check``,
``refresh``, the monthly workflow and a reading command's Freshness Check
print. Synthetic JSON through a scripted client; no network."""

import json

import pytest

from bmc_toolkit.spec import cli
from bmc_toolkit.spec import listing as L
from bmc_toolkit.spec.catalog import CatalogError, load_catalog
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG, ok
from tests.test_catalog_workflow import _run_refresh_block

CHECK_WHEN_DUE = cli._check_when_due

TXT = "https://www.rfc-editor.org/rfc/rfc{n}.txt"
JSON_URL = "https://www.rfc-editor.org/rfc/rfc{n}.json"

RFC_CATALOG = (
    MINI_CATALOG
    + """
[families.ietf]
title = "IETF Requests for Comments"
publisher = "IETF"

[[documents]]
id = "RFC1111"
family = "ietf"
title = "An example protocol"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "March 2026"
url = "https://www.rfc-editor.org/rfc/rfc1111.txt"
type = "txt"
published = "2026-03-01"

[[documents]]
id = "RFC2222"
family = "ietf"
title = "An older protocol"
access = "open"
fetch = "direct"
obsoleted_by = ["RFC3333"]

[[documents.versions]]
version = "May 2001"
url = "https://www.rfc-editor.org/rfc/rfc2222.txt"
type = "txt"
published = "2001-05-01"
"""
)

RFC_TEXT = "Writer\n\n1.  Introduction\n\n   The example protocol is defined here.\n"


def obsoleted(n: int) -> str:
    return (
        f"obsoleted RFC{n}: the RFC Editor lists it as obsoleted by "
        f"RFC4444 ({TXT.format(n=4444)})"
    )


def rfc_json(*ids, status=200, body=None):
    from bmc_toolkit.spec import fetch as fetch_mod

    if body is None:
        body = json.dumps({"doc_id": "RFCx", "obsoleted_by": list(ids)}).encode()
    return fetch_mod.Response(status, {"content-type": "application/json"}, body)


@pytest.fixture
def catalog_file(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(RFC_CATALOG, encoding="utf-8", newline="")
    return path


def run(capsys, catalog_file, *argv):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


# ------------------------------------------------------------- catalog


def test_an_ietf_rfc_gets_the_rfc_listing(catalog_file, capsys):
    cat = load_catalog(catalog_file)
    assert cat.get("RFC1111").listing == "rfc:1111"
    assert cat.get("RFC1111").obsoleted_by == ()
    assert cat.get("RFC2222").obsoleted_by == ("RFC3333",)
    code, out = run(capsys, catalog_file, "catalog", "RFC2222")
    assert code == 0
    assert "listing: rfc:2222" in out
    assert "obsoleted_by: RFC3333" in out
    code, out = run(capsys, catalog_file, "catalog", "RFC1111")
    assert "obsoleted_by" not in out


@pytest.mark.parametrize(
    "value",
    ['"RFC3333"', '["rfc 3333"]', '["RFC3333", "RFC3333"]', '["DSP0236"]', "[1]"],
)
def test_a_malformed_obsoleted_by_does_not_load(tmp_path, value):
    path = tmp_path / "bad.toml"
    path.write_text(
        RFC_CATALOG.replace('obsoleted_by = ["RFC3333"]', f"obsoleted_by = {value}"),
        encoding="utf-8",
        newline="",
    )
    with pytest.raises(CatalogError, match="obsoleted_by"):
        load_catalog(path)


def test_the_shipped_rfc5246_records_its_two_obsoleting_rfcs():
    cat = load_catalog()
    assert cat.get("RFC5246").obsoleted_by == ("RFC8446", "RFC9846")
    ietf = [d for d in cat.documents if d.family == "ietf"]
    assert len(ietf) == 17
    assert all(d.listing == f"rfc:{d.id[3:]}" for d in ietf)
    assert [d.id for d in ietf if d.obsoleted_by] == ["RFC5246"]


# ------------------------------------------------------------- listing


class _Client:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        reply = self.responses.get(url)
        if reply is None:
            raise OSError("no route")
        return reply


def test_the_listing_reads_obsoleted_by_from_the_rfc_json():
    client = _Client({JSON_URL.format(n=1111): rfc_json("RFC 4444", "rfc5555")})
    seen = L.Listings(client).current("rfc:1111")
    assert [(s.version, s.url) for s in seen] == [
        ("RFC4444", TXT.format(n=4444)),
        ("RFC5555", TXT.format(n=5555)),
    ]
    assert client.calls == [JSON_URL.format(n=1111)]
    empty = _Client({JSON_URL.format(n=1): rfc_json()})
    assert L.Listings(empty).current("rfc:1") == []


@pytest.mark.parametrize(
    "reply",
    [
        rfc_json(status=404),
        rfc_json(body=b"<html>not json</html>"),
        rfc_json(body=b'{"doc_id": "RFC1111"}'),
        rfc_json(body=b'{"obsoleted_by": "RFC4444"}'),
    ],
    ids=["404", "not-json", "no-field", "not-a-list"],
)
def test_an_unusable_answer_is_a_listing_error(reply):
    client = _Client({JSON_URL.format(n=1111): reply})
    with pytest.raises(L.ListingError):
        L.Listings(client).current("rfc:1111")


# --------------------------------------------------------------- check


def test_check_names_an_obsoleting_rfc_the_catalog_lacks(
    catalog_file, library, scripted, capsys
):
    scripted.responses[JSON_URL.format(n=1111)] = rfc_json("RFC4444")
    code, out = run(capsys, catalog_file, "check", "RFC1111")
    assert code == 0
    assert out.splitlines()[0] == obsoleted(1111)
    state = json.loads((library.root / "freshness.json").read_text("utf-8"))
    newer = state["documents"]["RFC1111"]["newer"]
    assert [(n["version"], n["url"]) for n in newer] == [
        ("RFC4444", TXT.format(n=4444))
    ]


@pytest.mark.parametrize(
    "ids, expected",
    [
        (["RFC3333"], "current RFC2222 May 2001"),
        ([], "current RFC2222 May 2001"),
        (
            ["RFC3333", "RFC4444"],
            "obsoleted RFC2222: the RFC Editor lists it as obsoleted by "
            f"RFC4444 ({TXT.format(n=4444)})",
        ),
    ],
    ids=["known-only", "none", "known-and-new"],
)
def test_a_recorded_obsoleting_rfc_is_not_reported_again(
    catalog_file, library, scripted, capsys, ids, expected
):
    scripted.responses[JSON_URL.format(n=2222)] = rfc_json(*ids)
    code, out = run(capsys, catalog_file, "check", "RFC2222")
    assert code == 0
    assert out.splitlines()[0] == expected


def test_several_new_obsoleting_rfcs_are_joined(
    catalog_file, library, scripted, capsys
):
    scripted.responses[JSON_URL.format(n=1111)] = rfc_json("RFC4444", "RFC5555")
    code, out = run(capsys, catalog_file, "check", "RFC1111")
    assert out.splitlines()[0] == (
        "obsoleted RFC1111: the RFC Editor lists it as obsoleted by "
        f"RFC4444 ({TXT.format(n=4444)}); RFC5555 ({TXT.format(n=5555)})"
    )


def test_an_unreachable_rfc_json_is_reported_as_unreachable(
    catalog_file, library, scripted, capsys
):
    scripted.responses[JSON_URL.format(n=1111)] = rfc_json(status=404)
    code, out = run(capsys, catalog_file, "check", "RFC1111")
    first = out.splitlines()[0]
    assert first.startswith("unreachable RFC1111: ")
    assert first.count(JSON_URL.format(n=1111)) == 1, first


def test_a_body_that_is_not_json_names_the_url_once():
    url = JSON_URL.format(n=1111)
    client = _Client({url: rfc_json(body=b"<html>not json</html>")})
    with pytest.raises(L.ListingError) as info:
        L.Listings(client).current("rfc:1111")
    assert str(info.value).count(url) == 1, str(info.value)


# ------------------------------------------------------------- refresh

SUMMARY = "summary: add 0, confirm 0, changed 0, unreachable 0, obsoleted {n}"


def test_refresh_prints_the_obsoleted_line_and_counts_it(
    catalog_file, scripted, capsys
):
    scripted.responses[JSON_URL.format(n=1111)] = rfc_json("RFC4444")
    code, out = run(capsys, catalog_file, "refresh", "RFC1111")
    assert code == 0
    assert out.splitlines() == [
        obsoleted(1111),
        SUMMARY.format(n=1) + " (dry run; --write adds them)",
    ]


def test_refresh_of_a_current_rfc_prints_only_the_summary(
    catalog_file, scripted, capsys
):
    scripted.responses[JSON_URL.format(n=2222)] = rfc_json("RFC3333")
    code, out = run(capsys, catalog_file, "refresh", "RFC2222")
    assert out.splitlines() == [SUMMARY.format(n=0) + " (dry run; --write adds them)"]


def test_refresh_write_never_writes_an_obsoleted_rfc(catalog_file, scripted, capsys):
    before = catalog_file.read_bytes()
    scripted.responses[JSON_URL.format(n=1111)] = rfc_json("RFC4444")
    code, out = run(capsys, catalog_file, "refresh", "RFC1111", "--write")
    assert out.splitlines() == [obsoleted(1111), SUMMARY.format(n=1) + ", written 0"]
    assert catalog_file.read_bytes() == before


def test_skip_source_rfc_leaves_the_rfcs_out(catalog_file, scripted, capsys):
    code, out = run(capsys, catalog_file, "refresh", "RFC1111", "--skip-source", "rfc")
    assert code == 2
    assert out.strip() == (
        "RFC1111 is checked against the RFC Editor, which --skip-source rfc leaves out"
    )
    assert scripted.calls == []


def test_a_refresh_without_rfcs_prints_its_summary_as_before(
    catalog_file, scripted, capsys
):
    code, out = run(
        capsys,
        catalog_file,
        "refresh",
        "--skip-source",
        "rfc",
        "--skip-source",
        "dmtf",
        "--skip-source",
        "github",
    )
    assert out.splitlines()[-1] == (
        "summary: add 0, confirm 0, changed 0, unreachable 0 "
        "(dry run; --write adds them)"
    )


def test_the_monthly_workflow_counts_obsoleted_as_a_proposal(tmp_path):
    out = obsoleted(1111) + "\n" + SUMMARY.format(n=1) + " (dry run)\n"
    proc, summary, proposals = _run_refresh_block(tmp_path, out)
    assert proc.returncode == 0
    assert proposals == "1"


# --------------------------------------------- reading Freshness Check


@pytest.fixture
def checking(monkeypatch):
    monkeypatch.setattr(cli, "_check_when_due", CHECK_WHEN_DUE)


def test_a_reading_command_notes_an_obsoleting_rfc(
    catalog_file, library, scripted, checking, capsys
):
    scripted.responses[TXT.format(n=1111)] = ok(RFC_TEXT.encode())
    scripted.responses[JSON_URL.format(n=1111)] = rfc_json("RFC4444")
    code, out = run(capsys, catalog_file, "section", "RFC1111", "Introduction")
    assert code == 0, out
    assert out.splitlines()[-1] == "note: " + obsoleted(1111)
    assert scripted.calls[-1] == JSON_URL.format(n=1111)


def test_offline_stops_the_reading_check_of_an_rfc(
    catalog_file, library, scripted, checking, capsys
):
    scripted.responses[TXT.format(n=1111)] = ok(RFC_TEXT.encode())
    code, out = run(capsys, catalog_file, "fetch", "RFC1111")
    assert code == 0, out
    (library.root / "config.toml").write_text(
        "[library]\noffline = true\n", encoding="utf-8"
    )
    code, out = run(capsys, catalog_file, "section", "RFC1111", "Introduction")
    assert code == 0, out
    assert JSON_URL.format(n=1111) not in scripted.calls
    assert "obsoleted" not in out
