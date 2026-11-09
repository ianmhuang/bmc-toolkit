"""The 2026-11-09 catalog batch: DSP0220 FRU Data, DSP0244 IPMI PET to
Platform Message Registry Mapping and DSP0280 PMCI Test Tools, with their
versions, Golden Questions and the DMTF ids leaving not_taken. Shipped
files only, no network."""

import shutil
from pathlib import Path

import pytest

from bmc_toolkit.spec import support
from bmc_toolkit.spec.catalog import CatalogError, load_catalog

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "bmc_toolkit" / "spec" / "catalog.toml"
GOLDEN = ROOT / "docs" / "golden-questions.md"

NEW = {
    "DSP0220": (
        "pldm",
        "Field Replaceable Unit (FRU) Data Specification",
        [("1.0.0", "2025-05-19"), ("1.0.1", "2025-09-22")],
    ),
    "DSP0244": (
        "ipmi",
        "IPMI PET to Platform Message Registry Mapping",
        [("1.0.0", "2009-05-13"), ("1.1.0", "2009-11-02"), ("1.2.0", "2010-10-27")],
    ),
    "DSP0280": (
        "mctp",
        "PMCI Test Tools Interface and Design Specification",
        [("1.0.0", "2022-10-10"), ("1.1.0", "2026-07-02")],
    ),
}
QUESTIONS = {"G111": "DSP0220 1.0.1", "G112": "DSP0244 1.2.0", "G113": "DSP0280 1.1.0"}
DMTF_FILES = "https://www.dmtf.org/sites/default/files/standards/documents/"


# ---------------------------------------------------------------- AC-1


def test_the_three_follow_dsp0294_as_the_last_documents():
    cat = load_catalog()
    ids = [d.id for d in cat.documents]
    at = ids.index("DSP0294")
    assert ids[at + 1 :] == list(NEW)
    for doc_id, (family, title, versions) in NEW.items():
        doc = cat.get(doc_id)
        assert (doc.family, doc.title) == (family, title), doc_id
        assert (doc.access, doc.fetch) == ("open", "direct"), doc_id
        assert doc.listing == f"dmtf:{doc_id}"
        assert [(v.version, v.published) for v in doc.versions] == versions
        assert doc.latest().version == versions[-1][0], doc_id
        for v in doc.versions:
            assert v.type == "pdf", doc_id
            assert v.url == f"{DMTF_FILES}{doc_id}_{v.version}.pdf"


def test_dsp0244_names_its_dmtf_listing_outside_a_dmtf_family():
    cat = load_catalog()
    assert cat.families["ipmi"].publisher != "DMTF"
    text = CATALOG.read_text("utf-8")
    block = text[text.index('id = "DSP0244"') : text.index('id = "DSP0280"')]
    assert 'listing = "dmtf:DSP0244"' in block
    assert "DSP0244" in cat.dmtf_listed()


# ---------------------------------------------------------------- AC-2


def test_dsp0244_1_1_0_carries_the_cover_date_and_says_so():
    doc = load_catalog().get("DSP0244")
    (v110,) = [v for v in doc.versions if v.version == "1.1.0"]
    assert v110.published == "2009-11-02"
    assert "2010-11-02" in v110.notes and "cover" in v110.notes
    assert doc.latest().version == "1.2.0"


# ---------------------------------------------------------------- AC-3


def test_they_left_not_taken():
    cat = load_catalog()
    for dsp in NEW:
        assert dsp in cat.dmtf_listed()
        assert not cat.dmtf_not_taken_covers(dsp), dsp
    assert len(cat.dmtf_not_taken) == 130
    text = CATALOG.read_text("utf-8")
    comment = text[text.index("DMTF left out") : text.index("[listings.dmtf]")]
    for dsp in NEW:
        assert dsp not in comment, dsp
    flat = " ".join(comment.replace("#", " ").split())
    assert "PMCI white papers DSP2015, DSP2016 and DSP2037" in flat
    assert "PLDM modeling white papers DSP2054, DSP2061 and DSP2067" in flat


