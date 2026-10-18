"""Reviewer acceptance tests for the October 2026 DMTF releases (AC-1,
AC-2, AC-5, AC-7): the shipped catalog lists DSP0283 1.1.1 and DSP0248
1.4.0 with DMTF's date, URL and type while the earlier versions stay,
``catalog <id>`` reports each new version as latest, the Golden rows on the
two documents name the new version with no row dropped, and the per-family
Support table in ``docs/SUPPORT.md`` is the generator's output with the new
Latest and PASS. The answers themselves (AC-4), the live fetches (AC-3)
and the Freshness wording (AC-6) are checked by hand."""

import re
from pathlib import Path

import pytest

from bmc_toolkit.spec import support
from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "docs" / "golden-questions.md"
SUPPORT = ROOT / "docs" / "SUPPORT.md"
DMTF_FILES = "https://www.dmtf.org/sites/default/files/standards/documents/"

# AC-1: (document, version, published, type) as DMTF's listing gives them.
ADDED = [
    ("DSP0283", "1.1.1", "2026-10-08", "pdf"),
    ("DSP0248", "1.4.0", "2026-10-12", "pdf"),
]

# AC-2: the new latest and the version it replaces, which stays listed.
LATEST = {
    "DSP0283": ("1.1.1", "1.1.0"),
    "DSP0248": ("1.4.0", "1.3.1"),
}

# AC-4 / AC-5 / AC-7: the Golden rows on the two documents, in file order.
GOLDEN_ROWS = {
    "DSP0283": ["G51"],
    "DSP0248": ["G13", "G15"],
}


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


def _catalog_output(capsys, doc_id: str) -> tuple[str, list[list[str]]]:
    """(the ``latest:`` value, the version rows newest first) of
    ``catalog <id>``."""
    code = main(["catalog", doc_id])
    out = capsys.readouterr().out
    assert code == 0, out
    latest = [ln for ln in out.splitlines() if ln.startswith("latest: ")]
    assert len(latest) == 1, out
    rows = [ln[1:].split("\t") for ln in out.splitlines() if ln.startswith("\t")]
    return latest[0][len("latest: ") :], rows


# ------------------------------------------------------------------ AC-1


@pytest.mark.parametrize("doc_id, version, published, type_", ADDED)
def test_ac1_version_listed_as_dmtf_lists_it(
    shipped, doc_id, version, published, type_
):
    doc = shipped.get(doc_id)
    assert doc is not None
    found = doc.find_version(version)
    assert found is not None, f"{doc_id} {version} is not in the catalog"
    assert found.published == published
    assert found.type == type_
    assert found.url == f"{DMTF_FILES}{doc_id}_{version}.{type_}"
    assert found.wip is False
    assert found.access == "open"


@pytest.mark.parametrize("doc_id", sorted(LATEST))
def test_ac1_previous_version_is_kept_and_older(shipped, doc_id):
    """The diff adds lines only: the version that was latest before is
    still listed with its own earlier date, and no version is listed
    twice."""
    doc = shipped.get(doc_id)
    new, previous = LATEST[doc_id]
    kept = doc.find_version(previous)
    assert kept is not None, f"{doc_id} {previous} was dropped"
    assert kept.published < doc.find_version(new).published
    assert kept.url == f"{DMTF_FILES}{doc_id}_{previous}.pdf"
    assert len({v.version for v in doc.versions}) == len(doc.versions)


@pytest.mark.parametrize("doc_id", sorted(LATEST))
def test_ac1_new_block_follows_the_previous_one_in_catalog_order(shipped, doc_id):
    """``refresh --write`` appends after the document's last version block,
    so the new version is the last entry of the document, not inserted
    before an older one or attached to another document."""
    doc = shipped.get(doc_id)
    new, previous = LATEST[doc_id]
    order = [v.version for v in doc.versions]
    assert order[-1] == new
    assert order.index(previous) == len(order) - 2
    url = f"{DMTF_FILES}{doc_id}_{new}.pdf"
    holders = [d.id for d in shipped.documents if any(v.url == url for v in d.versions)]
    assert holders == [doc_id]


# ------------------------------------------------------------------ AC-2


@pytest.mark.parametrize("doc_id", sorted(LATEST))
def test_ac2_catalog_reports_the_new_version_as_latest(capsys, shipped, doc_id):
    new, previous = LATEST[doc_id]
    latest, rows = _catalog_output(capsys, doc_id)
    assert latest == new
    assert rows[0][0] == new
    assert rows[0][3] == "published"
    assert previous in [r[0] for r in rows], (doc_id, rows)
    doc = shipped.get(doc_id)
    assert doc.latest().version == new
    assert doc.latest(include_wip=True).version == new
    assert doc.newest_open().version == new


