"""Reviewer acceptance tests for M8 (feature/golden-m8): the shipped Golden
Questions file covers every open, extractable document (AC-1), names catalog
versions (AC-2), numbers questions without gaps (AC-3), cites a page and a
command per row (AC-4), records document defects as catalog limits that the
Support Level table prints (AC-5), and keeps the file's shape and the
existing rows (AC-6).

Only the shipped catalog and the shipped Markdown file are read; no test
touches the network or the Library. The factual content of an answer (that
the cited page really says what the row claims) cannot be checked here.
"""

import re
from pathlib import Path

import pytest

from bmc_toolkit.spec import support
from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "docs" / "golden-questions.md"

# The two ZIP bundles `extract` does not unpack yet (M9); excluded by AC-1.
ZIP_BUNDLES = {"DSP8011", "DSP8013"}

# The subcommands AC-4 accepts in a Commands cell.
SUBCOMMANDS = {
    "find",
    "section",
    "page",
    "table",
    "render",
    "schema",
    "grep",
    "code",
    "clone",
}

# The sixteen documents verified before M8 (M3-M6), by catalog id.
M8A_VERIFIED = {
    "IPMI",
    "IPMI-UPDATE",
    "DCMI",
    "DSP0236",
    "DSP0237",
    "DSP0239",
    "DSP0240",
    "DSP0245",
    "DSP0248",
    "DSP0267",
    "DSP0274",
    "DSP8010",
    "DSP0266",
    "NVME-MI",
    "DC-SCM",
    "UM10204",
}

# Known Limits recorded at M8a; AC-5 says none is removed.
M8A_LIMITS = {
    "IPMI": "Table numbers are missing from the PDF's text layer",
    "DC-SCM": "Tables are images",
    "CMIS": "Tables have no ruling lines",
    "DSP0274": "Most tables have no ruling lines",
    "DSP0239": "One page holds an emoji that breaks pdfium's character order",
    "DSP8011": "ZIP of registries",
    "DSP8013": "ZIP of profiles",
}

_ROW_RE = re.compile(r"^\|\s*(G\d+)\s*\|")


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def text():
    return GOLDEN.read_bytes().decode("utf-8")


@pytest.fixture(scope="module")
def rows(text):
    """Question rows as (id, cells, heading); cells stripped, outer pipes off.

    Only rows of a table whose header has the five Golden Questions columns
    are collected, so the Named table checks table is skipped.
    """
    out = []
    heading = ""
    columns = None
    for line in text.splitlines():
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
        m = _ROW_RE.match(line)
        if not m:
            continue
        expected = ["#", "Question", "Document", "Where the answer is", "Commands"]
        assert columns[:5] == expected, line
        assert len(cells) >= 5, line
        out.append((m.group(1), cells, heading))
    assert out, "no question rows found"
    return out


def _number(qid: str) -> int:
    return int(qid[1:])


def _entries(document_cell: str) -> list[tuple[str, str]]:
    """(id, version) pairs of a Document cell; empty for '-'."""
    pairs = []
    for entry in document_cell.split(";"):
        entry = entry.strip()
        if not entry or entry == "-":
            continue
        doc_id, _, version = entry.partition(" ")
        pairs.append((doc_id, version.strip()))
    return pairs


def _open_documents(catalog):
    return [d for d in catalog.documents if d.access == "open"]


# ------------------------------------------------------------------ AC-1


def test_ac1_every_open_document_but_the_zip_bundles_has_a_question(catalog):
    verified, problems = support.read_golden(GOLDEN, catalog)
    assert problems == []
    expected = {d.id for d in _open_documents(catalog)} - ZIP_BUNDLES
    missing = sorted(doc_id for doc_id in expected if not verified.get(doc_id.lower()))
    assert missing == [], f"open documents without a Golden Question: {missing}"
    # the two ZIP bundles stay unverified until M9
    for doc_id in ZIP_BUNDLES:
        assert doc_id.lower() not in verified
    # the M8a set stays verified
    assert {d.upper() for d in verified} >= M8A_VERIFIED


