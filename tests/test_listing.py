"""Publisher listing parsers on hand-written pages shaped like the real ones,
and the version-in-URL parsers over the shipped catalog."""

import json
import re

import pytest

from bmc_toolkit.spec import listing as L
from bmc_toolkit.spec.catalog import load_catalog
from tests.conftest import ScriptedClient

DMTF_PUBLISHED_HTML = """
<html><body>
<table class="views-table"><thead><tr>
<th>DSP </th><th>Version </th><th>Title </th><th>Comments </th><th>DSP </th>
</tr></thead><tbody>
<tr><td> DSP0236 </td><td> 1.3.3 </td>
<td><a href="/sites/default/files/standards/documents/DSP0236_1.3.3.pdf">MCTP Base</a></td>
<td> Standard </td><td><a href="/dsp/DSP0236">View</a></td></tr>
<tr><td> DSP8010 </td><td> 2026.1 </td>
<td><a href="/sites/default/files/standards/documents/DSP8010_2026.1.zip">Redfish Schema Bundle</a></td>
<td> Standard </td><td><a href="/dsp/DSP8010">View</a></td></tr>
<tr><td> </td><td> </td><td>a row without a DSP</td><td></td><td></td></tr>
</tbody></table>
<table><tr><th>Unrelated</th><th>Table</th></tr><tr><td>1</td><td>2</td></tr></table>
</body></html>
"""

DMTF_DSP_HTML = """
<html><body><h1>All Published Versions of DSP0236</h1>
<table class="views-table"><thead><tr>
<th>Version </th><th>Title </th><th>Publication Date </th><th>Comments </th>
</tr></thead><tbody>
<tr><td> 1.3.4 </td>
<td><a href="/sites/default/files/standards/documents/DSP0236_1.3.4.pdf">MCTP Base</a></td>
<td> 3 Aug 2026 </td><td> Standard </td></tr>
<tr><td> 1.3.3 </td>
<td><a href="/sites/default/files/standards/documents/DSP0236_1.3.3_0.pdf">MCTP Base</a></td>
<td> 25 Mar 2024 </td><td> Standard </td></tr>
<tr><td> 1.4.0 </td>
<td><a href="/sites/default/files/standards/documents/DSP0236_1.4.0_WIP.pdf">MCTP Base</a></td>
<td> 1 Jan 2027 </td><td> Work in Progress </td></tr>
</tbody></table></body></html>
"""

NVME_JSON = json.dumps(
    {
        "posts": [
            {
                "slug": "nvm-express-base-specification",
                "post_title": "NVM Express® Base Specification",
                "file": {
                    "url": "https://nvmexpress.org/wp-content/uploads/"
                    "NVM-Express-Base-Specification-Revision-2.4-Ratified-2026.07.31.pdf"
                },
            },
            {
                "slug": "nvme-mi-specification",
                "post_title": "NVM Express Management Interface Specification",
                "file": {
                    "url": "https://nvmexpress.org/wp-content/uploads/"
                    "NVM-Express-Management-Interface-Specification-Revision-2.2-"
                    "Ratified-2026.07.31.pdf"
                },
            },
            {"slug": "no-file", "post_title": "x", "file": None},
            "not a post",
        ],
        "types": {},
    }
)

OCP_WIKI_HTML = """
<html><body>
<h3>Latest Base Specs</h3>
<table class="wikitable"><tbody>
<tr><th>Type</th><th>Description</th><th>Version</th><th>Submit Date</th>
<th>Contributor</th><th>Link</th><th>Notes</th></tr>
<tr><td>Specification</td><td>M-CRPS Base Specification</td><td>1.06</td>
<td>4/24/26</td><td>Someone</td>
<td><a href="https://drive.google.com/file/d/abc/view">Link (Base Spec)</a>
<a href="https://drive.google.com/file/d/def/view">Link (Drawings)</a></td>
<td>Updates: MAJOR Release</td></tr>
<tr><td>Specification</td><td>M-XIO Base Specification</td><td>1.04 RC1</td>
<td>2/28/24</td><td>Someone</td>
<td><a href="https://drive.google.com/file/d/ghi/view">Link</a></td><td></td></tr>
<tr><td>Specification</td><td>M-DNO Base Specification</td><td>1.1 RC2</td>
<td>3/21/2024</td><td>Someone</td><td><a href="https://x/dno">Link</a></td><td></td></tr>
</tbody></table>
<table class="wikitable"><tbody>
<tr><th>Type</th><th>Description</th><th>Revision</th><th>Submit Date</th>
<th>Contributor</th><th>License</th><th>Notes</th></tr>
<tr><td>Specification</td>
<td><a href="https://drive.google.com/file/d/scm22/view">OCP DC-SCM Rev 2.2 Ver1.0</a>
<br/>OCP DC-SCM LTPI Rev1.2</td><td>2.2</td><td>October 16, 2025</td>
<td>Many</td><td>OWFa</td><td>last updated October 2025</td></tr>
<tr><td>Specification</td><td>OCP HPM Common Circuit Type 1 Pinlist</td><td>1.0</td>
<td>August 21, 2024</td><td>Many</td><td>OWFa</td><td></td></tr>
</tbody></table>
</body></html>
"""


