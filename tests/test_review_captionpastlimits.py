"""Review tests for the catalog limits that fix/caption-past-header-line
rewrites (AC-7): DSP0282 no longer says Table 2's caption prints as `-`
and keeps the cut rows of Table 1; docs/SUPPORT.md carries the same two
rows. PMBUS-II's limit on Table 31 was dropped by
fix/caption-to-line-bottom (AC-8), which takes that caption. Shipped files
only."""

from pathlib import Path

from bmc_toolkit.spec.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "docs" / "SUPPORT.md"


def support_row(doc_id: str) -> str:
    rows = [
        ln
        for ln in SUPPORT.read_text("utf-8").splitlines()
        if ln.startswith(f"| `{doc_id}` ")
    ]
    assert len(rows) == 1, (doc_id, rows)
    return rows[0]


def test_ac7_dsp0282_keeps_only_the_cut_rows_of_table_1():
    limits = load_catalog().get("DSP0282").limits
    assert "Table 2" not in limits
    assert "caption" not in limits
    assert "`-`" not in limits
    assert "Table 1" in limits
    assert "byte number" in limits
    assert "page" in limits


def test_pmbus_ii_no_longer_names_table_31():
    # fix/caption-to-line-bottom (AC-8) takes Table 31's caption, so the
    # limit this test pinned is gone
    limits = load_catalog().get("PMBUS-II").limits
    assert "Table 31" not in limits
    assert "`-`" not in limits


def test_ac7_support_md_carries_the_two_catalog_limits():
    cat = load_catalog()
    for doc_id in ("DSP0282", "PMBUS-II"):
        row = support_row(doc_id)
        limits = cat.get(doc_id).limits
        assert (limits or "| - |") in row, doc_id
    assert "Table 2's caption" not in support_row("DSP0282")
    assert "Table 31" not in support_row("PMBUS-II")