def test_ac1_support_table_prints_verified_for_every_open_document(catalog, capsys):
    code = main(["catalog", "--table", "--golden", str(GOLDEN)])
    captured = capsys.readouterr()
    assert code == 0, captured.out
    assert captured.err == "", captured.err
    lines = captured.out.splitlines()
    assert lines[0].startswith("| Family | Document | ")
    cells_by_id = {}
    for ln in lines[2:]:
        cells = [c.strip() for c in ln[2:-2].split(" | ")]
        assert len(cells) == 7, ln
        cells_by_id[cells[1].split("`")[1]] = cells
    for doc in _open_documents(catalog):
        verified = cells_by_id[doc.id][5]
        if doc.id in ZIP_BUNDLES:
            assert verified == "-", doc.id
        else:
            assert verified != "-", f"{doc.id} not Verified"
            assert re.fullmatch(r"G\d+(, G\d+)*", verified), (doc.id, verified)


# ------------------------------------------------------------------ AC-2


def test_ac2_every_document_entry_names_a_catalog_id_and_a_listed_version(catalog, rows):
    for qid, cells, _ in rows:
        entries = _entries(cells[2])
        if not entries:
            assert cells[2].strip() == "-", (qid, cells[2])
            continue
        for doc_id, version in entries:
            doc = catalog.get(doc_id)
            assert doc is not None, f"{qid}: unknown document {doc_id!r}"
            assert doc.id == doc_id, f"{qid}: id {doc_id!r} not written as the catalog does"
            assert version, f"{qid}: {doc_id} has no version"
            assert doc.find_version(version) is not None, (
                f"{qid}: {doc_id} version {version!r} is not in the catalog"
            )


def test_ac2_new_questions_are_asked_on_the_latest_version(catalog, rows):
    """Rows added by M8 (G25 and later) name the catalog's Latest.

    Where Latest is a gated version the tool cannot download (PMBUS-I and
    PMBUS-II 1.5), the newest open version is accepted: the AC text says
    Latest, the shipped rows name 1.3.1; see the review findings.
    """
    new_rows = [(qid, cells) for qid, cells, _ in rows if _number(qid) > 24]
    assert new_rows, "M8 adds questions numbered from G25"
    for qid, cells in new_rows:
        for doc_id, version in _entries(cells[2]):
            doc = catalog.get(doc_id)
            latest = doc.latest()
            newest_open = doc.newest_open()
            accepted = {latest.version}
            if newest_open is not None:
                accepted.add(newest_open.version)
            assert version in accepted, (
                f"{qid}: {doc_id} {version!r} is neither Latest {latest.version!r} "
                f"nor the newest open version"
            )
    # every open document new to M8 got its row on Latest or newest open
    covered_new = {doc_id for _, cells in new_rows for doc_id, _ in _entries(cells[2])}
    expected_new = {d.id for d in _open_documents(catalog)} - ZIP_BUNDLES - M8A_VERIFIED
    assert covered_new >= expected_new, sorted(expected_new - covered_new)


def test_ac2_ipmi_rows_name_both_ipmi_and_the_errata(rows):
    ipmi_rows = [
        (qid, cells)
        for qid, cells, _ in rows
        if any(doc_id == "IPMI" for doc_id, _ in _entries(cells[2]))
    ]
    assert ipmi_rows
    for qid, cells in ipmi_rows:
        ids = {doc_id for doc_id, _ in _entries(cells[2])}
        assert {"IPMI", "IPMI-UPDATE"} <= ids, (qid, cells[2])


# ------------------------------------------------------------------ AC-3


def test_ac3_question_ids_are_unique_gap_free_and_continue_past_g24(rows):
    ids = [qid for qid, _, _ in rows]
    assert all(re.fullmatch(r"G[1-9]\d*", qid) for qid in ids)
    assert len(ids) == len(set(ids)), "duplicate question id"
    numbers = sorted(_number(qid) for qid in ids)
    assert numbers == list(range(1, len(numbers) + 1)), "gap in the numbering"
    assert numbers[-1] > 24, "no question numbered past the existing G1-G24"


# ------------------------------------------------------------------ AC-4


def test_ac4_new_rows_cite_a_page_and_a_locator(rows):
    locator = re.compile(
        r"\b(section|sections|table|tables|figure|figures|appendix|clause)\b", re.I
    )
    page = re.compile(r"\bpages?\s+\d+", re.I)
    for qid, cells, _ in rows:
        if _number(qid) <= 24:
            continue
        where = cells[3]
        assert where.strip() and where.strip() != "-", qid
        assert locator.search(where), f"{qid}: no section, table or figure named"
        assert page.search(where), f"{qid}: no physical PDF page named"
        # the cell starts by naming the document, not with the locator
        assert not locator.match(where.strip()), f"{qid}: cell does not open with the document"


