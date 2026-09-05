"""Reviewer acceptance tests for the M9 catalog, Golden Questions, docs
and refresh follow-ups (AC-5, AC-6, AC-11 to AC-15): the shipped catalog's
limits and notes, the two bundle questions, what the README and SKILL.md
say, the refresh text scan."""

import re
from pathlib import Path

import pytest

from bmc_toolkit.spec import listing as L
from bmc_toolkit.spec import refresh as R
from bmc_toolkit.spec import support
from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main
from tests.conftest import ok

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "docs" / "golden-questions.md"
README = ROOT / "README.md"
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"

# The documents whose Golden page the description says table reads now.
READS_WITH_TABLE = {
    "DSP0239": "G9",
    "DSP0245": "G12",
    "DSP0274": "G16",
    "DSP0256": "G50",
    "DSP0242": "G59",
    "DSP0257": "G63",
    "DSP0275": "G65",
    "DSP0277": "G67",
    "DSP0289": "G70",
    "DSP0268": "G75",
    "DSP2046": "G76",
    "DSP0270": "G77",
    "DSP0272": "G78",
    "DSP2053": "G79",
}


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


@pytest.fixture(scope="module")
def golden_rows():
    """Question id -> the five cells of its row."""
    rows = {}
    for line in GOLDEN.read_text("utf-8").splitlines():
        m = re.match(r"^\|\s*(G\d+)\s*\|", line)
        if m:
            rows[m.group(1)] = support._cells(line)
    assert rows
    return rows


def commands(cell: str) -> set[str]:
    return {c.split()[0] for c in re.findall(r"`([^`]+)`", cell)}


# ------------------------------------------------------------------ AC-6


def test_ac6_the_no_ruling_lines_limit_is_gone_where_table_reads(shipped, golden_rows):
    for doc in shipped.documents:
        assert "page and render, not table" not in (doc.limits or ""), doc.id
    for doc_id, qid in READS_WITH_TABLE.items():
        row = golden_rows[qid]
        assert row[2].startswith(doc_id), (qid, row[2])
        assert "table" in commands(row[4]), (qid, row[4])
        assert f"table {doc_id} --page" in row[4], (qid, row[4])
        limits = (shipped.get(doc_id).limits or "").lower()
        if "ruling lines" in limits:  # the M8a wording that is kept
            assert "cell boxes" in limits and "table reads" in limits, (doc_id, limits)
    assert "emoji" in shipped.get("DSP0239").limits
    assert "ruling lines" not in shipped.get("DSP0239").limits
    long_table = shipped.get("DSP2053").limits.lower()
    assert "one property table" in long_table and "--all-rows" in long_table


