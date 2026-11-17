"""The 2026-11-17 catalog batch: the four OData 4.0 documents DSP0266 cites,
in a new OASIS family, each as the 4.0 OASIS Standard and the 4.0 Plus
Errata 03 edition, with their Golden Questions. Shipped files only, no
network."""

import re
from pathlib import Path

from bmc_toolkit.spec import support
from bmc_toolkit.spec.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "docs" / "golden-questions.md"
OASIS = "https://docs.oasis-open.org/odata/"

NEW = {
    "ODATA-PROTOCOL": (
        "OData Version 4.0 Part 1: Protocol",
        "odata/v4.0/os/part1-protocol/odata-v4.0-os-part1-protocol.pdf",
        "odata/v4.0/errata03/os/complete/part1-protocol/"
        "odata-v4.0-errata03-os-part1-protocol-complete.pdf",
    ),
    "ODATA-URL": (
        "OData Version 4.0 Part 2: URL Conventions",
        "odata/v4.0/os/part2-url-conventions/odata-v4.0-os-part2-url-conventions.pdf",
        "odata/v4.0/errata03/os/complete/part2-url-conventions/"
        "odata-v4.0-errata03-os-part2-url-conventions-complete.pdf",
    ),
    "ODATA-CSDL": (
        "OData Version 4.0 Part 3: Common Schema Definition Language (CSDL)",
        "odata/v4.0/os/part3-csdl/odata-v4.0-os-part3-csdl.pdf",
        "odata/v4.0/errata03/os/complete/part3-csdl/"
        "odata-v4.0-errata03-os-part3-csdl-complete.pdf",
    ),
    "ODATA-JSON": (
        "OData JSON Format Version 4.0",
        "odata-json-format/v4.0/os/odata-json-format-v4.0-os.pdf",
        "odata-json-format/v4.0/errata03/os/"
        "odata-json-format-v4.0-errata03-os-complete.pdf",
    ),
}
VERSIONS = [("4.0", "2014-02-24"), ("4.0 Errata 03", "2016-06-02")]
QUESTIONS = {
    "G114": "ODATA-PROTOCOL",
    "G115": "ODATA-URL",
    "G116": "ODATA-CSDL",
    "G117": "ODATA-JSON",
}
HEADING = "## Catalog additions of 2026-11-17"


# ---------------------------------------------------------------- AC-1


def test_the_family_is_oasis_and_sits_after_redfish():
    cat = load_catalog()
    family = cat.families["odata"]
    assert (family.title, family.publisher) == (
        "Open Data Protocol (OData 4.0)",
        "OASIS",
    )
    names = list(cat.families)
    assert names[names.index("redfish") + 1] == "odata"


def test_the_four_follow_dsp0280_with_both_versions():
    cat = load_catalog()
    ids = [d.id for d in cat.documents]
    at = ids.index("DSP0280")
    assert ids[at + 1 :][:4] == list(NEW)
    for doc_id, (title, os_path, errata_path) in NEW.items():
        doc = cat.get(doc_id)
        assert (doc.family, doc.title) == ("odata", title), doc_id
        assert (doc.access, doc.fetch, doc.listing) == ("open", "direct", "")
        assert [(v.version, v.published) for v in doc.versions] == VERSIONS
        assert [v.url for v in doc.versions] == [
            OASIS + os_path,
            OASIS + errata_path,
        ]
        assert all(v.type == "pdf" and not v.wip for v in doc.versions)
        assert doc.latest().version == "4.0 Errata 03", doc_id


# ---------------------------------------------------------------- AC-2


def test_notes_say_redfish_cites_4_0_and_4_01_is_left_out():
    cat = load_catalog()
    for doc_id in NEW:
        doc = cat.get(doc_id)
        assert "Redfish (DSP0266) cites OData 4.0" in doc.notes, doc_id
        assert "4.01 is not listed" in doc.notes, doc_id
        listed = [v.version for v in doc.versions]
        assert not any(v.startswith("4.01") for v in listed), listed
        assert not any("Errata 01" in v or "Errata 02" in v for v in listed)


