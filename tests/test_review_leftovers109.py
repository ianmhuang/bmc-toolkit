"""Acceptance tests for the PR #109 leftovers change.

AC-1: ``bmc_toolkit.spec.listing`` no longer carries ``parse_dmtf_titles``,
neither as an attribute nor in ``__all__``, and every name ``__all__`` still
lists resolves.
AC-2: the published-documents page still gives the same versions, URLs and
titles through ``parse_dmtf_published`` and ``Listings.dmtf_published``.
"""

import importlib

import pytest

from bmc_toolkit.spec import listing as L
from tests.conftest import ScriptedClient, ok

FILES = "https://www.dmtf.org/sites/default/files/standards/documents"

PUBLISHED_HTML = """
<html><body>
<table><thead><tr>
<th>DSP </th><th>Version </th><th>Title </th><th>Comments </th><th>DSP </th>
</tr></thead><tbody>
<tr><td> DSP0236 </td><td> 1.3.3 </td>
<td><a href="/sites/default/files/standards/documents/DSP0236_1.3.3.pdf">
MCTP Base Specification</a></td>
<td> Standard </td><td><a href="/dsp/DSP0236">View</a></td></tr>
<tr><td> DSP0274 </td><td> 1.3.2 </td>
<td><a href="/sites/default/files/standards/documents/DSP0274_1.3.2.pdf">
Security Protocol and Data Model</a></td>
<td> Standard </td><td><a href="/dsp/DSP0274">View</a></td></tr>
<tr><td> </td><td> </td><td>a row without a DSP id</td><td></td><td></td></tr>
<tr><td> DSP0999 </td><td> </td><td>a row without a version</td><td></td>
<td></td></tr>
</tbody></table>
<table><tr><th>Other</th><th>Table</th></tr><tr><td>1</td><td>2</td></tr></table>
</body></html>
"""

NO_ROWS_HTML = """
<html><body>
<table><tr><th>Other</th><th>Table</th></tr><tr><td>1</td><td>2</td></tr></table>
</body></html>
"""

EXPECTED = {
    "DSP0236": (
        L.Seen("1.3.3", f"{FILES}/DSP0236_1.3.3.pdf"),
        "MCTP Base Specification",
    ),
    "DSP0274": (
        L.Seen("1.3.2", f"{FILES}/DSP0274_1.3.2.pdf"),
        "Security Protocol and Data Model",
    ),
}


def _listings(html):
    client = ScriptedClient({L.DMTF_PUBLISHED: ok(html.encode(), "text/html")})
    return L.Listings(client), client


# ---------------------------------------------------------------- AC-1


def test_parse_dmtf_titles_is_gone_from_the_module():
    assert not hasattr(L, "parse_dmtf_titles")


def test_parse_dmtf_titles_is_gone_from_all():
    assert "parse_dmtf_titles" not in L.__all__


def test_every_exported_name_is_an_attribute():
    assert [name for name in L.__all__ if not hasattr(L, name)] == []


def test_star_import_resolves_and_omits_the_removed_name():
    namespace = {}
    exec("from bmc_toolkit.spec.listing import *", namespace)
    assert "parse_dmtf_titles" not in namespace
    assert "parse_dmtf_published" in namespace
    assert "Listings" in namespace


def test_all_lists_no_name_twice():
    assert len(L.__all__) == len(set(L.__all__))


@pytest.mark.parametrize(
    "module", ["bmc_toolkit.spec.refresh", "bmc_toolkit.spec.freshness"]
)
def test_modules_that_read_listing_still_import(module):
    # Both import names from the listing module; neither may have relied on
    # the removed one.
    assert importlib.import_module(module) is not None


# ---------------------------------------------------------------- AC-2


def test_parse_dmtf_published_gives_the_same_versions():
    table = L.parse_dmtf_published(PUBLISHED_HTML)
    assert table == {dsp: seen for dsp, (seen, _) in EXPECTED.items()}


def test_parse_dmtf_published_on_a_page_without_dsp_rows_is_empty():
    assert L.parse_dmtf_published(NO_ROWS_HTML) == {}
    assert L.parse_dmtf_published("") == {}


def test_listings_dmtf_published_gives_versions_and_titles():
    listings, _ = _listings(PUBLISHED_HTML)
    assert listings.dmtf_published() == EXPECTED


def test_listings_dmtf_published_agrees_with_the_parser_and_current():
    listings, client = _listings(PUBLISHED_HTML)
    rows = listings.dmtf_published()
    parsed = L.parse_dmtf_published(PUBLISHED_HTML)
    assert {dsp: seen for dsp, (seen, _) in rows.items()} == parsed
    assert listings.current("dmtf:DSP0274") == [parsed["DSP0274"]]
    assert client.calls.count(L.DMTF_PUBLISHED) == 1


def test_listings_dmtf_published_without_dsp_rows_is_an_error():
    listings, _ = _listings(NO_ROWS_HTML)
    with pytest.raises(L.ListingError):
        listings.dmtf_published()


def test_listings_dmtf_published_reports_a_transport_failure():
    listings = L.Listings(ScriptedClient({}))
    with pytest.raises(L.ListingError):
        listings.dmtf_published()
