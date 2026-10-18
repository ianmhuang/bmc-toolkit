"""Reviewer acceptance tests for the OCP listing move (T44): the eight OCP
documents are read from the opencompute.org project pages that replaced
the retired MediaWiki. Black-box through the shipped catalog, ``Listings``
and the CLI with a scripted client; no network."""

import re

import pytest

from bmc_toolkit.spec import listing as L
from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main
from bmc_toolkit.spec.fetch import Response
from tests.conftest import ScriptedClient

DCSCM_PAGE = "server/data-center-secure-container-module"
MHS_PAGE = "server/mhs/dc-mhs-specs-and-designs"
DCSCM_URL = f"https://www.opencompute.org/projects/{DCSCM_PAGE}/"
MHS_URL = f"https://www.opencompute.org/projects/{MHS_PAGE}/"
OLD_WIKI_URL = (
    "https://www.opencompute.org/w/index.php?title=Server/MHS/DC-MHS-Specs-and-Designs"
)

MHS_IDS = ["M-CRPS", "M-PIC", "M-XIO", "M-DNO", "M-FLW", "M-PESTI", "M-SDNO"]
OCP_IDS = ["DC-SCM", *MHS_IDS]


def _html(text: str) -> Response:
    return Response(200, {"content-type": "text/html"}, text.encode())


def _mhs_page(versions: dict[str, str]) -> str:
    """The DC-MHS specs-and-designs table with one row per M-* document at
    the given version, plus the row the live page carries with an empty
    description (``v0.70``), which must match no catalog prefix."""
    rows = "".join(
        f"<tr><td>Specification</td><td>{doc_id} Base Specification</td>"
        f"<td>{version}</td><td>4/24/26</td><td>Someone</td>"
        f'<td><a href="https://drive.google.com/file/d/{doc_id.lower()}/view">Link</a>'
        "</td><td></td></tr>"
        for doc_id, version in versions.items()
    )
    empty = (
        "<tr><td>Specification</td><td></td><td>v0.70</td><td>10/11/26</td>"
        '<td>Someone</td><td><a href="https://drive.google.com/file/d/x/view">Link</a>'
        "</td><td></td></tr>"
    )
    return (
        "<html><body><h3>Latest Base Specs</h3><table><tbody>"
        "<tr><th>Type</th><th>Description</th><th>Version</th><th>Submit Date</th>"
        "<th>Contributor</th><th>Link</th><th>Notes</th></tr>"
        f"{rows}{empty}</tbody></table></body></html>"
    )


def _dcscm_page(revision: str) -> str:
    return (
        "<html><body><table><tbody>"
        "<tr><th>Type</th><th>Description</th><th>Revision</th><th>Submit Date</th>"
        "<th>Contributor</th><th>License</th><th>Notes</th></tr>"
        "<tr><td>Specification</td>"
        '<td><a href="https://drive.google.com/file/d/scm/view">OCP DC-SCM Rev 2.2 Ver1.0</a>'
        f"<br/>OCP DC-SCM LTPI Rev1.2</td><td>{revision}</td><td>October 16, 2025</td>"
        "<td>Many</td><td>OWFa</td><td></td></tr>"
        "</tbody></table></body></html>"
    )


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


def _serve_catalog_versions(client: ScriptedClient, shipped) -> None:
    """Both project pages, each row at the version the shipped catalog
    holds as latest, so every document is ``current``."""
    mhs = {doc_id: shipped.get(doc_id).latest().version for doc_id in MHS_IDS}
    client.responses[MHS_URL] = _html(_mhs_page(mhs))
    client.responses[DCSCM_URL] = _html(
        _dcscm_page(shipped.get("DC-SCM").latest().version)
    )


# ------------------------------------------------ AC-1: keys and template


def test_shipped_ocp_listing_keys_name_the_two_project_pages(shipped):
    ocp = [d for d in shipped.documents if d.listing_source == "ocp"]
    assert sorted(d.id for d in ocp) == sorted(OCP_IDS)
    pages = {}
    for doc in ocp:
        page, sep, prefix = doc.listing_key.partition("|")
        assert sep == "|" and prefix, doc.id
        assert "index.php" not in doc.listing and "Server/MHS" not in doc.listing
        pages[doc.id] = page
    assert pages["DC-SCM"] == DCSCM_PAGE
    assert all(pages[doc_id] == MHS_PAGE for doc_id in MHS_IDS), pages
    assert shipped.get("DC-SCM").listing_key.endswith("|OCP DC-SCM")
    for doc_id in MHS_IDS:
        assert shipped.get(doc_id).listing_key.endswith(f"|{doc_id} Base")


def test_template_yields_the_project_page_urls_for_the_catalog_keys():
    assert L.OCP_WIKI.format(page=DCSCM_PAGE) == DCSCM_URL
    assert L.OCP_WIKI.format(page=MHS_PAGE) == MHS_URL
    assert "index.php" not in L.OCP_WIKI and "?" not in L.OCP_WIKI