# ---------------------------------------------------------------- AC-3


def test_the_contents_depth_limit_is_recorded_where_it_applies():
    cat = load_catalog()
    examples = {
        "ODATA-PROTOCOL": "8.2.8.1",
        "ODATA-URL": "5.1.1.1",
        "ODATA-CSDL": "12.1.1.1",
    }
    for doc_id, section in examples.items():
        limits = cat.get(doc_id).limits
        assert "4.0 Errata 03 edition" in limits, doc_id
        assert "third heading level" in limits, doc_id
        assert f"such as {section}" in limits, doc_id
    assert cat.get("ODATA-JSON").limits == ""


# ---------------------------------------------------------------- AC-4


def test_each_is_verified_by_its_own_question_on_errata_03():
    cat = load_catalog()
    verified, problems = support.read_golden(GOLDEN, cat)
    assert problems == []
    for qid, doc_id in QUESTIONS.items():
        assert verified[doc_id.lower()] == [(qid, "4.0 Errata 03")], doc_id
    text = GOLDEN.read_text("utf-8")
    start = text.index(HEADING)
    assert text.index("## Catalog additions of 2026-11-09") < start
    section = text[start : text.index("## OpenBMC")]
    for qid, doc_id in QUESTIONS.items():
        (row,) = [ln for ln in section.splitlines() if ln.startswith(f"| {qid} |")]
        cells = row.split(" | ")
        assert cells[2] == f"{doc_id} 4.0 Errata 03", qid
        assert cells[3].startswith(f"{doc_id} 4.0 Errata 03, section "), qid
        assert "page" in cells[3], qid
        commands = cells[4].split("`")[1::2]
        assert commands and all(doc_id in c for c in commands), qid
    fresh = text[text.index("## Freshness") :]
    assert "2026-11-17" in fresh
    for doc_id in NEW:
        assert doc_id in fresh, doc_id


def test_no_golden_command_puts_a_dollar_inside_double_quotes():
    """PR #135 F1: bash and PowerShell expand `$name` inside double quotes,
    so `section ODATA-URL "$expand"` reached the tool as an empty query."""
    text = GOLDEN.read_text("utf-8")
    rows = [ln for ln in text.splitlines() if re.match(r"\| G\d+ \|", ln)]
    assert len(rows) >= 117
    bad = []
    for row in rows:
        commands = row.rsplit(" | ", 1)[1]
        for command in commands.split("`")[1::2]:
            if re.search(r'"[^"]*\$[^"]*"', command):
                bad.append((row.split(" | ")[0], command))
    assert bad == []
    (row,) = [ln for ln in rows if ln.startswith("| G115 |")]
    assert "`section ODATA-URL 5.1.2`" in row


# ---------------------------------------------------------------- AC-5


def test_support_has_an_odata_section_after_redfish():
    cat = load_catalog()
    lines = (ROOT / "docs" / "SUPPORT.md").read_text("utf-8").splitlines()
    headings = [ln for ln in lines if ln.startswith("## ")]
    at = headings.index("## Open Data Protocol (OData 4.0)")
    assert headings[at - 1] == "## Redfish"
    for doc_id, (title, _, _) in NEW.items():
        (row,) = [ln for ln in lines if ln.startswith(f"| `{doc_id}` ")]
        limit = cat.get(doc_id).limits or "-"
        assert row == f"| `{doc_id}` {title} | open | 4.0 Errata 03 | PASS | {limit} |"


def test_readme_counts_the_catalog():
    docs = load_catalog().documents
    readme = " ".join((ROOT / "README.md").read_text("utf-8").split())
    total = len(docs)
    open_docs = sum(d.access == "open" for d in docs)
    families = len({d.family for d in docs})
    assert (total, open_docs, families) == (128, 108, 36)
    assert f"lists {total} documents in {families} families" in readme
    assert f"The {open_docs} open ones" in readme
