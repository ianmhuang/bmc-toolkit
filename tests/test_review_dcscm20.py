"""Reviewer acceptance tests for fix/dcscm-2-0-direct: DC-SCM Rev 2.0 Ver 1.0
is a Google Drive direct download in the shipped catalog (AC-1), ``fetch``
downloads it through that URL alone (AC-3), and ``refresh`` keeps treating
the wiki's viewer link for that row as nothing to report (AC-4).

Black-box: the shipped catalog through ``load_catalog`` and the CLI through
``bmc_toolkit.spec.cli.main`` with the scripted client from conftest, so no
test reaches the network. AC-2 (the wording of the catalog notes) is
documentation and is not pinned here.
"""

import urllib.parse

import pytest

from bmc_toolkit.spec import fetch as fetch_mod
from bmc_toolkit.spec import listing as L
from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main
from tests.conftest import HTML_BYTES, PDF_BYTES, ok, wayback_miss

DOC = "DC-SCM"
VERSION = "Rev 2.0 Ver 1.0"
FILE_ID = "13BxuseSrKo647hjIXjp087ei8l5QQVb0"
DIRECT_URL = f"https://drive.google.com/uc?export=download&id={FILE_ID}"
VIEWER_URL = f"https://drive.google.com/file/d/{FILE_ID}/view"
WIKI_PAGE = "Server/MHS/DC-SCM-Specs-and-Designs"
WIKI_URL = L.OCP_WIKI.format(page=WIKI_PAGE)

# The OCP wiki table as the catalog's listing reads it: the Rev 2.0 row still
# links the Drive viewer, the Rev 2.2 row links opencompute.org.
WIKI_HTML = f"""
<html><body>
<table class="wikitable"><tbody>
<tr><th>Type</th><th>Description</th><th>Revision</th><th>Submit Date</th>
<th>Contributor</th><th>License</th><th>Notes</th></tr>
<tr><td>Specification</td>
<td><a href="https://www.opencompute.org/documents/ocp-dc-scm-rev2-2-ver1-0-pdf">OCP DC-SCM Rev 2.2 Ver1.0</a></td>
<td>2.2</td><td>October 16, 2025</td><td>Many</td><td>OWFa</td><td></td></tr>
<tr><td>Specification</td>
<td><a href="{VIEWER_URL}">OCP DC-SCM Rev 2.0 Ver1.0</a></td>
<td>2.0</td><td>July 27, 2022</td><td>Many</td><td>OWFa</td><td></td></tr>
</tbody></table>
</body></html>
"""


def _html(text: str) -> fetch_mod.Response:
    return fetch_mod.Response(200, {"content-type": "text/html"}, text.encode())


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


# ----------------------------------------------------------------- AC-1


def test_ac1_rev_2_0_is_the_drive_direct_download(shipped):
    doc = shipped.get(DOC)
    assert doc is not None
    ver = doc.find_version(VERSION)
    assert ver is not None
    assert ver.url == DIRECT_URL
    assert ver.type == "pdf"
    assert ver.published == "2022-07-27"
    assert ver.open and not ver.wip


def test_ac1_rev_2_2_is_still_the_latest(shipped):
    doc = shipped.get(DOC)
    assert doc.latest().version == "Rev 2.2 Ver 1.0"
    assert doc.newest_open().version == "Rev 2.2 Ver 1.0"
    # The direct-download entry sits where its date puts it, between 1.0 and 2.1.
    versions = [v.version for v in doc.versions]
    assert versions.index("Rev 1.0") < versions.index(VERSION)
    assert versions.index(VERSION) < versions.index("Rev 2.1 Ver 1.1")


def test_ac1_catalog_command_prints_the_direct_url(capsys):
    code = main(["catalog", DOC])
    out = capsys.readouterr().out
    assert code == 0, out
    assert DIRECT_URL in out
    assert VIEWER_URL not in out


# ----------------------------------------------------------------- AC-3


