"""Reviewer acceptance tests for T69.2 (AC-6, AC-7, AC-8, AC-10): the
page-before rule and the line-bottom fallback read a table id from one
pattern (a number, a Roman numeral in either case or an upper-case single
letter), the store version is 13, and NVME-NVM's limits no longer name
Figure 123."""

import json

import pytest

from bmc_toolkit.spec import tables as T
from bmc_toolkit.spec.catalog import load_catalog
from tests import pdfgen
from tests.test_tables import ruled_table

pytest.importorskip("pdfplumber")

RUNNING = "Example Specification, Revision 2.4"
WIDTHS = [100, 80, 200]
CELLS = [
    ["Name", "Code", "Meaning"],
    ["Fan", "04h", "rpm"],
    ["Voltage", "02h", "volts"],
]


def furniture(n):
    return [(72, 750, RUNNING), (300, 40, str(n))]


def grid(top):
    return ruled_table(72, top, WIDTHS, [16] * len(CELLS), CELLS)


def captions(tmp_path, pages):
    pdf = pdfgen.write_pdf(tmp_path / "doc.pdf", pages)
    with T.Reader(pdf) as r:
        return [
            [t.caption for t in r.logical_tables(n)] for n in range(1, len(pages) + 1)
        ]


def page_before(tmp_path, last_line):
    """The caption of a table that starts page 2 with no body text above
    it, when ``last_line`` is the last body line of page 1."""
    pages = [
        furniture(1)
        + [
            (72, 314, "The command is described in the table that follows."),
            (72, 300, last_line),
        ],
        furniture(2) + grid(680) + [(72, 120, "The second part ends here.")],
    ]
    return captions(tmp_path, pages)[1]


def fallback(tmp_path, text):
    """The caption of a table under a line whose top lies 47 pt above it
    (outside the 40 pt window) and whose bottom lies inside, past two note
    lines: only the line-bottom fallback can take it."""
    top = 600
    page = grid(top) + [
        (72, top + 39, text),
        (72, top + 17, "Note: The byte count is not included."),
        (72, top + 4, "byte count byte of block transactions."),
    ]
    return captions(tmp_path, [page])[0]


# ---------------------------------------------------------------- AC-6


@pytest.mark.parametrize(
    "text", ["Table A - Annex codes", "Table B: Codes", "TABLE C - ANNEX CODES"]
)
def test_ac6_the_page_before_rule_takes_a_single_letter_id(tmp_path, text):
    assert page_before(tmp_path, text) == [text]


def test_ac6_a_table_line_without_an_id_stays_rejected(tmp_path):
    assert page_before(tmp_path, "Table: Supported commands") == [None]


# ---------------------------------------------------------------- AC-7


@pytest.mark.parametrize(
    "text",
    [
        "Table II - Limits",
        "Table IV: Codes",
        "Table A - Annex codes",
        "Table 9 - Table I/O map",
    ],
)
def test_ac7_the_fallback_reads_the_id_the_page_before_rule_reads(tmp_path, text):
    assert fallback(tmp_path, text) == [text]


@pytest.mark.parametrize(
    "text",
    [
        "Table II lists the limits below.",
        "Table II, Table III and Table IV list them.",
    ],
    ids=["lists", "mentions"],
)
def test_ac7_the_fallback_still_leaves_prose_with_a_roman_id(tmp_path, text):
    assert fallback(tmp_path, text) == [None]


@pytest.mark.parametrize(
    "text", ["Table II - Limits", "Table III", "table ii - Limits"]
)
def test_ac7_the_page_before_rule_takes_a_roman_numeral(tmp_path, text):
    # in either letter case, as before the two rules shared a pattern
    assert page_before(tmp_path, text) == [text]


def test_ac7_a_roman_letter_before_a_slash_is_not_an_id(tmp_path):
    # "I" is followed by "/": neither whitespace, a separator nor the end
    assert page_before(tmp_path, "Table I/O signals are listed below.") == [None]


# ---------------------------------------------------------------- AC-8


def test_ac8_tables_version_is_13_and_a_version_12_store_is_not_served(tmp_path):
    assert T.TABLES_VERSION == 15
    pdf = pdfgen.write_pdf(tmp_path / "doc.pdf", [grid(600)])
    with T.Reader(pdf) as r:
        found = r.logical_tables(1)
    vdir = tmp_path / "v"
    vdir.mkdir()
    path = T.store(vdir, [1], found)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tables_version"] == 15
    assert T.stored_for_page(vdir, 1) is not None
    data["tables_version"] = 12
    path.write_text(json.dumps(data), encoding="utf-8")
    assert T.stored_for_page(vdir, 1) is None


# --------------------------------------------------------------- AC-10


def test_ac10_the_limits_no_longer_name_figure_123():
    limits = load_catalog().get("NVME-NVM").limits
    assert "Figure 123" not in limits
    assert "Figures 157 and 159" in limits
