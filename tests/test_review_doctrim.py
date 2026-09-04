"""Reviewer acceptance tests for feature/support-doc-trim: the ``unlisted``
catalog field (AC-1), its effect on ``catalog --table --by-family`` (AC-2),
the reader's columns with Verified as PASS (AC-3), the flat table left alone
(AC-4), the shipped catalog and docs/SUPPORT.md (AC-5), the other commands
unaffected (AC-6) and the documentation (AC-7).

Black-box through the CLI and the catalog loader. No network: the scripted
client has no routes, so every listing lookup fails the same way with and
without the flag. Derived from the acceptance criteria, not the code.
"""

import re
import tomllib
from pathlib import Path

import pytest

from bmc_toolkit.spec.catalog import CatalogError, load_catalog, parse_catalog
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG, PDF_BYTES

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "docs" / "SUPPORT.md"
GOLDEN_SHIPPED = ROOT / "docs" / "golden-questions.md"
README = ROOT / "README.md"
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
MARKER = (
    "<!-- generated below: catalog --table --by-family "
    "--golden docs/golden-questions.md -->"
)

FLAT_HEADER = "| Family | Document | Access | Latest | Fetch | Verified | Known limit |"
FLAT_RULE = "|---|---|---|---|---|---|---|"
HEADER = "| Document | Access | Latest | Verified | Known limit |"
RULE = "|---|---|---|---|---|"
SOC_IDS = ("AST2500", "AST2600", "NPCM7XX", "NPCM8XX")

# DSP0236 gets a Known limit so the last column carries text, not "-".
_LIMIT = "Table numbers are missing from the text layer."
_ANCHOR = 'fetch = "direct"\n\n[[documents.versions]]\nversion = "1.3.2"'
assert MINI_CATALOG.count(_ANCHOR) == 1
BASE = MINI_CATALOG.replace(
    _ANCHOR, f'fetch = "direct"\nlimits = "{_LIMIT}"\n\n[[documents.versions]]\nversion = "1.3.2"'
)

# SECRET is the only Vendor document of MINI_CATALOG (documents[3]).
_SECRET_HEAD = 'id = "SECRET"\nfamily = "vendor"\n'
assert BASE.count(_SECRET_HEAD) == 1
UNLISTED = BASE.replace(_SECRET_HEAD, _SECRET_HEAD + "unlisted = true\n")

# A second, listed Vendor document keeps the family in the reader's form.
OTHER = """
[[documents]]
id = "OTHER"
family = "vendor"
title = "A gated standard registered without versions"
access = "gated"
fetch = "manual"
"""