def test_ac2_listing_line_names_the_new_latest(capsys):
    """The one-line-per-document form of ``catalog`` carries the latest in
    its fifth column and the new version among the known ones."""
    code = main(["catalog"])
    out = capsys.readouterr().out
    assert code == 0, out
    lines = {}
    for ln in out.splitlines():
        cells = ln.split("\t")
        if len(cells) == 7:
            lines[cells[1]] = cells
    for doc_id, (new, previous) in LATEST.items():
        cells = lines[doc_id]
        assert cells[4] == new, cells
        known = cells[6].split(";")
        assert new in known and previous in known, cells


# ------------------------------------------------------------------ AC-5 / AC-7


def test_ac5_golden_rows_name_the_new_version_and_none_is_dropped(shipped):
    verified, problems = support.read_golden(GOLDEN, shipped)
    assert problems == []
    for doc_id, questions in GOLDEN_ROWS.items():
        new = LATEST[doc_id][0]
        pairs = verified[doc_id.lower()]
        assert [q for q, _ in pairs] == questions, doc_id
        assert all(v == new for _, v in pairs), (doc_id, pairs)


def test_ac5_golden_answer_cells_carry_no_stale_version():
    """No row on the two documents still names the version that was latest
    before this change, in the Document or the Answer column."""
    text = GOLDEN.read_text(encoding="utf-8")
    seen = set()
    for line in text.splitlines():
        m = re.match(r"^\|\s*(G\d+)\s*\|", line)
        if not m:
            continue
        cells = support._cells(line)
        for doc_id, (new, previous) in LATEST.items():
            if doc_id in cells[2]:
                seen.add(m.group(1))
                assert f"{doc_id} {previous}" not in cells[2], (m.group(1), cells[2])
                assert f"{doc_id} {previous}" not in cells[3], (m.group(1), cells[3])
                assert f"{doc_id} {new}" in cells[3], (m.group(1), cells[3])
    assert seen == {q for qs in GOLDEN_ROWS.values() for q in qs}


def _by_family_rows(capsys) -> tuple[str, dict[str, list[str]]]:
    code = main(["catalog", "--table", "--by-family", "--golden", str(GOLDEN)])
    out = capsys.readouterr().out
    assert code == 0, out
    rows = {}
    for ln in out.splitlines():
        if not ln.startswith("| `"):
            continue
        cells = support._cells(ln)
        rows[cells[0].split("`")[1]] = cells
    return out, rows


def test_ac5_support_doc_shows_the_new_latest_and_stays_pass(capsys):
    out, rows = _by_family_rows(capsys)
    for doc_id, (new, _previous) in LATEST.items():
        _document, _access, latest, verified, _limit = rows[doc_id]
        assert latest == new, (doc_id, latest)
        assert verified == "PASS", (doc_id, verified)
    marker = (
        "<!-- generated below: catalog --table --by-family "
        "--golden docs/golden-questions.md -->\n\n"
    )
    stored = SUPPORT.read_text(encoding="utf-8")
    assert marker in stored
    assert stored.split(marker, 1)[1] == out


def test_ac5_support_doc_rows_for_the_two_documents_are_the_generated_ones():
    """The two rows the description says changed read as the generator
    prints them: id in backticks, open, the new Latest, PASS."""
    stored = SUPPORT.read_text(encoding="utf-8")
    for doc_id, (new, previous) in LATEST.items():
        rows = [ln for ln in stored.splitlines() if ln.startswith(f"| `{doc_id}`")]
        assert len(rows) == 1, (doc_id, rows)
        cells = support._cells(rows[0])
        assert cells[1:4] == ["open", new, "PASS"], cells
        assert f"| {previous} |" not in rows[0]


def test_ac7_support_table_verified_cell_groups_both_dsp0248_rows_on_1_4_0(capsys):
    """The full table form (the one tests/test_support.py pins) groups G13
    and G15 under the new version only."""
    code = main(["catalog", "--table", "--golden", str(GOLDEN)])
    out = capsys.readouterr().out
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith("| Family | Document | Access | Latest | Fetch | Verified |")
    rows = {}
    for ln in lines[2:]:
        cells = support._cells(ln)
        if len(cells) >= 6 and cells[1].startswith("`"):
            rows[cells[1].split("`")[1]] = cells
    assert rows["DSP0248"][3] == "1.4.0", rows["DSP0248"]
    assert rows["DSP0248"][5] == "G13, G15 (1.4.0)", rows["DSP0248"]
    assert rows["DSP0283"][3] == "1.1.1", rows["DSP0283"]
    assert rows["DSP0283"][5] == "G51 (1.1.1)", rows["DSP0283"]
