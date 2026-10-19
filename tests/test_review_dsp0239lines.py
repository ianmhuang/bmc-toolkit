"""Reviewer acceptance tests for the DSP0239 known limit (AC-3, AC-4).

The shipped Source Catalog is public interface: `catalog DSP0239` prints its
`limits:` line and `catalog --table` puts it in the Known Limits column,
from which docs/SUPPORT.md is generated. These tests read the shipped
catalog, the CLI output and the stored table; each fails on the base branch,
where the DSP0239 limit stops at the emoji sentence.
"""

import re
from pathlib import Path

import pytest

from bmc_toolkit.spec import support
from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "docs" / "SUPPORT.md"

M8A_LIMIT = "One page holds an emoji that breaks pdfium's character order"


@pytest.fixture(scope="module")
def limits() -> str:
    return load_catalog().get("DSP0239").limits


# ------------------------------------------------------------------ AC-3


def test_the_limit_names_the_pages_whose_line_numbers_are_not_read(limits):
    assert "13" in limits and "15" in limits and "17" in limits, limits
    assert "line number" in limits.lower(), limits
    assert "lines -" in limits, limits
    # the pages that print no numbers are not named: `lines -` is right there
    assert not re.search(r"\b1[46]\b", limits), limits


def test_the_m8a_limit_is_kept_as_the_start_of_the_string(limits):
    assert limits.startswith(M8A_LIMIT), limits
    assert "emoji" in limits and "ruling lines" not in limits
    # the known limit is prose: one string, no line break, ends in a sentence
    assert "\n" not in limits
    assert limits.endswith(".") or limits.endswith("`."), limits


def test_catalog_dsp0239_prints_the_limit_on_its_limits_line(capsys, limits):
    code = main(["catalog", "DSP0239"])
    out = capsys.readouterr().out
    assert code == 0
    limit_lines = [ln for ln in out.splitlines() if ln.startswith("limits: ")]
    assert len(limit_lines) == 1, out
    assert limit_lines[0] == f"limits: {limits}"
    assert "lines -" in limit_lines[0]


# ------------------------------------------------------------------ AC-4


def _support_row(doc_id: str) -> list[str]:
    lines = SUPPORT.read_text(encoding="utf-8").splitlines()
    rows = [ln for ln in lines if f"`{doc_id}`" in ln]
    assert len(rows) == 1, (doc_id, rows)
    return support._cells(rows[0])


def test_support_md_carries_the_catalog_limit_for_dsp0239(limits):
    cells = _support_row("DSP0239")
    assert cells[-1] == limits, cells
    assert "lines -" in cells[-1]


def test_support_md_rows_of_the_other_mctp_documents_are_unchanged():
    # the row above and the row below DSP0239 still carry their own limits
    catalog = load_catalog()
    for doc_id in ("DSP0237", "DSP0238", "DSP0233"):
        cells = _support_row(doc_id)
        assert cells[-1] == (catalog.get(doc_id).limits or "-"), doc_id
        assert "lines -" not in cells[-1], doc_id


def test_support_md_body_is_the_by_family_table(capsys):
    marker = (
        "<!-- generated below: catalog --table --by-family "
        "--golden docs/golden-questions.md -->\n\n"
    )
    doc = SUPPORT.read_text(encoding="utf-8")
    assert marker in doc
    stored = doc.split(marker, 1)[1]
    code = main(
        [
            "catalog",
            "--table",
            "--by-family",
            "--golden",
            str(ROOT / "docs" / "golden-questions.md"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert stored == out
    assert "Pages 13, 15 and 17" in out
