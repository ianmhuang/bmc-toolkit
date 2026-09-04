"""Reviewer acceptance tests for M10 (feature/m10-publishers): the second
round of publishers in the shipped catalog (AC-1), the UEFI Forum documents
through the Internet Archive (AC-2), the manual entries (AC-3), the Golden
Questions of the new documents (AC-5) and the version promise in the README
and SKILL.md (AC-6).

Black-box through the ``bmcspec`` CLI and the shipped catalog with a
scripted HTTP client; nothing touches the network. Whether a catalog URL
really serves the PDF today cannot be checked here.
"""

import re
import urllib.parse
from pathlib import Path

import pytest

from bmc_toolkit.spec import support
from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main
from bmc_toolkit.spec.fetch import WAYBACK_AVAILABLE
from tests.conftest import PDF_BYTES, ok, wayback_hit

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "docs" / "golden-questions.md"
README = ROOT / "README.md"
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"

# AC-1: fetched straight from the publisher, the current version only.
DIRECT = {
    "CALIPTRA": "ocp-security",
    "OCP-ATTEST": "ocp-security",
    "OCP-NIC": "ocp-nic",
    "SFF-8472": "sff",
    "SFF-8636": "sff",
    "SFF-8024": "sff",
    "SP800-193": "nist",
    "SBMR": "arm-server",
    "SBSA": "arm-server",
    "BBR": "arm-server",
}
# AC-1 as delivered: TCG refuses scripted clients, so these go to the
# Archive (the description's stated deviation); still one open version.
TCG = ("TPM2-P0", "TPM2-P1", "TPM2-P2", "TPM2-P3", "TCG-PFP", "DICE-HW", "DICE-ATT")
TPM_PARTS = {"TPM2-P0", "TPM2-P1", "TPM2-P2", "TPM2-P3"}
# AC-2: newest and previous release from the Archive.
UEFI_FORUM = {"UEFI": "2.11", "ACPI": "6.6", "PI": "1.10"}
# AC-3: listed, never downloaded.
MANUAL = {
    "JESD400-5": "gated",
    "JESD216": "gated",
    "JESD251": "gated",
    "JESD302": "gated",
    "MIPI-I3C-BASIC": "gated",
    "PCIE-BASE": "member",
    "IEEE-1149.1": "member",
    "SES": "member",
    "HPM.1": "member",
    "HPM.2": "member",
    "CXL": "member",
    "PECI": "confidential",
    "APML": "confidential",
    "PFR": "confidential",
    "ASD": "confidential",
    "AST2500": "confidential",
    "AST2600": "confidential",
    "NPCM7XX": "confidential",
    "NPCM8XX": "confidential",
    "SPI-PG": "confidential",
}
NEW_OPEN = list(DIRECT) + list(TCG) + list(UEFI_FORUM)
_ROW_RE = re.compile(r"^\|\s*(G\d+)\s*\|")


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