# G1 and G3 name DSP0236 on two versions, G2 names IPMI without a version,
# G7 names the unlisted SECRET; BUNDLE is never named.
GOLDEN = """# Golden Questions

| Id | Question | Document |
|---|---|---|
| G1 | What is the base version | DSP0236 1.3.3 |
| G3 | What was it before | DSP0236 1.3.2 |
| G2 | Which IPMI channel | IPMI |
| G7 | A datasheet register | SECRET 0.9 |
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8", newline="")
    return path


@pytest.fixture
def base_file(tmp_path):
    return _write(tmp_path, "base.toml", BASE)


@pytest.fixture
def unlisted_file(tmp_path):
    return _write(tmp_path, "unlisted.toml", UNLISTED)


@pytest.fixture
def other_file(tmp_path):
    return _write(tmp_path, "other.toml", UNLISTED + OTHER)


@pytest.fixture
def golden_file(tmp_path):
    return _write(tmp_path, "golden.md", GOLDEN)


def run(capsys, *argv, catalog_file=None):
    head = ["--catalog", str(catalog_file)] if catalog_file is not None else []
    code = main([*head, *argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _cells(line: str) -> list[str]:
    body = line.strip()[1:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", body)]


def _rows(out: str, id_index: int) -> dict[str, list[str]]:
    rows = {}
    for ln in out.splitlines():
        if ln.startswith("| ") and "`" in ln:
            cells = _cells(ln)
            rows[cells[id_index].split("`")[1]] = cells
    return rows


def _headings(out: str) -> list[str]:
    return [ln for ln in out.splitlines() if ln.startswith("## ")]


# ---------------------------------------------------------------- AC-1


def test_ac1_unlisted_is_optional_and_defaults_to_false(base_file, unlisted_file):
    base = load_catalog(base_file)
    assert all(doc.unlisted is False for doc in base.documents)
    flagged = load_catalog(unlisted_file)
    assert flagged.get("SECRET").unlisted is True
    assert [d.id for d in flagged.documents if d.unlisted] == ["SECRET"]
    # an explicit false is accepted too
    explicit = parse_catalog(
        tomllib.loads(UNLISTED.replace("unlisted = true", "unlisted = false"))
    )
    assert explicit.get("SECRET").unlisted is False


@pytest.mark.parametrize("value", ['"yes"', "1", '"true"', "[true]"])
def test_ac1_non_boolean_unlisted_is_a_catalog_error_naming_the_field(value):
    text = UNLISTED.replace("unlisted = true", f"unlisted = {value}")
    assert text != UNLISTED
    with pytest.raises(CatalogError, match=r"documents\[3\]\.unlisted"):
        parse_catalog(tomllib.loads(text))


# ---------------------------------------------------------------- AC-2


def test_ac2_by_family_leaves_out_the_unlisted_document_and_keeps_the_family(
    other_file, golden_file, capsys
):
    code, out, err = run(
        capsys,
        "catalog",
        "--table",
        "--by-family",
        "--golden",
        str(golden_file),
        catalog_file=other_file,
    )
    assert code == 0 and err == ""
    rows = _rows(out, 0)
    assert "SECRET" not in rows
    assert set(rows) == {"DSP0236", "BUNDLE", "IPMI", "OTHER"}
    assert _headings(out) == ["## MCTP", "## IPMI", "## Vendor documents"]
    # the unlisted document leaves no trace, not even its title
    assert "A confidential datasheet" not in out


def test_ac2_by_family_leaves_out_a_family_whose_documents_are_all_unlisted(
    unlisted_file, capsys
):
    code, out, err = run(
        capsys, "catalog", "--table", "--by-family", catalog_file=unlisted_file
    )
    assert code == 0 and err == ""
    assert _headings(out) == ["## MCTP", "## IPMI"]
    assert "Vendor" not in out and "SECRET" not in out
    lines = out.splitlines()
    # no dangling blank lines or empty table where the family used to be
    assert lines[-1].startswith("| `") and not out.endswith("\n\n")
    assert lines.count(HEADER) == 2
    assert lines[lines.index("## IPMI") - 1] == "" and lines[lines.index("## IPMI") + 1] == ""


def test_ac2_a_listed_document_stays_when_only_its_neighbour_is_unlisted(
    tmp_path, capsys
):
    # unlist BUNDLE (a document that shares the MCTP family with DSP0236)
    text = BASE.replace(
        'id = "BUNDLE"\nfamily = "mctp"\n', 'id = "BUNDLE"\nfamily = "mctp"\nunlisted = true\n'
    )
    assert text != BASE
    path = _write(tmp_path, "bundle.toml", text)
    code, out, _ = run(capsys, "catalog", "--table", "--by-family", catalog_file=path)
    assert code == 0
    assert _headings(out) == ["## MCTP", "## IPMI", "## Vendor documents"]
    rows = _rows(out, 0)
    assert "BUNDLE" not in rows and "DSP0236" in rows and "SECRET" in rows


# ---------------------------------------------------------------- AC-3


def test_ac3_by_family_has_five_columns_and_verified_is_pass_or_dash(
    other_file, golden_file, capsys
):
    code, out, err = run(
        capsys,
        "catalog",
        "--table",
        "--by-family",
        "--golden",
        str(golden_file),
        catalog_file=other_file,
    )
    assert code == 0 and err == ""
    lines = out.splitlines()
    assert lines.count(HEADER) == 3 and lines.count(RULE) == 3
    assert FLAT_HEADER not in out and "| Fetch |" not in out
    rows = _rows(out, 0)
    assert all(len(cells) == 5 for cells in rows.values())
    # named at least once: PASS, whatever the number of questions or version
    assert rows["DSP0236"][3] == "PASS"  # two questions, two versions
    assert rows["IPMI"][3] == "PASS"  # one question, no version
    assert rows["BUNDLE"][3] == "-"  # never named
    assert rows["OTHER"][3] == "-"
    # no question ids and no version in the Verified column
    assert not re.search(r"\bG\d+\b", out)
    assert "(1.3.3)" not in out and "(1.3.2)" not in out
    # the fetch methods appear nowhere in the reader's form
    for word in ("direct", "wayback", "manual", "Drop-in"):
        assert word not in out, word


def test_ac3_other_cells_are_those_of_the_flat_table(other_file, golden_file, capsys):
    code, flat, _ = run(
        capsys, "catalog", "--table", "--golden", str(golden_file), catalog_file=other_file
    )
    assert code == 0
    code, grouped, _ = run(
        capsys,
        "catalog",
        "--table",
        "--by-family",
        "--golden",
        str(golden_file),
        catalog_file=other_file,
    )
    assert code == 0
    flat_rows = _rows(flat, 1)
    for doc_id, cells in _rows(grouped, 0).items():
        f = flat_rows[doc_id]
        assert cells[0] == f[1], doc_id  # Document
        assert cells[1] == f[2], doc_id  # Access
        assert cells[2] == f[3], doc_id  # Latest
        assert cells[4] == f[6], doc_id  # Known limit
    rows = _rows(grouped, 0)
    assert rows["DSP0236"][0] == "`DSP0236` MCTP Base Specification"
    assert rows["DSP0236"][1] == "open"
    assert rows["DSP0236"][2] == "1.3.3"  # the wip 1.4.0 is not latest
    assert rows["DSP0236"][4] == _LIMIT
    assert rows["OTHER"][1:] == ["gated", "-", "-", "-"]


def test_ac3_without_golden_every_document_is_dash(other_file, capsys):
    code, out, err = run(
        capsys, "catalog", "--table", "--by-family", catalog_file=other_file
    )
    assert code == 0 and err == ""
    rows = _rows(out, 0)
    assert rows and all(cells[3] == "-" for cells in rows.values())
    assert "PASS" not in out


# ---------------------------------------------------------------- AC-4


def test_ac4_flat_table_keeps_seven_columns_fetch_and_unlisted_documents(
    other_file, golden_file, capsys
):
    code, out, err = run(
        capsys, "catalog", "--table", "--golden", str(golden_file), catalog_file=other_file
    )
    assert code == 0 and err == ""
    lines = out.splitlines()
    assert lines[0] == FLAT_HEADER and lines[1] == FLAT_RULE
    rows = _rows(out, 1)
    assert all(len(cells) == 7 for cells in rows.values())
    assert set(rows) == {"DSP0236", "IPMI", "BUNDLE", "SECRET", "OTHER"}
    # the unlisted document is there with its fetch method and its question
    assert rows["SECRET"][0] == "Vendor documents"
    assert rows["SECRET"][4] == "manual (Drop-in)"
    assert rows["SECRET"][5] == "G7 (0.9)"
    # Verified keeps the ids per version, not PASS
    assert rows["DSP0236"][5] == "G1 (1.3.3); G3 (1.3.2)"
    assert rows["IPMI"][5] == "G2"
    assert rows["IPMI"][4] == "wayback" and rows["DSP0236"][4] == "direct"
    assert "PASS" not in out


def test_ac4_flat_table_is_identical_with_and_without_the_flag(
    base_file, unlisted_file, golden_file, capsys
):
    _, with_flag, err1 = run(
        capsys, "catalog", "--table", "--golden", str(golden_file), catalog_file=unlisted_file
    )
    _, without, err2 = run(
        capsys, "catalog", "--table", "--golden", str(golden_file), catalog_file=base_file
    )
    assert with_flag == without and err1 == err2


# ---------------------------------------------------------------- AC-5


@pytest.fixture
def shipped():
    return load_catalog()


def test_ac5_shipped_catalog_unlists_exactly_the_four_soc_datasheets(shipped):
    assert sorted(d.id for d in shipped.documents if d.unlisted) == sorted(SOC_IDS)
    for doc_id in SOC_IDS:
        assert shipped.get(doc_id) is not None, doc_id  # still in the catalog


def test_ac5_support_doc_body_has_no_datasheets_no_fetch_and_no_question_ids():
    text = SUPPORT.read_text(encoding="utf-8")
    assert text.count(MARKER) == 1
    header, body = text.split(MARKER + "\n", 1)
    for doc_id in SOC_IDS:
        assert f"`{doc_id}`" not in body, doc_id
    for word in ("ASPEED", "Nuvoton"):
        assert word not in body, word
    assert "| Fetch |" not in body
    assert not re.search(r"\bG\d+\b", body)
    assert "manual (Drop-in)" not in body and "| direct |" not in body
    assert "| wayback |" not in body
    assert HEADER in body and "| PASS |" in body
    assert "| Document | Access | Latest | Fetch |" not in body
    # every table in the body has the five reader's columns
    for ln in body.splitlines():
        if ln.startswith("| `"):
            assert len(_cells(ln)) == 5, ln


def test_ac5_support_doc_header_describes_pass_and_no_fetch_column():
    header = SUPPORT.read_text(encoding="utf-8").split(MARKER, 1)[0]
    assert "**Fetch**" not in header
    verified = next(ln for ln in header.splitlines() if "**Verified**" in ln)
    assert "`PASS`" in verified
    for column in ("Document", "Access", "Latest", "Verified", "Known limit"):
        assert f"**{column}**" in header, column


def test_ac5_support_doc_is_in_sync_with_the_generator(capsys):
    code, out, err = run(
        capsys, "catalog", "--table", "--by-family", "--golden", str(GOLDEN_SHIPPED)
    )
    assert code == 0 and err == ""
    body = SUPPORT.read_text(encoding="utf-8").split(MARKER + "\n", 1)[1]
    assert body.lstrip("\n") == out
    # the reader's form drops the two families that hold only datasheets
    families_listed = {
        d.family for d in load_catalog().documents if not d.unlisted
    }
    assert len(_headings(out)) == len(families_listed)
    assert len(_rows(out, 0)) == len(load_catalog().documents) - len(SOC_IDS)


# ---------------------------------------------------------------- AC-6


def test_ac6_catalog_listing_and_catalog_doc_ignore_unlisted(
    base_file, unlisted_file, capsys
):
    for argv in (["catalog"], ["catalog", "SECRET"], ["catalog", "--family", "vendor"]):
        code1, with_flag, err1 = run(capsys, *argv, catalog_file=unlisted_file)
        code2, without, err2 = run(capsys, *argv, catalog_file=base_file)
        assert (code1, with_flag, err1) == (code2, without, err2), argv
    _, listing, _ = run(capsys, "catalog", catalog_file=unlisted_file)
    assert any(ln.split("\t")[1] == "SECRET" for ln in listing.splitlines())
    _, one, _ = run(capsys, "catalog", "SECRET", catalog_file=unlisted_file)
    assert "unlisted" not in one and "0.9" in one


def test_ac6_fetch_and_check_ignore_unlisted(
    base_file, unlisted_file, library, scripted, capsys
):
    for argv in (["fetch", "SECRET"], ["fetch", "--all"], ["check"], ["check", "SECRET"]):
        code1, with_flag, err1 = run(capsys, *argv, catalog_file=unlisted_file)
        code2, without, err2 = run(capsys, *argv, catalog_file=base_file)
        assert (code1, with_flag, err1) == (code2, without, err2), argv
    # the manual, confidential document is refused with the Drop-in advice
    code, out, _ = run(capsys, "fetch", "SECRET", catalog_file=unlisted_file)
    assert code == 2 and "Drop-in" in out
    code, out, _ = run(capsys, "check", catalog_file=unlisted_file)
    assert code == 0 and "unchecked (manual): SECRET (confidential)" in out


def test_ac6_add_registers_an_unlisted_document_as_before(
    unlisted_file, library, scripted, tmp_path, capsys
):
    src = tmp_path / "secret.pdf"
    src.write_bytes(PDF_BYTES)
    code, out, _ = run(
        capsys,
        "add",
        str(src),
        "--document",
        "SECRET",
        "--version",
        "0.9",
        catalog_file=unlisted_file,
    )
    assert code == 0 and "added SECRET 0.9 as Drop-in" in out
    assert library.find("SECRET", "0.9") is not None
    # held now: fetch reports it skipped and stays off the network
    code, out, _ = run(capsys, "fetch", "SECRET", catalog_file=unlisted_file)
    assert code == 0 and "skipped" in out
    assert scripted.calls == []
    # still absent from the reader's form, still in the flat table
    _, grouped, _ = run(capsys, "catalog", "--table", "--by-family", catalog_file=unlisted_file)
    assert "SECRET" not in grouped
    _, flat, _ = run(capsys, "catalog", "--table", catalog_file=unlisted_file)
    assert "`SECRET`" in flat


# ---------------------------------------------------------------- AC-7


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text[start + len(heading) :]
    m = re.search(r"\n## ", rest)
    return rest[: m.start()] if m else rest


def test_ac7_readme_source_catalog_section_documents_unlisted_and_the_reader_form():
    section = _section(README.read_text(encoding="utf-8"), "## The Source Catalog")
    assert "`unlisted = true`" in section or "`unlisted`" in section
    assert "--by-family" in section and "`PASS`" in section
    assert "docs/SUPPORT.md" in section


def test_ac7_skill_documents_unlisted_and_pass_on_the_by_family_row():
    text = SKILL.read_text(encoding="utf-8")
    row = next(ln for ln in text.splitlines() if "--by-family" in ln and ln.startswith("|"))
    assert "unlisted" in row and "`PASS`" in row
    assert "docs/SUPPORT.md" in row


def test_ac7_readme_counts_still_count_the_unlisted_documents(shipped):
    readme = README.read_text(encoding="utf-8")
    m = re.search(r"lists (\d+) documents in\s+(\d+) families\. The (\d+) open ones", readme)
    assert m, "README status paragraph moved"
    docs = shipped.documents
    open_docs = [d for d in docs if d.access == "open"]
    assert tuple(map(int, m.groups())) == (
        len(docs),
        len({d.family for d in docs}),
        len(open_docs),
    )
    # the four unlisted datasheets are part of those counts
    assert all(shipped.get(i) in docs for i in SOC_IDS)
    m = re.search(r"the (\d+) gated, member and NDA documents", readme)
    assert m and int(m.group(1)) == len(docs) - len(open_docs)
