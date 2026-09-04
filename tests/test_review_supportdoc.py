"""Reviewer acceptance tests for the shipped files of feature/support-doc:
docs/SUPPORT.md is the generated per-family table (AC-6), the README status
paragraph agrees with the catalog (AC-7), G102 lists every ReadRequirement
value (AC-8), and the new flag is documented (AC-9).

Runs against the shipped catalog and docs; no network, no Library.
"""

import re
from pathlib import Path

import pytest

from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "docs" / "SUPPORT.md"
GOLDEN = ROOT / "docs" / "golden-questions.md"
README = ROOT / "README.md"
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"

MARKER = (
    "<!-- generated below: catalog --table --by-family "
    "--golden docs/golden-questions.md -->"
)
HEADER = "| Document | Access | Latest | Fetch | Verified | Known limit |"


def run(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture
def shipped():
    return load_catalog()


@pytest.fixture
def generated(capsys):
    code, out, err = run(
        capsys, "catalog", "--table", "--by-family", "--golden", str(GOLDEN)
    )
    assert code == 0, out
    assert err == ""
    return out


# ---------------------------------------------------------------- AC-6


def test_ac6_support_doc_has_a_header_the_marker_and_the_generated_output(generated):
    assert SUPPORT.is_file()
    text = SUPPORT.read_text(encoding="utf-8")
    assert text.count(MARKER) == 1
    header, body = text.split(MARKER + "\n", 1)
    # the hand-written part is a header, not a table: it explains how to
    # regenerate and names the columns
    assert header.startswith("# Support Level")
    assert "catalog --table --by-family --golden docs/golden-questions.md" in header
    assert HEADER not in header and "## " not in header
    for column in ("Document", "Access", "Latest", "Fetch", "Verified", "Known limit"):
        assert f"**{column}**" in header, column
    # exactly the command's output after the marker line
    assert body.lstrip("\n") == generated
    assert body.startswith("\n## ")
    assert not text.endswith("\n\n")


def test_ac6_header_describes_fetch_of_a_gated_latest_as_the_tool_behaves():
    """Round 1 F1: the Access bullet must not say plain ``fetch`` takes the
    newest open version of an ``open (latest gated)`` document; ``fetch DOC``
    refuses it (exit 2, names ``--version X``) and only ``fetch --all`` takes
    the newest open one."""
    header = SUPPORT.read_text(encoding="utf-8").split(MARKER, 1)[0]
    bullet = header[header.index("**Access**") :]
    bullet = bullet[: bullet.index("\n- **")]
    flat = " ".join(bullet.split())
    assert "(latest gated)" in flat
    assert "`fetch DOC` refuses" in flat
    assert "`fetch --all` takes" in flat
    assert "and `fetch` takes the newest open one" not in flat


def test_ac6_support_doc_is_lf_and_would_fail_when_stale(generated):
    raw = SUPPORT.read_bytes()
    assert b"\r" not in raw
    text = raw.decode("utf-8")
    stored = text.split(MARKER + "\n", 1)[1].lstrip("\n")
    # a stale copy differs: drop one row and the comparison must fail
    stale = stored.replace(stored.splitlines()[4] + "\n", "", 1)
    assert stale != generated
    assert stored == generated


def test_ac6_generated_table_covers_every_document_and_family(shipped, generated):
    lines = generated.splitlines()
    headings = [ln[3:] for ln in lines if ln.startswith("## ")]
    families_with_docs = [
        f.title for f in shipped.families.values() if shipped.by_family(f.id)
    ]
    assert headings == families_with_docs
    ids = [ln.split("`")[1] for ln in lines if ln.startswith("| `")]
    assert sorted(ids) == sorted(d.id for d in shipped.documents)
    assert len(ids) == len(shipped.documents)
    # each document sits under its own family's heading
    family_of: dict[str, str] = {}
    current = None
    for ln in lines:
        if ln.startswith("## "):
            current = ln[3:]
        elif ln.startswith("| `"):
            family_of[ln.split("`")[1]] = current
    for doc in shipped.documents:
        assert family_of[doc.id] == shipped.families[doc.family].title, doc.id
    # the Redfish bundles, whose blocks close the catalog, are under Redfish
    assert family_of["DSP8011"] == family_of["DSP0266"]
    assert family_of["DSP8013"] == family_of["DSP0266"]
    assert generated.count(HEADER) == len(headings)


# ---------------------------------------------------------------- AC-7


def _status_numbers(readme: str) -> tuple[int, int, int, int]:
    m = re.search(
        r"\*\*Status:[^\n]*?\*\*\s+The Source Catalog lists (\d+) documents in\s+"
        r"(\d+) families\.\s+The (\d+) open ones",
        readme,
    )
    assert m, "README status paragraph with the counts not found"
    n = re.search(r"the (\d+) gated, member and NDA documents", readme)
    assert n, "README status paragraph does not count the non-open documents"
    return tuple(int(x) for x in (*m.groups(), n.group(1)))


def test_ac7_readme_status_counts_match_the_shipped_catalog(shipped):
    readme = README.read_text(encoding="utf-8")
    docs, families, open_docs, closed_docs = _status_numbers(readme)
    assert docs == len(shipped.documents)
    assert families == len({d.family for d in shipped.documents})
    assert open_docs == sum(1 for d in shipped.documents if d.access == "open")
    assert closed_docs == docs - open_docs
    assert open_docs + closed_docs == docs


def test_ac7_readme_links_to_the_support_doc_and_no_longer_denies_uefi():
    readme = README.read_text(encoding="utf-8")
    status = readme[readme.index("**Status:") :]
    status = status[: status.index("\n\n")]
    assert "(docs/SUPPORT.md)" in status
    assert "docs/golden-questions.md" in status
    assert "not in the catalog" not in status


def test_ac7_every_open_document_is_verified_as_the_readme_claims(shipped, generated):
    """The README says every open document has been checked against the
    Golden Questions; the Verified column must bear that out."""
    for ln in generated.splitlines():
        if not ln.startswith("| `"):
            continue
        cells = ln[2:-2].split(" | ")
        doc = shipped.get(cells[0].split("`")[1])
        if doc.access == "open":
            assert re.match(r"^G\d+", cells[4]), doc.id
        else:
            assert cells[4] == "-", doc.id


# ---------------------------------------------------------------- AC-8


def _g102_row() -> str:
    rows = [ln for ln in GOLDEN.read_text(encoding="utf-8").splitlines() if ln.startswith("| G102 ")]
    assert len(rows) == 1
    return rows[0]


def test_ac8_g102_names_all_eight_read_requirement_values():
    row = _g102_row()
    m = re.search(r"ReadRequirement takes (.+?)\(`#/definitions/ReadRequirement`\)", row)
    assert m, row
    listed = m.group(1)
    for value in (
        "Mandatory",
        "Supported",
        "Recommended",
        "IfImplemented",
        "IfPopulated",
        "Conditional",
        "Excluded",
        "None",
    ):
        assert re.search(rf"\b{value}\b", listed), value
    assert "Excluded" in listed


def test_ac8_g102_still_targets_dsp8013_2026_1_and_its_commands():
    row = _g102_row()
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[2] == "DSP8013 2026.1"
    assert "--definition ReadRequirement" in cells[4]


# ---------------------------------------------------------------- AC-9


def test_ac9_readme_and_skill_document_the_flag(capsys):
    readme = README.read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8")
    assert "--by-family" in readme
    assert "catalog --table --by-family --golden docs/golden-questions.md" in readme
    table_rows = [ln for ln in skill.splitlines() if ln.startswith("| `catalog --table")]
    assert len(table_rows) == 1
    assert "--by-family" in table_rows[0]
    assert "SUPPORT.md" in table_rows[0]
    with pytest.raises(SystemExit) as exc:
        main(["catalog", "--help"])
    assert exc.value.code == 0
    assert "--by-family" in capsys.readouterr().out