def test_ac4_new_rows_list_a_bmcspec_command_that_exists(rows):
    for qid, cells, _ in rows:
        if _number(qid) <= 24:
            continue
        commands = re.findall(r"`([^`]+)`", cells[4])
        assert commands, f"{qid}: no command in backticks"
        heads = [c.split()[0] for c in commands if c.split()]
        assert any(h in SUBCOMMANDS for h in heads), (qid, commands)
        # a command on a document names the document id as its first argument
        doc_ids = {doc_id for doc_id, _ in _entries(cells[2])}
        for c in commands:
            parts = c.split()
            if len(parts) >= 2 and parts[0] in {"find", "section", "page", "table", "render"}:
                assert parts[1] in doc_ids, f"{qid}: {c!r} does not name the row's document"


# ------------------------------------------------------------------ AC-5


def test_ac5_m8a_limits_are_kept_and_defects_named_in_rows_are_limits(catalog, rows):
    for doc_id, fragment in M8A_LIMITS.items():
        assert fragment in catalog.get(doc_id).limits, doc_id
    flagged = {
        "no ruling lines": "ruling lines",
        "tables are images": "images",
        "bookmarks are anchors": "anchors",
    }
    for qid, cells, _ in rows:
        blob = (cells[3] + " " + cells[4]).lower()
        for phrase, limit_word in flagged.items():
            if phrase not in blob:
                continue
            for doc_id, _ in _entries(cells[2]):
                doc = catalog.get(doc_id)
                assert limit_word in doc.limits.lower(), (
                    f"{qid} says {phrase!r} about {doc_id} but its limits do not"
                )


def test_ac5_limits_are_not_repeated_in_notes_and_print_in_the_table(catalog, capsys):
    with_limits = [d for d in catalog.documents if d.limits]
    assert len(with_limits) > len(M8A_LIMITS), "M8 records the defects it met"
    for doc in with_limits:
        assert doc.limits.strip()
        assert doc.limits not in doc.notes, doc.id
    code = main(["catalog", "--table"])
    captured = capsys.readouterr()
    assert code == 0
    printed = {}
    for ln in captured.out.splitlines()[2:]:
        cells = [c.strip() for c in ln[2:-2].split(" | ")]
        printed[cells[1].split("`")[1]] = cells[6]
    for doc in catalog.documents:
        expected = doc.limits.replace("|", "\\|") if doc.limits else "-"
        assert printed[doc.id] == expected, doc.id


# ------------------------------------------------------------------ AC-6


def test_ac6_file_is_lf_english_markdown_with_a_heading_per_group(text, rows, catalog):
    raw = GOLDEN.read_bytes()
    assert b"\r" not in raw, "CRLF line ending"
    assert text.startswith("# Golden Questions")
    # no non-ASCII beyond the odd typographic mark: the file is English
    assert not re.search(r"[぀-ヿ一-鿿]", text), "CJK text in the file"
    # rows added by M8 sit under headings of their own, in catalog order
    order = {d.id: i for i, d in enumerate(catalog.documents)}
    first_index = {}
    for qid, cells, heading in rows:
        if _number(qid) <= 24:
            continue
        assert heading not in ("", "Documents", "OpenBMC"), (qid, heading)
        entries = _entries(cells[2])
        assert entries, qid
        first_index.setdefault(heading, order[entries[0][0]])
    assert len(first_index) >= 2
    seen = list(first_index.values())
    assert seen == sorted(seen), f"groups not in catalog order: {list(first_index)}"


def test_ac6_existing_rows_g1_to_g24_keep_their_content(rows):
    by_id = {qid: cells for qid, cells, _ in rows}
    assert {f"G{n}" for n in range(1, 25)} <= set(by_id)
    # spot checks on question text that must not move
    assert by_id["G1"][1] == "Get Device ID: NetFn, command code, response fields"
    assert by_id["G9"][1] == "MCTP message type values for PLDM, NVMe-MI, SPDM"
    assert by_id["G12"][1] == "PLDM type numbers"
    assert by_id["G24"][1].startswith("Which pldm code sends RequestUpdate")
    assert by_id["G19"][2] == "NVME-MI 2.1"
    # G9 and G12 no longer name `table` on pages without ruling lines
    for qid in ("G9", "G12"):
        commands = re.findall(r"`([^`]+)`", by_id[qid][4])
        heads = {c.split()[0] for c in commands}
        assert "table" not in heads, (qid, commands)
        assert "page" in heads, (qid, commands)