def run(capsys, *argv, catalog_file=None):
    args = ["--catalog", str(catalog_file)] if catalog_file else []
    code = main([*args, *argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _availability(url: str) -> str:
    return WAYBACK_AVAILABLE + urllib.parse.quote(url, safe=":/?=&")


def _archive(scripted, url: str, timestamp: str = "20260904000000") -> str:
    """Script the Archive for ``url``: the availability API answers with a
    snapshot and the raw-bytes URL of that snapshot serves a PDF."""
    scripted.responses[_availability(url)] = wayback_hit(url, timestamp)
    raw = f"http://web.archive.org/web/{timestamp}id_/{url}"
    scripted.responses[raw] = ok(PDF_BYTES)
    return raw


def _table_rows(out: str) -> dict[str, list[str]]:
    rows = {}
    for line in out.splitlines()[2:]:
        cells = [c.strip() for c in line[2:-2].split(" | ")]
        assert len(cells) == 7, line
        rows[cells[1].split("`")[1]] = cells
    return rows


# ------------------------------------------------------------------ AC-1


def test_ac1_new_families_exist_with_a_publisher(shipped):
    for family in ("tcg", "nist", "arm-server", "ocp-security", "ocp-nic", "uefi"):
        assert family in shipped.families, family
        assert shipped.families[family].publisher.strip(), family
        assert shipped.by_family(family), f"family {family} lists no document"


@pytest.mark.parametrize("doc_id", sorted(DIRECT))
def test_ac1_direct_publishers_hold_one_open_pdf_version(shipped, doc_id):
    doc = shipped.get(doc_id)
    assert doc is not None, doc_id
    assert doc.id == doc_id  # written as the catalog does
    assert doc.family == DIRECT[doc_id]
    assert doc.access == "open" and doc.fetch == "direct"
    assert len(doc.versions) == 1, [v.version for v in doc.versions]
    (ver,) = doc.versions
    assert ver.open and not ver.wip
    assert ver.type == "pdf"
    assert ver.url.startswith("https://"), ver.url
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", ver.published)
    assert doc.latest() is ver and doc.newest_open() is ver


@pytest.mark.parametrize("doc_id", TCG)
def test_ac1_tcg_documents_hold_one_open_version_reached_through_the_archive(
    shipped, doc_id
):
    doc = shipped.get(doc_id)
    assert doc is not None, doc_id
    assert doc.family == "tcg" and doc.access == "open"
    assert doc.fetch in ("direct", "wayback")
    assert len(doc.versions) == 1, [v.version for v in doc.versions]
    (ver,) = doc.versions
    assert ver.open and ver.type == "pdf"
    assert ver.url.startswith("https://trustedcomputinggroup.org/")
    if doc.fetch == "wayback":
        # the user is told why the publisher is not contacted
        assert "archive" in doc.notes.lower(), doc.notes


def test_ac1_tpm_library_parts_are_searched_with_each_other(shipped):
    for part in TPM_PARTS:
        assert set(shipped.get(part).searched_with) == TPM_PARTS - {part}, part


def test_ac1_fetch_of_a_direct_document_uses_the_catalog_url(
    shipped, library, scripted, capsys
):
    ver = shipped.get("SP800-193").latest()
    scripted.responses[ver.url] = ok(PDF_BYTES)
    code, out, _ = run(capsys, "fetch", "SP800-193")
    assert code == 0, out
    assert f"fetched SP800-193 {ver.version} via direct" in out
    assert scripted.calls == [ver.url]
    assert library.find("SP800-193", ver.version) is not None


def test_ac1_fetch_of_a_tcg_document_never_contacts_the_publisher(
    shipped, library, scripted, capsys
):
    doc = shipped.get("DICE-ATT")
    ver = doc.latest()
    raw = _archive(scripted, ver.url)
    code, out, _ = run(capsys, "fetch", "DICE-ATT")
    assert code == 0, out
    assert f"fetched DICE-ATT {ver.version} via wayback" in out
    assert ver.url not in scripted.calls, "the publisher was contacted"
    assert scripted.calls == [_availability(ver.url), raw]
    assert library.find("DICE-ATT", ver.version) is not None


# ------------------------------------------------------------------ AC-2


@pytest.mark.parametrize("doc_id", sorted(UEFI_FORUM))
def test_ac2_uefi_forum_documents_list_the_newest_and_the_previous_release(
    shipped, doc_id
):
    doc = shipped.get(doc_id)
    assert doc is not None, doc_id
    assert doc.family == "uefi" and doc.access == "open"
    assert doc.fetch == "wayback"
    assert len(doc.versions) == 2, [v.version for v in doc.versions]
    assert doc.latest().version == UEFI_FORUM[doc_id]
    previous, newest = doc.versions
    assert newest.version == UEFI_FORUM[doc_id]
    assert previous.published < newest.published
    for v in doc.versions:
        assert v.open and v.type == "pdf" and not v.wip
        assert v.url.startswith("https://uefi.org/"), v.url
    assert "archive" in doc.notes.lower(), doc.notes
    assert "block" in doc.notes.lower() or "refuse" in doc.notes.lower(), doc.notes


@pytest.mark.parametrize("doc_id", sorted(UEFI_FORUM))
def test_ac2_both_uefi_forum_versions_fetch_through_the_archive_only(
    shipped, library, scripted, capsys, doc_id
):
    doc = shipped.get(doc_id)
    previous, newest = doc.versions
    raw_previous = _archive(scripted, previous.url, "20250101000000")
    raw_newest = _archive(scripted, newest.url, "20260101000000")
    code, out, _ = run(capsys, "fetch", doc_id)
    assert code == 0, out
    assert f"fetched {doc_id} {newest.version} via wayback" in out
    code, out, _ = run(capsys, "fetch", doc_id, "--version", previous.version)
    assert code == 0, out
    assert f"fetched {doc_id} {previous.version} via wayback" in out
    assert set(scripted.calls) == {
        _availability(newest.url),
        raw_newest,
        _availability(previous.url),
        raw_previous,
    }
    assert newest.url not in scripted.calls and previous.url not in scripted.calls
    assert library.find(doc_id, newest.version) is not None
    assert library.find(doc_id, previous.version) is not None


def test_ac2_uefi_forum_fetch_fails_cleanly_without_a_snapshot(
    shipped, library, scripted, capsys
):
    from tests.conftest import wayback_miss

    ver = shipped.get("ACPI").latest()
    scripted.responses[_availability(ver.url)] = wayback_miss()
    code, out, _ = run(capsys, "fetch", "ACPI")
    assert code == 2, out
    assert f"failed ACPI {ver.version}" in out
    assert "no Wayback snapshot" in out
    assert ver.url not in scripted.calls
    assert library.find("ACPI", ver.version) is None


# ------------------------------------------------------------------ AC-3


@pytest.mark.parametrize("doc_id", sorted(MANUAL))
def test_ac3_manual_entries_carry_tier_reason_and_no_url(shipped, doc_id):
    doc = shipped.get(doc_id)
    assert doc is not None, doc_id
    assert doc.id == doc_id
    assert doc.fetch == "manual"
    assert doc.access == MANUAL[doc_id]
    assert doc.notes.strip(), f"{doc_id}: no reason given"
    assert all(v.url == "" for v in doc.versions), doc_id
    assert doc.newest_open() is None


def test_ac3_no_manual_document_of_the_shipped_catalog_carries_a_url(shipped):
    manual = [d for d in shipped.documents if d.fetch == "manual"]
    assert {d.id for d in manual} >= set(MANUAL)
    for doc in manual:
        assert doc.access != "open", doc.id
        for v in doc.versions:
            assert v.url == "", (doc.id, v.version)


def test_ac3_fetch_all_skips_manual_entries_and_touches_only_the_open_url(
    tmp_path, library, scripted, capsys
):
    url = "https://example.test/open.pdf"
    text = (
        "schema_version = 1\n\n"
        '[families.jedec]\ntitle = "JEDEC"\npublisher = "JEDEC"\n\n'
        '[families.x]\ntitle = "X"\npublisher = "X"\n\n'
        '[[documents]]\nid = "JESD216"\nfamily = "jedec"\ntitle = "SFDP"\n'
        'access = "gated"\nfetch = "manual"\nnotes = "registration"\n\n'
        '[[documents]]\nid = "AST2600"\nfamily = "x"\ntitle = "Datasheet"\n'
        'access = "confidential"\nfetch = "manual"\nnotes = "NDA"\n\n'
        '[[documents]]\nid = "OPEN"\nfamily = "x"\ntitle = "An open one"\n'
        'access = "open"\nfetch = "direct"\n\n'
        f'[[documents.versions]]\nversion = "1.0"\nurl = "{url}"\n'
        'type = "pdf"\npublished = "2026-01-01"\n'
    )
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    scripted.responses[url] = ok(PDF_BYTES)
    code, out, _ = run(capsys, "fetch", "--all", catalog_file=path)
    assert code == 0, out
    assert scripted.calls == [url]
    assert "fetched OPEN 1.0 via direct" in out
    assert "summary: fetched 1, skipped 0, failed 0" in out
    assert "JESD216" not in out and "AST2600" not in out


def test_ac3_fetch_of_a_manual_document_prints_the_add_instruction_offline(
    library, scripted, capsys
):
    code, out, _ = run(capsys, "fetch", "PECI")
    assert code == 2, out
    assert "add FILE --document PECI" in out
    assert scripted.calls == []


def test_ac3_catalog_prints_the_add_instruction_and_no_url(library, capsys):
    for doc_id in ("JESD216", "PCIE-BASE", "AST2600"):
        code, out, _ = run(capsys, "catalog", doc_id)
        assert code == 0, out
        assert "fetch: manual" in out
        assert f"add FILE --document {doc_id}" in out
        assert "https://" not in out and "http://" not in out
        assert f"access: {MANUAL[doc_id]}" in out


def test_ac3_support_table_names_the_tier_and_manual_drop_in(library, capsys):
    code, out, _ = run(capsys, "catalog", "--table")
    assert code == 0, out
    rows = _table_rows(out)
    for doc_id, tier in MANUAL.items():
        cells = rows[doc_id]
        assert cells[2] == tier, (doc_id, cells)
        assert cells[3] == "-", (doc_id, cells)
        assert cells[4] == "manual (Drop-in)", (doc_id, cells)


def test_ac3_check_reports_manual_entries_as_never_fetched(library, scripted, capsys):
    """`check` over the shipped catalog: the manual entries are named on the
    manual line with their tier and no listing page is asked for them."""
    code, out, _ = run(capsys, "check")
    assert code == 0, out
    manual_lines = [ln for ln in out.splitlines() if ln.startswith("unchecked (manual):")]
    assert len(manual_lines) == 1, out
    for doc_id, tier in MANUAL.items():
        assert f"{doc_id} ({tier})" in manual_lines[0], doc_id


# ------------------------------------------------------------------ AC-5


@pytest.fixture(scope="module")
def golden_rows():
    """(id, cells) of every question row of the Golden Questions file."""
    rows = []
    for line in GOLDEN.read_bytes().decode("utf-8").splitlines():
        m = _ROW_RE.match(line)
        if m:
            rows.append((m.group(1), support._cells(line)))
    assert rows
    return rows


def _entries(cell: str) -> list[tuple[str, str]]:
    pairs = []
    for entry in cell.split(";"):
        entry = entry.strip()
        if entry and entry != "-":
            doc_id, _, version = entry.partition(" ")
            pairs.append((doc_id, version.strip()))
    return pairs


def test_ac5_one_new_row_per_new_document_on_the_version_checked(shipped, golden_rows):
    new_rows = [
        (qid, cells) for qid, cells in golden_rows if 81 <= int(qid[1:]) <= 100
    ]  # M9 added G101 and G102 for the bundles
    assert [qid for qid, _ in new_rows] == [f"G{n}" for n in range(81, 101)]
    covered = {}
    for qid, cells in new_rows:
        entries = _entries(cells[2])
        assert len(entries) == 1, (qid, cells[2])
        doc_id, version = entries[0]
        assert doc_id in NEW_OPEN, (qid, doc_id)
        assert doc_id not in covered, f"{qid}: {doc_id} already has {covered[doc_id]}"
        covered[doc_id] = qid
        doc = shipped.get(doc_id)
        assert doc.find_version(version) is not None, (qid, doc_id, version)
        assert version == doc.latest().version, (qid, doc_id, version)
        assert re.search(r"\bpages?\s+\d+", cells[3]), qid
        commands = re.findall(r"`([^`]+)`", cells[4])
        assert commands, qid
        assert any(c.split()[1] == doc_id for c in commands if len(c.split()) > 1), qid
    assert set(covered) == set(NEW_OPEN)


def test_ac5_support_table_marks_the_twenty_new_documents_verified(shipped, capsys):
    code = main(["catalog", "--table", "--golden", str(GOLDEN)])
    captured = capsys.readouterr()
    assert code == 0, captured.out
    assert captured.err == "", captured.err
    rows = _table_rows(captured.out)
    for doc_id in NEW_OPEN:
        verified = rows[doc_id][5]
        latest = shipped.get(doc_id).latest().version
        assert verified != "-", doc_id
        assert f"({latest})" in verified, (doc_id, verified)
        ids = re.findall(r"G(\d+)", verified)
        assert ids and all(int(n) >= 81 for n in ids), (doc_id, verified)


def test_ac5_g52_no_longer_says_section_finds_nothing(golden_rows):
    by_id = dict(golden_rows)
    commands_cell = by_id["G52"][4]
    assert "finds nothing" not in commands_cell.lower()
    assert "section DSP0284" in commands_cell


# ------------------------------------------------------------------ AC-6


def test_ac6_readme_states_the_version_promise_per_publisher():
    # since 1.0.0 the Source Catalog section is docs/CATALOG.md, whole
    raw = (ROOT / "docs" / "CATALOG.md").read_bytes()
    assert b"\r" not in raw
    section = raw.decode("utf-8")
    assert section.startswith("# The Source Catalog\n")
    assert "full version history" in section
    assert "DMTF" in section and "NVM Express" in section
    assert "current version" in section
    for publisher in ("Intel", "OCP", "SFF", "TCG", "NIST", "Arm"):
        assert publisher in section, publisher
    assert "Internet Archive" in section
    assert "UEFI" in section
    assert "never downloaded" in section


def test_ac6_skill_says_the_same_in_its_catalog_paragraph():
    text = SKILL.read_bytes().decode("utf-8")
    assert b"\r" not in SKILL.read_bytes()
    assert "Version coverage" in text
    assert "full" in text and "version history" in text
    assert "Internet Archive" in text
    assert "linux" in text
