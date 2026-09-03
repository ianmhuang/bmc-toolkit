"""Review acceptance tests for catalog refresh (AC-6) and the listing
parsers over the shipped catalog (AC-7).

Black-box through the CLI with a scripted client; the parser checks use
the module's public functions. Nothing touches the network.
"""

import json
import re

import pytest

from bmc_toolkit.spec import cli
from bmc_toolkit.spec import listing as listing_mod
from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.fetch import Response
from tests.conftest import MINI_CATALOG, ScriptedClient, ok

DMTF_PUBLISHED = "https://www.dmtf.org/standards/published_documents"
DMTF_DSP0236 = "https://www.dmtf.org/dsp/DSP0236"
NVME_API = "https://nvmexpress.org/wp-json/vtm/v1/specifications"
OCP_PAGE = "Server/MHS/DC-MHS-Specs-and-Designs"
OCP_WIKI = f"https://www.opencompute.org/w/index.php?title={OCP_PAGE}"

URL_132 = "https://example.test/DSP0236_1.3.2.pdf"  # as in the catalog
URL_133_MOVED = "https://example.test/moved/DSP0236_1.3.3_0.pdf"  # re-upload
URL_134 = "https://example.test/DSP0236_1.3.4.pdf"
URL_140 = "https://example.test/DSP0236_1.4.0.pdf"  # as in the catalog (WIP)
NVME_MI_22_URL = (
    "https://nvmexpress.org/wp-content/uploads/NVM-Express-Management-Interface-"
    "Specification-Revision-2.2-Ratified-2026.07.31.pdf"
)
DRIVE_URL = "https://drive.google.com/file/d/review-crps/view"

PUBLISHED_HTML = f"""
<html><body><table><thead><tr>
<th>DSP</th><th>Version</th><th>Title</th><th>Comments</th><th>DSP</th>
</tr></thead><tbody>
<tr><td>DSP0236</td><td>1.3.4</td><td><a href="{URL_134}">MCTP Base</a></td>
<td>Standard</td><td><a href="/dsp/DSP0236">View</a></td></tr>
</tbody></table></body></html>
"""


def dsp_page(extra_rows: str = "") -> str:
    return f"""
<html><body><h1>All Published Versions of DSP0236</h1>
<table><thead><tr>
<th>Version</th><th>Title</th><th>Publication Date</th><th>Comments</th>
</tr></thead><tbody>
{extra_rows}
<tr><td>1.3.4</td><td><a href="{URL_134}">MCTP Base</a></td>
<td>3 Aug 2026</td><td>Standard</td></tr>
<tr><td>1.3.3</td><td><a href="{URL_133_MOVED}">MCTP Base</a></td>
<td>25 Mar 2024</td><td>Standard</td></tr>
<tr><td>1.3.2</td><td><a href="{URL_132}">MCTP Base</a></td>
<td>2 Jan 2024</td><td>Standard</td></tr>
<tr><td>1.4.0</td><td><a href="{URL_140}">MCTP Base</a></td>
<td>1 Jun 2025</td><td>Work in Progress</td></tr>
</tbody></table></body></html>
"""


NVME_JSON = json.dumps(
    {
        "posts": [
            {
                "slug": "nvme-mi-specification",
                "post_title": "NVM Express Management Interface Specification",
                "file": {"url": NVME_MI_22_URL},
            }
        ]
    }
)

OCP_HTML = f"""
<html><body><table class="wikitable"><tbody>
<tr><th>Type</th><th>Description</th><th>Version</th><th>Submit Date</th>
<th>Contributor</th><th>Link</th><th>Notes</th></tr>
<tr><td>Specification</td><td>M-CRPS Base Specification</td><td>1.06</td>
<td>4/24/26</td><td>Someone</td>
<td><a href="{DRIVE_URL}">Link (Base Spec)</a></td><td></td></tr>
</tbody></table></body></html>
"""

