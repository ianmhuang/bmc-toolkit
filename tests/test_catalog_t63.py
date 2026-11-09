"""The 2026-11-08 catalog batch: DSP0285 RedPath and DSP0294 DMTF
Authorization Policy, with their versions, Golden Questions and the DMTF
ids leaving not_taken. Shipped files only, no network."""

import shutil
from pathlib import Path

import pytest

from bmc_toolkit.spec import support
from bmc_toolkit.spec.catalog import CatalogError, load_catalog

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "bmc_toolkit" / "spec" / "catalog.toml"
GOLDEN = ROOT / "docs" / "golden-questions.md"

NEW = {
    "DSP0285": (
        "redfish",
        "RedPath Specification",
        [
            ("1.0.0", "2022-11-30"),
            ("1.0.1", "2023-01-23"),
            ("1.1.0", "2023-05-22"),
        ],
    ),
    "DSP0294": (
        "spdm",
        "DMTF Authorization Policy Specification",
        [("1.0.0", "2026-08-31")],
    ),
}
QUESTIONS = {"G109": "DSP0285 1.1.0", "G110": "DSP0294 1.0.0"}
DMTF_FILES = "https://www.dmtf.org/sites/default/files/standards/documents/"


def test_the_two_follow_nvme_nvm_as_the_last_documents():
    cat = load_catalog()
    ids = [d.id for d in cat.documents]
    at = ids.index("NVME-NVM")
    # T72 (2026-11-09) added DSP0220, DSP0244 and DSP0280 after the two
    assert ids[at + 1 :][:2] == list(NEW)
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


def test_they_left_not_taken():
    cat = load_catalog()
    for dsp in NEW:
        assert dsp in cat.dmtf_listed()
        assert not cat.dmtf_not_taken_covers(dsp), dsp
    # T72 (2026-11-09) took three more
    assert len(cat.dmtf_not_taken) == 130
    text = CATALOG.read_text("utf-8")
    comment = text[text.index("DMTF left out") : text.index("[listings.dmtf]")]
    for dsp in NEW:
        assert dsp not in comment, dsp
    assert "RedPath" not in comment
    flat = " ".join(comment.replace("#", " ").split())
    assert "PMCI white papers DSP2015, DSP2016 and DSP2037" in flat


@pytest.mark.parametrize("dsp", list(NEW))
def test_a_not_taken_entry_naming_one_is_refused(tmp_path, dsp):
    copy = tmp_path / "catalog.toml"
    shutil.copyfile(CATALOG, copy)
    text = copy.read_text("utf-8")
    text = text.replace("not_taken = [\n", f'not_taken = [\n    "{dsp}",\n', 1)
    copy.write_text(text, "utf-8", newline="")
    with pytest.raises(CatalogError, match=dsp):
        load_catalog(copy)


def test_neither_has_limits():
    cat = load_catalog()
    for doc_id in NEW:
        assert cat.get(doc_id).limits == "", doc_id


def test_each_is_verified_by_its_own_question():
    cat = load_catalog()
    verified, problems = support.read_golden(GOLDEN, cat)
    assert problems == []
    assert verified["dsp0285"] == [("G109", "1.1.0")]
    assert verified["dsp0294"] == [("G110", "1.0.0")]
    text = GOLDEN.read_text("utf-8")
    start = text.index("## Catalog additions of 2026-11-08")
    assert text.index("## Catalog additions of 2026-10-21") < start
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
    assert "2026-11-08" in fresh and "DSP0285" in fresh and "DSP0294" in fresh


def test_support_rows_read_pass():
    lines = (ROOT / "docs" / "SUPPORT.md").read_text("utf-8").splitlines()
    for doc_id, (_, title, versions) in NEW.items():
        (row,) = [ln for ln in lines if ln.startswith(f"| `{doc_id}` ")]
        assert row == f"| `{doc_id}` {title} | open | {versions[-1][0]} | PASS | - |"


def test_readme_counts_the_catalog():
    cat = load_catalog()
    docs = cat.documents
    readme = " ".join((ROOT / "README.md").read_text("utf-8").split())
    total = len(docs)
    open_docs = sum(d.access == "open" for d in docs)
    families = len({d.family for d in docs})
    # T72 (2026-11-09) added three open documents
    assert (total, open_docs, families) == (124, 104, 35)
    assert f"lists {total} documents in {families} families" in readme
    assert f"The {open_docs} open ones" in readme
