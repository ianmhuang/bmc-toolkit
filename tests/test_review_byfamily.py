"""Reviewer acceptance tests for the per-family Support Level table
(``catalog --table --by-family``): AC-1 to AC-5 of feature/support-doc.

Black-box through the CLI on a mini catalog written to tmp_path. No
network, no Library: ``catalog`` reads the catalog file only.
"""

import pytest

from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG

# Two documents whose catalog blocks sit apart from their family: LATE is an
# MCTP document listed after the vendor document (like DSP8011 / DSP8013 in
# the shipped catalog); NOVER is a manual vendor document without versions.
# LATE's limits carry a pipe so the escaping of the flat table is checked.
EXTRA = """
[[documents]]
id = "LATE"
family = "mctp"
title = "An MCTP binding listed after the vendor block"
access = "open"
fetch = "direct"
limits = "Use find | page, not table."

[[documents.versions]]
version = "1.0"
url = "https://example.test/late-1.0.pdf"
type = "pdf"
published = "2019-05-05"

[[documents.versions]]
version = "1.1"
url = ""
type = "pdf"
published = "2023-01-01"
access = "gated"

[[documents]]
id = "NOVER"
family = "vendor"
title = "A gated standard registered without versions"
access = "gated"
fetch = "manual"
"""

EMPTY_FAMILY = '[families.empty]\ntitle = "An empty family"\npublisher = "Nobody"\n\n'

GOLDEN = """# Golden Questions

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G1 | header layout | DSP0236 1.3.3 | section 8 | `page DSP0236 24` |
| G2 | two documents | IPMI 2.0 rev 1.1; LATE 1.0 | pages 1-2 | `find IPMI x` |
| G3 | again the base | DSP0236 1.3.2 | section 9 | `find DSP0236 y` |
| G4 | code only | - | bmcweb | `grep bmcweb z` |
| G5 | a typo | NOPE 1.0 | nowhere | `find NOPE q` |
"""

FLAT_HEADER = "| Family | Document | Access | Latest | Fetch | Verified | Known limit |"
HEADER = "| Document | Access | Latest | Verified | Known limit |"
RULE = "|---|---|---|---|---|"


@pytest.fixture
def cat_file(tmp_path):
    """MINI_CATALOG with an empty family inserted before ``vendor`` and the
    two extra documents appended after it."""
    anchor = '[families.vendor]\ntitle = "Vendor documents"'
    assert anchor in MINI_CATALOG
    text = MINI_CATALOG.replace(anchor, EMPTY_FAMILY + anchor) + EXTRA
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


@pytest.fixture
def golden_file(tmp_path):
    path = tmp_path / "golden.md"
    path.write_text(GOLDEN, encoding="utf-8", newline="")
    return path


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _cells(line: str) -> list[str]:
    assert line.startswith("| ") and line.endswith(" |"), line
    return line[2:-2].split(" | ")


def _by_family_rows(out: str) -> dict[str, list[str]]:
    """Document rows keyed by catalog id, in output order."""
    rows = {}
    for ln in out.splitlines():
        if ln.startswith("| `"):
            cells = _cells(ln)
            rows[cells[0].split("`")[1]] = cells
    return rows


def _flat_rows(out: str) -> dict[str, list[str]]:
    rows = {}
    for ln in out.splitlines()[2:]:
        cells = _cells(ln)
        rows[cells[1].split("`")[1]] = cells
    return rows


# ---------------------------------------------------------------- AC-1


def test_ac1_one_heading_and_five_column_table_per_family_in_catalog_order(
    cat_file, capsys
):
    code, out, err = run(capsys, "catalog", "--table", "--by-family", catalog_file=cat_file)
    assert code == 0 and err == ""
    lines = out.splitlines()
    headings = [ln for ln in lines if ln.startswith("## ")]
    assert headings == ["## MCTP", "## IPMI", "## Vendor documents"]
    # heading, blank line, header, rule, rows
    for heading in headings:
        i = lines.index(heading)
        assert lines[i + 1] == ""
        assert lines[i + 2] == HEADER
        assert lines[i + 3] == RULE
        assert lines[i + 4].startswith("| `")
    # the Family and Fetch columns are gone: five cells per row
    for ln in lines:
        if ln.startswith("| `"):
            assert len(_cells(ln)) == 5, ln
    assert FLAT_HEADER not in out