INNER_COMMENT = "# URL confirmed by hand on 2026-09-03 (review fixture)"

CATALOG = (
    MINI_CATALOG.replace(
        'title = "MCTP Base Specification"\naccess = "open"\nfetch = "direct"\n',
        'title = "MCTP Base Specification"\naccess = "open"\nfetch = "direct"\n'
        f"{INNER_COMMENT}\n",
        1,
    )
    + """
[families.nvme]
title = "NVM Express"
publisher = "NVM Express, Inc."

[families.ocp]
title = "OCP"
publisher = "Open Compute Project"

[[documents]]
id = "NVME-MI"
family = "nvme"
title = "NVMe Management Interface"
access = "open"
fetch = "direct"
listing = "nvme:nvme-mi-specification"

[[documents.versions]]
version = "2.1"
url = "https://example.test/NVM-Express-Management-Interface-Specification-Revision-2.1-2025.08.01-Ratified.pdf"
type = "pdf"
published = "2025-08-01"

[[documents]]
id = "M-CRPS"
family = "ocp"
title = "M-CRPS Base Specification"
access = "open"
fetch = "direct"
listing = "ocp:Server/MHS/DC-MHS-Specs-and-Designs|M-CRPS Base"

[[documents.versions]]
version = "R1 v1.0 RC4"
url = "https://example.test/m-crps-r1-v1p0-rc4-pdf"
type = "pdf"
published = "2023-01-01"
"""
)
assert INNER_COMMENT in CATALOG


def html(text: str) -> Response:
    return Response(200, {"content-type": "text/html"}, text.encode("utf-8"))


