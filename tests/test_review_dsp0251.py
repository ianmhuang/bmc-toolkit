"""Reviewer acceptance tests for the DSP0251 catalog entry (AC-1, AC-2,
AC-3's catalog keys, AC-5's shape, AC-6, AC-7): the shipped catalog lists
DSP0251 1.0.0 as an open, directly fetched PLDM document after DSP8013,
``catalog`` reports it, DSP0248 names it in ``searched_with`` with a note,
the Golden file verifies it under a group of its own placed after the
Redfish bundles, and ``docs/SUPPORT.md`` is the generator's output with
the new row under PLDM as PASS. The live fetch (AC-4), the answer of G103
and the Freshness wording (AC-5) are checked by hand."""

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
DSP0251_URL = f"{DMTF_FILES}DSP0251_1.0.0.pdf"
TITLE = (
    "Platform Level Data Model (PLDM) Platform Descriptor Record (PDR) Specification"
)


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


def _run(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ------------------------------------------------------------------ AC-1


def test_ac1_entry_is_an_open_direct_pldm_document_with_one_version(shipped):
    doc = shipped.get("DSP0251")
    assert doc is not None, "DSP0251 is not in the catalog"
    assert doc.id == "DSP0251"
    assert doc.family == "pldm"
    assert shipped.families[doc.family].publisher == "DMTF"
    assert doc.title == TITLE
    assert doc.access == "open"
    assert doc.fetch == "direct"
    assert doc.unlisted is False
    assert [v.version for v in doc.versions] == ["1.0.0"]
    only = doc.versions[0]
    assert only.url == DSP0251_URL
    assert only.type == "pdf"
    assert only.published == "2026-10-12"
    assert only.wip is False
    assert only.access == "open" and only.open
    # the DMTF listing applies, so check and refresh can follow it
    assert doc.listing == "dmtf:DSP0251"


def test_ac1_entry_is_the_last_document_after_dsp8013(shipped):
    ids = [d.id for d in shipped.documents]
    assert ids[-1] == "DSP0251", ids[-3:]
    assert ids[-2] == "DSP8013", ids[-3:]
    assert ids.count("DSP0251") == 1


def test_ac1_no_other_document_holds_the_dsp0251_url(shipped):
    holders = []
    for d in shipped.documents:
        if any(v.url == DSP0251_URL for v in d.versions):
            holders.append(d.id)
    assert holders == ["DSP0251"]


# ------------------------------------------------------------------ AC-2


def test_ac2_catalog_reports_1_0_0_as_latest(shipped, capsys):
    code, out, err = _run(capsys, "catalog", "DSP0251")
    assert code == 0, out
    assert err == ""
    lines = out.splitlines()
    assert "document: DSP0251" in lines
    assert f"title: {TITLE}" in lines
    assert "family: pldm (DMTF)" in lines
    assert "access: open" in lines
    assert "fetch: direct" in lines
    assert "latest: 1.0.0" in lines
    assert "listing: dmtf:DSP0251" in lines
    rows = [ln[1:].split("\t") for ln in lines if ln.startswith("\t")]
    assert len(rows) == 1, rows
    assert rows[0][0] == "1.0.0"
    assert rows[0][1] == "2026-10-12"
    assert rows[0][2] == "pdf"
    assert rows[0][3] == "published"
    assert rows[0][4] == DSP0251_URL
    assert rows[0][5] == "open"
    doc = shipped.get("DSP0251")
    assert doc.latest().version == "1.0.0"
    assert doc.latest(include_wip=True).version == "1.0.0"
    assert doc.newest_open().version == "1.0.0"


def test_ac2_listing_line_and_case_insensitive_lookup(shipped, capsys):
    code, out, _ = _run(capsys, "catalog")
    assert code == 0, out
    rows = [ln.split("\t") for ln in out.splitlines()]
    mine = [cells for cells in rows if len(cells) == 7 and cells[1] == "DSP0251"]
    assert len(mine) == 1, out
    assert mine[0][4] == "1.0.0", mine[0]
    assert mine[0][6] == "1.0.0", mine[0]
    # the family filter and a lower-case id reach the same entry
    code, out, _ = _run(capsys, "catalog", "--family", "pldm")
    assert code == 0 and "\tDSP0251\t" in out
    assert shipped.get("dsp0251") is shipped.get("DSP0251")
    code, out, _ = _run(capsys, "catalog", "dsp0251")
    assert code == 0 and "document: DSP0251" in out


# ----------------------------------------------------- AC-3 (catalog keys)


def test_ac3_dsp0248_is_searched_with_dsp0251_only_and_its_notes_say_so(shipped):
    doc = shipped.get("DSP0248")
    assert doc.searched_with == ("DSP0251",)
    notes = doc.notes
    assert "DSP0251" in notes
    assert "1.4.0" in notes
    assert "find" in notes
    # the companion link is one way: a search of DSP0251 does not pull in
    # DSP0248, as IPMI-UPDATE does not pull in IPMI
    assert shipped.get("DSP0251").searched_with == ()
    # the Latest of DSP0248 is the version that moved the definitions
    assert doc.latest().version == "1.4.0"


def test_ac3_catalog_dsp0248_prints_the_note(capsys):
    code, out, _ = _run(capsys, "catalog", "DSP0248")
    assert code == 0, out
    notes = [ln for ln in out.splitlines() if ln.startswith("notes: ")]
    assert len(notes) == 1, out
    assert "DSP0251" in notes[0] and "1.4.0" in notes[0]


# ------------------------------------------------------- AC-5 (the shape)


def _golden_rows():
    """(id, cells, heading) of every Golden Question row, in file order."""
    rows = []
    heading = ""
    columns = None
    for line in GOLDEN.read_bytes().decode("utf-8").splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
            columns = None
            continue
        if not line.startswith("|"):
            columns = None
            continue
        cells = support._cells(line)
        if columns is None:
            columns = cells
            continue
        if support._RULE_RE.match(line):
            continue
        m = re.match(r"^\|\s*(G\d+)\s*\|", line)
        if m and columns[:5] == [
            "#",
            "Question",
            "Document",
            "Where the answer is",
            "Commands",
        ]:
            rows.append((m.group(1), cells, heading))
    assert rows
    return rows


def test_ac5_golden_verifies_dsp0251_1_0_0_by_g103(shipped):
    verified, problems = support.read_golden(GOLDEN, shipped)
    assert problems == []
    assert verified.get("dsp0251") == [("G103", "1.0.0")]
    # the DSP0248 rows are untouched: still G13 and G15 on 1.4.0
    assert verified["dsp0248"] == [("G13", "1.4.0"), ("G15", "1.4.0")]


def test_ac5_g103_sits_under_its_own_group_after_the_redfish_bundles():
    rows = _golden_rows()
    by_id = {qid: (cells, heading) for qid, cells, heading in rows}
    assert "G103" in by_id, sorted(by_id)[-3:]
    cells, heading = by_id["G103"]
    assert cells[2] == "DSP0251 1.0.0", cells[2]
    assert heading not in ("", "Documents", "Redfish bundles", "OpenBMC"), heading
    # the only row of its group, and the group follows the Redfish bundles
    group = [qid for qid, _, h in rows if h == heading]
    assert group == ["G103"], group
    headings = []
    for _, _, h in rows:
        if h not in headings:
            headings.append(h)
    assert headings.index("Redfish bundles") + 1 == headings.index(heading), headings
    # ids stay gap-free and G103 is the highest, so file order is kept
    numbers = sorted(int(qid[1:]) for qid, _, _ in rows)
    assert numbers == list(range(1, len(numbers) + 1))
    assert numbers[-1] == 103
    assert [qid for qid, _, _ in rows if int(qid[1:]) > 24][-1] == "G103"
    # the answer names a page and a section or table, and every command on
    # the document names DSP0251 (the AC-4 rules of M8)
    where = cells[3]
    assert where.startswith("DSP0251 1.0.0"), where
    assert re.search(r"\bpages?\s+\d+", where, re.I), where
    assert re.search(r"\b(section|table)\b", where, re.I), where
    commands = re.findall(r"`([^`]+)`", cells[4])
    assert commands, cells[4]
    for c in commands:
        parts = c.split()
        if parts[0] in {"find", "section", "page", "table", "render"}:
            assert parts[1] == "DSP0251", c


# ------------------------------------------------------------------ AC-6


def _by_family(capsys):
    code, out, err = _run(
        capsys, "catalog", "--table", "--by-family", "--golden", str(GOLDEN)
    )
    assert code == 0, out
    assert err == "", err
    return out


def test_ac6_support_doc_equals_the_generator_output(capsys):
    out = _by_family(capsys)
    marker = (
        "<!-- generated below: catalog --table --by-family "
        "--golden docs/golden-questions.md -->\n\n"
    )
    stored = SUPPORT.read_bytes().decode("utf-8")
    assert "\r" not in stored
    assert marker in stored
    assert stored.split(marker, 1)[1] == out


def test_ac6_dsp0251_row_is_under_pldm_and_pass(capsys):
    out = _by_family(capsys)
    lines = out.splitlines()
    heading = None
    found = None
    for ln in lines:
        if ln.startswith("## "):
            heading = ln[3:]
        elif ln.startswith("| `DSP0251`"):
            assert found is None, "DSP0251 listed twice"
            found = (heading, support._cells(ln))
    assert found is not None, out
    heading, cells = found
    assert heading == "Platform Level Data Model", heading
    assert cells == [f"`DSP0251` {TITLE}", "open", "1.0.0", "PASS", "-"], cells
    # the last row of the PLDM group, the way the catalog lists it last
    ids = [ln.split("`")[1] for ln in lines if ln.startswith("| `")]
    assert ids.index("DSP0251") == ids.index("DSP0218") + 1, ids
    # the flat table marks it Verified by G103 on 1.0.0
    code, flat, _ = _run(capsys, "catalog", "--table", "--golden", str(GOLDEN))
    assert code == 0
    row = [ln for ln in flat.splitlines() if "`DSP0251`" in ln]
    assert len(row) == 1, flat
    flat_cells = support._cells(row[0])
    assert flat_cells[0] == "Platform Level Data Model"
    assert flat_cells[2:6] == ["open", "1.0.0", "direct", "G103 (1.0.0)"], flat_cells


# ------------------------------------------------------------------ AC-7


def test_ac7_every_open_document_including_dsp0251_is_verified(shipped):
    verified, problems = support.read_golden(GOLDEN, shipped)
    assert problems == []
    expected = {d.id.lower() for d in shipped.documents if d.access == "open"}
    assert "dsp0251" in expected
    assert set(verified) == expected


def test_ac7_counts_grew_by_exactly_the_new_entry(shipped):
    """The description says 113 -> 114 documents and 93 -> 94 open ones,
    with the gated count (20) and the 35 families unchanged."""
    docs = shipped.documents
    open_docs = [d for d in docs if d.access == "open"]
    assert len(docs) == 114
    assert len(open_docs) == 94
    assert len(docs) - len(open_docs) == 20
    assert len({d.family for d in docs}) == 35
    assert len({d.id.lower() for d in docs}) == len(docs)
