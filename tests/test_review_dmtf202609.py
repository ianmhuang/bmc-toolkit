"""Reviewer acceptance tests for the September 2026 DMTF releases (AC-1,
AC-2, AC-5, AC-6): the shipped catalog lists the eleven versions with
DMTF's date, URL and type, ``catalog <id>`` reports each new version as
latest, the Golden rows of the ten documents name the new version, and the
per-family Support table shows the new Latest with PASS. The answers
themselves (AC-5) and the live fetches (AC-3, AC-4) are checked by hand."""

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

# The eleven versions of AC-1: (document, version, published, type).
ADDED = [
    ("DSP0236", "1.4.0", "2026-09-07", "pdf"),
    ("DSP0134", "3.10.0", "2026-09-07", "pdf"),
    ("DSP0240", "1.2.1", "2026-09-14", "pdf"),
    ("DSP0266", "1.24.1", "2026-09-14", "pdf"),
    ("DSP0266", "1.25.0", "2026-09-14", "pdf"),
    ("DSP8010", "2026.2", "2026-09-14", "zip"),
    ("DSP0268", "2026.2", "2026-09-14", "pdf"),
    ("DSP2046", "2026.2", "2026-09-14", "pdf"),
    ("DSP2053", "2026.2", "2026-09-14", "pdf"),
    ("DSP2065", "2026.2", "2026-09-14", "pdf"),
    ("DSP8011", "2026.2", "2026-09-14", "zip"),
]

# AC-2: what ``catalog <id>`` reports as latest, and the version it replaces
# (which the catalog keeps: the diff adds lines only).
LATEST = {
    "DSP0236": ("1.4.0", "1.3.3"),
    "DSP0134": ("3.10.0", "3.9.0"),
    "DSP0240": ("1.2.1", "1.1.1"),
    "DSP0266": ("1.25.0", "1.24.0"),
    "DSP8010": ("2026.2", "2026.1"),
    "DSP0268": ("2026.2", "2026.1"),
    "DSP2046": ("2026.2", "2026.1"),
    "DSP2053": ("2026.2", "2026.1"),
    "DSP2065": ("2026.2", "2026.1"),
    "DSP8011": ("2026.2", "2026.1"),
}

# AC-5: the Golden Questions on those documents.
GOLDEN_ROWS = {
    "DSP0236": ["G8"],
    "DSP0240": ["G11"],
    "DSP8010": ["G17"],
    "DSP0266": ["G18"],
    "DSP0134": ["G74"],
    "DSP0268": ["G75"],
    "DSP2046": ["G76"],
    "DSP2053": ["G79"],
    "DSP2065": ["G80"],
    "DSP8011": ["G101"],
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
def test_ac1_previous_versions_are_kept(shipped, doc_id):
    """The diff adds lines only: the version that was latest before is
    still listed, with its own date, so a Library holding it still
    resolves."""
    doc = shipped.get(doc_id)
    new, previous = LATEST[doc_id]
    kept = doc.find_version(previous)
    assert kept is not None, f"{doc_id} {previous} was dropped"
    assert kept.published < doc.find_version(new).published
    assert len({v.version for v in doc.versions}) == len(doc.versions)


def test_ac1_dsp0134_block_belongs_to_dsp0134_not_redfish(shipped):
    """3.10.0 is a version of the SMBIOS document and no Redfish document
    picked it up."""
    for doc in shipped.by_family("redfish"):
        assert doc.find_version("3.10.0") is None, doc.id
    assert shipped.get("DSP0134").family != "redfish"


# ------------------------------------------------------------------ AC-2


@pytest.mark.parametrize("doc_id", sorted(LATEST))
def test_ac2_catalog_reports_the_new_version_as_latest(capsys, shipped, doc_id):
    new, _previous = LATEST[doc_id]
    latest, rows = _catalog_output(capsys, doc_id)
    assert latest == new
    assert rows[0][0] == new
    assert rows[0][3] == "published"
    assert shipped.get(doc_id).latest().version == new
    assert shipped.get(doc_id).newest_open().version == new


def test_ac2_dsp0266_same_day_versions_are_told_apart_by_number(capsys, shipped):
    """1.24.1 and 1.25.0 share 2026-09-14: 1.25.0 is latest and the newest
    first listing puts 1.25.0, then 1.24.1, then 1.24.0."""
    latest, rows = _catalog_output(capsys, "DSP0266")
    assert latest == "1.25.0"
    assert [r[0] for r in rows[:3]] == ["1.25.0", "1.24.1", "1.24.0"]
    assert rows[0][1] == rows[1][1] == "2026-09-14"
    doc = shipped.get("DSP0266")
    order = [v.version for v in doc.versions]
    assert order.index("1.24.0") < order.index("1.24.1") < order.index("1.25.0")


# ------------------------------------------------------------------ AC-5


def test_ac5_golden_rows_name_the_newest_version_and_none_is_dropped(shipped):
    verified, problems = support.read_golden(GOLDEN, shipped)
    assert problems == []
    for doc_id, questions in GOLDEN_ROWS.items():
        new = LATEST[doc_id][0]
        pairs = verified[doc_id.lower()]
        assert [q for q, _ in pairs] == questions, doc_id
        assert all(v == new for _, v in pairs), (doc_id, pairs)


def test_ac5_golden_document_cells_carry_no_stale_version():
    """No row on one of the ten documents still names the version that
    was latest before this change."""
    text = GOLDEN.read_text(encoding="utf-8")
    for line in text.splitlines():
        m = re.match(r"^\|\s*(G\d+)\s*\|", line)
        if not m:
            continue
        cells = support._cells(line)
        for doc_id, (_new, previous) in LATEST.items():
            assert f"{doc_id} {previous}" not in cells[2], (m.group(1), cells[2])


# ------------------------------------------------------------------ AC-6


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


def test_ac6_support_doc_shows_the_new_latest_and_stays_pass(capsys):
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