def test_ac1_families_are_separated_by_exactly_one_blank_line(cat_file, capsys):
    code, out, _ = run(capsys, "catalog", "--table", "--by-family", catalog_file=cat_file)
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "## MCTP"
    for ln_no, ln in enumerate(lines):
        if ln.startswith("## ") and ln_no:
            assert lines[ln_no - 1] == "" and lines[ln_no - 2] != "", ln
    assert lines[-1].startswith("| `")
    assert out.endswith(" |\n") and not out.endswith("\n\n")
    assert "\n\n\n" not in out


def test_ac1_a_family_without_documents_is_left_out(cat_file, capsys):
    code, out, _ = run(capsys, "catalog", "--table", "--by-family", catalog_file=cat_file)
    assert code == 0
    assert "An empty family" not in out
    assert out.count(HEADER) == 3 and out.count("## ") == 3


# ---------------------------------------------------------------- AC-2


def test_ac2_a_document_listed_apart_from_its_family_lands_under_its_heading(
    cat_file, capsys
):
    code, out, _ = run(capsys, "catalog", "--table", "--by-family", catalog_file=cat_file)
    assert code == 0
    lines = out.splitlines()
    ids = [ln.split("`")[1] for ln in lines if ln.startswith("| `")]
    # catalog order is DSP0236, IPMI, BUNDLE, SECRET, LATE, NOVER; grouped
    # the MCTP documents come first, LATE after BUNDLE, NOVER after SECRET
    assert ids == ["DSP0236", "BUNDLE", "LATE", "IPMI", "SECRET", "NOVER"]
    mctp = lines.index("## MCTP")
    ipmi = lines.index("## IPMI")
    vendor = lines.index("## Vendor documents")
    late = next(i for i, ln in enumerate(lines) if ln.startswith("| `LATE`"))
    nover = next(i for i, ln in enumerate(lines) if ln.startswith("| `NOVER`"))
    assert mctp < late < ipmi
    assert vendor < nover


# ---------------------------------------------------------------- AC-3


def test_ac3_golden_fills_verified_as_in_the_flat_table(cat_file, golden_file, capsys):
    code, flat, flat_err = run(
        capsys, "catalog", "--table", "--golden", str(golden_file), catalog_file=cat_file
    )
    assert code == 0
    code, grouped, grouped_err = run(
        capsys,
        "catalog",
        "--table",
        "--by-family",
        "--golden",
        str(golden_file),
        catalog_file=cat_file,
    )
    assert code == 0
    assert grouped_err == flat_err
    assert "G5: unknown document 'NOPE'" in grouped_err
    assert "NOPE" not in grouped
    rows = _by_family_rows(grouped)
    # the reader's form says PASS where the flat table lists the questions
    flat_rows = _flat_rows(flat)
    assert flat_rows["DSP0236"][5] == "G1 (1.3.3); G3 (1.3.2)"
    for doc_id in ("DSP0236", "LATE", "IPMI"):
        assert rows[doc_id][3] == "PASS", doc_id
    for doc_id in ("BUNDLE", "SECRET", "NOVER"):
        assert rows[doc_id][3] == "-", doc_id
    # the other cells are the flat table's without Family and Fetch
    assert list(rows) != list(flat_rows)  # grouped order differs ...
    assert set(rows) == set(flat_rows)
    for doc_id, cells in rows.items():
        flat_cells = flat_rows[doc_id]
        assert cells[:3] == flat_cells[1:4] and cells[4] == flat_cells[6], doc_id