def test_dmtf_published_page_gives_the_current_version_per_dsp():
    table = L.parse_dmtf_published(DMTF_PUBLISHED_HTML)
    assert set(table) == {"DSP0236", "DSP8010"}
    assert table["DSP0236"] == L.Seen(
        "1.3.3",
        "https://www.dmtf.org/sites/default/files/standards/documents/DSP0236_1.3.3.pdf",
    )
    assert table["DSP8010"].url.endswith("DSP8010_2026.1.zip")


def test_dmtf_dsp_page_gives_every_version_with_its_date():
    rows = L.parse_dmtf_versions(DMTF_DSP_HTML)
    assert [(r.version, r.published, r.note) for r in rows] == [
        ("1.3.4", "2026-08-03", ""),
        ("1.3.3", "2024-03-25", ""),
        ("1.4.0", "2027-01-01", "Work in Progress"),
    ]
    assert rows[1].url.endswith("DSP0236_1.3.3_0.pdf")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("25 Mar 2024", "2024-03-25"),
        ("3 August 2026", "2026-08-03"),
        ("Mar 25 2024", ""),
        ("31 Feb 2024", ""),
        ("", ""),
    ],
)
def test_dmtf_date(text, expected):
    assert L.dmtf_date(text) == expected


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://x/documents/DSP0236_1.3.3.pdf", "1.3.3"),
        ("https://x/documents/DSP0236_1.3.3_0.pdf", "1.3.3"),
        ("https://x/documents/DSP8010_2019.1_1.zip", "2019.1"),
        ("https://x/documents/DSP0134V2.4Final.pdf", ""),
        ("https://x/documents/DSP0236_1.3.3.pdf?x=1", ""),
    ],
)
def test_dmtf_version_of_url(url, expected):
    assert L.dmtf_version_of_url(url) == expected


def test_nvme_api_gives_the_current_file_per_slug():
    table = L.parse_nvme(NVME_JSON.encode())
    assert set(table) == {"nvm-express-base-specification", "nvme-mi-specification"}
    base = table["nvm-express-base-specification"]
    assert (base.version, base.published) == ("2.4", "2026-07-31")
    assert base.url.endswith("Ratified-2026.07.31.pdf")
    assert base.note == ""
    assert table["nvme-mi-specification"].version == "2.2"
    with pytest.raises(L.ListingError):
        L.parse_nvme(b"<html>")
    with pytest.raises(L.ListingError):
        L.parse_nvme(b'{"types": {}}')


@pytest.mark.parametrize(
    "name, expected",
    [
        ("NVM-Express-Base-Specification-Revision-2.4-Ratified-2026.07.31.pdf", "2.4"),
        ("NVM-Express-Base-Specification-2.0e-2024.07.29-Ratified.pdf", "2.0e"),
        ("NVM-Express-1_3d-2019.03.20-Ratified.pdf", "1.3d"),
        ("NVM_Express_Management_Interface_1_0_gold.pdf", "1.0"),
        ("NVM_Express_Management_Interface_1_0a_2017.04.08_-_gold.pdf", "1.0a"),
        ("NVM-Express-Management-Interface-1.1-Ratified.pdf", "1.1"),
        ("NVM-Express-Revision-Changes-2026.07.30.pdf", ""),
    ],
)
def test_nvme_version_of_url(name, expected):
    assert L.nvme_version_of_url(
        "https://nvmexpress.org/wp-content/uploads/" + name
    ) == (expected)


def test_ocp_wiki_rows_by_description_prefix():
    crps = L.parse_ocp(OCP_WIKI_HTML, "M-CRPS Base")
    assert crps == [
        L.Seen(
            "1.06",
            "https://drive.google.com/file/d/abc/view",
            "2026-04-24",
            "M-CRPS Base Specification",
        )
    ]
    assert [r.version for r in L.parse_ocp(OCP_WIKI_HTML, "m-xio base")] == ["1.04 RC1"]
    assert L.parse_ocp(OCP_WIKI_HTML, "M-DNO Base")[0].published == "2024-03-21"
    scm = L.parse_ocp(OCP_WIKI_HTML, "OCP DC-SCM")
    assert [(r.version, r.published) for r in scm] == [("2.2", "2025-10-16")]
    assert scm[0].url == "https://drive.google.com/file/d/scm22/view"
    assert L.parse_ocp(OCP_WIKI_HTML, "nothing") == []


@pytest.mark.parametrize(
    "text, expected",
    [
        ("4/24/26", "2026-04-24"),
        ("03/25/25", "2025-03-25"),
        ("3/21/2024", "2024-03-21"),
        ("October 16, 2025", "2025-10-16"),
        ("3/26/2021 12/02/2020 11/10/2020", "2021-03-26"),
        ("Q3 2024", ""),
    ],
)
def test_ocp_date(text, expected):
    assert L.ocp_date(text) == expected


