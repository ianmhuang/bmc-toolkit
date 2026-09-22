"""Review tests for the fix on branch fix/catalog-urls-26: `refresh` does not
report `changed` while any listed row of a version names the catalog URL
(scheme ignored), and the shipped catalog carries M-CRPS 1.06 and the
DSP8011 2017.x notes. Black-box through the CLI and the shipped catalog."""

import pytest

from bmc_toolkit.spec import listing as L
from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main
from tests.test_listing import OCP_WIKI_HTML

DMTF_FILES = "https://www.dmtf.org/sites/default/files/standards/documents/"
FIRST = DMTF_FILES + "DSP0266_1.20.2_0.pdf"
SECOND = DMTF_FILES + "DSP0266_1.20.2.pdf"


def _html(text):
    from bmc_toolkit.spec.fetch import Response

    return Response(200, {"content-type": "text/html"}, text.encode())


def _dsp_page(*rows):
    """A DMTF per-DSP page; rows are (version, href, date)."""
    body = "".join(
        f'<tr><td> {version} </td><td><a href="{href}">Redfish</a></td>'
        f"<td> {date} </td><td> Standard </td></tr>"
        for version, href, date in rows
    )
    return (
        "<html><body><table><thead><tr><th>Version </th><th>Title </th>"
        "<th>Publication Date </th><th>Comments </th></tr></thead>"
        f"<tbody>{body}</tbody></table></body></html>"
    )


TWICE = _dsp_page(
    ("1.20.2", "/sites/default/files/standards/documents/DSP0266_1.20.2_0.pdf", "16 Sep 2024"),
    ("1.20.2", "/sites/default/files/standards/documents/DSP0266_1.20.2.pdf", "19 Aug 2024"),
)


def _catalog(tmp_path, url, source="dmtf:DSP0266"):
    text = (
        "schema_version = 1\n\n"
        '[families.redfish]\ntitle = "Redfish"\npublisher = "DMTF"\n\n'
        '[[documents]]\nid = "DSP0266"\nfamily = "redfish"\n'
        f'title = "Redfish Specification"\naccess = "open"\nfetch = "direct"\n'
        f'listing = "{source}"\n\n'
        f'[[documents.versions]]\nversion = "1.20.2"\nurl = "{url}"\n'
        'type = "pdf"\npublished = "2024-09-16"\n'
    )
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


def _refresh(capsys, catalog_path, *argv):
    code = main(["--catalog", str(catalog_path), "refresh", *argv])
    return code, capsys.readouterr().out


# ------------------------------------------------ AC-1: a version listed twice


@pytest.mark.parametrize("url", [FIRST, SECOND])
def test_no_changed_while_one_of_two_listed_rows_names_the_catalog_url(
    tmp_path, library, scripted, capsys, url
):
    scripted.responses[L.DMTF_DSP.format(key="DSP0266")] = _html(TWICE)
    code, out = _refresh(capsys, _catalog(tmp_path, url))
    assert code == 0, out
    assert "changed" not in out.splitlines()[:-1], out
    assert out.splitlines()[-1].startswith(
        "summary: add 0, confirm 0, changed 0, unreachable 0"
    )


# ---------------------------------------- AC-3: no listed row names the URL


def test_every_listed_row_is_changed_when_none_names_the_catalog_url(
    tmp_path, library, scripted, capsys
):
    scripted.responses[L.DMTF_DSP.format(key="DSP0266")] = _html(TWICE)
    code, out = _refresh(capsys, _catalog(tmp_path, DMTF_FILES + "DSP0266_1.20.2_1.pdf"))
    assert code == 0, out
    lines = out.splitlines()
    assert lines[:-1] == [
        f"changed DSP0266 1.20.2 (2024-09-16) {FIRST}",
        f"changed DSP0266 1.20.2 (2024-08-19) {SECOND}",
    ]
    assert lines[-1].startswith("summary: add 0, confirm 0, changed 2, unreachable 0")


def test_a_single_listed_row_with_another_url_is_still_changed(
    tmp_path, library, scripted, capsys
):
    # The pre-existing rule for a version listed once: the URL moved.
    page = _dsp_page(
        ("1.20.2", "/sites/default/files/standards/documents/DSP0266_1.20.2_0.pdf", "16 Sep 2024")
    )
    scripted.responses[L.DMTF_DSP.format(key="DSP0266")] = _html(page)
    code, out = _refresh(capsys, _catalog(tmp_path, SECOND))
    assert code == 0, out
    assert out.splitlines()[0] == f"changed DSP0266 1.20.2 (2024-09-16) {FIRST}"