def test_ac3_without_golden_nothing_is_verified(cat_file, capsys):
    code, out, err = run(capsys, "catalog", "--table", "--by-family", catalog_file=cat_file)
    assert code == 0 and err == ""
    assert all(cells[3] == "-" for cells in _by_family_rows(out).values())


def test_ac3_missing_golden_file_is_cannot_read_exit_1(cat_file, tmp_path, capsys):
    absent = tmp_path / "absent.md"
    code, out, _ = run(
        capsys,
        "catalog",
        "--table",
        "--by-family",
        "--golden",
        str(absent),
        catalog_file=cat_file,
    )
    assert code == 1
    assert out.startswith(f"cannot read {absent}")
    assert "## " not in out and HEADER not in out


def test_ac3_golden_file_in_another_encoding_is_cannot_read_exit_1(
    cat_file, tmp_path, capsys
):
    golden = tmp_path / "golden.md"
    rows = "| # | Question | Document |\n|---|---|---|\n| G1 | café | DSP0236 1.3.3 |\n"
    golden.write_bytes(rows.encode("cp1252"))
    code, out, _ = run(
        capsys,
        "catalog",
        "--table",
        "--by-family",
        "--golden",
        str(golden),
        catalog_file=cat_file,
    )
    assert code == 1
    assert out.startswith(f"cannot read {golden}")
    assert "## " not in out


# ---------------------------------------------------------------- AC-4


def test_ac4_by_family_without_table_exits_2(cat_file, capsys):
    code, out, _ = run(capsys, "catalog", "--by-family", catalog_file=cat_file)
    assert code == 2
    assert out.strip() == "--by-family goes with --table"
    # nor does it fall through to the document view or the list
    code, out, _ = run(capsys, "catalog", "--by-family", "DSP0236", catalog_file=cat_file)
    assert code == 2 and "document: DSP0236" not in out
    code, out, _ = run(
        capsys, "catalog", "--by-family", "--family", "mctp", catalog_file=cat_file
    )
    assert code == 2 and "\t" not in out


def test_ac4_by_family_with_a_document_id_or_family_is_refused_like_table(
    cat_file, capsys
):
    for extra in (["DSP0236"], ["--family", "mctp"], ["late", "--family", "vendor"]):
        code, out, _ = run(
            capsys, "catalog", "--table", "--by-family", *extra, catalog_file=cat_file
        )
        assert code == 2, extra
        assert "drop the document id or --family" in out, extra
        assert "## " not in out and HEADER not in out, extra


# ---------------------------------------------------------------- AC-5


def test_ac5_flat_table_is_unchanged_and_carries_the_same_cells(cat_file, capsys):
    code, flat, err = run(capsys, "catalog", "--table", catalog_file=cat_file)
    assert code == 0 and err == ""
    lines = flat.splitlines()
    assert lines[0] == FLAT_HEADER
    assert lines[1] == "|" + "---|" * 7
    assert "## " not in flat
    rows = _flat_rows(flat)
    # flat order is catalog order, LATE after SECRET
    assert list(rows) == ["DSP0236", "IPMI", "BUNDLE", "SECRET", "LATE", "NOVER"]
    assert all(len(c) == 7 for c in rows.values())
    assert rows["LATE"] == [
        "MCTP",
        "`LATE` An MCTP binding listed after the vendor block",
        "open (latest gated)",
        "1.1",
        "direct",
        "-",
        "Use find \\| page, not table.",
    ]
    assert rows["NOVER"][2:] == ["gated", "-", "manual (Drop-in)", "-", "-"]
    code, grouped, _ = run(capsys, "catalog", "--table", "--by-family", catalog_file=cat_file)
    assert code == 0
    grouped_rows = _by_family_rows(grouped)
    for doc_id, cells in rows.items():
        assert grouped_rows[doc_id] == [*cells[1:4], cells[5], cells[6]], doc_id
    # the pipe in Known limit stays escaped in both forms
    assert "Use find \\| page, not table. |" in grouped
