"""Review tests for the 2026-11-09 catalog batch against DMTF's listing:
``refresh DOC`` on DSP0220, DSP0244 and DSP0280 has nothing to add, confirm
or change when DMTF's per-DSP page lists the catalog's versions, also where
that page dates DSP0244 1.1.0 a year later than the catalog does (AC-2);
``check`` prints ``current`` with the newest version, and the published
page reports none of the three as unlisted (the offline part of AC-5).
A copy of the shipped catalog and a scripted HTTP client, no network."""

import datetime
from pathlib import Path

import pytest

from bmc_toolkit.spec import cli
from bmc_toolkit.spec import listing as listing_mod
from bmc_toolkit.spec import refresh as refresh_mod
from bmc_toolkit.spec.catalog import load_catalog
from tests.conftest import ScriptedClient, ok

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = ROOT / "bmc_toolkit" / "spec" / "catalog.toml"
FILES = "https://www.dmtf.org/sites/default/files/standards/documents"
PUBLISHED = listing_mod.DMTF_PUBLISHED

# id -> (title, (version, the date DMTF's page gives) in publication order)
BATCH = {
    "DSP0220": (
        "Field Replaceable Unit (FRU) Data Specification",
        (("1.0.0", "2025-05-19"), ("1.0.1", "2025-09-22")),
    ),
    # DMTF's page dates 1.1.0 2010-11-02; the catalog records the cover's
    # 2009-11-02
    "DSP0244": (
        "IPMI PET to Platform Message Registry Mapping",
        (
            ("1.0.0", "2009-05-13"),
            ("1.1.0", "2010-11-02"),
            ("1.2.0", "2010-10-27"),
        ),
    ),
    "DSP0280": (
        "PMCI Test Tools Interface and Design Specification",
        (("1.0.0", "2022-10-10"), ("1.1.0", "2026-07-02")),
    ),
}
NEWEST = {"DSP0220": "1.0.1", "DSP0244": "1.2.0", "DSP0280": "1.1.0"}
NOTHING = "summary: add 0, confirm 0, changed 0, unreachable 0"
KINDS = ("add ", "confirm ", "changed ", "unreachable ", "unlisted ")
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


# ------------------------------------------------------------- fixtures


def dmtf_day(iso: str) -> str:
    """``2010-11-02`` as DMTF's pages print it: ``2 Nov 2010``."""
    day = datetime.date.fromisoformat(iso)
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


def dsp_page(dsp: str, title: str, versions) -> bytes:
    """The per-DSP page: every version, newest row first."""
    rows = "".join(
        f'<tr><td>{version}</td><td><a href="{FILES}/{dsp}_{version}.pdf">'
        f"{title}</a></td><td>{dmtf_day(date)}</td><td>Standard</td></tr>"
        for version, date in reversed(versions)
    )
    return (
        "<html><body><table><thead><tr><th>Version</th><th>Title</th>"
        "<th>Publication Date</th><th>Comments</th></tr></thead><tbody>"
        + rows
        + "</tbody></table></body></html>"
    ).encode()


def published_page(rows) -> bytes:
    """The published-documents page: one row per (DSP id, version, title)."""
    body = "".join(
        f"<tr><td>{dsp}</td><td>{version}</td>"
        f'<td><a href="{FILES}/{dsp}_{version}.pdf">{title}</a></td>'
        f'<td>Standard</td><td><a href="/dsp/{dsp}">Versions</a></td></tr>'
        for dsp, version, title in rows
    )
    return (
        "<html><body><table><thead><tr><th>DSP #</th><th>Version</th>"
        "<th>Title</th><th>Comments</th><th>Versions</th></tr></thead>"
        "<tbody>" + body + "</tbody></table></body></html>"
    ).encode()


def dsp_url(dsp: str) -> str:
    return listing_mod.DMTF_DSP.format(key=dsp)


@pytest.fixture
def catalog_copy(tmp_path, monkeypatch):
    """The shipped catalog, byte for byte, where a command may not harm it."""
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(tmp_path / "lib"))
    path = tmp_path / "catalog.toml"
    path.write_bytes(SHIPPED.read_bytes())
    return path


def use(monkeypatch, responses) -> ScriptedClient:
    client = ScriptedClient(responses)
    monkeypatch.setattr(cli, "CLIENT_FACTORY", lambda: client)
    return client


def run(capsys, catalog_path, *argv):
    code = cli.main(["--catalog", str(catalog_path), *argv])
    return code, capsys.readouterr().out


def proposal_lines(out: str) -> list[str]:
    return [ln for ln in out.splitlines() if ln.startswith(KINDS)]


def summary_line(out: str) -> str:
    (line,) = [ln for ln in out.splitlines() if ln.startswith("summary:")]
    return line


# ------------------------------------------------------- AC-2 and AC-5


@pytest.mark.parametrize("dsp", list(BATCH))
def test_refresh_has_nothing_to_add_confirm_or_change(
    catalog_copy, monkeypatch, capsys, dsp
):
    title, versions = BATCH[dsp]
    page = ok(dsp_page(dsp, title, versions), "text/html")
    client = use(monkeypatch, {dsp_url(dsp): page})
    before = catalog_copy.read_bytes()
    code, out = run(capsys, catalog_copy, "refresh", dsp)
    assert code == 0, out
    assert proposal_lines(out) == []
    assert summary_line(out).startswith(NOTHING)
    # only the document's own DMTF page was asked, and nothing was written
    assert set(client.calls) == {dsp_url(dsp)}
    assert catalog_copy.read_bytes() == before