def test_ac3_fetch_downloads_rev_2_0_via_direct(library, scripted, capsys):
    scripted.responses[DIRECT_URL] = ok(PDF_BYTES)
    code = main(["fetch", DOC, "--version", VERSION, "--no-extract"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert f"fetched {DOC} {VERSION} via direct" in out
    assert scripted.calls == [DIRECT_URL]
    held = library.find(DOC, VERSION)
    assert held is not None
    assert (held.path / "original.pdf").read_bytes() == PDF_BYTES


def test_ac3_fetch_does_not_touch_the_viewer_link(library, scripted, capsys):
    # A client that only knows the viewer URL: fetch must not ask for it.
    scripted.responses[VIEWER_URL] = ok(PDF_BYTES)
    scripted.responses[fetch_mod.WAYBACK_AVAILABLE + DIRECT_URL] = wayback_miss()
    code = main(["fetch", DOC, "--version", VERSION, "--no-extract"])
    out = capsys.readouterr().out
    assert code != 0, out
    assert VIEWER_URL not in scripted.calls
    assert library.find(DOC, VERSION) is None


def test_ac3_direct_failure_falls_back_to_wayback_of_the_direct_url(
    library, scripted, capsys
):
    # Drive answers with an HTML page (quota, consent): the chain goes on to
    # the Wayback Machine for the same URL and then prints the instruction
    # naming the direct URL, like any other direct document.
    scripted.responses[DIRECT_URL] = ok(HTML_BYTES, "text/html")
    query = fetch_mod.WAYBACK_AVAILABLE + urllib.parse.quote(
        DIRECT_URL, safe=":/?=&"
    )
    scripted.responses[query] = wayback_miss()
    code = main(["fetch", DOC, "--version", VERSION, "--no-extract"])
    out = capsys.readouterr().out
    assert code == 2, out
    assert scripted.calls == [DIRECT_URL, query]
    assert f"  {DOC} {VERSION}: direct: not a pdf" in out
    assert f"  {DOC} {VERSION}: wayback: no Wayback snapshot" in out
    assert f"Open in a browser: {DIRECT_URL}" in out
    assert library.find(DOC, VERSION) is None


def test_ac3_fetch_of_the_latest_is_unchanged(library, scripted, capsys, shipped):
    # The direct-download entry does not become the version a bare fetch picks.
    latest_url = shipped.get(DOC).latest().url
    scripted.responses[latest_url] = ok(PDF_BYTES)
    code = main(["fetch", DOC, "--no-extract"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert f"fetched {DOC} Rev 2.2 Ver 1.0 via direct" in out
    assert scripted.calls == [latest_url]


# ----------------------------------------------------------------- AC-4


def test_ac4_refresh_reports_nothing_for_the_wiki_viewer_row(
    library, scripted, capsys, shipped
):
    # The catalog URL differs from the row's viewer link; an OCP row is
    # never `changed`, and a known version is never `confirm`.
    assert shipped.get(DOC).find_version(VERSION).url != VIEWER_URL
    scripted.responses[WIKI_URL] = _html(WIKI_HTML)
    code = main(["refresh", DOC])
    out = capsys.readouterr().out
    assert code == 0, out
    lines = out.splitlines()
    assert not any(ln.startswith("changed ") for ln in lines), out
    assert not any(ln.startswith(f"confirm {DOC} ") for ln in lines), out
    assert lines[-1].startswith("summary: add 0, confirm 0, changed 0, unreachable 0")
    assert scripted.calls == [WIKI_URL]


def test_ac4_refresh_write_leaves_the_shipped_catalog_alone(
    library, scripted, capsys, tmp_path, shipped
):
    # With --write against a copy of the shipped catalog, nothing is inserted.
    from bmc_toolkit.spec.cli import DEFAULT_CATALOG

    copy = tmp_path / "catalog.toml"
    copy.write_bytes(DEFAULT_CATALOG.read_bytes())
    before = copy.read_bytes()
    scripted.responses[WIKI_URL] = _html(WIKI_HTML)
    code = main(["--catalog", str(copy), "refresh", DOC, "--write"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert copy.read_bytes() == before
    assert load_catalog(copy).get(DOC).find_version(VERSION).url == DIRECT_URL


def test_ac4_check_reports_current_for_the_wiki_viewer_row(
    library, scripted, capsys
):
    scripted.responses[WIKI_URL] = _html(WIKI_HTML)
    code = main(["check", DOC])
    out = capsys.readouterr().out
    assert code == 0, out
    assert f"current {DOC} Rev 2.2 Ver 1.0" in out.splitlines()
    assert not any(ln.startswith("newer ") for ln in out.splitlines()), out