@pytest.mark.parametrize(
    "source, a, b, same",
    [
        ("dmtf", "1.3.3", "1.3.3", True),
        ("dmtf", "1.3.3", "1.3.3_0", False),
        ("ocp", "R1 v1.2 RC3", "1.2 RC3", True),
        ("ocp", "R1 v1.2 RC3", "1.2 RC4", False),
        ("ocp", "Rev 2.1 Ver 1.1", "2.1", True),
        ("ocp", "Rev 2.1 Ver 1.1", "2.2", False),
        ("ocp", "v1.1 RC2", "1.1 rc2", True),
        ("ocp", "R1 v1.0 RC4", "1.06", False),
    ],
)
def test_version_key(source, a, b, same):
    assert (L.version_key(source, a) == L.version_key(source, b)) is same


def test_listings_fetch_once_and_raise_for_unknown_keys():
    client = ScriptedClient(
        {
            L.DMTF_PUBLISHED: L.Seen and _ok(DMTF_PUBLISHED_HTML.encode(), "text/html"),
            L.DMTF_DSP.format(key="DSP0236"): _ok(DMTF_DSP_HTML.encode(), "text/html"),
            L.NVME_API: _ok(NVME_JSON.encode(), "application/json"),
            L.OCP_WIKI.format(page="Server/MHS/DC-MHS-Specs-and-Designs"): _ok(
                OCP_WIKI_HTML.encode(), "text/html"
            ),
        }
    )
    listings = L.Listings(client)
    assert listings.current("dmtf:DSP0236")[0].version == "1.3.3"
    assert listings.current("dmtf:dsp8010")[0].version == "2026.1"
    assert [s.version for s in listings.history("dmtf:DSP0236")] == [
        "1.3.4",
        "1.3.3",
        "1.4.0",
    ]
    assert listings.current("nvme:nvme-mi-specification")[0].version == "2.2"
    assert listings.history("nvme:nvme-mi-specification")[0].version == "2.2"
    key = "ocp:Server/MHS/DC-MHS-Specs-and-Designs|M-CRPS Base"
    assert listings.current(key)[0].version == "1.06"
    assert client.calls.count(L.DMTF_PUBLISHED) == 1  # cached
    assert client.calls.count(L.NVME_API) == 1
    with pytest.raises(L.ListingError, match="DSP9999 is not on"):
        listings.current("dmtf:DSP9999")
    with pytest.raises(L.ListingError, match="no specification 'zzz'"):
        listings.current("nvme:zzz")
    with pytest.raises(L.ListingError, match="no row starting with"):
        listings.current("ocp:Server/MHS/DC-MHS-Specs-and-Designs|M-ZZZ")
    with pytest.raises(L.ListingError, match="not '<page>|<prefix>'"):
        listings.current("ocp:page-without-prefix")
    with pytest.raises(L.ListingError, match="unknown listing source"):
        listings.current("intel:x")
    with pytest.raises(L.ListingError, match="is not '<source>:<key>'"):
        listings.current("nokey")


def test_listings_report_transport_and_http_failures():
    client = ScriptedClient(
        {
            L.NVME_API: L.Seen and _status(503),
        }
    )
    listings = L.Listings(client)
    with pytest.raises(L.ListingError, match="HTTP 503"):
        listings.current("nvme:x")
    with pytest.raises(L.ListingError, match="no route to"):
        listings.current("dmtf:DSP0236")


def _ok(body, ctype):
    from bmc_toolkit.spec.fetch import Response

    return Response(200, {"content-type": ctype}, body)


def _status(code):
    from bmc_toolkit.spec.fetch import Response

    return Response(code, {}, b"")


# ---------------------------------------------------- shipped catalog


def test_shipped_catalog_urls_carry_the_catalog_version_string():
    """AC-7: the parsers recover the version string from every regular DMTF
    and NVMe URL in the shipped catalog."""
    catalog = load_catalog()
    regular = re.compile(r"/DSP\d+_")
    checked = 0
    for doc in catalog.documents:
        for v in doc.versions:
            if doc.listing_source == "dmtf" and regular.search(v.url):
                assert L.dmtf_version_of_url(v.url) == v.version, (doc.id, v.url)
                checked += 1
            elif doc.listing_source == "nvme":
                assert L.nvme_version_of_url(v.url) == v.version, (doc.id, v.url)
                checked += 1
    assert checked > 400


def test_shipped_catalog_listing_keys():
    catalog = load_catalog()
    assert catalog.get("DSP0236").listing == "dmtf:DSP0236"
    assert catalog.get("NVME-MI").listing == "nvme:nvme-mi-specification"
    assert catalog.get("M-CRPS").listing_source == "ocp"
    assert catalog.get("IPMI").listing == ""
    for doc in catalog.documents:
        if doc.listing_source == "ocp":
            page, _, prefix = doc.listing_key.partition("|")
            assert page.startswith("Server/MHS/") and prefix, doc.id