def test_ac6_support_table_no_longer_carries_the_sentence(capsys):
    code = main(["catalog", "--table", "--golden", str(GOLDEN)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "page and render, not table" not in out


# ----------------------------------------------------------------- AC-11


def test_ac11_bundle_questions_verify_dsp8011_and_dsp8013(shipped, golden_rows):
    verified, problems = support.read_golden(GOLDEN, shipped)
    assert problems == []
    assert verified["dsp8011"] == [("G101", "2026.1")]
    assert verified["dsp8013"] == [("G102", "2026.1")]
    g101 = golden_rows["G101"]
    assert g101[2] == "DSP8011 2026.1"
    assert "#/Messages/" in g101[3] and "Base" in g101[3]
    assert "registry DSP8011 Base " in g101[4]
    g102 = golden_rows["G102"]
    assert g102[2] == "DSP8013 2026.1"
    assert "ReadRequirement" in g102[3]
    for value in ("Mandatory", "Supported", "Recommended", "IfImplemented"):
        assert value in g102[3]
    assert "schema DSP8013 RedfishInteroperabilityProfile" in g102[4]
    every_open = {d.id.lower() for d in shipped.documents if d.access == "open"}
    assert set(verified) == every_open


def test_ac11_bundle_limits_say_what_still_holds(shipped):
    dsp8011 = shipped.get("DSP8011").limits
    assert dsp8011.startswith("ZIP of registries")
    assert "registry" in dsp8011 and "privilege" in dsp8011.lower()
    assert "until" not in dsp8011
    dsp8013 = shipped.get("DSP8013").limits
    assert dsp8013.startswith("ZIP of profiles")
    assert "schema" in dsp8013 and "until" not in dsp8013


def test_ac11_support_table_marks_the_bundles_verified(capsys):
    code = main(["catalog", "--table", "--golden", str(GOLDEN)])
    out = capsys.readouterr().out
    assert code == 0, out
    cells_by_id = {}
    for ln in out.splitlines()[2:]:
        cells = [c.strip() for c in ln[2:-2].split(" | ")]
        if len(cells) == 7 and "`" in cells[1]:
            cells_by_id[cells[1].split("`")[1]] = cells
    assert cells_by_id["DSP8011"][5] == "G101 (2026.1)"
    assert cells_by_id["DSP8013"][5] == "G102 (2026.1)"


# ------------------------------------------------------------ AC-5, AC-12


def test_ac5_skill_and_readme_describe_both_drawings():
    skill = SKILL.read_text("utf-8")
    readme = README.read_text("utf-8")
    assert "no ruled table" not in skill and "no ruled table" not in readme
    assert "Tables without ruling lines are not detected" not in readme
    definition = skill[skill.index("**Logical Table**") :]
    definition = definition[: definition.index("**Code Tree**")]
    assert "`ruled`" in definition and "`cells`" in definition
    step5 = skill[skill.index("run `table DOC --page N`") :]
    step5 = step5[: step5.index("6. When a hit")]
    assert "`cells`" in step5
    assert "empty" in step5 and "`page`" in step5
    assert "no table on page N" in step5
    table_row = next(ln for ln in skill.splitlines() if ln.startswith("| `table DOC"))
    assert "cells (no ruling lines)" in table_row and "--all-rows" in table_row
    assert "no table on page N" in table_row
    # since 1.0.0 the command paragraphs live in docs/COMMANDS.md
    commands = (ROOT / "docs" / "COMMANDS.md").read_text("utf-8")
    assert "no ruled table" not in commands
    paragraph = commands[commands.index("`table` prints every table") :]
    paragraph = paragraph[: paragraph.index("\n\n")]
    assert "`ruled`" in paragraph and "`cells`" in paragraph
    assert "--all-rows" in paragraph
    # round 1, F4: the dependency reason for pdfplumber names both drawings
    reason = readme[readme.index("- `pdfplumber` (MIT)") :]
    reason = reason[: reason.index("\n\n")]
    assert "cell boxes" in reason
    assert "of ruled tables" not in reason


def test_ac12_registry_command_and_layout_are_documented():
    skill = SKILL.read_text("utf-8")
    readme = README.read_text("utf-8")
    registry_row = next(
        ln for ln in skill.splitlines() if ln.startswith("| `registry DOC")
    )
    assert "#/Messages/<Key>" in registry_row and "verbatim" in registry_row
    assert "**Registries bundle**" in skill and "`registries/`" in skill
    assert "DSP8013" in skill
    cite_rules = skill[skill.index("A registry answer cites") :]
    assert "verbatim" in cite_rules[:400]
    # since 1.0.0 the command paragraphs and the network list are in
    # docs/COMMANDS.md and the Library layout in docs/LIBRARY.md
    commands = (ROOT / "docs" / "COMMANDS.md").read_text("utf-8")
    layout = (ROOT / "docs" / "LIBRARY.md").read_text("utf-8")
    assert "`registry` reads the Redfish message registries bundle" in commands
    assert "`registries/`" in layout
    assert "DSP8013" in readme
    network = commands[commands.index("From the registries bundle (DSP8011)") :]
    network = network[: network.index("\n- ")]
    assert "privilege registries" in network and "stay in the ZIP" in network
    assert "registry DSP8011 Base" in readme


# ----------------------------------------------------------------- AC-13


def test_ac13_refresh_says_insert_not_append(capsys):
    assert "inserts each" in R.__doc__
    assert "appends" not in R.__doc__
    with pytest.raises(SystemExit):
        main(["refresh", "--help"])
    out = capsys.readouterr().out
    assert "insert the new entries into the catalog, in publication order" in out
    assert "append" not in out
    skill = SKILL.read_text("utf-8")
    refresh_row = next(ln for ln in skill.splitlines() if ln.startswith("| `refresh"))
    assert "inserts" in refresh_row and "appends" not in refresh_row


# ----------------------------------------------------------------- AC-14


CATALOG = """schema_version = 1

[families.mctp]
title = "MCTP"
publisher = "DMTF"

[[documents]]
id = "DSP0236"
family = "mctp"
title = "MCTP Base"
access = "open"
fetch = "direct"
listing = "dmtf:DSP0236"

[[documents.versions]]
version = "1.3.0"  # the first release
url = "https://example.test/DSP0236_1.3.0.pdf"
type = "pdf"
published = '2020-01-01'

[[documents.versions]]
version = '1.3.2'   # a literal string
url = "https://example.test/DSP0236_1.3.2.pdf"
type = "pdf"
published = "2022-01-01" # re-issued

[[documents.versions]]
version = "1.3.3"
url = "https://example.test/DSP0236_1.3.3.pdf"
type = "pdf"
published = "2024-03-25"
"""


def _seen(version, published):
    return L.Seen(version, f"https://example.test/DSP0236_{version}.pdf", published)


def test_ac14_commented_and_literal_lines_place_a_block_correctly(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(CATALOG, "utf-8", newline="")
    R.append_versions(path, "DSP0236", [_seen("1.3.1", "2021-01-01")])
    text = path.read_text("utf-8")
    order = [
        text.index('version = "1.3.0"'),
        text.index('version = "1.3.1"'),
        text.index("version = '1.3.2'"),
        text.index('version = "1.3.3"'),
    ]
    assert order == sorted(order)
    assert "# a literal string" in text and "# re-issued" in text
    assert load_catalog(path).get("DSP0236").latest().version == "1.3.3"


@pytest.mark.parametrize(
    "bad",
    [
        'version = "1.3\\"3"',  # an escape sequence
        'version = """1.3.3"""',  # a multi-line string
    ],
)
def test_ac14_an_unreadable_block_leaves_the_file_untouched(tmp_path, bad):
    path = tmp_path / "catalog.toml"
    broken = CATALOG.replace('version = "1.3.3"', bad)
    path.write_text(broken, "utf-8", newline="")
    assert load_catalog(path).get("DSP0236") is not None  # valid TOML still
    with pytest.raises(R.UnreadableBlock) as info:
        R.append_versions(path, "DSP0236", [_seen("1.3.1", "2021-01-01")])
    assert bad in str(info.value)
    assert path.read_bytes() == broken.encode("utf-8")


def _dmtf_listing():
    html = (
        "<html><body><h1>All Published Versions of DSP0236</h1>"
        "<table><thead><tr><th>Version</th><th>Title</th><th>Publication Date</th>"
        "<th>Comments</th></tr></thead><tbody>"
        '<tr><td>1.3.4</td><td><a href="https://example.test/DSP0236_1.3.4.pdf">'
        "MCTP Base</a></td><td>3 Aug 2026</td><td>Standard</td></tr>"
        "</tbody></table></body></html>"
    )
    return ok(html.encode(), ctype="text/html")


def test_ac14_refresh_write_reports_the_document_and_moves_on(
    tmp_path, library, scripted, capsys
):
    path = tmp_path / "catalog.toml"
    broken = CATALOG.replace('version = "1.3.3"', 'version = "1.3\\"3"')
    path.write_text(broken, "utf-8", newline="")
    scripted.responses["https://www.dmtf.org/dsp/DSP0236"] = _dmtf_listing()
    code = main(["--catalog", str(path), "refresh", "DSP0236", "--write"])
    out = capsys.readouterr().out
    assert code == 0, out
    (skipped,) = [ln for ln in out.splitlines() if ln.startswith("skipped DSP0236")]
    assert "cannot be placed" in skipped
    assert 'version = "1.3\\"3"' in skipped
    assert "Traceback" not in out
    assert path.read_bytes() == broken.encode("utf-8")


# ----------------------------------------------------------------- AC-15


def test_ac15_f3_dsp0284_limit_keeps_anchor_and_drops_finds_nothing(shipped):
    limits = shipped.get("DSP0284").limits
    assert "anchor" in limits
    assert "finds nothing" not in limits
    assert "5.2" in limits and "5.1.3" in limits
    assert "single letters" in limits  # the M8 wording stays


def test_ac15_f4_limits_for_the_defects_named_in_golden_rows(shipped):
    for doc_id in ("OCP-ATTEST", "DICE-HW"):
        limits = shipped.get(doc_id).limits
        assert "bookmarks" in limits, doc_id
        assert "contents page" in limits or "section" in limits, doc_id
    assert "margin" in shipped.get("SP800-193").limits
    assert "rotated" in shipped.get("SP800-193").limits.lower()
    nic = shipped.get("OCP-NIC")
    assert "line-numbered" in nic.limits
    assert "line-numbered" not in (nic.notes or "")
    assert "line number" in nic.limits.lower()


def test_ac15_f5_sff_notes_warn_about_the_download_number(shipped):
    for doc_id in ("SFF-8472", "SFF-8636", "SFF-8024"):
        notes = shipped.get(doc_id).notes
        assert "members.snia.org/document/dl/<n>" in notes, doc_id
        assert "current revision" in notes, doc_id
        assert "newer revision" in notes, doc_id
        assert "refresh" in notes, doc_id