def test_listings_request_the_project_page_and_not_the_old_wiki_url():
    client = ScriptedClient(
        {MHS_URL: _html(_mhs_page({"M-CRPS": "1.06"}))}
    )
    rows = L.Listings(client).current(f"ocp:{MHS_PAGE}|M-CRPS Base")
    assert [r.version for r in rows] == ["1.06"]
    assert rows[0].published == "2026-04-24"
    assert rows[0].url == "https://drive.google.com/file/d/m-crps/view"
    assert client.calls == [MHS_URL]

    # A server that still answers only the old wiki address is not consulted.
    old_only = ScriptedClient({OLD_WIKI_URL: _html(_mhs_page({"M-CRPS": "1.06"}))})
    with pytest.raises(L.ListingError, match="no route to"):
        L.Listings(old_only).current(f"ocp:{MHS_PAGE}|M-CRPS Base")
    assert OLD_WIKI_URL not in old_only.calls


# ------------------------------------------------ AC-3: user-facing words


def test_missing_row_message_names_the_ocp_page_not_a_wiki():
    client = ScriptedClient({MHS_URL: _html(_mhs_page({"M-CRPS": "1.06"}))})
    with pytest.raises(L.ListingError) as info:
        L.Listings(client).current(f"ocp:{MHS_PAGE}|M-ZZZ Base")
    message = str(info.value)
    assert "no row starting with 'M-ZZZ Base'" in message
    assert f"on OCP page {MHS_PAGE}" in message
    assert "wiki" not in message.lower()


def test_publisher_name_for_ocp_is_the_project_page(tmp_path, library, scripted, capsys):
    assert "wiki" not in L.PUBLISHER_NAMES["ocp"].lower()
    assert "project page" in L.PUBLISHER_NAMES["ocp"]
    text = (
        "schema_version = 1\n\n"
        '[families.ocp]\ntitle = "OCP"\npublisher = "Open Compute Project"\n\n'
        '[[documents]]\nid = "M-CRPS"\nfamily = "ocp"\n'
        'title = "M-CRPS Base Specification"\naccess = "open"\nfetch = "direct"\n'
        f'listing = "ocp:{MHS_PAGE}|M-CRPS Base"\n\n'
        '[[documents.versions]]\nversion = "R1 v1.0 RC4"\n'
        'url = "https://example.test/m-crps-r1-v1p0-rc4.pdf"\n'
        'type = "pdf"\npublished = "2023-01-01"\n'
    )
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    scripted.responses[MHS_URL] = _html(_mhs_page({"M-CRPS": "1.06"}))
    code = main(["--catalog", str(path), "check", "M-CRPS"])
    out = capsys.readouterr().out
    assert code == 0, out
    first = out.splitlines()[0]
    assert first.startswith("newer M-CRPS: catalog latest R1 v1.0 RC4, "), first
    assert re.search(r"the OCP project pages? lists 1\.06 \(2026-04-24\)", first), first
    assert "wiki" not in out.lower()


# ------------------------- AC-1 / offline analogue of AC-2: check and refresh


@pytest.mark.parametrize("doc_id", OCP_IDS)
def test_check_each_shipped_ocp_document_is_current_from_its_project_page(
    doc_id, shipped, library, scripted, capsys
):
    _serve_catalog_versions(scripted, shipped)
    code = main(["check", doc_id])
    out = capsys.readouterr().out
    assert code == 0, out
    latest = shipped.get(doc_id).latest().version
    assert out.splitlines()[0] == f"current {doc_id} {latest}", out
    assert out.splitlines()[-1] == "summary: current 1, newer 0, unreachable 0", out
    expected = DCSCM_URL if doc_id == "DC-SCM" else MHS_URL
    assert scripted.calls == [expected]


def test_check_all_ocp_documents_reads_each_project_page_once(
    shipped, library, scripted, capsys
):
    # Every other listing is unreachable on purpose: only the OCP lines matter.
    _serve_catalog_versions(scripted, shipped)
    code = main(["check"])
    out = capsys.readouterr().out
    assert code == 0, out
    lines = out.splitlines()
    for doc_id in OCP_IDS:
        latest = shipped.get(doc_id).latest().version
        assert f"current {doc_id} {latest}" in lines, doc_id
    unreachable_ocp = [
        ln
        for ln in lines
        if ln.startswith("unreachable ") and ln.split()[1].rstrip(":") in OCP_IDS
    ]
    assert unreachable_ocp == [], out
    assert scripted.calls.count(MHS_URL) == 1
    assert scripted.calls.count(DCSCM_URL) == 1
    assert OLD_WIKI_URL not in scripted.calls


def test_refresh_over_ocp_reports_nothing_unreachable_and_ignores_the_empty_row(
    shipped, library, scripted, capsys
):
    _serve_catalog_versions(scripted, shipped)
    code = main(["refresh", "--skip-source", "dmtf", "--skip-source", "nvme"])
    out = capsys.readouterr().out
    assert code == 0, out
    lines = out.splitlines()
    assert not any(ln.startswith("unreachable ") for ln in lines), out
    assert "0.70" not in out  # the empty-description row matches no prefix
    assert lines[-1].startswith("summary: add 0, confirm 0, changed 0, unreachable 0"), out
    assert sorted(set(scripted.calls)) == sorted([DCSCM_URL, MHS_URL])