def test_ac2_refresh_does_not_report_the_date_dmtf_gives_dsp0244_1_1_0(
    catalog_copy, monkeypatch, capsys
):
    """DMTF's page and the catalog disagree on the date of 1.1.0 and agree
    on its URL: refresh compares URLs, so it has nothing to say."""
    title, versions = BATCH["DSP0244"]
    page = dsp_page("DSP0244", title, versions)
    seen = {s.version: s for s in listing_mod.parse_dmtf_versions(page.decode())}
    doc = load_catalog(catalog_copy).get("DSP0244")
    assert doc is not None, "DSP0244 is not in the catalog"
    known = doc.find_version("1.1.0")
    assert seen["1.1.0"].published == "2010-11-02"
    assert known.published == "2009-11-02"
    assert seen["1.1.0"].url == known.url
    # as listed, 1.1.0 is the later of the two; as recorded, 1.2.0 is
    assert seen["1.1.0"].published > seen["1.2.0"].published
    assert doc.latest().version == "1.2.0"

    use(monkeypatch, {dsp_url("DSP0244"): ok(page, "text/html")})
    code, out = run(capsys, catalog_copy, "refresh", "DSP0244")
    assert code == 0, out
    assert proposal_lines(out) == []
    assert summary_line(out).startswith(NOTHING)


def test_refresh_reports_a_version_the_catalog_lacks(
    catalog_copy, monkeypatch, capsys
):
    """The control for the tests above: the same page with one more row is
    an ``add``, and a dry run leaves the catalog alone."""
    title, versions = BATCH["DSP0280"]
    more = (*versions, ("9.9.9", "2027-01-04"))
    page = ok(dsp_page("DSP0280", title, more), "text/html")
    use(monkeypatch, {dsp_url("DSP0280"): page})
    before = catalog_copy.read_bytes()
    code, out = run(capsys, catalog_copy, "refresh", "DSP0280")
    assert code == 0, out
    (line,) = proposal_lines(out)
    assert line.startswith("add DSP0280 9.9.9 (2027-01-04) ")
    assert line.endswith(f"{FILES}/DSP0280_9.9.9.pdf")
    assert summary_line(out).startswith(
        "summary: add 1, confirm 0, changed 0, unreachable 0"
    )
    assert catalog_copy.read_bytes() == before


@pytest.mark.parametrize("dsp", list(BATCH))
def test_refresh_reports_an_unreachable_listing(
    catalog_copy, monkeypatch, capsys, dsp
):
    """Network failure: the page cannot be read, which is said and counted
    and is not an error of the command."""
    use(monkeypatch, {})
    code, out = run(capsys, catalog_copy, "refresh", dsp)
    assert code == 0, out
    (line,) = proposal_lines(out)
    assert line.startswith(f"unreachable {dsp}: ")
    assert dsp_url(dsp) in line
    assert summary_line(out).startswith(
        "summary: add 0, confirm 0, changed 0, unreachable 1"
    )


# ------------------------------------------------------------------ AC-5


@pytest.mark.parametrize("dsp", list(BATCH))
def test_check_prints_current_with_the_newest_version(
    catalog_copy, monkeypatch, capsys, dsp
):
    rows = [(d, NEWEST[d], BATCH[d][0]) for d in BATCH]
    use(monkeypatch, {PUBLISHED: ok(published_page(rows), "text/html")})
    code, out = run(capsys, catalog_copy, "check", dsp)
    assert code == 0, out
    assert f"current {dsp} {NEWEST[dsp]}" in out.splitlines()
    assert summary_line(out).startswith("summary: current 1, newer 0, unreachable 0")


def test_check_names_a_newer_version_of_dsp0244(catalog_copy, monkeypatch, capsys):
    """The control: a version DMTF lists and the catalog lacks is reported
    against the catalog's latest, which is 1.2.0 and not 1.1.0."""
    rows = [("DSP0244", "1.3.0", BATCH["DSP0244"][0])]
    use(monkeypatch, {PUBLISHED: ok(published_page(rows), "text/html")})
    code, out = run(capsys, catalog_copy, "check", "DSP0244")
    assert code == 0, out
    (line,) = [ln for ln in out.splitlines() if ln.startswith("newer DSP0244")]
    assert "catalog latest 1.2.0" in line
    assert "1.3.0" in line
    assert summary_line(out).startswith("summary: current 0, newer 1, unreachable 0")


def test_the_published_page_reports_none_of_the_three_as_unlisted():
    """Whole-catalog ``refresh`` counts as unlisted any id on DMTF's page
    that no document lists and not_taken does not cover: the three are
    listed, what the change leaves out is covered, an undecided id shows."""
    catalog = load_catalog()
    listed = catalog.dmtf_listed()
    for dsp in BATCH:
        assert listed.get(dsp) == dsp, dsp
        assert not catalog.dmtf_not_taken_covers(dsp), dsp
    rows = [(d, NEWEST[d], BATCH[d][0]) for d in BATCH]
    rows.append(("DSP8007", "1.0.0", "Platform Message Registry"))
    client = ScriptedClient({PUBLISHED: ok(published_page(rows), "text/html")})
    assert refresh_mod.unlisted(catalog, listing_mod.Listings(client)) == []

    rows.append(("DSP0999", "1.0.0", "A document nobody has decided on"))
    client = ScriptedClient({PUBLISHED: ok(published_page(rows), "text/html")})
    found = refresh_mod.unlisted(catalog, listing_mod.Listings(client))
    assert [item.dsp for item in found] == ["DSP0999"]