@pytest.fixture
def catalog_file(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(CATALOG, encoding="utf-8", newline="")
    return path


@pytest.fixture
def lib_root(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


@pytest.fixture
def client(monkeypatch):
    scripted = ScriptedClient(
        {
            DMTF_PUBLISHED: html(PUBLISHED_HTML),
            DMTF_DSP0236: html(dsp_page()),
            NVME_API: ok(NVME_JSON.encode("utf-8"), "application/json"),
            OCP_WIKI: html(OCP_HTML),
        }
    )
    monkeypatch.setattr(cli, "CLIENT_FACTORY", lambda: scripted)
    return scripted


def run(capsys, *argv, catalog_file):
    code = cli.main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


# ----------------------------------------------------------------- AC-6


def test_refresh_dry_run_reports_add_changed_and_confirm_without_writing(
    catalog_file, lib_root, client, capsys
):
    before = catalog_file.read_bytes()
    code, out = run(capsys, "refresh", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert f"add DSP0236 1.3.4 (2026-08-03) {URL_134}" in lines
    assert f"changed DSP0236 1.3.3 (2024-03-25) {URL_133_MOVED}" in lines
    # versions the catalog has at the same URL are not reported
    assert not any("DSP0236 1.3.2" in ln for ln in lines)
    assert not any("DSP0236 1.4.0" in ln for ln in lines)
    assert f"add NVME-MI 2.2 (2026-07-31) {NVME_MI_22_URL}" in lines
    confirm = [ln for ln in lines if ln.startswith("confirm M-CRPS ")]
    assert len(confirm) == 1
    assert confirm[0].startswith(
        f"confirm M-CRPS 1.06 (2026-04-24) {DRIVE_URL} (URL to confirm by hand)"
    )
    summary = [ln for ln in lines if ln.startswith("summary: ")]
    assert len(summary) == 1
    assert summary[0].startswith("summary: add 2, confirm 1, changed 1, unreachable 0")
    assert catalog_file.read_bytes() == before  # a dry run
    # no document was downloaded, only listings were read
    assert set(client.calls) <= {DMTF_PUBLISHED, DMTF_DSP0236, NVME_API, OCP_WIKI}


def test_refresh_write_appends_dmtf_and_nvme_entries_and_never_ocp(
    catalog_file, lib_root, client, capsys
):
    before = catalog_file.read_text("utf-8")
    code, out = run(capsys, "refresh", "--write", catalog_file=catalog_file)
    assert code == 0, out
    summary = [ln for ln in out.splitlines() if ln.startswith("summary: ")][0]
    assert "written 2" in summary
    after = catalog_file.read_text("utf-8")
    assert "\r" not in catalog_file.read_bytes().decode("utf-8")
    # every original line survives, in order, comments included
    it = iter(after.split("\n"))
    for original in before.split("\n"):
        assert any(got == original for got in it), original
    assert INNER_COMMENT in after
    # the new DSP0236 block sits at the end of the document's block
    dsp = after.index('id = "DSP0236"')
    nxt = after.index("[[documents]]", dsp)
    block = after[dsp:nxt]
    assert block.count("[[documents.versions]]") == 4
    new = block.index('version = "1.3.4"')
    assert new > block.index('version = "1.4.0"')
    assert f'url = "{URL_134}"' in block[new:]
    assert 'type = "pdf"' in block[new:]
    assert 'published = "2026-08-03"' in block[new:]
    # the "changed" URL is reported, not rewritten
    assert 'url = "https://example.test/DSP0236_1.3.3.pdf"' in block
    assert URL_133_MOVED not in after
    # the NVMe entry, and no OCP entry
    nvme = after.index('id = "NVME-MI"')
    nvme_end = after.index("[[documents]]", nvme)
    assert f'url = "{NVME_MI_22_URL}"' in after[nvme:nvme_end]
    assert DRIVE_URL not in after
    assert "1.06" not in after[after.index('id = "M-CRPS"') :]
    # the file parses and the catalog now knows the versions
    catalog = load_catalog(catalog_file)
    dsp0236 = catalog.get("DSP0236")
    assert dsp0236.latest().version == "1.3.4"
    assert dsp0236.find_version("1.3.4").published == "2026-08-03"
    assert dsp0236.find_version("1.4.0").wip
    assert catalog.get("NVME-MI").latest().version == "2.2"
    assert catalog.get("M-CRPS").latest().version == "R1 v1.0 RC4"
    # a second run has nothing to add
    code, out = run(capsys, "refresh", catalog_file=catalog_file)
    assert code == 0
    assert not any(ln.startswith("add ") for ln in out.splitlines())


def test_refresh_one_document_touches_only_that_document(
    catalog_file, lib_root, client, capsys
):
    code, out = run(capsys, "refresh", "NVME-MI", "--write", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert not any("DSP0236" in ln or "M-CRPS" in ln for ln in lines)
    catalog = load_catalog(catalog_file)
    assert catalog.get("NVME-MI").latest().version == "2.2"
    assert catalog.get("DSP0236").latest().version == "1.3.3"
    assert DMTF_DSP0236 not in client.calls


def test_refresh_write_restores_the_file_when_the_edit_does_not_parse(
    catalog_file, lib_root, client, capsys
):
    """A publisher version string carrying a double quote makes a TOML line
    that does not parse; the catalog must come back unchanged, exit 1."""
    row = (
        '<tr><td>1.3.5"beta</td><td><a href="https://example.test/DSP0236_1.3.5.pdf">'
        "MCTP Base</a></td><td>4 Sep 2026</td><td>Standard</td></tr>"
    )
    client.responses[DMTF_DSP0236] = html(dsp_page(row))
    before = catalog_file.read_bytes()
    code, out = run(capsys, "refresh", "DSP0236", "--write", catalog_file=catalog_file)
    assert code == 1, out
    assert "DSP0236" in out
    assert catalog_file.read_bytes() == before
    load_catalog(catalog_file)


def test_refresh_unreachable_listing_and_unlisted_document(
    catalog_file, lib_root, client, capsys
):
    del client.responses[NVME_API]
    before = catalog_file.read_bytes()
    code, out = run(capsys, "refresh", "--write", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    unreachable = [ln for ln in lines if ln.startswith("unreachable NVME-MI: ")]
    assert len(unreachable) == 1 and "no route to" in unreachable[0]
    assert f"add DSP0236 1.3.4 (2026-08-03) {URL_134}" in lines  # went on
    summary = [ln for ln in lines if ln.startswith("summary: ")][0]
    assert "unreachable 1" in summary
    assert catalog_file.read_bytes() != before  # DSP0236 was still written
    assert load_catalog(catalog_file).get("NVME-MI").latest().version == "2.1"
    code, out = run(capsys, "refresh", "IPMI", catalog_file=catalog_file)
    assert code == 2 and "IPMI" in out
    code, out = run(capsys, "refresh", "NOPE", catalog_file=catalog_file)
    assert code == 2


def test_refresh_ocp_is_never_written_even_alone(
    catalog_file, lib_root, client, capsys
):
    before = catalog_file.read_bytes()
    code, out = run(capsys, "refresh", "M-CRPS", "--write", catalog_file=catalog_file)
    assert code == 0, out
    assert any(ln.startswith("confirm M-CRPS 1.06") for ln in out.splitlines())
    assert "written 0" in out
    assert catalog_file.read_bytes() == before


# ----------------------------------------------------------------- AC-7


def test_shipped_catalog_dmtf_and_nvme_urls_carry_their_version_strings():
    catalog = load_catalog()
    regular = re.compile(r"/DSP\d+_")
    dmtf = nvme = 0
    for doc in catalog.documents:
        for v in doc.versions:
            if doc.listing_source == "dmtf" and regular.search(v.url):
                got = listing_mod.dmtf_version_of_url(v.url)
                assert got == v.version, (doc.id, v.version, v.url)
                dmtf += 1
            elif doc.listing_source == "nvme":
                got = listing_mod.nvme_version_of_url(v.url)
                assert got == v.version, (doc.id, v.version, v.url)
                nvme += 1
    assert dmtf > 100 and nvme >= 3


@pytest.mark.parametrize(
    "url, version",
    [
        ("https://x/documents/DSP0236_1.3.3.pdf", "1.3.3"),
        ("https://x/documents/DSP0236_1.3.3_0.pdf", "1.3.3"),
        ("https://x/documents/DSP8010_2019.1_1.zip", "2019.1"),
    ],
)
def test_dmtf_reupload_suffix_is_not_part_of_the_version(url, version):
    assert listing_mod.dmtf_version_of_url(url) == version


def test_dmtf_publication_date_is_read_as_iso():
    assert listing_mod.dmtf_date("25 Mar 2024") == "2024-03-25"
    assert listing_mod.dmtf_date("3 Aug 2026") == "2026-08-03"
    assert listing_mod.dmtf_date("not a date") == ""
    rows = listing_mod.parse_dmtf_versions(dsp_page())
    assert [(r.version, r.published) for r in rows][:2] == [
        ("1.3.4", "2026-08-03"),
        ("1.3.3", "2024-03-25"),
    ]


def test_nvme_filename_date_is_read_as_iso():
    table = listing_mod.parse_nvme(NVME_JSON.encode("utf-8"))
    seen = table["nvme-mi-specification"]
    assert (seen.version, seen.published) == ("2.2", "2026-07-31")
    assert seen.url == NVME_MI_22_URL


@pytest.mark.parametrize(
    "text, expected",
    [
        ("4/24/26", "2026-04-24"),
        ("3/21/2024", "2024-03-21"),
        ("October 16, 2025", "2025-10-16"),
        ("Q3 2024", ""),
    ],
)
def test_ocp_wiki_dates_are_read_as_iso(text, expected):
    assert listing_mod.ocp_date(text) == expected


def test_ocp_rows_carry_the_wiki_date():
    rows = listing_mod.parse_ocp(OCP_HTML, "M-CRPS Base")
    assert [(r.version, r.published, r.url) for r in rows] == [
        ("1.06", "2026-04-24", DRIVE_URL)
    ]