# ----------------------------------------------- AC-2: http and https alike


def test_a_listing_http_link_matches_the_catalog_https_url(
    tmp_path, library, scripted, capsys
):
    page = _dsp_page(("1.20.2", FIRST.replace("https://", "http://"), "16 Sep 2024"))
    scripted.responses[L.DMTF_DSP.format(key="DSP0266")] = _html(page)
    code, out = _refresh(capsys, _catalog(tmp_path, FIRST))
    assert code == 0, out
    assert out.splitlines() == [
        "summary: add 0, confirm 0, changed 0, unreachable 0 (dry run; --write adds them)"
    ]


def test_a_catalog_http_url_matches_the_listing_https_link(
    tmp_path, library, scripted, capsys
):
    page = _dsp_page(("1.20.2", FIRST, "16 Sep 2024"))
    scripted.responses[L.DMTF_DSP.format(key="DSP0266")] = _html(page)
    code, out = _refresh(capsys, _catalog(tmp_path, FIRST.replace("https://", "http://")))
    assert code == 0, out
    assert "changed" not in out


def test_a_different_path_is_changed_even_when_only_the_scheme_also_differs(
    tmp_path, library, scripted, capsys
):
    # Ignoring the scheme must not make every http:// row a match.
    page = _dsp_page(("1.20.2", FIRST.replace("https://", "http://"), "16 Sep 2024"))
    scripted.responses[L.DMTF_DSP.format(key="DSP0266")] = _html(page)
    code, out = _refresh(capsys, _catalog(tmp_path, SECOND))
    assert code == 0, out
    assert out.splitlines()[0].startswith("changed DSP0266 1.20.2 (2024-09-16) http://")


# --------------------------- AC-4 and AC-9 (offline part): OCP rows, shipped


def test_shipped_m_crps_1_06_is_known_so_the_wiki_row_is_not_confirm(
    library, scripted, capsys
):
    # The OCP wiki row for 1.06 carries a viewer link that differs from the
    # catalog's direct download URL: an OCP row is never `changed`, and a
    # version the catalog holds is not `confirm`.
    scripted.responses[
        L.OCP_WIKI.format(page="Server/MHS/DC-MHS-Specs-and-Designs")
    ] = _html(OCP_WIKI_HTML)
    code = main(["refresh", "M-CRPS"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "confirm M-CRPS 1.06" not in out
    assert "changed" not in out
    assert out.splitlines()[-1].startswith(
        "summary: add 0, confirm 0, changed 0, unreachable 0"
    )


# ------------------------------------------------- AC-5: M-CRPS 1.06 shipped


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


def test_shipped_catalog_lists_m_crps_1_06_as_a_direct_download(shipped):
    doc = shipped.get("M-CRPS")
    ver = doc.find_version("1.06")
    assert ver is not None
    assert ver.published == "2026-04-24"
    assert ver.type == "pdf"
    assert ver.url.startswith("https://drive.google.com/uc?export=download&id=")
    assert "1.06.00 RC1" in ver.notes
    assert doc.latest().version == "1.06"
    assert doc.newest_open().version == "1.06"


def test_shipped_m_crps_document_note_no_longer_says_1_06_is_not_listed(shipped):
    # AC-5: "The document-level note saying 1.06 is not listed is gone."
    notes = shipped.get("M-CRPS").notes.lower()
    assert not ("1.06" in notes and "not listed" in notes), shipped.get("M-CRPS").notes


# ------------------------------------------------- AC-6: DSP8011 2017.1/2017.2


def test_shipped_dsp8011_2017_versions_keep_https_and_carry_notes(shipped):
    doc = shipped.get("DSP8011")
    first = doc.find_version("2017.1")
    second = doc.find_version("2017.2")
    assert first.url.startswith("https://") and first.url.endswith("DSP8011_2017.1.zip")
    assert second.url.startswith("https://") and second.url.endswith("DSP8011_2017.2.zip")
    assert "wayback" in first.notes.lower()
    assert "dsp8010" in first.notes.lower()
    assert "drop-in" in second.notes.lower()