def test_the_comment_names_only_ids_still_not_taken():
    cat = load_catalog()
    text = CATALOG.read_text("utf-8")
    comment = text[text.index("DMTF left out") : text.index("[listings.dmtf]")]
    named = {w.strip(",.():") for w in comment.split() if w.startswith("DSP")}
    named = {w for w in named if w[3:].isdigit() and len(w) == 7}
    assert named
    for dsp in named:
        assert cat.dmtf_not_taken_covers(dsp), dsp


@pytest.mark.parametrize("dsp", list(NEW))
def test_a_not_taken_entry_naming_one_is_refused(tmp_path, dsp):
    copy = tmp_path / "catalog.toml"
    shutil.copyfile(CATALOG, copy)
    text = copy.read_text("utf-8")
    text = text.replace("not_taken = [\n", f'not_taken = [\n    "{dsp}",\n', 1)
    copy.write_text(text, "utf-8", newline="")
    with pytest.raises(CatalogError, match=dsp):
        load_catalog(copy)


# ---------------------------------------------------------------- AC-4


def test_only_dsp0220_has_a_limit_and_it_names_table_1():
    cat = load_catalog()
    limits = cat.get("DSP0220").limits
    assert "Table 1 (page 13)" in limits and "Component" in limits
    assert "FRU File(s)" in limits
    assert cat.get("DSP0244").limits == ""
    assert cat.get("DSP0280").limits == ""


# ---------------------------------------------------------------- AC-6


def test_each_is_verified_by_its_own_question():
    cat = load_catalog()
    verified, problems = support.read_golden(GOLDEN, cat)
    assert problems == []
    assert verified["dsp0220"] == [("G111", "1.0.1")]
    assert verified["dsp0244"] == [("G112", "1.2.0")]
    assert verified["dsp0280"] == [("G113", "1.1.0")]
    text = GOLDEN.read_text("utf-8")
    start = text.index("## Catalog additions of 2026-11-09")
    assert text.index("## Catalog additions of 2026-11-08") < start
    section = text[start : text.index("## OpenBMC")]
    for qid, doc in QUESTIONS.items():
        (row,) = [ln for ln in section.splitlines() if ln.startswith(f"| {qid} |")]
        cells = row.split(" | ")
        assert cells[2] == doc, qid
        assert "page" in cells[3] and "section" in cells[3], qid
        doc_id = doc.split()[0]
        commands = [c for c in cells[4].split("`")[1::2]]
        assert commands and all(doc_id in c for c in commands), qid
    fresh = text[text.index("## Freshness") :]
    assert "2026-11-09" in fresh
    for dsp in NEW:
        assert dsp in fresh, dsp
    assert "2010-11-02" in fresh and "2009-11-02" in fresh


# ---------------------------------------------------------------- AC-7


def test_support_rows_read_pass():
    cat = load_catalog()
    lines = (ROOT / "docs" / "SUPPORT.md").read_text("utf-8").splitlines()
    for doc_id, (_, title, versions) in NEW.items():
        (row,) = [ln for ln in lines if ln.startswith(f"| `{doc_id}` ")]
        limit = cat.get(doc_id).limits or "-"
        assert row == (
            f"| `{doc_id}` {title} | open | {versions[-1][0]} | PASS | {limit} |"
        )


def test_readme_counts_the_catalog():
    cat = load_catalog()
    docs = cat.documents
    readme = " ".join((ROOT / "README.md").read_text("utf-8").split())
    total = len(docs)
    open_docs = sum(d.access == "open" for d in docs)
    families = len({d.family for d in docs})
    assert (total, open_docs, families) == (124, 104, 35)
    assert f"lists {total} documents in {families} families" in readme
    assert f"The {open_docs} open ones" in readme
